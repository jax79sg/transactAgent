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
