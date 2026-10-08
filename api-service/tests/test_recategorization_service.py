import uuid
from datetime import date
from decimal import Decimal

import pytest
from transactagent_db.models import (
    BankStatement,
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    Category,
    CategorySource,
    RecategorizationJob,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    Transaction,
)

from api_service.errors import (
    DisagreementNotPendingError,
    InvalidResolutionCategoryError,
    NotFoundError,
    ProposalNotPendingError,
)
from api_service.recategorization import service


def _make_category(db, name):
    category = Category(name=name, active=True, is_reserved=False)
    db.add(category)
    db.flush()
    return category


def _make_transaction(db, description, category, source=CategorySource.SIMILARITY):
    statement = BankStatement(drive_file_id="f1", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    db.add(statement)
    db.flush()
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


def _make_job(db, source_transaction_id):
    job = RecategorizationJob(source_transaction_id=source_transaction_id)
    db.add(job)
    db.flush()
    return job


def _make_proposal(db, job, candidate, proposed_category, status=RecategorizationProposalStatus.PENDING, bucket=RecategorizationProposalSourceBucket.UNSURE):
    proposal = RecategorizationProposal(
        recategorization_job_id=job.id,
        candidate_transaction_id=candidate.id,
        proposed_category_id=proposed_category.id,
        match_score=Decimal("90.00"),
        source_bucket=bucket,
        status=status,
    )
    db.add(proposal)
    db.flush()
    return proposal


def _make_disagreement(db, transaction, similarity_category, llm_category, status=CategorizationDisagreementStatus.PENDING):
    disagreement = CategorizationDisagreement(
        transaction_id=transaction.id,
        similarity_category_id=similarity_category.id,
        llm_category_id=llm_category.id,
        similarity_score=Decimal("88.00"),
        status=status,
    )
    db.add(disagreement)
    db.flush()
    return disagreement


class TestListPendingProposals:
    def test_only_pending_proposals_are_returned(self, db_session):
        household = _make_category(db_session, "Household")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)

        pending_candidate = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        resolved_candidate = _make_transaction(db_session, "IKEA #3", unsure, CategorySource.UNSURE)
        _make_proposal(db_session, job, pending_candidate, household, status=RecategorizationProposalStatus.PENDING)
        _make_proposal(db_session, job, resolved_candidate, household, status=RecategorizationProposalStatus.APPROVED)

        items, total_count = service.list_pending_proposals(db_session, page=1, page_size=20)

        assert total_count == 1
        assert [p.candidate_transaction_id for p in items] == [pending_candidate.id]


class TestListPendingProposalsSort:
    """Issue #10 (column sorting): score sorts directly on RecategorizationProposal;
    date sorts through the explicit join to Transaction added in repository.py's
    _apply_proposal_sort -- proven separately since a join bug wouldn't show up in
    a score-only test."""

    def _make_two_proposals(self, db_session):
        household = _make_category(db_session, "Household")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)

        low = _make_transaction(db_session, "Low candidate", household, CategorySource.UNSURE)
        low.transaction_date = date(2026, 1, 1)
        high = _make_transaction(db_session, "High candidate", household, CategorySource.UNSURE)
        high.transaction_date = date(2026, 6, 1)
        db_session.flush()

        proposal_low = _make_proposal(db_session, job, low, household)
        proposal_low.match_score = Decimal("50.00")
        proposal_high = _make_proposal(db_session, job, high, household)
        proposal_high.match_score = Decimal("95.00")
        db_session.flush()
        return proposal_low, proposal_high

    def test_sorts_by_score_ascending(self, db_session):
        low, high = self._make_two_proposals(db_session)

        items, _ = service.list_pending_proposals(db_session, page=1, page_size=20, sort_by="score", sort_dir="asc")

        assert [p.id for p in items] == [low.id, high.id]

    def test_sorts_by_score_descending(self, db_session):
        low, high = self._make_two_proposals(db_session)

        items, _ = service.list_pending_proposals(db_session, page=1, page_size=20, sort_by="score", sort_dir="desc")

        assert [p.id for p in items] == [high.id, low.id]

    def test_sorts_by_date_via_candidate_transaction(self, db_session):
        low, high = self._make_two_proposals(db_session)

        items, _ = service.list_pending_proposals(db_session, page=1, page_size=20, sort_by="date", sort_dir="asc")

        assert [p.id for p in items] == [low.id, high.id]


