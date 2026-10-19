"""Account Management data access (AR-51 to AR-54) against a real PostgreSQL."""

from datetime import date
from decimal import Decimal

import pytest
from account_helpers import (
    account_with_history,
    make_account,
    make_section,
    make_statement,
    make_tx,
    make_unlinked_tx,
    set_anchor,
)
from sqlalchemy.exc import IntegrityError
from transactagent_db.models import (
    AccountKey,
    AccountType,
    BalanceAnchor,
    StatementAccount,
)

from api_service.accounts import repository


class TestListAccountRows:
    def test_an_account_with_nothing_is_listed_with_zeros(self, db_session):
        make_account(db_session)
        [row] = repository.list_account_rows(db_session)
        assert (row.statement_count, row.closing_balance_count, row.transaction_count) == (0, 0, 0)
        assert row.latest_transaction_date is None and row.anchor is None

    def test_counts_dates_and_identifier_are_per_account(self, db_session):
        one, _section = account_with_history(db_session, "One", flows=[(date(2026, 1, 5), "10"), (date(2026, 3, 9), "-4")], identifier="1111")
        make_section(db_session, one, closing="6.00", closing_date=date(2026, 3, 31))
        _two, _ = account_with_history(db_session, "Two", flows=[(date(2026, 2, 1), "1")], identifier="2222")
        make_unlinked_tx(db_session, date(2026, 4, 1), "99")  # belongs to nobody

        rows = {r.account.name: r for r in repository.list_account_rows(db_session)}

        assert (rows["One"].statement_count, rows["One"].closing_balance_count, rows["One"].transaction_count) == (2, 1, 2)
        assert rows["One"].latest_transaction_date == date(2026, 3, 9) and rows["One"].account_identifier == "1111"
        assert (rows["Two"].transaction_count, rows["Two"].latest_transaction_date, rows["Two"].account_identifier) == (1, date(2026, 2, 1), "2222")

    def test_an_account_whose_keys_have_no_identifier_shows_none(self, db_session):
        make_account(db_session, identifier=None)
        assert repository.list_account_rows(db_session)[0].account_identifier is None

    def test_the_anchor_comes_with_its_account(self, db_session):
        account = make_account(db_session)
        set_anchor(db_session, account, "123.45", date(2026, 6, 30))
        [row] = repository.list_account_rows(db_session)
        assert (row.anchor.balance, row.anchor.as_of_date) == (Decimal("123.45"), date(2026, 6, 30))

    def test_every_type_is_listed(self, db_session):
        for kind in AccountType:
            make_account(db_session, name=kind.value, account_type=kind, identifier=kind.value)
        assert {r.account.account_type for r in repository.list_account_rows(db_session)} == set(AccountType)


class TestAnchor:
    def test_the_first_write_creates_and_the_second_replaces_the_one_anchor(self, db_session):
        account = make_account(db_session)
        first = repository.upsert_anchor(db_session, account.id, Decimal("100.00"), date(2026, 1, 31))
        second = repository.upsert_anchor(db_session, account.id, Decimal("-5.50"), date(2026, 2, 28))
        assert second.id == first.id
        assert (second.balance, second.as_of_date) == (Decimal("-5.50"), date(2026, 2, 28))
        assert db_session.query(BalanceAnchor).count() == 1

    def test_get_anchor_is_none_without_one(self, db_session):
        assert repository.get_anchor(db_session, make_account(db_session).id) is None


class TestMergeSupport:
    def test_two_accounts_in_one_statement_are_found(self, db_session):
        a, b, c = (make_account(db_session, name=n, identifier=n) for n in "abc")
        shared = make_statement(db_session)
        make_section(db_session, a, statement=shared)
        make_section(db_session, b, statement=shared)
        make_section(db_session, c)
        assert repository.statement_lists_both(db_session, a.id, b.id) is True
        assert repository.statement_lists_both(db_session, b.id, a.id) is True
        assert repository.statement_lists_both(db_session, a.id, c.id) is False

    def test_sections_and_keys_move_and_the_emptied_account_can_then_be_deleted(self, db_session):
        survivor, absorbed = make_account(db_session, name="S", identifier="1"), make_account(db_session, name="A", identifier="2")
        section = make_section(db_session, absorbed)
        make_tx(db_session, section, date(2026, 1, 2), "5")

        assert repository.repoint_sections(db_session, absorbed.id, survivor.id) == 1
        assert repository.repoint_keys(db_session, absorbed.id, survivor.id) == 1
        db_session.expire_all()
        repository.delete_account(db_session, absorbed.id)

        assert db_session.query(StatementAccount).filter_by(account_id=survivor.id).count() == 1
        assert db_session.query(AccountKey).filter_by(account_id=survivor.id).count() == 2
        assert {r.account.name for r in repository.list_account_rows(db_session)} == {"S"}

    def test_an_account_that_still_has_a_section_cannot_be_deleted(self, db_session):
        account, _ = account_with_history(db_session)
        with pytest.raises(IntegrityError), db_session.begin_nested():
            repository.delete_account(db_session, account.id)

    def test_the_anchor_can_move_to_the_survivor(self, db_session):
        survivor, absorbed = make_account(db_session, name="S", identifier="1"), make_account(db_session, name="A", identifier="2")
        set_anchor(db_session, absorbed, "50.00", date(2026, 5, 1))
        repository.move_anchor(db_session, absorbed.id, survivor.id)
        db_session.expire_all()
        assert repository.get_anchor(db_session, survivor.id).balance == Decimal("50.00")
        assert repository.get_anchor(db_session, absorbed.id) is None

    def test_deleting_an_anchor_leaves_the_account(self, db_session):
        account = make_account(db_session)
        set_anchor(db_session, account, "1.00", date(2026, 1, 1))
        repository.delete_anchor(db_session, account.id)
        assert repository.get_anchor(db_session, account.id) is None and repository.get_account(db_session, account.id)

    def test_locking_returns_exactly_the_named_accounts(self, db_session):
        a, b, _ = (make_account(db_session, name=n, identifier=n) for n in "abc")
        locked = repository.lock_accounts(db_session, [b.id, a.id])
        assert set(locked) == {a.id, b.id}
