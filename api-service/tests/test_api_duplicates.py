"""Duplicate Review API (functional-design AR-38..AR-50, Epic 14), through the real app against a real
PostgreSQL. The worker's shapes are used throughout: the UOB June pair (5 and 5 transactions, corrections on the
kept copy), the Trust June pair, and an information-only pair of clearly different sizes. The API never
recomputes the worker's proposal, so the pairs here are written the way the worker writes them."""

# ruff: noqa: E402  -- the environment must be set before api_service is imported (see below)
import os

# api_service.config validates its required settings when first imported, which for this module happens at
# collection time -- before the `engine` fixture sets them -- so set the same test defaults here.
for _name, _value in (
    ("DB_USER", "test"), ("DB_PASSWORD", "test"), ("JWT_SECRET", "test-secret-do-not-use-in-prod"),
    ("GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com"),
    ("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret"), ("GEMINI_API_KEY", "test-gemini-key"),
):
    os.environ.setdefault(_name, _value)

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import update
from transactagent_db.models import (
    BankStatement,
    Base,
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    Category,
    CategorySource,
    ComparisonRowMarker,
    ComparisonSide,
    DuplicateComparison,
    DuplicateComparisonRow,
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateScanState,
    IngestionRun,
    IngestionRunFile,
    IngestionRunFileOutcome,
    IngestionRunStatus,
    KnownFile,
    KnownFileState,
    RecategorizationJob,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
    StatementRemovalJob,
    StatementRemovalJobStatus,
    Transaction,
)

from api_service.duplicates import repository, service

H_KEEP, H_REMOVE = "1" * 64, "2" * 64
S = StatementRemovalJobStatus


def category(db, name="Groceries"):
    found = db.query(Category).filter_by(name=name).first()
    if found is None:
        found = Category(name=name, active=True, is_reserved=False)
        db.add(found)
        db.flush()
    return found


def statement(db, content_hash, *, bank="UOB", n=5, manual=0, month=6):
    s = BankStatement(drive_file_id=f"drive-{content_hash[:4]}", pdf_content_hash=content_hash, bank_name=bank)
    db.add(s)
    db.flush()
    cat = category(db)
    for i in range(n):
        db.add(
            Transaction(
                bank_statement_id=s.id, transaction_date=date(2026, month, 2 + i), description=f"MERCHANT {i}",
                out_flow=Decimal(10 + i), currency="SGD", bank_name=bank, category_id=cat.id,
                category_source=CategorySource.MANUAL if i < manual else CategorySource.SIMILARITY,
            )
        )
    db.flush()
    return s


def comparison(db, earlier_hash=H_KEEP, later_hash=H_REMOVE, *, earlier_count=5, later_count=5, matched=5, rows=True,
               reason="5 of 5 transactions match", earlier_file="first.pdf", later_file="second.pdf"):
    c = DuplicateComparison(
        earlier_content_hash=earlier_hash, earlier_file_name=earlier_file, earlier_bank_name="UOB",
        earlier_period_start=date(2026, 6, 2), earlier_period_end=date(2026, 6, 30), earlier_transaction_count=earlier_count,
        later_content_hash=later_hash, later_file_name=later_file, later_bank_name="UOB",
        later_period_start=date(2026, 6, 2), later_period_end=date(2026, 6, 30), later_transaction_count=later_count,
        matched_count=matched, match_ratio=Decimal("1.0000"), reason=reason,
    )
    db.add(c)
    db.flush()
    if rows:
        for side in (ComparisonSide.EARLIER, ComparisonSide.LATER):
            for rank in (2, 1):  # inserted out of order on purpose: the API must return them ranked
                db.add(DuplicateComparisonRow(
                    comparison_id=c.id, side=side, rank=rank, transaction_date=date(2026, 6, 5), description=f"{side.value} {rank}",
                    out_flow=Decimal(100 - rank), currency="SGD",
                    marker=ComparisonRowMarker.ALSO_ON_OTHER if rank == 1 else ComparisonRowMarker.ONLY_ON_THIS_ONE,
                ))
        db.flush()
    return c


def pair(db, *, keep=H_KEEP, other=H_REMOVE, removal_allowed=True, status=DuplicatePairStatus.PENDING, cmp=None, found_at=None,
         decided_at=None):
    a, b = sorted((keep, other))
    cmp = cmp or comparison(db, a, b)
    p = DuplicatePair(hash_a=a, hash_b=b, comparison_id=cmp.id, keep_hash=keep, removal_allowed=removal_allowed, status=status,
                      decided_at=decided_at)
    if found_at is not None:
        p.found_at = found_at
    db.add(p)
    db.flush()
    return p


def job(db, p, status=S.QUEUED, **kw):
    kwargs = {"pair_id": p.id, "remove_statement_hash": H_REMOVE, "status": status}
    if status in (S.EMBEDDINGS_PENDING, S.EMBEDDINGS_FAILED):
        kwargs["removed_transaction_ids"] = [uuid.uuid4()]
    if status in (S.FAILED, S.EMBEDDINGS_FAILED):
        kwargs["failure_reason"] = "boom"
    kwargs.update(kw)
    j = StatementRemovalJob(**kwargs)
    db.add(j)
    db.flush()
    return j