class TestListPendingProposalsSortByTextColumns:
    """Issue #23 follow-up: Description, Current category and Proposed category sort too. Each goes through its own
    join (the two category columns through their own aliases of Category), so each is proven separately, and with
    names chosen so that byte order and alphabetical order disagree."""

    @pytest.fixture
    def three(self, db_session):
        """Proposals whose descriptions, current categories and proposed categories sort in three DIFFERENT orders,
        so a column sorted by the wrong join shows up."""
        categories = {name: _make_category(db_session, name) for name in ("banana", "Zebra", "apple", "Cherry", "mango", "Delta")}
        source = _make_transaction(db_session, "IKEA", categories["Zebra"], CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        # chosen so that byte order (capitals first) and alphabetical order disagree in every column
        specs = [("banana stand", "Zebra", "mango"),
                 ("Zebra Cafe", "banana", "Delta"),
                 ("apple store", "Cherry", "apple")]
        proposals = {}
        for description, current, proposed in specs:
            candidate = _make_transaction(db_session, description, categories[current], CategorySource.UNSURE)
            proposals[description] = _make_proposal(db_session, job, candidate, categories[proposed])
        return proposals

    @pytest.mark.parametrize(
        ("sort_by", "ascending"),
        [
            ("description", ["apple store", "banana stand", "Zebra Cafe"]),
            ("currentCategory", ["Zebra Cafe", "apple store", "banana stand"]),  # banana, Cherry, Zebra
            ("proposedCategory", ["apple store", "Zebra Cafe", "banana stand"]),  # apple, Delta, mango
        ],
    )
    def test_sorts_alphabetically_whatever_the_case_in_both_directions(self, db_session, three, sort_by, ascending):
        asc, _ = service.list_pending_proposals(db_session, page=1, page_size=20, sort_by=sort_by, sort_dir="asc")
        desc, _ = service.list_pending_proposals(db_session, page=1, page_size=20, sort_by=sort_by, sort_dir="desc")

        assert [p.id for p in asc] == [three[name].id for name in ascending]
        assert [p.id for p in desc] == [three[name].id for name in reversed(ascending)]

    @pytest.mark.parametrize("sort_by", ["description", "currentCategory", "proposedCategory", "score", "source", "date", "amount"])
    @pytest.mark.parametrize("sort_dir", ["asc", "desc"])
    def test_paging_through_tied_rows_yields_each_proposal_once_in_one_order(self, db_session, sort_by, sort_dir):
        """Eleven proposals with the same description and categories, created together (so also the same created_at):
        every sort ties on every row, and page after page must still be consecutive slices of one list."""
        household = _make_category(db_session, "Household")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        for _ in range(11):
            candidate = _make_transaction(db_session, "SHOPEE SINGAPORE", household, CategorySource.UNSURE)
            _make_proposal(db_session, job, candidate, household)

        seen = []
        for page in range(1, 7):
            items, total = service.list_pending_proposals(db_session, page=page, page_size=2, sort_by=sort_by, sort_dir=sort_dir)
            assert total == 11
            seen.extend(p.id for p in items)
        everything, _ = service.list_pending_proposals(db_session, page=1, page_size=50, sort_by=sort_by, sort_dir=sort_dir)

        assert len(seen) == len(set(seen)) == 11
        assert seen == [p.id for p in everything]

    def test_a_resolved_proposal_never_appears_whatever_the_sort(self, db_session):
        household = _make_category(db_session, "Household")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        pending = _make_proposal(db_session, job, _make_transaction(db_session, "A", household, CategorySource.UNSURE), household)
        _make_proposal(db_session, job, _make_transaction(db_session, "B", household, CategorySource.UNSURE), household,
                       status=RecategorizationProposalStatus.APPROVED)

        for sort_by in ("description", "currentCategory", "proposedCategory"):
            items, total = service.list_pending_proposals(db_session, page=1, page_size=20, sort_by=sort_by, sort_dir="asc")
            assert [p.id for p in items] == [pending.id] and total == 1


class TestGetPendingCount:
    def test_counts_only_pending(self, db_session):
        household = _make_category(db_session, "Household")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)

        candidate_a = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        candidate_b = _make_transaction(db_session, "IKEA #3", unsure, CategorySource.UNSURE)
        _make_proposal(db_session, job, candidate_a, household, status=RecategorizationProposalStatus.PENDING)
        _make_proposal(db_session, job, candidate_b, household, status=RecategorizationProposalStatus.AUTO_APPLIED)

        assert service.get_pending_count(db_session) == 1

    def test_sums_pending_proposals_and_pending_disagreements(self, db_session):
        """AR-26 (Matching Precision Refinement): one combined number, not two
        separate badges."""
        household = _make_category(db_session, "Household")
        dining = _make_category(db_session, "Dining")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        candidate = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        _make_proposal(db_session, job, candidate, household, status=RecategorizationProposalStatus.PENDING)

        disagreement_txn = _make_transaction(db_session, "NTUC FAIRPRICE", unsure, CategorySource.UNSURE)
        _make_disagreement(db_session, disagreement_txn, household, dining)

        assert service.get_pending_count(db_session) == 2


