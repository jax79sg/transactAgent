import uuid
from datetime import date
from decimal import Decimal


def _make_category(db, name):
    from transactagent_db.models import Category

    category = Category(name=name, active=True, is_reserved=False)
    db.add(category)
    db.flush()
    return category


def _make_transaction(db, description, category, source):
    from transactagent_db.models import BankStatement, Transaction

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


def _make_pending_proposal(db, description="IKEA #2"):
    from transactagent_db.models import (
        CategorySource,
        RecategorizationJob,
        RecategorizationProposal,
        RecategorizationProposalSourceBucket,
        RecategorizationProposalStatus,
    )

    household = _make_category(db, f"Household-{uuid.uuid4().hex[:8]}")
    unsure = _make_category(db, f"UNSURE-{uuid.uuid4().hex[:8]}")
    source = _make_transaction(db, "IKEA", household, CategorySource.MANUAL)
    job = RecategorizationJob(source_transaction_id=source.id)
    db.add(job)
    db.flush()
    candidate = _make_transaction(db, description, unsure, CategorySource.UNSURE)
    proposal = RecategorizationProposal(
        recategorization_job_id=job.id,
        candidate_transaction_id=candidate.id,
        proposed_category_id=household.id,
        match_score=Decimal("90.00"),
        source_bucket=RecategorizationProposalSourceBucket.UNSURE,
        status=RecategorizationProposalStatus.PENDING,
    )
    db.add(proposal)
    db.flush()
    return proposal, candidate, household


class TestListProposalsApi:
    def test_requires_auth(self, client):
        response = client.get("/recategorization/proposals")
        assert response.status_code == 401

    def test_returns_pending_proposals(self, client, auth_headers, db_session):
        proposal, candidate, household = _make_pending_proposal(db_session)

        response = client.get("/recategorization/proposals", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["totalCount"] == 1
        item = body["items"][0]
        assert item["id"] == str(proposal.id)
        assert item["candidateTransaction"]["id"] == str(candidate.id)
        assert item["proposedCategory"]["id"] == str(household.id)
        assert item["status"] == "pending"
        assert item["sourceBucket"] == "unsure"


class TestPendingCountApi:
    def test_returns_zero_when_none_pending(self, client, auth_headers):
        response = client.get("/recategorization/proposals/pending-count", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["pendingCount"] == 0

    def test_reflects_pending_proposals(self, client, auth_headers, db_session):
        _make_pending_proposal(db_session)

        response = client.get("/recategorization/proposals/pending-count", headers=auth_headers)

        assert response.json()["pendingCount"] == 1


class TestApproveProposalApi:
    def test_approve_writes_category_and_returns_updated_proposal(self, client, auth_headers, db_session):
        proposal, candidate, household = _make_pending_proposal(db_session)

        response = client.post(f"/recategorization/proposals/{proposal.id}/approve", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"

        db_session.refresh(candidate)
        assert candidate.category_id == household.id

    def test_unknown_proposal_returns_404(self, client, auth_headers):
        response = client.post(f"/recategorization/proposals/{uuid.uuid4()}/approve", headers=auth_headers)
        assert response.status_code == 404

    def test_already_resolved_proposal_returns_409(self, client, auth_headers, db_session):
        proposal, _, _ = _make_pending_proposal(db_session)
        first = client.post(f"/recategorization/proposals/{proposal.id}/approve", headers=auth_headers)
        assert first.status_code == 200

        second = client.post(f"/recategorization/proposals/{proposal.id}/approve", headers=auth_headers)
        assert second.status_code == 409
        assert second.json()["error"] == "proposal_not_pending"


class TestRejectProposalApi:
    def test_reject_leaves_candidate_untouched(self, client, auth_headers, db_session):
        proposal, candidate, household = _make_pending_proposal(db_session)
        original_category_id = candidate.category_id

        response = client.post(f"/recategorization/proposals/{proposal.id}/reject", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        db_session.refresh(candidate)
        assert candidate.category_id == original_category_id


class TestBulkApproveApi:
    def test_bulk_approve_reports_success_and_failure_per_item(self, client, auth_headers, db_session):
        proposal, _, _ = _make_pending_proposal(db_session)
        missing_id = uuid.uuid4()

        response = client.post(
            "/recategorization/proposals/bulk-approve",
            headers=auth_headers,
            json={"proposalIds": [str(proposal.id), str(missing_id)]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["approvedIds"] == [str(proposal.id)]
        assert body["failedIds"] == [str(missing_id)]


class TestBulkRejectApi:
    def test_bulk_reject_reports_success_and_failure_per_item(self, client, auth_headers, db_session):
        proposal, _, _ = _make_pending_proposal(db_session)
        missing_id = uuid.uuid4()

        response = client.post(
            "/recategorization/proposals/bulk-reject",
            headers=auth_headers,
            json={"proposalIds": [str(proposal.id), str(missing_id)]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["rejectedIds"] == [str(proposal.id)]
        assert body["failedIds"] == [str(missing_id)]