@pytest.fixture
def uob(db_session):
    """The UOB shape: the kept copy carries 2 manual corrections; the other carries none."""
    keep = statement(db_session, H_KEEP, manual=2)
    remove = statement(db_session, H_REMOVE)
    return pair(db_session), keep, remove


def body(remove_hash=H_REMOVE, acknowledged=0):
    return {"removeStatementHash": remove_hash, "acknowledgedCorrectionsLost": acknowledged}


class TestAuthentication:
    @pytest.mark.parametrize("method,path", [
        ("get", "/duplicates/pairs"), ("get", "/duplicates/pairs/pending-count"), ("get", f"/duplicates/comparisons/{uuid.uuid4()}"),
        ("post", f"/duplicates/pairs/{uuid.uuid4()}/remove"), ("post", f"/duplicates/pairs/{uuid.uuid4()}/dismiss"),
        ("post", f"/duplicates/comparisons/{uuid.uuid4()}/override"), ("get", "/duplicates/scan-status"), ("post", "/duplicates/recheck"),
    ])
    def test_every_route_requires_a_login(self, client, method, path):
        assert getattr(client, method)(path).status_code == 401


class TestListPairs:
    def test_empty(self, client, auth_headers):
        response = client.get("/duplicates/pairs", headers=auth_headers)
        assert response.status_code == 200 and response.json() == {"items": [], "page": 1, "pageSize": 20, "totalCount": 0}

    def test_a_pending_pair_shows_labels_from_the_stored_comparison_and_the_workers_proposal(self, client, auth_headers, db_session, uob):
        response = client.get("/duplicates/pairs", headers=auth_headers).json()

        (item,) = response["items"]
        assert item["status"] == "pending" and item["removalOffered"] is True and item["stale"] is False
        assert item["keep"]["fileName"] == "first.pdf" and item["keep"]["contentHash"] == H_KEEP
        assert item["remove"]["fileName"] == "second.pdf" and item["remove"]["contentHash"] == H_REMOVE
        assert item["keep"]["bankName"] == "UOB" and item["keep"]["periodStart"] == "2026-06-02" and item["keep"]["transactionCount"] == 5

    def test_the_proposal_is_whatever_the_worker_stored_not_recomputed(self, client, auth_headers, db_session):
        """The worker said keep the LATER hash, although the corrections are on the other copy: the API shows that."""
        statement(db_session, H_KEEP, manual=2)
        statement(db_session, H_REMOVE)
        pair(db_session, keep=H_REMOVE, other=H_KEEP)

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["keep"]["contentHash"] == H_REMOVE and item["remove"]["contentHash"] == H_KEEP

    def test_correction_counts_are_read_live(self, client, auth_headers, db_session, uob):
        _p, _keep, remove = uob
        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]
        assert (item["correctionsOnKept"], item["correctionsOnRemoved"]) == (2, 0)

        first = db_session.query(Transaction).filter_by(bank_statement_id=remove.id).first()
        first.category_source = CategorySource.MANUAL
        db_session.flush()

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]
        assert item["correctionsOnRemoved"] == 1 and item["preview"]["correctionsLost"] == 1

    def test_the_preview_counts_what_would_be_deleted(self, client, auth_headers, db_session, uob):
        _p, keep, remove = uob
        cat = category(db_session)
        txn = db_session.query(Transaction).filter_by(bank_statement_id=remove.id).first()
        other = db_session.query(Transaction).filter_by(bank_statement_id=keep.id).first()
        rjob = RecategorizationJob(source_transaction_id=txn.id)
        db_session.add(rjob)
        db_session.flush()
        db_session.add_all([
            RecategorizationProposal(recategorization_job_id=rjob.id, candidate_transaction_id=other.id, proposed_category_id=cat.id,
                                     match_score=Decimal("90.00"), source_bucket=RecategorizationProposalSourceBucket.UNSURE,
                                     status=RecategorizationProposalStatus.PENDING),
            CategorizationDisagreement(transaction_id=txn.id, similarity_category_id=cat.id, llm_category_id=cat.id,
                                       similarity_score=Decimal("70.00"), status=CategorizationDisagreementStatus.PENDING),
        ])
        payment = RecurringPayment(name="Gym", expected_amount=Decimal("80.00"), frequency=RecurringPaymentFrequency.MONTHLY, due_day=15)
        db_session.add(payment)
        db_session.flush()
        db_session.add(RecurringPaymentMatch(recurring_payment_id=payment.id, transaction_id=txn.id, cycle_period="2026-06",
                                             status=RecurringPaymentMatchStatus.PENDING, amount_at_match=Decimal("10.00")))
        db_session.flush()

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["preview"] == {
            "transactions": 5, "statementSections": 0, "recategorizationJobs": 1, "recategorizationProposals": 1,
            "categorizationDisagreements": 1, "recurringPaymentMatches": 1, "correctionsLost": 0, "onlyOnRemovedCopy": 0,
        }

    def test_only_on_removed_copy_is_the_removed_sides_count_minus_the_matched_count(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP, n=10)
        statement(db_session, H_REMOVE, n=10)
        pair(db_session, cmp=comparison(db_session, H_KEEP, H_REMOVE, earlier_count=10, later_count=10, matched=8))

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["preview"]["onlyOnRemovedCopy"] == 2

    def test_a_pair_of_clearly_different_sizes_is_information_only(self, client, auth_headers, db_session):
        """Question 1 = C: listed, no removal offered, no preview."""
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE, n=15)
        pair(db_session, removal_allowed=False)

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["removalOffered"] is False and item["preview"] is None and item["stale"] is False

    def test_a_pair_whose_statement_is_gone_is_stale_with_no_counts_and_no_removal(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        pair(db_session)  # the other statement does not exist

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["stale"] is True and item["removalOffered"] is False
        assert item["correctionsOnKept"] is None and item["correctionsOnRemoved"] is None and item["preview"] is None

    def test_groups_are_in_flight_then_pending_then_recently_removed_and_old_removals_drop_out(self, client, auth_headers, db_session):
        now = datetime.now(UTC)
        for h in "abcdef":
            statement(db_session, h * 64)
        in_flight = pair(db_session, keep="a" * 64, other="b" * 64, found_at=now - timedelta(days=5))
        job(db_session, in_flight, S.QUEUED, remove_statement_hash="b" * 64)
        pending_new = pair(db_session, keep="c" * 64, other="d" * 64, found_at=now - timedelta(days=1))
        pending_old = pair(db_session, keep="e" * 64, other="f" * 64, found_at=now - timedelta(days=3))
        recent = pair(db_session, keep="1" * 64, other="2" * 64, status=DuplicatePairStatus.REMOVED, decided_at=now - timedelta(hours=2),
                      found_at=now - timedelta(days=9))
        pair(db_session, keep="3" * 64, other="4" * 64, status=DuplicatePairStatus.REMOVED, decided_at=now - timedelta(hours=30))
        pair(db_session, keep="5" * 64, other="6" * 64, status=DuplicatePairStatus.DISMISSED)

        items = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert [i["id"] for i in items] == [str(in_flight.id), str(pending_new.id), str(pending_old.id), str(recent.id)]

    def test_a_removal_in_flight_is_shown_with_its_status_and_a_failed_one_keeps_the_pair_pending(self, client, auth_headers, db_session, uob):
        p, *_ = uob
        job(db_session, p, S.FAILED)

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["status"] == "pending" and item["removalOffered"] is True  # a failed job can be retried
        assert item["removal"]["status"] == "failed" and item["removal"]["failureReason"] == "boom"

        # A retry is a separate request, so its job has a later requested_at (inside one test transaction both
        # rows would share the database's now(), so it is set explicitly).
        job(db_session, p, S.QUEUED, requested_at=datetime.now(UTC) + timedelta(seconds=5))
        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]
        assert item["removal"]["status"] == "queued" and item["removalOffered"] is False

    def test_a_recently_removed_pair_shows_what_was_deleted(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        p = pair(db_session, status=DuplicatePairStatus.REMOVED, decided_at=datetime.now(UTC))
        job(db_session, p, S.COMPLETED, deleted_counts={"transactions": 5}, finished_at=datetime.now(UTC))

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["status"] == "removed" and item["removalOffered"] is False and item["stale"] is False
        assert item["removal"]["status"] == "completed" and item["removal"]["deletedCounts"] == {"transactions": 5}

    def test_a_removal_that_could_not_clean_up_embeddings_is_visible_as_such(self, client, auth_headers, db_session):
        p = pair(db_session, status=DuplicatePairStatus.REMOVED, decided_at=datetime.now(UTC))
        job(db_session, p, S.EMBEDDINGS_FAILED)

        (item,) = client.get("/duplicates/pairs", headers=auth_headers).json()["items"]

        assert item["removal"]["status"] == "embeddings_failed"

    def test_pagination(self, client, auth_headers, db_session):
        for i in range(5):
            h1, h2 = f"{i}a" * 32, f"{i}b" * 32
            statement(db_session, h1)
            statement(db_session, h2)
            pair(db_session, keep=h1, other=h2, found_at=datetime.now(UTC) - timedelta(minutes=i))

        page = client.get("/duplicates/pairs?page=2&page_size=2", headers=auth_headers).json()

        assert page["totalCount"] == 5 and len(page["items"]) == 2 and page["page"] == 2 and page["pageSize"] == 2


class TestPendingCount:
    def test_counts_pending_pairs_without_a_removal_in_flight(self, client, auth_headers, db_session):
        for h in "abcdefgh":
            statement(db_session, h * 64)
        pair(db_session, keep="a" * 64, other="b" * 64)
        pair(db_session, keep="c" * 64, other="d" * 64, removal_allowed=False)  # information only still counts (Question 1 = C)
        in_flight = pair(db_session, keep="e" * 64, other="f" * 64)
        job(db_session, in_flight, S.RUNNING, remove_statement_hash="f" * 64)
        pair(db_session, keep="g" * 64, other="h" * 64, status=DuplicatePairStatus.DISMISSED)

        assert client.get("/duplicates/pairs/pending-count", headers=auth_headers).json() == {"pendingCount": 2}

    def test_zero_when_there_is_nothing(self, client, auth_headers):
        assert client.get("/duplicates/pairs/pending-count", headers=auth_headers).json() == {"pendingCount": 0}


class TestConfirmRemoval:
    def post(self, client, auth_headers, pair_id, **kw):
        return client.post(f"/duplicates/pairs/{pair_id}/remove", json=body(**kw), headers=auth_headers)

    def test_success_queues_exactly_one_job_carrying_what_the_user_was_shown(self, client, auth_headers, db_session, uob):
        p, *_ = uob

        response = self.post(client, auth_headers, p.id)

        assert response.status_code == 200
        (queued,) = db_session.query(StatementRemovalJob).all()
        assert queued.status is S.QUEUED and queued.remove_statement_hash == H_REMOVE and queued.corrections_acknowledged == 0
        data = response.json()
        assert data["removal"]["status"] == "queued" and data["removalOffered"] is False
        db_session.refresh(p)
        assert p.status is DuplicatePairStatus.PENDING  # the API deletes nothing and decides nothing else

    def test_the_acknowledged_count_is_stored_when_the_removed_copy_has_corrections(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE, manual=2)
        p = pair(db_session)

        assert self.post(client, auth_headers, p.id, acknowledged=2).status_code == 200
        assert db_session.query(StatementRemovalJob).one().corrections_acknowledged == 2

    def test_unknown_pair_is_404(self, client, auth_headers):
        assert self.post(client, auth_headers, uuid.uuid4()).status_code == 404

    @pytest.mark.parametrize("status", [DuplicatePairStatus.DISMISSED, DuplicatePairStatus.REMOVED, DuplicatePairStatus.SUPERSEDED])
    def test_a_pair_that_is_not_pending_is_refused(self, client, auth_headers, db_session, status):
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE)
        p = pair(db_session, status=status)

        response = self.post(client, auth_headers, p.id)

        assert response.status_code == 409 and response.json()["error"] == "pair_not_pending"
        assert db_session.query(StatementRemovalJob).count() == 0

    def test_removal_not_offered_is_refused(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE, n=15)
        p = pair(db_session, removal_allowed=False)

        response = self.post(client, auth_headers, p.id)

        assert response.status_code == 409 and response.json()["error"] == "removal_not_offered"
        assert db_session.query(StatementRemovalJob).count() == 0

    def test_a_removal_already_in_progress_is_refused(self, client, auth_headers, db_session, uob):
        p, *_ = uob
        job(db_session, p, S.EMBEDDINGS_PENDING)

        response = self.post(client, auth_headers, p.id)

        assert response.status_code == 409 and response.json()["error"] == "removal_already_requested"

    def test_a_missing_statement_is_refused(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        p = pair(db_session)

        response = self.post(client, auth_headers, p.id)

        assert response.status_code == 409 and response.json()["error"] == "statement_missing"

    def test_confirming_the_wrong_copy_is_out_of_date(self, client, auth_headers, db_session, uob):
        p, *_ = uob

        response = self.post(client, auth_headers, p.id, remove_hash=H_KEEP)

        assert response.status_code == 409 and response.json()["error"] == "confirmation_out_of_date"
        assert db_session.query(StatementRemovalJob).count() == 0

    @pytest.mark.parametrize("shown", [0, 1, 5])
    def test_a_different_correction_count_than_shown_is_out_of_date(self, client, auth_headers, db_session, shown):
        """The user saw `shown` corrections; the live count is 2. Both a lower and a higher count are refused:
        the user acknowledged an exact number."""
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE, manual=2)
        p = pair(db_session)

        response = self.post(client, auth_headers, p.id, acknowledged=shown)

        assert response.status_code == 409 and response.json()["error"] == "confirmation_out_of_date"
        assert "from" in response.json()["message"] and db_session.query(StatementRemovalJob).count() == 0

    def test_checks_run_in_order_not_offered_wins_over_out_of_date(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE, manual=2)
        p = pair(db_session, removal_allowed=False)

        response = self.post(client, auth_headers, p.id, remove_hash=H_KEEP, acknowledged=99)

        assert response.json()["error"] == "removal_not_offered"

    def test_a_lost_race_is_a_clear_409_and_the_session_stays_usable(self, client, auth_headers, db_session, uob):
        """Two confirmations at once: the second passes the application's check (simulated) and is stopped by the
        database's one-active-job rule inside a savepoint."""
        p, *_ = uob
        job(db_session, p, S.QUEUED)

        with patch.object(repository, "has_active_job", return_value=False):
            response = self.post(client, auth_headers, p.id)

        assert response.status_code == 409 and response.json()["error"] == "removal_already_requested"
        assert db_session.query(StatementRemovalJob).count() == 1  # still usable, and still exactly one job

    def test_a_retry_after_a_failed_job_is_accepted(self, client, auth_headers, db_session, uob):
        p, *_ = uob
        job(db_session, p, S.FAILED)

        assert self.post(client, auth_headers, p.id).status_code == 200
        assert db_session.query(StatementRemovalJob).count() == 2