class TestApproveProposal:
    def test_writes_category_to_candidate_and_marks_approved(self, db_session):
        household = _make_category(db_session, "Household")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        candidate = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        proposal = _make_proposal(db_session, job, candidate, household)

        result = service.approve_proposal(db_session, proposal.id)

        # Asserted on the SAME in-memory object returned by approve_proposal, before
        # any refresh/re-query -- catches the relationship-staleness bug a
        # db_session.refresh() beforehand would silently paper over (found via live
        # verification: the API's immediate response body showed the transaction's OLD
        # category right after approval, even though the committed row was correct).
        assert result.candidate_transaction.category.id == household.id
        assert result.candidate_transaction.category.name == "Household"

        db_session.refresh(candidate)
        assert candidate.category_id == household.id
        assert candidate.category_source == CategorySource.SIMILARITY  # AR-13: not 'manual'
        assert result.status == RecategorizationProposalStatus.APPROVED
        assert result.resolved_at is not None

    def test_unknown_proposal_raises_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            service.approve_proposal(db_session, uuid.uuid4())

    def test_already_resolved_proposal_is_rejected(self, db_session):
        household = _make_category(db_session, "Household")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        candidate = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        proposal = _make_proposal(db_session, job, candidate, household, status=RecategorizationProposalStatus.REJECTED)

        with pytest.raises(ProposalNotPendingError):
            service.approve_proposal(db_session, proposal.id)


class TestRejectProposal:
    def test_leaves_candidate_untouched_and_marks_rejected(self, db_session):
        household = _make_category(db_session, "Household")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        candidate = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        proposal = _make_proposal(db_session, job, candidate, household)

        result = service.reject_proposal(db_session, proposal.id)

        db_session.refresh(candidate)
        assert candidate.category_id == unsure.id  # untouched
        assert candidate.category_source == CategorySource.UNSURE  # untouched
        assert result.status == RecategorizationProposalStatus.REJECTED
        assert result.resolved_at is not None


class TestBulkApprove:
    def test_partial_failure_does_not_abort_batch(self, db_session):
        household = _make_category(db_session, "Household")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        good_candidate = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        good_proposal = _make_proposal(db_session, job, good_candidate, household)
        already_resolved_candidate = _make_transaction(db_session, "IKEA #3", unsure, CategorySource.UNSURE)
        bad_proposal = _make_proposal(
            db_session, job, already_resolved_candidate, household, status=RecategorizationProposalStatus.REJECTED
        )
        missing_id = uuid.uuid4()

        approved_ids, failed_ids = service.bulk_approve(
            db_session, [good_proposal.id, bad_proposal.id, missing_id]
        )

        assert approved_ids == [good_proposal.id]
        assert set(failed_ids) == {bad_proposal.id, missing_id}

        db_session.refresh(good_candidate)
        assert good_candidate.category_id == household.id


class TestBulkReject:
    def test_partial_failure_does_not_abort_batch(self, db_session):
        household = _make_category(db_session, "Household")
        unsure = _make_category(db_session, "UNSURE")
        source = _make_transaction(db_session, "IKEA", household, CategorySource.MANUAL)
        job = _make_job(db_session, source.id)
        good_candidate = _make_transaction(db_session, "IKEA #2", unsure, CategorySource.UNSURE)
        good_proposal = _make_proposal(db_session, job, good_candidate, household)
        missing_id = uuid.uuid4()

        rejected_ids, failed_ids = service.bulk_reject(db_session, [good_proposal.id, missing_id])

        assert rejected_ids == [good_proposal.id]
        assert failed_ids == [missing_id]


