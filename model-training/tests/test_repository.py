"""MTR-1..4: eligibility query and whitelist query correctness, against a real
Postgres (testcontainers) -- same pattern the other 3 backend units already use.
"""

import ast
import inspect
import uuid
from datetime import date
from decimal import Decimal
from typing import ClassVar

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

from model_training import repository


def _make_category(db, name, active=True):
    category = Category(name=name, active=active, is_reserved=(name == "UNSURE"))
    db.add(category)
    db.flush()
    return category


def _make_statement(db):
    stmt = BankStatement(drive_file_id="f1", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    db.add(stmt)
    db.flush()
    return stmt


def _make_transaction(db, description, category, source, amount_sgd=Decimal("10.00")):
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
        converted_amount_sgd=amount_sgd,
    )
    db.add(txn)
    db.flush()
    return txn


def _make_approved_proposal(db, candidate_transaction, proposed_category):
    job = RecategorizationJob(source_transaction_id=candidate_transaction.id)
    db.add(job)
    db.flush()
    proposal = RecategorizationProposal(
        recategorization_job_id=job.id,
        candidate_transaction_id=candidate_transaction.id,
        proposed_category_id=proposed_category.id,
        match_score=Decimal("95.00"),
        source_bucket=RecategorizationProposalSourceBucket.CATEGORIZED,
        status=RecategorizationProposalStatus.APPROVED,
    )
    db.add(proposal)
    db.flush()
    return proposal


class TestFindEligibleTransactions:
    def test_manual_source_is_eligible(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, CategorySource.MANUAL)

        result = repository.find_eligible_transactions(db_session)

        assert any(row.transaction_id == txn.id for row in result)

    def test_llm_source_is_excluded(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, CategorySource.LLM)

        result = repository.find_eligible_transactions(db_session)

        assert not any(row.transaction_id == txn.id for row in result)

    def test_unsure_source_is_excluded(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, CategorySource.UNSURE)

        result = repository.find_eligible_transactions(db_session)

        assert not any(row.transaction_id == txn.id for row in result)

    def test_raw_unreviewed_similarity_is_excluded(self, db_session):
        """MTR-1: similarity alone (no approved proposal) is NOT eligible -- only
        similarity rows a human reviewed and approved qualify."""
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, CategorySource.SIMILARITY)

        result = repository.find_eligible_transactions(db_session)

        assert not any(row.transaction_id == txn.id for row in result)

    def test_similarity_with_approved_proposal_is_eligible(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, CategorySource.SIMILARITY)
        _make_approved_proposal(db_session, txn, groceries)

        result = repository.find_eligible_transactions(db_session)

        assert any(row.transaction_id == txn.id for row in result)

    def test_similarity_with_pending_proposal_is_excluded(self, db_session):
        """Only status='approved' counts -- a pending (not-yet-reviewed) proposal
        does not make a similarity-sourced transaction eligible."""
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, CategorySource.SIMILARITY)
        job = RecategorizationJob(source_transaction_id=txn.id)
        db_session.add(job)
        db_session.flush()
        db_session.add(
            RecategorizationProposal(
                recategorization_job_id=job.id,
                candidate_transaction_id=txn.id,
                proposed_category_id=groceries.id,
                match_score=Decimal("95.00"),
                source_bucket=RecategorizationProposalSourceBucket.CATEGORIZED,
                status=RecategorizationProposalStatus.PENDING,
            )
        )
        db_session.flush()

        result = repository.find_eligible_transactions(db_session)

        assert not any(row.transaction_id == txn.id for row in result)

    def test_carries_amount_and_category_name(self, db_session):
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(
            db_session, "NTUC FAIRPRICE", groceries, CategorySource.MANUAL, amount_sgd=Decimal("45.20")
        )

        result = repository.find_eligible_transactions(db_session)

        row = next(r for r in result if r.transaction_id == txn.id)
        assert row.description == "NTUC FAIRPRICE"
        assert row.amount_sgd == Decimal("45.20")
        assert row.category_name == "Groceries"

    def test_null_amount_is_still_returned_by_the_repository(self, db_session):
        """MTR-2's null-amount exclusion is curate.py's job, not this query's --
        the repository returns everything eligible per MTR-1, unfiltered on amount."""
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, CategorySource.MANUAL, amount_sgd=None)

        result = repository.find_eligible_transactions(db_session)

        row = next(r for r in result if r.transaction_id == txn.id)
        assert row.amount_sgd is None

    def test_ordered_by_transaction_id_for_deterministic_split(self, db_session):
        """MTR-4: the split step depends on this ordering being stable/deterministic."""
        groceries = _make_category(db_session, "Groceries")
        txns = [_make_transaction(db_session, f"MERCHANT {i}", groceries, CategorySource.MANUAL) for i in range(5)]

        result = repository.find_eligible_transactions(db_session)

        ids = [row.transaction_id for row in result if row.transaction_id in {t.id for t in txns}]
        assert ids == sorted(ids)


class TestListActiveCategoryNames:
    def test_returns_only_active_categories(self, db_session):
        _make_category(db_session, "Groceries", active=True)
        _make_category(db_session, "Retired Category", active=False)

        result = repository.list_active_category_names(db_session)

        assert "Groceries" in result
        assert "Retired Category" not in result


class TestReadOnlyDiscipline:
    """NFR-CFT-2/NFR Design's 'Read-Only Session Discipline': this module must
    never call a write method on the Session. AST-based (not substring
    matching) so this doesn't false-positive on the module's own docstring
    mentioning these method names in prose."""

    _FORBIDDEN_METHODS: ClassVar[set[str]] = {"add", "flush", "commit", "delete", "merge", "execute"}
    # 'execute' would also flag legitimate SELECT execution -- excluded from the
    # forbidden set actually enforced below; kept here only as a documented
    # reminder that raw SQL writes via execute() are the other thing to watch for
    # if this module ever changes.
    _ENFORCED = _FORBIDDEN_METHODS - {"execute"}

    def test_no_write_calls_anywhere_in_the_module_source(self):
        tree = ast.parse(inspect.getsource(repository))
        called_methods = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        offending = called_methods & self._ENFORCED
        assert not offending, f"repository.py must never call Session.{{{', '.join(offending)}}}()"