class TestDismiss:
    def test_dismisses_a_pending_pair_and_stamps_the_decision(self, client, auth_headers, db_session, uob):
        p, *_ = uob

        response = client.post(f"/duplicates/pairs/{p.id}/dismiss", headers=auth_headers)

        assert response.status_code == 200 and response.json()["status"] == "dismissed"
        db_session.refresh(p)
        assert p.status is DuplicatePairStatus.DISMISSED and p.decided_at is not None

    def test_an_information_only_pair_can_be_dismissed(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE, n=15)
        p = pair(db_session, removal_allowed=False)

        assert client.post(f"/duplicates/pairs/{p.id}/dismiss", headers=auth_headers).status_code == 200

    def test_unknown_pair_is_404(self, client, auth_headers):
        assert client.post(f"/duplicates/pairs/{uuid.uuid4()}/dismiss", headers=auth_headers).status_code == 404

    def test_an_already_decided_pair_is_refused(self, client, auth_headers, db_session):
        statement(db_session, H_KEEP)
        statement(db_session, H_REMOVE)
        p = pair(db_session, status=DuplicatePairStatus.DISMISSED)

        response = client.post(f"/duplicates/pairs/{p.id}/dismiss", headers=auth_headers)

        assert response.status_code == 409 and response.json()["error"] == "pair_not_pending"

    def test_a_pair_with_a_removal_in_flight_is_refused(self, client, auth_headers, db_session, uob):
        p, *_ = uob
        job(db_session, p, S.RUNNING)

        response = client.post(f"/duplicates/pairs/{p.id}/dismiss", headers=auth_headers)

        assert response.status_code == 409 and response.json()["error"] == "removal_already_requested"

    def test_a_decision_made_meanwhile_is_never_overwritten(self, client, auth_headers, db_session, uob):
        """The write is conditional on the pair still being pending: if another decision lands between the
        check and the write, the second is refused rather than silently replacing it."""
        p, *_ = uob
        decided = datetime(2026, 1, 1, tzinfo=UTC)

        def decided_meanwhile(_db, _pair_id):
            db_session.execute(update(DuplicatePair).where(DuplicatePair.id == p.id)
                               .values(status=DuplicatePairStatus.REMOVED, decided_at=decided))
            return False

        with patch.object(repository, "has_active_job", side_effect=decided_meanwhile):
            response = client.post(f"/duplicates/pairs/{p.id}/dismiss", headers=auth_headers)

        assert response.status_code == 409 and response.json()["error"] == "pair_not_pending"
        db_session.refresh(p)
        assert p.status is DuplicatePairStatus.REMOVED and p.decided_at == decided