class TestListPendingDisagreements:
    def test_only_pending_disagreements_are_returned(self, db_session):
        household = _make_category(db_session, "Household")
        dining = _make_category(db_session, "Dining")
        unsure = _make_category(db_session, "UNSURE")
        pending_txn = _make_transaction(db_session, "IKEA", unsure, CategorySource.UNSURE)
        resolved_txn = _make_transaction(db_session, "NTUC FAIRPRICE", household, CategorySource.SIMILARITY)
        _make_disagreement(db_session, pending_txn, household, dining)
        _make_disagreement(db_session, resolved_txn, household, dining, status=CategorizationDisagreementStatus.RESOLVED)

        items, total_count = service.list_pending_disagreements(db_session, page=1, page_size=20)

        assert total_count == 1
        assert [d.transaction_id for d in items] == [pending_txn.id]


class TestResolveDisagreement:
    def test_choosing_the_similarity_category_writes_through_with_similarity_source(self, db_session):
        household = _make_category(db_session, "Household")
        dining = _make_category(db_session, "Dining")
        unsure = _make_category(db_session, "UNSURE")
        txn = _make_transaction(db_session, "IKEA", unsure, CategorySource.UNSURE)
        disagreement = _make_disagreement(db_session, txn, household, dining)

        result = service.resolve_disagreement(db_session, disagreement.id, household.id)

        assert result.status == CategorizationDisagreementStatus.RESOLVED
        assert result.resolved_category_id == household.id
        assert result.resolved_at is not None
        db_session.refresh(txn)
        assert txn.category_id == household.id
        assert txn.category_source == CategorySource.SIMILARITY  # AR-25: not 'manual'

    def test_choosing_the_llm_category_writes_through_with_llm_source(self, db_session):
        household = _make_category(db_session, "Household")
        dining = _make_category(db_session, "Dining")
        unsure = _make_category(db_session, "UNSURE")
        txn = _make_transaction(db_session, "IKEA", unsure, CategorySource.UNSURE)
        disagreement = _make_disagreement(db_session, txn, household, dining)

        result = service.resolve_disagreement(db_session, disagreement.id, dining.id)

        assert result.resolved_category_id == dining.id
        db_session.refresh(txn)
        assert txn.category_id == dining.id
        assert txn.category_source == CategorySource.LLM  # AR-25: not 'manual'

    def test_third_category_is_rejected(self, db_session):
        """AR-24: chosenCategoryId must be one of the two offered candidates."""
        household = _make_category(db_session, "Household")
        dining = _make_category(db_session, "Dining")
        groceries = _make_category(db_session, "Groceries")
        unsure = _make_category(db_session, "UNSURE")
        txn = _make_transaction(db_session, "IKEA", unsure, CategorySource.UNSURE)
        disagreement = _make_disagreement(db_session, txn, household, dining)

        with pytest.raises(InvalidResolutionCategoryError):
            service.resolve_disagreement(db_session, disagreement.id, groceries.id)

        db_session.refresh(txn)
        assert txn.category_id == unsure.id  # untouched

    def test_unknown_disagreement_raises_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            service.resolve_disagreement(db_session, uuid.uuid4(), uuid.uuid4())

    def test_already_resolved_disagreement_is_rejected(self, db_session):
        household = _make_category(db_session, "Household")
        dining = _make_category(db_session, "Dining")
        unsure = _make_category(db_session, "UNSURE")
        txn = _make_transaction(db_session, "IKEA", unsure, CategorySource.UNSURE)
        disagreement = _make_disagreement(db_session, txn, household, dining, status=CategorizationDisagreementStatus.REJECTED)

        with pytest.raises(DisagreementNotPendingError):
            service.resolve_disagreement(db_session, disagreement.id, household.id)


class TestRejectDisagreement:
    def test_leaves_transaction_untouched_and_marks_rejected(self, db_session):
        household = _make_category(db_session, "Household")
        dining = _make_category(db_session, "Dining")
        unsure = _make_category(db_session, "UNSURE")
        txn = _make_transaction(db_session, "IKEA", unsure, CategorySource.UNSURE)
        disagreement = _make_disagreement(db_session, txn, household, dining)

        result = service.reject_disagreement(db_session, disagreement.id)

        db_session.refresh(txn)
        assert txn.category_id == unsure.id  # untouched
        assert txn.category_source == CategorySource.UNSURE  # untouched
        assert result.status == CategorizationDisagreementStatus.REJECTED
        assert result.resolved_at is not None
        assert result.resolved_category_id is None  # no suppression record, no resolution recorded
