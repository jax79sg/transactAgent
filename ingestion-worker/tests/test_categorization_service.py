import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import select

from ingestion_worker.categorization.service import categorize, recategorize_unsure_from_precedent
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


def _make_transaction(db, description, category, source):
    statement = _make_statement(db)
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 1),
        description=description,
        out_flow=Decimal("10.00"),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=source,
    )
    db.add(txn)
    db.flush()
    return txn


class TestCategorize:
    def test_uses_similarity_match_when_available(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        _make_transaction(db_session, "NTUC FAIRPRICE #123", groceries, CategorySource.SIMILARITY)

        # A single-digit change (#123 -> #124) scores ~95 with rapidfuzz token_sort_ratio,
        # comfortably above the default 85 threshold. Note: "#123" vs "#456" (all 3
        # digits differ) only scores ~84 -- just under the default threshold, a real
        # boundary case caught by actually running rapidfuzz rather than assuming.
        # Confirms the threshold is workable for near-duplicate merchant strings, but
        # is genuinely tunable per FR-5.2's config option, not an exact science.
        with patch("ingestion_worker.categorization.service.llm_classifier.classify") as mock_llm:
            result = categorize(db_session, "NTUC FAIRPRICE #124")

        assert result.source == "similarity"
        assert result.category_name == "Groceries"
        mock_llm.assert_not_called()

    def test_falls_back_to_llm_when_no_similar_precedent(self, db_session):
        _make_category(db_session, "Dining")
        _make_category(db_session, "UNSURE")

        with patch("ingestion_worker.categorization.service.llm_classifier.classify", return_value="Dining") as mock_llm:
            result = categorize(db_session, "SOME BRAND NEW MERCHANT XYZ")

        assert result.source == "llm"
        assert result.category_name == "Dining"
        mock_llm.assert_called_once()

    def test_llm_unsure_response_yields_unsure_result(self, db_session):
        _make_category(db_session, "Dining")
        _make_category(db_session, "UNSURE")

        with patch("ingestion_worker.categorization.service.llm_classifier.classify", return_value="UNSURE"):
            result = categorize(db_session, "TOTALLY AMBIGUOUS TRANSACTION")

        assert result.source == "unsure"
        assert result.category_name == "UNSURE"


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