class TestComparison:
    def test_the_stored_snapshot_with_rows_ranked_and_marked(self, client, auth_headers, db_session, uob):
        p, *_ = uob

        data = client.get(f"/duplicates/comparisons/{p.comparison_id}", headers=auth_headers).json()

        assert data["reason"] == "5 of 5 transactions match" and data["matchedCount"] == 5
        assert data["earlier"]["label"]["fileName"] == "first.pdf" and data["later"]["label"]["fileName"] == "second.pdf"
        assert [r["rank"] for r in data["earlier"]["rows"]] == [1, 2]
        assert [r["marker"] for r in data["earlier"]["rows"]] == ["also_on_other", "only_on_this_one"]
        assert data["state"] == "pair_pending" and data["pairId"] == str(p.id) and data["removalOffered"] is True
        assert data["thisFileSide"] is None and data["canOverride"] is False

    def test_unknown_comparison_is_404(self, client, auth_headers):
        assert client.get(f"/duplicates/comparisons/{uuid.uuid4()}", headers=auth_headers).status_code == 404

    def test_it_is_unchanged_when_the_original_is_later_removed(self, client, auth_headers, db_session, uob):
        p, keep, _ = uob
        before = client.get(f"/duplicates/comparisons/{p.comparison_id}", headers=auth_headers).json()
        db_session.query(Transaction).filter_by(bank_statement_id=keep.id).delete()
        db_session.delete(keep)
        db_session.flush()

        after = client.get(f"/duplicates/comparisons/{p.comparison_id}", headers=auth_headers).json()

        assert after["earlier"] == before["earlier"] and after["reason"] == before["reason"]

    @pytest.mark.parametrize("pair_status,expected", [
        (DuplicatePairStatus.PENDING, "pair_pending"), (DuplicatePairStatus.DISMISSED, "pair_dismissed"),
        (DuplicatePairStatus.SUPERSEDED, "pair_superseded"), (DuplicatePairStatus.REMOVED, "removed"),
    ])
    def test_a_held_pairs_state_follows_the_pair(self, client, auth_headers, db_session, pair_status, expected):
        p = pair(db_session, status=pair_status)

        data = client.get(f"/duplicates/comparisons/{p.comparison_id}", headers=auth_headers).json()

        assert data["state"] == expected

    def test_a_pair_with_a_removal_in_flight_does_not_offer_removal(self, client, auth_headers, db_session, uob):
        p, *_ = uob
        job(db_session, p, S.QUEUED)

        assert client.get(f"/duplicates/comparisons/{p.comparison_id}", headers=auth_headers).json()["removalOffered"] is False

    @pytest.mark.parametrize("known_state,expected,can_override", [
        (KnownFileState.PROBABLE_DUPLICATE, "skipped", True),
        (KnownFileState.CONFIRMED_DUPLICATE, "removed", True),
        (KnownFileState.OVERRIDDEN, "ingest_at_next_run", False),
    ])
    def test_a_remembered_files_state_and_which_side_is_this_file(self, client, auth_headers, db_session, known_state, expected, can_override):
        cmp = comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=H_REMOVE, state=known_state, matched_statement_hash=H_KEEP, comparison_id=cmp.id))
        db_session.flush()

        data = client.get(f"/duplicates/comparisons/{cmp.id}", headers=auth_headers).json()

        assert data["state"] == expected and data["canOverride"] is can_override
        assert data["thisFileSide"] == "later"  # the skipped file is the later side
        assert data["pairId"] is None

    def test_this_file_is_the_earlier_side_when_its_hash_is_the_earlier_ones(self, client, auth_headers, db_session):
        cmp = comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=H_KEEP, state=KnownFileState.CONFIRMED_DUPLICATE, matched_statement_hash=H_REMOVE, comparison_id=cmp.id))
        db_session.flush()

        assert client.get(f"/duplicates/comparisons/{cmp.id}", headers=auth_headers).json()["thisFileSide"] == "earlier"

    def test_an_overridden_file_that_has_since_been_ingested_says_so(self, client, auth_headers, db_session):
        cmp = comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=H_REMOVE, state=KnownFileState.OVERRIDDEN, matched_statement_hash=H_KEEP, comparison_id=cmp.id))
        statement(db_session, H_REMOVE)
        db_session.flush()

        assert client.get(f"/duplicates/comparisons/{cmp.id}", headers=auth_headers).json()["state"] == "ingested_at_your_request"


