"""Account Management business rules (AR-51 to AR-54, AR-65) against a real PostgreSQL."""

import threading
from datetime import date
from decimal import Decimal

import pytest
from account_helpers import (
    account_with_history,
    make_account,
    make_section,
    make_statement,
    make_tx,
    set_anchor,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from transactagent_db.models import (
    Account,
    AccountKey,
    AccountType,
    BalanceAnchor,
    StatementAccount,
)

from api_service.accounts import repository, service
from api_service.accounts.schemas import (
    AccountUpdateRequest,
    AnchorRequest,
    MergeRequest,
)
from api_service.errors import (
    AccountNotFoundError,
    AnchorDateInFutureError,
    AnchorDateOutOfRangeError,
    InvalidAccountNameError,
    InvalidAccountTypeError,
    InvalidAnchorValueError,
    MergeAnchorChoiceInvalidError,
    MergeAnchorChoiceRequiredError,
    MergeAppearTogetherError,
    MergeCurrencyMismatchError,
    MergeSameAccountError,
    NotADepositAccountError,
    NothingToChangeError,
)

TODAY = date(2026, 10, 18)


class TestList:
    def test_deposit_then_credit_card_then_unknown_each_by_name_ignoring_case(self, db_session):
        make_account(db_session, name="zeta", account_type=AccountType.UNKNOWN, identifier="1")
        make_account(db_session, name="Card", account_type=AccountType.CREDIT_CARD, identifier="2")
        make_account(db_session, name="beta", identifier="3")
        make_account(db_session, name="Alpha", identifier="4")
        assert [a.name for a in service.list_accounts(db_session).items] == ["Alpha", "beta", "Card", "zeta"]

    def test_can_have_anchor_is_true_only_for_deposit_accounts_and_the_fields_are_filled(self, db_session):
        _account, _ = account_with_history(db_session, "Main", flows=[(date(2026, 1, 5), "10")], anchor=("5.00", date(2026, 1, 1)), identifier="9876")
        make_account(db_session, name="Card", account_type=AccountType.CREDIT_CARD, identifier="2")
        items = {a.name: a for a in service.list_accounts(db_session).items}
        assert items["Main"].can_have_anchor and not items["Card"].can_have_anchor
        assert (items["Main"].account_identifier, items["Main"].transaction_count, items["Main"].statement_count) == ("9876", 1, 1)
        assert items["Main"].anchor.balance == Decimal("5.00") and items["Main"].type == "deposit"


class TestUpdate:
    def test_a_rename_is_trimmed_and_does_not_set_the_type_flag(self, db_session):
        account = make_account(db_session)
        result = service.update_account(db_session, account.id, AccountUpdateRequest(name="  My savings  "))
        assert result.name == "My savings" and result.type_set_by_user is False

    @pytest.mark.parametrize("name", ["", "   ", "x" * 256])
    def test_an_empty_or_overlong_name_is_refused(self, db_session, name):
        account = make_account(db_session)
        with pytest.raises(InvalidAccountNameError):
            service.update_account(db_session, account.id, AccountUpdateRequest(name=name))

    def test_names_need_not_be_unique(self, db_session):
        a, b = make_account(db_session, name="One", identifier="1"), make_account(db_session, name="Two", identifier="2")
        service.update_account(db_session, a.id, AccountUpdateRequest(name="Same"))
        service.update_account(db_session, b.id, AccountUpdateRequest(name="Same"))
        assert [x.name for x in service.list_accounts(db_session).items] == ["Same", "Same"]

    def test_a_type_change_sets_the_user_flag_and_keeps_the_anchor(self, db_session):
        account = make_account(db_session)
        set_anchor(db_session, account, "100.00", date(2026, 1, 1))
        as_card = service.update_account(db_session, account.id, AccountUpdateRequest(type="credit_card"))
        assert (as_card.type, as_card.type_set_by_user, as_card.can_have_anchor) == ("credit_card", True, False)
        assert as_card.anchor.balance == Decimal("100.00")  # kept, not deleted
        back = service.update_account(db_session, account.id, AccountUpdateRequest(type="deposit"))
        assert back.can_have_anchor and back.anchor.balance == Decimal("100.00")

    def test_an_unknown_type_value_is_refused(self, db_session):
        account = make_account(db_session)
        with pytest.raises(InvalidAccountTypeError):
            service.update_account(db_session, account.id, AccountUpdateRequest(type="savings"))

    def test_naming_neither_field_or_changing_nothing_is_refused(self, db_session):
        account = make_account(db_session, name="Same")
        with pytest.raises(NothingToChangeError):
            service.update_account(db_session, account.id, AccountUpdateRequest())
        with pytest.raises(NothingToChangeError):
            service.update_account(db_session, account.id, AccountUpdateRequest(name="Same", type="deposit"))

    def test_an_unknown_account_is_not_found(self, db_session):
        import uuid

        with pytest.raises(AccountNotFoundError):
            service.update_account(db_session, uuid.uuid4(), AccountUpdateRequest(name="x"))


class TestSetAnchor:
    def request(self, balance="100.00", day=date(2026, 6, 30)):
        return AnchorRequest(balance=balance, as_of_date=day)

    def test_the_first_anchor_has_no_previous_and_a_replacement_returns_the_one_it_replaced(self, db_session):
        account = make_account(db_session)
        first = service.set_anchor(db_session, account.id, self.request("100.00"), TODAY)
        second = service.set_anchor(db_session, account.id, self.request("250.50", date(2026, 7, 31)), TODAY)
        assert first.previous is None and first.anchor.balance == Decimal("100.00")
        assert second.previous.balance == Decimal("100.00") and second.previous.as_of_date == date(2026, 6, 30)
        assert (second.anchor.balance, second.anchor.as_of_date) == (Decimal("250.50"), date(2026, 7, 31))
        assert db_session.scalar(select(func.count(BalanceAnchor.id))) == 1

    @pytest.mark.parametrize("value", ["-12.34", "0", 500, 12.5, "7", " 3.10 "])
    def test_negative_zero_whole_and_numeric_values_are_accepted(self, db_session, value):
        account = make_account(db_session)
        assert service.set_anchor(db_session, account.id, self.request(value), TODAY).anchor.balance == Decimal(str(value).strip())

    @pytest.mark.parametrize("value", ["abc", "", "1.234", "NaN", "Infinity", "-Infinity", "1e16", "10000000000000000.00", 0.001])
    def test_a_value_that_is_not_a_two_place_decimal_in_range_is_refused_and_nothing_is_saved(self, db_session, value):
        account = make_account(db_session)
        with pytest.raises(InvalidAnchorValueError):
            service.set_anchor(db_session, account.id, self.request(value), TODAY)
        assert repository.get_anchor(db_session, account.id) is None

    def test_the_date_may_be_today_but_not_after_and_not_before_2000(self, db_session):
        account = make_account(db_session)
        assert service.set_anchor(db_session, account.id, self.request(day=TODAY), TODAY).anchor.as_of_date == TODAY
        with pytest.raises(AnchorDateInFutureError):
            service.set_anchor(db_session, account.id, self.request(day=date(2026, 10, 19)), TODAY)
        with pytest.raises(AnchorDateOutOfRangeError):
            service.set_anchor(db_session, account.id, self.request(day=date(1999, 12, 31)), TODAY)

    def test_a_credit_card_or_unknown_account_cannot_have_an_anchor(self, db_session):
        for kind in (AccountType.CREDIT_CARD, AccountType.UNKNOWN):
            account = make_account(db_session, name=kind.value, account_type=kind, identifier=kind.value)
            with pytest.raises(NotADepositAccountError):
                service.set_anchor(db_session, account.id, self.request(), TODAY)

    def test_the_checks_run_in_the_designed_order(self, db_session):
        card = make_account(db_session, account_type=AccountType.CREDIT_CARD)
        with pytest.raises(NotADepositAccountError):  # the type is checked before the value
            service.set_anchor(db_session, card.id, self.request("abc"), TODAY)
        deposit = make_account(db_session, name="d", identifier="d")
        with pytest.raises(InvalidAnchorValueError):  # the value before the date
            service.set_anchor(db_session, deposit.id, self.request("abc", date(2099, 1, 1)), TODAY)

    def test_an_unknown_account_is_not_found(self, db_session):
        import uuid

        with pytest.raises(AccountNotFoundError):
            service.set_anchor(db_session, uuid.uuid4(), self.request(), TODAY)


class TestMerge:
    def pair(self, db_session, **kwargs):
        survivor = make_account(db_session, name="Survivor", identifier="1", **kwargs)
        absorbed = make_account(db_session, name="Absorbed", identifier="2", **kwargs)
        return survivor, absorbed

    def merge(self, db_session, survivor, absorbed, keep=None):
        return service.merge_accounts(db_session, survivor.id, MergeRequest(absorbed_account_id=absorbed.id, keep_anchor_from=keep))

    def test_everything_moves_to_the_survivor_and_the_absorbed_account_is_gone(self, db_session):
        survivor, absorbed = self.pair(db_session)
        section = make_section(db_session, absorbed, closing="10.00", closing_date=date(2026, 1, 31))
        make_tx(db_session, section, date(2026, 1, 5), "5")
        make_section(db_session, survivor)

        result = self.merge(db_session, survivor, absorbed)

        assert result.id == survivor.id and result.name == "Survivor"
        assert (result.statement_count, result.transaction_count, result.closing_balance_count) == (2, 1, 1)
        assert db_session.scalar(select(func.count(Account.id))) == 1
        assert db_session.scalar(select(func.count(AccountKey.id)).where(AccountKey.account_id == survivor.id)) == 2

    def test_a_future_statement_that_used_to_resolve_to_the_absorbed_account_now_resolves_to_the_survivor(self, db_session):
        survivor, absorbed = self.pair(db_session)
        absorbed_key = db_session.scalar(select(AccountKey).where(AccountKey.account_id == absorbed.id))
        self.merge(db_session, survivor, absorbed)
        db_session.refresh(absorbed_key)
        assert absorbed_key.account_id == survivor.id

    def test_different_currencies_are_refused_and_nothing_changes(self, db_session):
        a = make_account(db_session, name="a", identifier="1", currency="SGD")
        b = make_account(db_session, name="b", identifier="2", currency="USD")
        make_section(db_session, b)
        with pytest.raises(MergeCurrencyMismatchError):
            self.merge(db_session, a, b)
        assert db_session.scalar(select(func.count(Account.id))) == 2 and db_session.scalar(select(func.count(StatementAccount.id))) == 1

    def test_two_accounts_listed_in_one_statement_cannot_be_merged(self, db_session):
        a, b = self.pair(db_session)
        shared = make_statement(db_session)
        make_section(db_session, a, statement=shared)
        make_section(db_session, b, statement=shared)
        with pytest.raises(MergeAppearTogetherError):
            self.merge(db_session, a, b)

    def test_merging_an_account_into_itself_or_a_missing_one_is_refused(self, db_session):
        import uuid

        a = make_account(db_session)
        with pytest.raises(MergeSameAccountError):
            self.merge(db_session, a, a)
        with pytest.raises(AccountNotFoundError):
            service.merge_accounts(db_session, a.id, MergeRequest(absorbed_account_id=uuid.uuid4()))
        with pytest.raises(AccountNotFoundError):
            service.merge_accounts(db_session, uuid.uuid4(), MergeRequest(absorbed_account_id=a.id))

    def test_both_anchors_need_a_choice_and_the_choice_decides_which_survives(self, db_session):
        survivor, absorbed = self.pair(db_session)
        set_anchor(db_session, survivor, "100.00", date(2026, 1, 1))
        set_anchor(db_session, absorbed, "200.00", date(2026, 2, 1))
        with pytest.raises(MergeAnchorChoiceRequiredError):
            self.merge(db_session, survivor, absorbed)
        import uuid

        with pytest.raises(MergeAnchorChoiceInvalidError):
            self.merge(db_session, survivor, absorbed, keep=uuid.uuid4())
        result = self.merge(db_session, survivor, absorbed, keep=absorbed.id)
        assert (result.anchor.balance, result.anchor.as_of_date) == (Decimal("200.00"), date(2026, 2, 1))
        assert db_session.scalar(select(func.count(BalanceAnchor.id))) == 1

    def test_keeping_the_survivors_own_anchor_drops_the_absorbed_ones(self, db_session):
        survivor, absorbed = self.pair(db_session)
        set_anchor(db_session, survivor, "100.00", date(2026, 1, 1))
        set_anchor(db_session, absorbed, "200.00", date(2026, 2, 1))
        assert self.merge(db_session, survivor, absorbed, keep=survivor.id).anchor.balance == Decimal("100.00")

    def test_a_single_anchor_is_kept_whichever_account_has_it_and_a_wrong_choice_is_refused(self, db_session):
        survivor, absorbed = self.pair(db_session)
        set_anchor(db_session, absorbed, "50.00", date(2026, 3, 1))
        with pytest.raises(MergeAnchorChoiceInvalidError):
            self.merge(db_session, survivor, absorbed, keep=survivor.id)  # names the account that has none
        assert self.merge(db_session, survivor, absorbed).anchor.balance == Decimal("50.00")

    def test_naming_an_anchor_to_keep_when_neither_has_one_is_refused(self, db_session):
        survivor, absorbed = self.pair(db_session)
        with pytest.raises(MergeAnchorChoiceInvalidError):
            self.merge(db_session, survivor, absorbed, keep=survivor.id)

    def test_the_survivor_keeps_its_type_unless_only_the_absorbed_ones_was_set_by_the_user(self, db_session):
        survivor, absorbed = self.pair(db_session, account_type=AccountType.UNKNOWN)
        absorbed.account_type, absorbed.type_user_set = AccountType.DEPOSIT, True
        db_session.flush()
        result = self.merge(db_session, survivor, absorbed)
        assert (result.type, result.type_set_by_user) == ("deposit", True)

    def test_a_type_the_survivors_user_chose_is_not_overwritten(self, db_session):
        survivor, absorbed = self.pair(db_session)
        survivor.account_type, survivor.type_user_set = AccountType.CREDIT_CARD, True
        absorbed.account_type, absorbed.type_user_set = AccountType.DEPOSIT, True
        db_session.flush()
        assert self.merge(db_session, survivor, absorbed).type == "credit_card"

    def test_a_merge_that_fails_halfway_changes_nothing(self, db_session, monkeypatch):
        survivor, absorbed = self.pair(db_session)
        section = make_section(db_session, absorbed)
        set_anchor(db_session, absorbed, "9.00", date(2026, 1, 1))

        def boom(*args, **kwargs):
            raise RuntimeError("the database went away")

        monkeypatch.setattr(repository, "delete_account", boom)
        with pytest.raises(RuntimeError), db_session.begin_nested():
            self.merge(db_session, survivor, absorbed)
        monkeypatch.undo()

        db_session.expire_all()
        assert db_session.get(StatementAccount, section.id).account_id == absorbed.id
        assert db_session.scalar(select(func.count(Account.id))) == 2
        assert repository.get_anchor(db_session, absorbed.id).balance == Decimal("9.00")


class TestMergeRace:
    """Two merges of the same accounts at once: the second waits for the first's lock, then finds the absorbed account
    gone, and is refused rather than corrupting anything (AR-65). Uses its own committed data on separate connections,
    and removes it afterwards."""

    def test_the_second_of_two_concurrent_merges_is_refused(self, engine):
        setup = Session(engine)
        survivor = make_account(setup, name="RaceSurvivor", identifier="race-1")
        absorbed = make_account(setup, name="RaceAbsorbed", identifier="race-2")
        survivor_id, absorbed_id = survivor.id, absorbed.id
        setup.commit()
        setup.close()

        outcome: dict[str, object] = {}
        first_has_locked = threading.Event()
        let_first_finish = threading.Event()

        def first():
            db = Session(engine)
            try:
                repository.lock_accounts(db, [survivor_id, absorbed_id])
                first_has_locked.set()
                let_first_finish.wait(10)
                outcome["first"] = service.merge_accounts(db, survivor_id, MergeRequest(absorbed_account_id=absorbed_id))
                db.commit()
            finally:
                db.close()

        def second():
            first_has_locked.wait(10)
            db = Session(engine)
            try:
                service.merge_accounts(db, survivor_id, MergeRequest(absorbed_account_id=absorbed_id))
                db.commit()
                outcome["second"] = "merged"
            except Exception as exc:  # noqa: BLE001 -- the thread reports whatever happened; the main thread asserts on it
                outcome["second"] = exc
                db.rollback()
            finally:
                db.close()

        t1, t2 = threading.Thread(target=first), threading.Thread(target=second)
        try:
            t1.start()
            first_has_locked.wait(10)
            t2.start()
            t2.join(0.5)  # the second is blocked on the first's row locks
            assert t2.is_alive()
            let_first_finish.set()
            t1.join(15)
            t2.join(15)
            assert outcome["first"].id == survivor_id
            assert isinstance(outcome["second"], AccountNotFoundError)
        finally:
            let_first_finish.set()
            cleanup = Session(engine)
            cleanup.query(AccountKey).filter(AccountKey.account_id.in_([survivor_id, absorbed_id])).delete()
            cleanup.query(Account).filter(Account.id.in_([survivor_id, absorbed_id])).delete()
            cleanup.commit()
            cleanup.close()
