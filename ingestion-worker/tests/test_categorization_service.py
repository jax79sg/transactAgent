import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select

from ingestion_worker.categorization.service import (
    categorize,
    classify_batch,
    find_similar_transaction_via_embedding,
    recategorize_unsure_from_precedent,
)
from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    RecategorizationJob,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    Transaction,
)


def _make_category(db, name, active=True):
    category = Category(name=name, active=active, is_reserved=(name == "UNSURE"))
    db.add(category)
    db.flush()
    return category


def _make_statement(db):
    # A fresh hash per call -- BankStatement.pdf_content_hash is unique (BR-3), and
    # each test-helper transaction gets its own statement, so a fixed hash would
    # collide the moment a test creates more than one transaction (caught by
    # actually running this against Postgres).
    stmt = BankStatement(drive_file_id="f1", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    db.add(stmt)
    db.flush()
    return stmt


def _make_transaction(db, description, category, source, amount=Decimal("10.00")):
    statement = _make_statement(db)
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 1),
        description=description,
        out_flow=amount,
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=source,
    )
    db.add(txn)
    db.flush()
    return txn


class TestCategorize:
    """Matching Precision Refinement (WR-27/28): categorize() no longer calls
    llm_classifier itself -- the LLM classification is now always already known
    (computed upfront by classify_batch, see TestClassifyBatch below) and passed in
    as `llm_category`."""

    def test_similarity_and_llm_agree_auto_assigns(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        _make_transaction(db_session, "NTUC FAIRPRICE #123", groceries, CategorySource.SIMILARITY)

        # A single-digit change (#123 -> #124) scores ~95 with rapidfuzz token_sort_ratio,
        # comfortably above the default 85 threshold.
        result = categorize(db_session, "NTUC FAIRPRICE #124", Decimal("10.00"), "Groceries")

        assert result.source == "similarity"
        assert result.category_name == "Groceries"
        assert result.llm_suggested_category_name == "Groceries"
        assert result.disagreement is None

    def test_llm_abstains_similarity_wins_directly(self, db_session):
        """WR-28: similarity confident, LLM abstained (UNSURE) -- not a disagreement,
        the confident signal wins directly."""
        groceries = _make_category(db_session, "Groceries")
        _make_transaction(db_session, "NTUC FAIRPRICE #123", groceries, CategorySource.SIMILARITY)

        result = categorize(db_session, "NTUC FAIRPRICE #124", Decimal("10.00"), "UNSURE")

        assert result.source == "similarity"
        assert result.category_name == "Groceries"
        assert result.llm_suggested_category_name is None
        assert result.disagreement is None

    def test_similarity_match_rejected_when_amount_far_outside_range(self, db_session):
        """Regression: same fix as the AXS incident, exercised through categorize()
        (the ingestion-time fallback chain) rather than the recategorization re-scan
        -- both share find_best_match, so both needed the amount gate."""
        groceries = _make_category(db_session, "Groceries")
        _make_category(db_session, "UNSURE")
        _make_transaction(db_session, "NTUC FAIRPRICE #123", groceries, CategorySource.SIMILARITY, amount=Decimal("10.00"))

        result = categorize(db_session, "NTUC FAIRPRICE #124", Decimal("500.00"), "UNSURE")

        assert result.source == "unsure"  # text match rejected by amount gate; LLM also abstained

    def test_similarity_finds_nothing_llm_wins_directly(self, db_session):
        """WR-28: no similarity candidate, LLM confident -- not a disagreement,
        the confident signal wins directly."""
        _make_category(db_session, "Dining")
        _make_category(db_session, "UNSURE")

        result = categorize(db_session, "SOME BRAND NEW MERCHANT XYZ", Decimal("10.00"), "Dining")

        assert result.source == "llm"
        assert result.category_name == "Dining"
        assert result.llm_suggested_category_name == "Dining"

    def test_both_abstain_yields_unsure_result(self, db_session):
        _make_category(db_session, "Dining")
        _make_category(db_session, "UNSURE")

        result = categorize(db_session, "TOTALLY AMBIGUOUS TRANSACTION", Decimal("10.00"), "UNSURE")

        assert result.source == "unsure"
        assert result.category_name == "UNSURE"
        assert result.llm_suggested_category_name is None
        assert result.disagreement is None

    def test_genuine_disagreement_yields_unsure_with_disagreement_info(self, db_session):
        """WR-28's third case: both similarity and the LLM are confident, but they
        differ -- neither is auto-assigned; the disagreement is carried forward for
        the Orchestrator to record after the transaction is persisted (domain-
        entities.md's DisagreementInfo)."""
        groceries = _make_category(db_session, "Groceries")
        _make_category(db_session, "Dining")
        _make_transaction(db_session, "NTUC FAIRPRICE #123", groceries, CategorySource.SIMILARITY)

        result = categorize(db_session, "NTUC FAIRPRICE #124", Decimal("10.00"), "Dining")

        assert result.source == "unsure"
        assert result.category_name == "UNSURE"
        assert result.llm_suggested_category_name == "Dining"
        assert result.disagreement is not None
        assert result.disagreement.similarity_category_name == "Groceries"
        assert result.disagreement.llm_category_name == "Dining"
        assert result.disagreement.similarity_score > 0


class TestRecategorizeUnsureFromPrecedent:
    def _make_job(self, db, source_transaction_id):
        job = RecategorizationJob(source_transaction_id=source_transaction_id)
        db.add(job)
        db.flush()
        return job

    def test_auto_applies_near_identical_unsure_match(self, db_session):
        """WR-9: a match clearing the (higher) auto-apply threshold writes directly,
        exactly as WR-5 always did -- also recorded as an auto_applied proposal row."""
        household = _make_category(db_session, "Household")
        unsure_category = _make_category(db_session, "UNSURE")

        corrected = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.MANUAL)
        job = self._make_job(db_session, corrected.id)
        # Exact description match -- rapidfuzz token_sort_ratio = 100, comfortably
        # above the default recategorization_auto_apply_threshold (97.0).
        unsure_txn = _make_transaction(db_session, "IKEA FURNITURE STORE", unsure_category, CategorySource.UNSURE)
        unrelated_unsure = _make_transaction(db_session, "COMPLETELY DIFFERENT MERCHANT", unsure_category, CategorySource.UNSURE)

        auto_applied_ids = recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        db_session.refresh(unsure_txn)
        db_session.refresh(unrelated_unsure)
        assert unsure_txn.id in auto_applied_ids
        assert unsure_txn.category_id == household.id
        assert unsure_txn.category_source == CategorySource.SIMILARITY  # not MANUAL -- see WR-5
        assert unrelated_unsure.id not in auto_applied_ids
        assert unrelated_unsure.category_source == CategorySource.UNSURE  # untouched

        proposal = db_session.scalars(
            select(RecategorizationProposal).where(RecategorizationProposal.candidate_transaction_id == unsure_txn.id)
        ).one()
        assert proposal.status == RecategorizationProposalStatus.AUTO_APPLIED
        assert proposal.source_bucket == RecategorizationProposalSourceBucket.UNSURE
        assert proposal.resolved_at is not None
        assert (
            db_session.scalars(
                select(RecategorizationProposal).where(
                    RecategorizationProposal.candidate_transaction_id == unrelated_unsure.id
                )
            ).first()
            is None
        )

    def test_moderate_confidence_unsure_match_becomes_pending_not_applied(self, db_session):
        """WR-9: a match at/above similarity_threshold but below the auto-apply
        threshold is left untouched and recorded as a pending proposal instead."""
        household = _make_category(db_session, "Household")
        unsure_category = _make_category(db_session, "UNSURE")

        corrected = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.MANUAL)
        job = self._make_job(db_session, corrected.id)
        # "#2" suffix scores ~93 -- above similarity_threshold (85) but below the
        # default auto-apply threshold (97).
        unsure_txn = _make_transaction(db_session, "IKEA FURNITURE STORE #2", unsure_category, CategorySource.UNSURE)

        auto_applied_ids = recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        db_session.refresh(unsure_txn)
        assert unsure_txn.id not in auto_applied_ids
        assert unsure_txn.category_id == unsure_category.id  # untouched
        assert unsure_txn.category_source == CategorySource.UNSURE  # untouched

        proposal = db_session.scalars(
            select(RecategorizationProposal).where(RecategorizationProposal.candidate_transaction_id == unsure_txn.id)
        ).one()
        assert proposal.status == RecategorizationProposalStatus.PENDING
        assert proposal.source_bucket == RecategorizationProposalSourceBucket.UNSURE
        assert proposal.proposed_category_id == household.id
        assert proposal.resolved_at is None

    def test_categorized_bucket_match_is_always_pending_even_at_high_score(self, db_session):
        """WR-10: a match against an already-categorized transaction never
        auto-applies, no matter how high the score is."""
        household = _make_category(db_session, "Household")
        groceries = _make_category(db_session, "Groceries")

        corrected = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.MANUAL)
        job = self._make_job(db_session, corrected.id)
        # Exact description match (score 100) -- would auto-apply if this were the
        # UNSURE bucket, but this candidate already has a category (Groceries).
        already_categorized = _make_transaction(
            db_session, "IKEA FURNITURE STORE", groceries, CategorySource.SIMILARITY
        )

        auto_applied_ids = recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        db_session.refresh(already_categorized)
        assert already_categorized.id not in auto_applied_ids
        assert already_categorized.category_id == groceries.id  # untouched
        assert already_categorized.category_source == CategorySource.SIMILARITY  # untouched

        proposal = db_session.scalars(
            select(RecategorizationProposal).where(
                RecategorizationProposal.candidate_transaction_id == already_categorized.id
            )
        ).one()
        assert proposal.status == RecategorizationProposalStatus.PENDING
        assert proposal.source_bucket == RecategorizationProposalSourceBucket.CATEGORIZED

    def test_candidate_already_at_proposed_category_is_skipped(self, db_session):
        """WR-10: a candidate already assigned the exact category being proposed is
        skipped entirely -- not a proposal, since applying it would be a no-op."""
        household = _make_category(db_session, "Household")

        corrected = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.MANUAL)
        job = self._make_job(db_session, corrected.id)
        already_household = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.SIMILARITY)

        recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        proposal = db_session.scalars(
            select(RecategorizationProposal).where(
                RecategorizationProposal.candidate_transaction_id == already_household.id
            )
        ).first()
        assert proposal is None

    def test_source_transaction_is_never_proposed_against_itself(self, db_session):
        """BR-15 (Unit 1): the corrected transaction can't be its own candidate --
        explicitly excluded by ID in find_categorized_transactions_excluding, not just
        incidentally skipped by the same-category check (it's also excluded by ID even
        when, as here, it's already at the exact category being proposed -- both
        filters would independently prevent it, but this asserts the outcome either way)."""
        household = _make_category(db_session, "Household")
        corrected = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.MANUAL)
        job = self._make_job(db_session, corrected.id)

        recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        proposal = db_session.scalars(
            select(RecategorizationProposal).where(RecategorizationProposal.candidate_transaction_id == corrected.id)
        ).first()
        assert proposal is None

    def test_non_manual_source_transaction_is_a_no_op(self, db_session):
        household = _make_category(db_session, "Household")
        auto_txn = _make_transaction(db_session, "SOME STORE", household, CategorySource.SIMILARITY)
        job = self._make_job(db_session, auto_txn.id)

        updated_ids = recategorize_unsure_from_precedent(db_session, job.id, auto_txn.id)

        assert updated_ids == []

    def test_same_merchant_wildly_different_amount_is_not_proposed(self, db_session):
        """Real reported incident, reproduced end-to-end: two OCBC "FAST PAYMENT via
        PayNow-UEN to AXS PTE. LTD." transactions -- AXS is a bill-payment kiosk used
        for many unrelated bill types -- with near-identical description text (only
        the trailing reference number differs -- single-digit here, scoring 98.57 via
        rapidfuzz, comfortably above both similarity_threshold=85 and
        recategorization_auto_apply_threshold=97, verified by actually running
        rapidfuzz rather than assumed) but wildly different amounts: $699 a car loan
        installment, $81.70 a conservancy fee. Correcting the car loan one must NOT
        surface the conservancy one as a match, in either bucket. See
        aidlc-docs/audit.md 2026-08-06."""
        car_loan = _make_category(db_session, "Car Loan")
        conservancy = _make_category(db_session, "Conservancy")
        unsure_category = _make_category(db_session, "UNSURE")

        corrected = _make_transaction(
            db_session,
            "FAST PAYMENT via PayNow-UEN to AXS PTE. LTD. OTHR - 251129591611147661",  # corrected precedent
            car_loan,
            CategorySource.MANUAL,
            amount=Decimal("699.00"),
        )
        job = self._make_job(db_session, corrected.id)

        conservancy_unsure = _make_transaction(
            db_session,
            "FAST PAYMENT via PayNow-UEN to AXS PTE. LTD. OTHR - 251129591611147662",  # 1 digit different
            unsure_category,
            CategorySource.UNSURE,
            amount=Decimal("81.70"),
        )
        conservancy_categorized = _make_transaction(
            db_session,
            "FAST PAYMENT via PayNow-UEN to AXS PTE. LTD. OTHR - 251129591611147663",  # 1 digit different
            conservancy,
            CategorySource.MANUAL,
            amount=Decimal("81.70"),
        )

        auto_applied_ids = recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        db_session.refresh(conservancy_unsure)
        db_session.refresh(conservancy_categorized)
        assert conservancy_unsure.id not in auto_applied_ids
        assert conservancy_unsure.category_source == CategorySource.UNSURE  # untouched
        assert conservancy_categorized.category_id == conservancy.id  # untouched

        # Neither bucket should have recorded a proposal at all -- the amount gate
        # rejects the candidate before a score is even eligible.
        assert (
            db_session.scalars(
                select(RecategorizationProposal).where(
                    RecategorizationProposal.candidate_transaction_id == conservancy_unsure.id
                )
            ).first()
            is None
        )
        assert (
            db_session.scalars(
                select(RecategorizationProposal).where(
                    RecategorizationProposal.candidate_transaction_id == conservancy_categorized.id
                )
            ).first()
            is None
        )

    def test_same_merchant_similar_amount_is_still_proposed(self, db_session):
        """The amount gate must not become so strict that legitimate same-category
        precedent (a second car loan installment, similar amount) stops matching."""
        car_loan = _make_category(db_session, "Car Loan")
        unsure_category = _make_category(db_session, "UNSURE")

        corrected = _make_transaction(
            db_session,
            "FAST PAYMENT via PayNow-UEN to AXS PTE. LTD. OTHR - 251129591611147661",  # corrected precedent
            car_loan,
            CategorySource.MANUAL,
            amount=Decimal("699.00"),
        )
        job = self._make_job(db_session, corrected.id)
        next_installment = _make_transaction(
            db_session,
            "FAST PAYMENT via PayNow-UEN to AXS PTE. LTD. OTHR - 251129591611147662",  # 1 digit different
            unsure_category,
            CategorySource.UNSURE,
            amount=Decimal("699.00"),
        )

        auto_applied_ids = recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        db_session.refresh(next_installment)
        assert next_installment.id in auto_applied_ids
        assert next_installment.category_id == car_loan.id