class TestOverride:
    def known(self, db, state=KnownFileState.PROBABLE_DUPLICATE):
        cmp = comparison(db)
        k = KnownFile(pdf_content_hash=H_REMOVE, state=state, matched_statement_hash=H_KEEP, comparison_id=cmp.id)
        db.add(k)
        db.flush()
        return cmp, k

    def test_overrides_a_skipped_file_for_the_next_run(self, client, auth_headers, db_session):
        cmp, k = self.known(db_session)

        response = client.post(f"/duplicates/comparisons/{cmp.id}/override", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"comparisonId": str(cmp.id), "state": "ingest_at_next_run", "note": None}
        db_session.refresh(k)
        assert k.state is KnownFileState.OVERRIDDEN and k.decided_at is not None

    def test_overriding_a_removed_copy_says_its_corrections_are_not_restored(self, client, auth_headers, db_session):
        cmp, k = self.known(db_session, KnownFileState.CONFIRMED_DUPLICATE)

        data = client.post(f"/duplicates/comparisons/{cmp.id}/override", headers=auth_headers).json()

        assert "not restored" in data["note"] and data["state"] == "ingest_at_next_run"
        db_session.refresh(k)
        assert k.state is KnownFileState.OVERRIDDEN

    def test_it_is_idempotent_and_does_not_restamp_the_decision(self, client, auth_headers, db_session):
        cmp, k = self.known(db_session)
        client.post(f"/duplicates/comparisons/{cmp.id}/override", headers=auth_headers)
        db_session.refresh(k)
        stamped = k.decided_at

        again = client.post(f"/duplicates/comparisons/{cmp.id}/override", headers=auth_headers)

        assert again.status_code == 200 and again.json()["note"] is None
        db_session.refresh(k)
        assert k.decided_at == stamped

    def test_once_the_file_has_been_ingested_the_response_says_so(self, client, auth_headers, db_session):
        cmp, _k = self.known(db_session)
        statement(db_session, H_REMOVE)

        assert client.post(f"/duplicates/comparisons/{cmp.id}/override", headers=auth_headers).json()["state"] == "ingested_at_your_request"

    def test_a_held_pairs_comparison_has_nothing_to_override(self, client, auth_headers, db_session, uob):
        p, *_ = uob

        response = client.post(f"/duplicates/comparisons/{p.comparison_id}/override", headers=auth_headers)

        assert response.status_code == 409 and response.json()["error"] == "not_a_skipped_file"

    def test_unknown_comparison_is_404(self, client, auth_headers):
        assert client.post(f"/duplicates/comparisons/{uuid.uuid4()}/override", headers=auth_headers).status_code == 404


