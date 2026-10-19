"""Cross-service scenario for Epic 14: the WORKER detects a pair, the API lists it and takes the user's removal
request, the WORKER executes it, and the API then reports the result -- all through the real code of both services
against one real PostgreSQL (only Drive, extraction and the vector store are faked, as in each service's own tests)."""
from unittest.mock import patch

from duplicates_helpers import extracted, june
from sqlalchemy import select
from test_duplicates_end_to_end import FIRST, SECOND, _run  # the worker's own run helper
from transactagent_db.models import BankStatement, Category, CategorySource, StatementRemovalJob, Transaction, User

from api_service.auth.security import hash_password
from api_service import config as api_config
from ingestion_worker import config
from ingestion_worker.duplicates import removal, service


def _login(client, db):
    db.add(User(username="account_owner", password_hash=hash_password("correct horse battery staple")))
    db.flush()
    r = client.post("/auth/login", json={"username": "account_owner", "password": "correct horse battery staple"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_worker_detects_api_requests_worker_removes_api_reports(db_session, client, monkeypatch):
    db = db_session
    headers = _login(client, db)
    for name in ("Groceries", "UNSURE"):
        db.add(Category(name=name, active=True, is_reserved=(name == "UNSURE")))
    db.flush()
    statement = extracted(june(5), bank="UOB")

    # -- two downloads of the same statement, ingested as today (detection OFF) --------------------------------
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", False)
    run1, _ = _run(db, lambda _pdf: statement)
    assert db.query(BankStatement).count() == 2

    # the user has corrected 3 transactions on one copy and 1 on the other (so the keep rule and the preview have work to do)
    stmts = db.scalars(select(BankStatement).order_by(BankStatement.pdf_content_hash)).all()
    for stmt, n in zip(stmts, (3, 1), strict=True):
        for t in db.scalars(select(Transaction).where(Transaction.bank_statement_id == stmt.id).limit(n)):
            t.category_source = CategorySource.MANUAL
    db.flush()

    # detection ships OFF -> the API says so, and shows nothing, before the switch is on
    assert client.get("/duplicates/pairs/pending-count", headers=headers).json() == {"pendingCount": 0}
    assert client.get("/duplicates/scan-status", headers=headers).json()["detectionEnabled"] is False

    # -- the WORKER finds the pair ------------------------------------------------------------------------------
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", True)
    monkeypatch.setattr(api_config.settings, "duplicate_detection_enabled", True)  # production: one env var feeds both containers
    assert service.run_pair_scan(db) == 1
    db.flush()

    # -- the API lists it exactly as the frontend's types expect -------------------------------------------------
    assert client.get("/duplicates/pairs/pending-count", headers=headers).json() == {"pendingCount": 1}
    page = client.get("/duplicates/pairs", headers=headers).json()
    assert page["totalCount"] == 1
    pair = page["items"][0]
    assert pair["status"] == "pending" and pair["removalOffered"] is True and pair["stale"] is False
    assert pair["correctionsOnKept"] == 3 and pair["correctionsOnRemoved"] == 1      # the copy with MORE corrections is kept
    assert pair["keep"]["fileName"] and pair["remove"]["fileName"] and pair["keep"]["bankName"] == "UOB"
    assert pair["preview"]["transactions"] == 5 and pair["preview"]["correctionsLost"] == 1
    assert pair["preview"]["onlyOnRemovedCopy"] == 0 and pair["removal"] is None

    cmp = client.get(f"/duplicates/comparisons/{pair['comparisonId']}", headers=headers).json()
    assert cmp["state"] == "pair_pending" and cmp["canOverride"] is False and cmp["matchedCount"] == 5
    assert len(cmp["earlier"]["rows"]) == 5 and all(r["marker"] == "also_on_other" for r in cmp["earlier"]["rows"] + cmp["later"]["rows"])

    # -- the API refuses an out-of-date or wrong confirmation, and nothing is deleted ----------------------------
    url = f"/duplicates/pairs/{pair['id']}/remove"
    wrong_count = client.post(url, headers=headers, json={"removeStatementHash": pair["remove"]["contentHash"], "acknowledgedCorrectionsLost": 0})
    assert wrong_count.status_code == 409 and wrong_count.json()["error"] == "confirmation_out_of_date"
    wrong_copy = client.post(url, headers=headers, json={"removeStatementHash": pair["keep"]["contentHash"], "acknowledgedCorrectionsLost": 3})
    assert wrong_copy.status_code in (409, 422), wrong_copy.text
    assert db.query(StatementRemovalJob).count() == 0 and db.query(BankStatement).count() == 2

    # -- the user confirms exactly what the dialog showed -------------------------------------------------------
    ok = client.post(url, headers=headers, json={"removeStatementHash": pair["remove"]["contentHash"], "acknowledgedCorrectionsLost": 1})
    assert ok.status_code == 200, ok.text
    assert ok.json()["removal"]["status"] == "queued"
    again = client.post(url, headers=headers, json={"removeStatementHash": pair["remove"]["contentHash"], "acknowledgedCorrectionsLost": 1})
    assert again.status_code == 409 and again.json()["error"] == "removal_already_requested"
    assert client.get("/duplicates/pairs/pending-count", headers=headers).json() == {"pendingCount": 0}  # in flight leaves the badge

    # -- the WORKER executes the API's job ---------------------------------------------------------------------
    removed_ids = sorted(str(t.id) for t in db.scalars(
        select(Transaction).join(BankStatement).where(BankStatement.pdf_content_hash == pair["remove"]["contentHash"])))
    with patch("ingestion_worker.duplicates.removal.vector_store.delete_embeddings", return_value=True) as delete:
        result = removal.process_next_removal(db, sleep=lambda _s: None)
    assert result.status == "completed" and sorted(delete.call_args.args[1]) == removed_ids

    # -- the API reports the outcome ---------------------------------------------------------------------------
    after = client.get("/duplicates/pairs", headers=headers).json()["items"][0]
    assert after["status"] == "removed" and after["removal"]["status"] == "completed"
    assert after["removal"]["deletedCounts"]["transactions"] == 5
    assert db.query(BankStatement).count() == 1
    removed_state = client.get(f"/duplicates/comparisons/{pair['comparisonId']}", headers=headers).json()
    assert removed_state["state"] == "removed" and removed_state["canOverride"] is True
    scan = client.get("/duplicates/scan-status", headers=headers).json()
    assert scan["detectionEnabled"] is True and scan["pairsFound"] == 0

    # -- the next ingestion run recognises the removed copy's FILE without reading it; the API shows the link --------
    calls = []
    run2, extract_mock = _run(db, lambda pdf: calls.append(pdf) or statement)
    assert extract_mock.call_count == 0
    files = client.get(f"/ingestion/runs/{run2.id}/files", headers=headers).json()
    skipped = [f for f in files if f["outcome"] == "skipped_probable_duplicate"]
    assert len(skipped) == 1 and skipped[0]["duplicateComparisonId"] == pair["comparisonId"]
    assert skipped[0]["matchedStatement"]["contentHash"] == pair["keep"]["contentHash"]   # "Probable duplicate of <the kept copy>"
    assert [f for f in files if f["outcome"] == "skipped_duplicate"] and all(f["outcome"] != "failed" for f in files)

    # -- the user changes their mind: override -> the worker ingests it at the next run -------------------------------
    ov = client.post(f"/duplicates/comparisons/{pair['comparisonId']}/override", headers=headers)
    assert ov.status_code == 200 and ov.json()["state"] == "ingest_at_next_run" and ov.json()["note"]
    run3, _ = _run(db, lambda _pdf: statement)
    assert db.query(BankStatement).count() == 2                       # the removed copy is back
    assert client.get(f"/duplicates/comparisons/{pair['comparisonId']}", headers=headers).json()["state"] == "ingested_at_your_request"
    service.run_pair_scan(db)                                         # an overridden file is never re-proposed
    assert client.get("/duplicates/pairs/pending-count", headers=headers).json() == {"pendingCount": 0}