class TestFindSimilarTransactionViaEmbedding:
    """WR-21/22/23 (Epic 9): embedding-based search against the `transactions`
    vector-store collection. compute_embedding/query_nearest_neighbors are mocked
    -- a real Qdrant instance is exercised at Build and Test, not here (same split
    as test_embedding_vector_store.py)."""

    def test_returns_none_when_embedding_computation_fails(self, db_session):
        with patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=None):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE", Decimal("10.00"))
        assert result is None

    def test_returns_none_when_vector_store_finds_nothing(self, db_session):
        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch("ingestion_worker.categorization.service.vector_store.query_nearest_neighbors", return_value=None),
        ):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE", Decimal("10.00"))
        assert result is None

    def test_returns_best_candidate_clearing_threshold_and_amount_gate(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        precedent = _make_transaction(db_session, "FAIRPRICE FINEST", groceries, CategorySource.SIMILARITY, amount=Decimal("10.00"))

        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.categorization.service.vector_store.query_nearest_neighbors",
                return_value=[(str(precedent.id), 0.9)],
            ),
        ):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE ONLINE", Decimal("10.00"))

        assert result is not None
        assert result.candidate.transaction_id == str(precedent.id)
        assert result.score == 90.0  # rescaled to the 0-100 scale, WR-23

    def test_candidate_rejected_when_below_embedding_threshold(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        precedent = _make_transaction(db_session, "FAIRPRICE FINEST", groceries, CategorySource.SIMILARITY, amount=Decimal("10.00"))

        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.categorization.service.vector_store.query_nearest_neighbors",
                # Default embedding_similarity_threshold is 0.75 -- 0.5 doesn't clear it.
                return_value=[(str(precedent.id), 0.5)],
            ),
        ):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE ONLINE", Decimal("10.00"))

        assert result is None

    def test_candidate_rejected_when_amount_far_outside_range(self, db_session):
        """NFR-1: the AXS-incident amount gate applies identically to the
        embedding-found path -- not bypassed or weakened."""
        groceries = _make_category(db_session, "Groceries")
        precedent = _make_transaction(db_session, "FAIRPRICE FINEST", groceries, CategorySource.SIMILARITY, amount=Decimal("10.00"))

        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.categorization.service.vector_store.query_nearest_neighbors",
                return_value=[(str(precedent.id), 0.99)],
            ),
        ):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE ONLINE", Decimal("500.00"))

        assert result is None

    def test_stale_vector_store_entry_is_skipped_not_an_error(self, db_session):
        """A neighbor ID with no matching Transaction row (e.g. deleted since it was
        embedded) is simply absent from the candidate lookup, not a crash."""
        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.categorization.service.vector_store.query_nearest_neighbors",
                return_value=[(str(uuid.uuid4()), 0.99)],
            ),
        ):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE ONLINE", Decimal("10.00"))

        assert result is None

    def test_llm_agreement_boost_lifts_a_below_threshold_candidate(self, db_session):
        """WR-30 (Matching Precision Refinement): a raw score just below the
        threshold is lifted above it when the candidate's actual category agrees
        with the given llm_category -- never the reverse (no penalty on
        disagreement, see the next test)."""
        groceries = _make_category(db_session, "Groceries")
        precedent = _make_transaction(db_session, "FAIRPRICE FINEST", groceries, CategorySource.SIMILARITY, amount=Decimal("10.00"))

        # Default embedding_similarity_threshold is 0.82; 0.80 alone doesn't clear
        # it, but 0.80 + the default 0.05 boost = 0.85 does.
        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.categorization.service.vector_store.query_nearest_neighbors",
                return_value=[(str(precedent.id), 0.80)],
            ),
        ):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE ONLINE", Decimal("10.00"), "Groceries")

        assert result is not None
        assert result.candidate.transaction_id == str(precedent.id)

    def test_no_boost_and_no_penalty_when_llm_category_disagrees(self, db_session):
        """A candidate whose category differs from llm_category gets no boost --
        the same raw score that failed without a boost still fails, it is not
        further penalized either."""
        groceries = _make_category(db_session, "Groceries")
        precedent = _make_transaction(db_session, "FAIRPRICE FINEST", groceries, CategorySource.SIMILARITY, amount=Decimal("10.00"))

        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.categorization.service.vector_store.query_nearest_neighbors",
                return_value=[(str(precedent.id), 0.80)],
            ),
        ):
            result = find_similar_transaction_via_embedding(db_session, "NTUC FAIRPRICE ONLINE", Decimal("10.00"), "Dining")

        assert result is None