class TestScanStatus:
    def test_defaults_when_no_scan_has_ever_run(self, client, auth_headers, settings_override_path):
        data = client.get("/duplicates/scan-status", headers=auth_headers).json()

        assert data == {"lastCompletedAt": None, "pairsFound": None, "recheckRequested": False, "detectionEnabled": False}

    def test_reports_the_effective_detection_setting(self, client, auth_headers, settings_override_path, monkeypatch):
        from api_service import config

        monkeypatch.setattr(config.settings, "duplicate_detection_enabled", True)

        assert client.get("/duplicates/scan-status", headers=auth_headers).json()["detectionEnabled"] is True

    def test_the_override_file_wins_over_the_deployed_value(self, client, auth_headers, settings_override_path):
        """The switch was changed on the Settings page: that is what the panel reports."""
        client.put("/settings/duplicate_detection_enabled", json={"value": "true"}, headers=auth_headers)

        assert client.get("/duplicates/scan-status", headers=auth_headers).json()["detectionEnabled"] is True

    def completed_scan(self, db, *, stored_pairs_found=None):
        done = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
        db.add(DuplicateScanState(id=1, last_scan_started_at=done - timedelta(seconds=3), last_scan_completed_at=done,
                                  last_scan_match_ratio=Decimal("0.8000"), last_scan_min_transactions=3,
                                  last_scan_pairs_found=stored_pairs_found))
        db.flush()

    def test_reports_the_last_scan(self, client, auth_headers, db_session, settings_override_path):
        statement(db_session, H_KEEP), statement(db_session, H_REMOVE)
        pair(db_session)
        self.completed_scan(db_session, stored_pairs_found=1)

        data = client.get("/duplicates/scan-status", headers=auth_headers).json()

        assert data["pairsFound"] == 1 and data["lastCompletedAt"].startswith("2026-10-04T12:00:00") and data["recheckRequested"] is False

    def test_pairs_found_is_the_number_awaiting_a_decision_now_not_the_figure_the_scan_stored(
        self, client, auth_headers, db_session, settings_override_path
    ):
        """The panel prints this beside its list. The scan stored 2, but one pair has since been dismissed, so the
        panel must say 1 -- not "2 found" next to a list showing one."""
        statement(db_session, H_KEEP), statement(db_session, H_REMOVE)
        pair(db_session)
        pair(db_session, keep=H_KEEP, other="d" * 64, status=DuplicatePairStatus.DISMISSED)
        pair(db_session, keep=H_KEEP, other="e" * 64, status=DuplicatePairStatus.REMOVED)
        pair(db_session, keep=H_KEEP, other="f" * 64, status=DuplicatePairStatus.SUPERSEDED)
        self.completed_scan(db_session, stored_pairs_found=2)

        assert client.get("/duplicates/scan-status", headers=auth_headers).json()["pairsFound"] == 1

    def test_pairs_found_falls_to_zero_once_the_only_pair_is_dismissed_or_removed(self, client, auth_headers, db_session, uob, settings_override_path):
        self.completed_scan(db_session, stored_pairs_found=1)
        assert client.get("/duplicates/scan-status", headers=auth_headers).json()["pairsFound"] == 1

        response = client.post(f"/duplicates/pairs/{uob[0].id}/dismiss", headers=auth_headers)

        assert response.status_code == 200
        assert client.get("/duplicates/scan-status", headers=auth_headers).json()["pairsFound"] == 0

    def test_a_pair_being_removed_still_counts_until_the_deletion_commits(self, client, auth_headers, db_session, uob, settings_override_path):
        job(db_session, uob[0], S.RUNNING)
        self.completed_scan(db_session, stored_pairs_found=1)

        assert client.get("/duplicates/scan-status", headers=auth_headers).json()["pairsFound"] == 1

    def test_pairs_found_is_null_until_a_scan_has_completed(self, client, auth_headers, db_session, settings_override_path):
        """A re-check was requested but nothing has ever been scanned: "Not checked yet", not "0 found"."""
        client.post("/duplicates/recheck", headers=auth_headers)

        data = client.get("/duplicates/scan-status", headers=auth_headers).json()

        assert data["pairsFound"] is None and data["lastCompletedAt"] is None

    def test_recheck_creates_the_single_row_and_is_idempotent(self, client, auth_headers, db_session, settings_override_path):
        first = client.post("/duplicates/recheck", headers=auth_headers)
        second = client.post("/duplicates/recheck", headers=auth_headers)

        assert first.status_code == 200 and first.json()["recheckRequested"] is True and second.json()["recheckRequested"] is True
        assert db_session.query(DuplicateScanState).count() == 1

    def test_a_recheck_requested_before_the_last_scan_began_is_no_longer_waiting(self, client, auth_headers, db_session, settings_override_path):
        now = datetime.now(UTC)
        db_session.add(DuplicateScanState(id=1, recheck_requested_at=now - timedelta(hours=1), last_scan_started_at=now - timedelta(minutes=5),
                                          last_scan_completed_at=now))
        db_session.flush()

        assert client.get("/duplicates/scan-status", headers=auth_headers).json()["recheckRequested"] is False