class TestCategorizeEmbeddingFirst:
    def test_embedding_match_takes_precedence_over_fuzzy_text(self, db_session):
        """WR-21: embedding is tried BEFORE the fuzzy-text fallback -- proven here
        by making the embedding path return a different category than the
        fuzzy-text precedent in the DB would, and asserting the embedding one wins.
        `llm_category` agrees with the embedding result, so this is a plain
        agreement, not a disagreement."""
        embedding_category = _make_category(db_session, "Embedding Match Category")
        fuzzy_category = _make_category(db_session, "Fuzzy Match Category")
        # Also present as a real DB row, so if embedding-first were broken (fuzzy
        # ran first), THIS is what categorize() would return instead.
        _make_transaction(db_session, "NTUC FAIRPRICE #123", fuzzy_category, CategorySource.SIMILARITY)
        embedding_precedent = _make_transaction(
            db_session, "SOME OTHER TEXT ENTIRELY", embedding_category, CategorySource.SIMILARITY
        )

        with (
            patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.categorization.service.vector_store.query_nearest_neighbors",
                return_value=[(str(embedding_precedent.id), 0.99)],
            ),
        ):
            result = categorize(db_session, "NTUC FAIRPRICE #124", Decimal("10.00"), "Embedding Match Category")

        assert result.category_name == "Embedding Match Category"
        assert result.source == "similarity"

    def test_falls_back_to_fuzzy_when_embedding_finds_nothing(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        _make_transaction(db_session, "NTUC FAIRPRICE #123", groceries, CategorySource.SIMILARITY)

        with patch("ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=None):
            result = categorize(db_session, "NTUC FAIRPRICE #124", Decimal("10.00"), "Groceries")

        assert result.category_name == "Groceries"
        assert result.source == "similarity"


class TestRecategorizeEmbeddingFirst:
    def _make_job(self, db, source_transaction_id):
        from transactagent_db.models import RecategorizationJob

        job = RecategorizationJob(source_transaction_id=source_transaction_id)
        db.add(job)
        db.flush()
        return job

    def test_embedding_pairwise_match_auto_applies_above_rescaled_threshold(self, db_session):
        """WR-21/23 (Epic 9): the embedding cosine score is rescaled to 0-100
        before being compared against recategorization_auto_apply_threshold (97.0)
        -- a raw 0.0-1.0 cosine score would never clear that threshold otherwise."""
        household = _make_category(db_session, "Household")
        unsure_category = _make_category(db_session, "UNSURE")

        corrected = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.MANUAL)
        job = self._make_job(db_session, corrected.id)
        # Deliberately NOT a fuzzy-text match (completely different wording) --
        # only the mocked embedding path can find this one.
        unsure_txn = _make_transaction(
            db_session, "SCANDINAVIAN HOME FURNISHINGS CO", unsure_category, CategorySource.UNSURE
        )

        with patch(
            "ingestion_worker.categorization.service.embedding_client.compute_embedding",
            return_value=[0.1, 0.2],  # identical vector for both calls -> cosine_similarity = 1.0
        ):
            auto_applied_ids = recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        db_session.refresh(unsure_txn)
        assert unsure_txn.id in auto_applied_ids
        assert unsure_txn.category_id == household.id
        assert unsure_txn.category_source == CategorySource.SIMILARITY

    def test_falls_back_to_fuzzy_when_embedding_unavailable(self, db_session):
        household = _make_category(db_session, "Household")
        unsure_category = _make_category(db_session, "UNSURE")

        corrected = _make_transaction(db_session, "IKEA FURNITURE STORE", household, CategorySource.MANUAL)
        job = self._make_job(db_session, corrected.id)
        unsure_txn = _make_transaction(db_session, "IKEA FURNITURE STORE", unsure_category, CategorySource.UNSURE)

        with patch(
            "ingestion_worker.categorization.service.embedding_client.compute_embedding", return_value=None
        ):
            auto_applied_ids = recategorize_unsure_from_precedent(db_session, job.id, corrected.id)

        db_session.refresh(unsure_txn)
        assert unsure_txn.id in auto_applied_ids  # exact-text fuzzy match (score 100) still auto-applies


class TestClassifyBatch:
    """WR-27 (Matching Precision Refinement, revised 2026-08-16 during Build and
    Test after live-testing against a real local model server): every transaction
    gets classified, always -- two phases, both deduplicated and bounded by
    llm_classification_concurrency: (1) chunks of llm_classification_batch_size
    descriptions classified via classify_batch_prompt (one prompt per chunk), (2)
    any description that phase didn't answer falls back to an individual
    classify() call.

    WR-34 (Categorization Model Fine-Tuning): classify_batch's input is now a list
    of (description, amountSgd) pairs, not bare descriptions -- every call below
    is updated accordingly. The amount values themselves aren't under test here
    (that's covered by test_openrouter_client.py's prompt-content tests); an
    arbitrary Decimal is used throughout."""

    def test_fully_resolved_by_the_batch_phase_never_calls_individual_classify(self, db_session):
        _make_category(db_session, "Groceries")
        _make_category(db_session, "Dining")
        _make_category(db_session, "UNSURE")

        with (
            patch(
                "ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt",
                return_value={"NTUC FAIRPRICE": "Groceries", "STARBUCKS": "Dining"},
            ),
            patch("ingestion_worker.categorization.service.llm_classifier.classify") as mock_classify,
        ):
            result = classify_batch(
                db_session,
                [("NTUC FAIRPRICE", Decimal("45.20")), ("STARBUCKS", Decimal("6.50")), ("NTUC FAIRPRICE", Decimal("45.20"))],
            )

        assert result == {"NTUC FAIRPRICE": "Groceries", "STARBUCKS": "Dining"}
        mock_classify.assert_not_called()

    def test_unresolved_descriptions_fall_back_to_individual_calls(self, db_session):
        """Only the specific description the batch phase couldn't answer redoes
        work -- the rest of that same batch's results are kept, not discarded."""
        _make_category(db_session, "Groceries")
        _make_category(db_session, "Dining")
        _make_category(db_session, "UNSURE")

        with (
            patch(
                "ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt",
                return_value={"NTUC FAIRPRICE": "Groceries"},  # STARBUCKS missing -- unparseable entry
            ),
            patch(
                "ingestion_worker.categorization.service.llm_classifier.classify", return_value="Dining"
            ) as mock_classify,
        ):
            result = classify_batch(db_session, [("NTUC FAIRPRICE", Decimal("45.20")), ("STARBUCKS", Decimal("6.50"))])

        assert result == {"NTUC FAIRPRICE": "Groceries", "STARBUCKS": "Dining"}
        mock_classify.assert_called_once()
        assert mock_classify.call_args.args[0] == "STARBUCKS"
        assert mock_classify.call_args.args[1] == Decimal("6.50")

    def test_whole_batch_phase_failure_falls_every_description_back_individually(self, db_session):
        """classify_batch_prompt returning {} (its own WR-4-style "never raises,
        return nothing on failure" contract) means every description in that chunk
        needs an individual call."""
        _make_category(db_session, "Groceries")
        _make_category(db_session, "UNSURE")

        with (
            patch("ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt", return_value={}),
            patch(
                "ingestion_worker.categorization.service.llm_classifier.classify", return_value="Groceries"
            ) as mock_classify,
        ):
            result = classify_batch(
                db_session, [("NTUC FAIRPRICE", Decimal("45.20")), ("COLD STORAGE", Decimal("12.00"))]
            )

        assert result == {"NTUC FAIRPRICE": "Groceries", "COLD STORAGE": "Groceries"}
        assert mock_classify.call_count == 2

    def test_chunks_descriptions_into_configured_batch_size(self, db_session):
        _make_category(db_session, "Groceries")
        _make_category(db_session, "UNSURE")
        items = [(f"MERCHANT {i}", Decimal("10.00")) for i in range(5)]

        with (
            patch("ingestion_worker.categorization.service.settings.llm_classification_batch_size", 2),
            patch(
                "ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt",
                side_effect=lambda chunk, whitelist: {d: "Groceries" for d, _amount in chunk},
            ) as mock_batch_prompt,
        ):
            result = classify_batch(db_session, items)

        assert len(result) == 5
        chunk_sizes = sorted(len(call.args[0]) for call in mock_batch_prompt.call_args_list)
        assert chunk_sizes == [1, 2, 2]  # 5 descriptions, batch size 2 -> chunks of 2, 2, 1

    def test_deduplicates_before_dispatch(self, db_session):
        """Two transactions sharing identical description text within the same file
        are classified once, not twice -- keeping the first occurrence's amount."""
        _make_category(db_session, "Groceries")
        _make_category(db_session, "UNSURE")

        with patch(
            "ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt",
        ) as mock_batch_prompt:
            mock_batch_prompt.return_value = {"NTUC FAIRPRICE": "Groceries"}
            classify_batch(
                db_session,
                [
                    ("NTUC FAIRPRICE", Decimal("45.20")),
                    ("NTUC FAIRPRICE", Decimal("99.99")),
                    ("NTUC FAIRPRICE", Decimal("1.00")),
                ],
            )

        mock_batch_prompt.assert_called_once()
        assert mock_batch_prompt.call_args.args[0] == [("NTUC FAIRPRICE", Decimal("45.20"))]

    def test_empty_input_returns_empty_dict_without_calling_llm(self, db_session):
        with patch("ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt") as mock_batch_prompt:
            result = classify_batch(db_session, [])

        assert result == {}
        mock_batch_prompt.assert_not_called()

    def test_whitelist_excludes_unsure(self, db_session):
        """The UNSURE category itself must never be offered to the LLM as a
        selectable category (same rule categorize()'s old internal whitelist build
        already enforced)."""
        _make_category(db_session, "Groceries")
        _make_category(db_session, "UNSURE")

        with patch(
            "ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt",
            return_value={"NTUC FAIRPRICE": "Groceries"},
        ) as mock_batch_prompt:
            classify_batch(db_session, [("NTUC FAIRPRICE", Decimal("45.20"))])

        called_whitelist = mock_batch_prompt.call_args.args[1]
        assert "UNSURE" not in called_whitelist
        assert "Groceries" in called_whitelist

    def test_amount_unavailable_is_passed_through_as_none(self, db_session):
        """WR-34: a transaction whose conversion was unavailable (WR-6) still gets
        classified -- amountSgd flows through as None, not a crash or a dropped
        item."""
        _make_category(db_session, "Groceries")
        _make_category(db_session, "UNSURE")

        with (
            patch("ingestion_worker.categorization.service.llm_classifier.classify_batch_prompt", return_value={}),
            patch(
                "ingestion_worker.categorization.service.llm_classifier.classify", return_value="Groceries"
            ) as mock_classify,
        ):
            result = classify_batch(db_session, [("NTUC FAIRPRICE", None)])

        assert result == {"NTUC FAIRPRICE": "Groceries"}
        assert mock_classify.call_args.args[1] is None