class TestRunFileDetail:
    def make_run(self, db):
        from transactagent_db.models import User

        user = User(username=f"u-{uuid.uuid4().hex[:6]}", password_hash="x")
        db.add(user)
        db.flush()
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.COMPLETED)
        db.add(run)
        db.flush()
        return run

    def test_a_probable_duplicate_file_returns_its_comparison_and_the_matched_statement(self, client, auth_headers, db_session):
        run = self.make_run(db_session)
        cmp = comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=H_REMOVE, state=KnownFileState.PROBABLE_DUPLICATE, matched_statement_hash=H_KEEP, comparison_id=cmp.id))
        db_session.add(IngestionRunFile(ingestion_run_id=run.id, drive_file_id="d1", drive_file_name="second.pdf",
                                        outcome=IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE, duplicate_comparison_id=cmp.id))
        db_session.flush()

        (file,) = client.get(f"/ingestion/runs/{run.id}/files", headers=auth_headers).json()

        assert file["outcome"] == "skipped_probable_duplicate" and file["duplicateComparisonId"] == str(cmp.id)
        assert file["matchedStatement"]["fileName"] == "first.pdf" and file["matchedStatement"]["bankName"] == "UOB"
        assert file["matchedStatement"]["contentHash"] == H_KEEP

    def test_for_a_removed_copy_the_matched_statement_is_the_copy_that_was_kept_even_when_it_is_the_later_side(self, client, auth_headers, db_session):
        """The matched side is found through the remembered file, not by position: here the removed copy is the
        EARLIER side of its comparison."""
        run = self.make_run(db_session)
        cmp = comparison(db_session)
        db_session.add(KnownFile(pdf_content_hash=H_KEEP, state=KnownFileState.CONFIRMED_DUPLICATE, matched_statement_hash=H_REMOVE, comparison_id=cmp.id))
        db_session.add(IngestionRunFile(ingestion_run_id=run.id, drive_file_id="d1", drive_file_name="first.pdf",
                                        outcome=IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE, duplicate_comparison_id=cmp.id))
        db_session.flush()

        (file,) = client.get(f"/ingestion/runs/{run.id}/files", headers=auth_headers).json()

        assert file["matchedStatement"]["fileName"] == "second.pdf"

    def test_other_outcomes_return_nulls(self, client, auth_headers, db_session):
        run = self.make_run(db_session)
        db_session.add(IngestionRunFile(ingestion_run_id=run.id, drive_file_id="d1", drive_file_name="a.pdf", outcome=IngestionRunFileOutcome.FAILED,
                                        failure_reason="no text"))
        db_session.flush()

        (file,) = client.get(f"/ingestion/runs/{run.id}/files", headers=auth_headers).json()

        assert file["duplicateComparisonId"] is None and file["matchedStatement"] is None


class TestSettingsEntries:
    def test_the_three_settings_are_in_their_own_category(self, client, auth_headers, settings_override_path):
        rows = {r["name"]: r for r in client.get("/settings", headers=auth_headers).json()}

        for name in ("duplicate_detection_enabled", "duplicate_match_ratio", "duplicate_min_transactions"):
            assert rows[name]["category"] == "Duplicate Statements" and rows[name]["owningServices"] == ["ingestion-worker"]
        assert rows["duplicate_detection_enabled"]["type"] == "enum" and rows["duplicate_detection_enabled"]["allowedValues"] == ["false", "true"]
        assert rows["duplicate_min_transactions"]["classification"] == "advanced"

    def test_the_switch_ships_off_and_displays_in_lowercase(self, client, auth_headers, settings_override_path):
        """A deployed boolean must show as `false`, matching the enum's allowed values, not Python's `False`."""
        row = client.get("/settings/duplicate_detection_enabled", headers=auth_headers).json()

        assert row["value"] == "false" and row["isOverridden"] is False

    def test_a_deployed_true_displays_as_lowercase_true(self, client, auth_headers, settings_override_path, monkeypatch):
        from api_service import config

        monkeypatch.setattr(config.settings, "duplicate_detection_enabled", True)

        assert client.get("/settings/duplicate_detection_enabled", headers=auth_headers).json()["value"] == "true"

    def test_the_switch_accepts_true_and_rejects_anything_else(self, client, auth_headers, settings_override_path):
        ok = client.put("/settings/duplicate_detection_enabled", json={"value": "true"}, headers=auth_headers)
        bad = client.put("/settings/duplicate_detection_enabled", json={"value": "maybe"}, headers=auth_headers)

        assert ok.status_code == 200 and ok.json()["restartGuidance"][0]["owningService"] == "ingestion-worker"
        assert bad.status_code == 400
        assert client.get("/settings/duplicate_detection_enabled", headers=auth_headers).json()["value"] == "true"

    @pytest.mark.parametrize("value,ok", [("0.5", True), ("0.8", True), ("1.0", True), ("0.49", False), ("1.01", False)])
    def test_the_match_ratio_is_bounded(self, client, auth_headers, settings_override_path, value, ok):
        response = client.put("/settings/duplicate_match_ratio", json={"value": value}, headers=auth_headers)

        assert (response.status_code == 200) is ok

    @pytest.mark.parametrize("value,ok", [("1", True), ("3", True), ("50", True), ("0", False), ("51", False)])
    def test_the_minimum_is_bounded(self, client, auth_headers, settings_override_path, value, ok):
        response = client.put("/settings/duplicate_min_transactions", json={"value": value}, headers=auth_headers)

        assert (response.status_code == 200) is ok


class TestPreviewMatchesTheRealDependents:
    """BR-51: the removal, the backfill wipe and this preview must agree on what depends on a statement."""

    def test_the_previews_dependent_kinds_cover_every_table_the_removal_deletes(self):
        statement_tables = {"bank_statements", "statement_accounts", "transactions"}
        references = {t.name: {fk.column.table.name for fk in t.foreign_keys} for t in Base.metadata.tables.values()}
        found, frontier = set(), set(statement_tables)
        while frontier:
            step = {n for n, refs in references.items() if refs & frontier and n not in found and n not in statement_tables}
            found |= step
            frontier = step

        deleted = found - {"ingestion_run_files"}  # detached (set null), not deleted
        assert set(repository.PREVIEW_DEPENDENT_KINDS) == deleted, (
            f"Tables that depend on a statement or its transactions changed ({sorted(found)}). Update the preview's "
            "counts, the Statement Removal Handler's delete helper and the Backfill Tool's wipe together (BR-51)."
        )

    def test_the_preview_reports_each_kind(self):
        assert set(repository.PREVIEW_DEPENDENT_KINDS) <= set(service.RemovalPreviewDTO.model_fields)
