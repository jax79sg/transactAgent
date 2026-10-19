"""Account Resolver (WR-48..WR-50): resolves each account section of an extracted statement
to an account. Real PostgreSQL; no external calls exist to mock."""

import logging
from decimal import Decimal

import pytest
from sqlalchemy import select
from transactagent_db.models import Account, AccountKey, AccountType

from ingestion_worker.accounts.service import resolve_sections
from ingestion_worker.extraction.schemas import RawExtractedStatement


def _txn(description="TXN", day="2026-01-15"):
    return {
        "transaction_date": day, "description": description, "amount": 10, "direction": "out",
        "printed_converted_amount_sgd": None, "confidence": "high",
    }


def _statement(*sections, bank="OCBC Bank", currency="SGD"):
    statement = RawExtractedStatement.model_validate(
        {"bank_name": bank, "currency": currency, "confidence": "high", "sections": list(sections)}
    )
    for section in statement.sections:  # what extraction does before the resolver runs
        section.currency = section.currency or statement.currency
    return statement


def _section(identifier=None, account_type="deposit", **fields):
    return {"account_identifier": identifier, "account_type": account_type, "transactions": [_txn()], **fields}


class TestCreatingAndLinking:
    def test_a_new_section_creates_an_account_and_its_first_key(self, db_session):
        resolved = resolve_sections(db_session, _statement(_section("501-123-456")))

        assert len(resolved) == 1 and resolved[0].was_created
        account = resolved[0].account
        assert account.name == "OCBC Bank 3456"
        assert (account.bank_name, account.currency, account.account_type) == ("OCBC Bank", "SGD", AccountType.DEPOSIT)
        key = db_session.scalar(select(AccountKey).where(AccountKey.account_id == account.id))
        assert (key.bank_key, key.account_identifier, key.currency) == ("ocbc", "501123456", "SGD")

    def test_a_second_statement_links_to_the_same_account(self, db_session):
        first = resolve_sections(db_session, _statement(_section("501-123-456")))
        second = resolve_sections(db_session, _statement(_section("501 123 456"), bank="OCBC"))  # other name, other spacing

        assert not second[0].was_created
        assert second[0].account.id == first[0].account.id
        assert db_session.query(Account).count() == 1

    def test_two_accounts_at_one_bank_stay_separate(self, db_session):
        a = resolve_sections(db_session, _statement(_section("111")))
        b = resolve_sections(db_session, _statement(_section("222")))

        assert a[0].account.id != b[0].account.id

    def test_the_same_identifier_in_two_currencies_is_two_accounts(self, db_session):
        sgd = resolve_sections(db_session, _statement(_section("111")))
        usd = resolve_sections(db_session, _statement(_section("111", currency="USD")))

        assert sgd[0].account.id != usd[0].account.id
        assert {sgd[0].account.currency, usd[0].account.currency} == {"SGD", "USD"}

    def test_no_identifier_falls_back_to_a_bank_only_account_and_reuses_it(self, db_session):
        first = resolve_sections(db_session, _statement(_section(None)))
        second = resolve_sections(db_session, _statement(_section(None), bank="OCBC"))

        assert first[0].account.name == "OCBC Bank"
        assert second[0].account.id == first[0].account.id
        key = db_session.scalar(select(AccountKey).where(AccountKey.account_id == first[0].account.id))
        assert key.account_identifier is None

    def test_several_sections_resolve_independently(self, db_session):
        resolved = resolve_sections(
            db_session,
            _statement(_section("111", "deposit"), _section("4111-1111", "credit_card")),
        )

        assert [r.account.account_type for r in resolved] == [AccountType.DEPOSIT, AccountType.CREDIT_CARD]
        assert resolved[0].account.id != resolved[1].account.id

    def test_a_merged_key_is_honored_on_later_statements(self, db_session):
        """Merge (BR-35) re-points an absorbed account's keys to the survivor; the resolver
        must then resolve that old name to the survivor instead of recreating the account."""
        survivor = resolve_sections(db_session, _statement(_section("111"), bank="DBS"))[0].account
        absorbed = resolve_sections(db_session, _statement(_section("111"), bank="POSB"))[0].account
        assert absorbed.id != survivor.id
        for key in db_session.scalars(select(AccountKey).where(AccountKey.account_id == absorbed.id)):
            key.account_id = survivor.id
        db_session.flush()
        db_session.delete(absorbed)
        db_session.flush()

        again = resolve_sections(db_session, _statement(_section("111"), bank="POSB"))

        assert not again[0].was_created
        assert again[0].account.id == survivor.id


class TestCollapsingSections:
    def test_two_sections_for_the_same_account_become_one(self, db_session):
        resolved = resolve_sections(
            db_session,
            _statement(
                {**_section("111"), "transactions": [_txn("A")]},
                {**_section("1-1-1"), "transactions": [_txn("B")]},
            ),
        )

        assert len(resolved) == 1
        assert [t.description for t in resolved[0].section.transactions] == ["A", "B"]
        assert db_session.query(Account).count() == 1

    def test_the_first_non_null_closing_balance_wins(self, db_session):
        resolved = resolve_sections(
            db_session,
            _statement(
                _section("111"),
                _section("111", closing_balance="75.00", closing_balance_date="2026-01-31"),
            ),
        )

        assert resolved[0].section.closing_balance == Decimal("75.00")

    def test_a_conflicting_balance_keeps_the_first_and_warns_never_errors(self, db_session, caplog):
        with caplog.at_level(logging.WARNING):
            resolved = resolve_sections(
                db_session,
                _statement(
                    _section("111", closing_balance="10.00", closing_balance_date="2026-01-31"),
                    _section("111", closing_balance="99.00", closing_balance_date="2026-01-31"),
                ),
            )

        assert resolved[0].section.closing_balance == Decimal("10.00")
        assert "different closing balances" in caplog.text


class TestTypeRules:
    def test_unknown_is_upgraded_to_a_known_type(self, db_session):
        account = resolve_sections(db_session, _statement(_section("111", "unknown")))[0].account
        assert account.account_type == AccountType.UNKNOWN

        again = resolve_sections(db_session, _statement(_section("111", "deposit")))[0].account

        assert again.id == account.id and again.account_type == AccountType.DEPOSIT

    def test_a_known_type_is_not_downgraded_to_unknown(self, db_session):
        resolve_sections(db_session, _statement(_section("111", "deposit")))
        again = resolve_sections(db_session, _statement(_section("111", "unknown")))[0].account

        assert again.account_type == AccountType.DEPOSIT

    def test_a_disagreeing_known_type_keeps_the_existing_one_and_warns(self, db_session, caplog):
        resolve_sections(db_session, _statement(_section("111", "deposit")))
        with caplog.at_level(logging.WARNING):
            again = resolve_sections(db_session, _statement(_section("111", "credit_card")))[0].account

        assert again.account_type == AccountType.DEPOSIT
        assert "keeping deposit" in caplog.text

    def test_a_user_set_type_is_never_changed(self, db_session):
        account = resolve_sections(db_session, _statement(_section("111", "unknown")))[0].account
        account.account_type = AccountType.CREDIT_CARD
        account.type_user_set = True
        db_session.flush()

        again = resolve_sections(db_session, _statement(_section("111", "deposit")))[0].account

        assert again.account_type == AccountType.CREDIT_CARD

    @pytest.mark.parametrize("extracted", ["deposit", "credit_card", "unknown"])
    def test_a_new_account_takes_the_extracted_type(self, db_session, extracted):
        account = resolve_sections(db_session, _statement(_section(extracted, extracted)))[0].account

        assert account.account_type == AccountType(extracted)

    def test_resolution_writes_run_log_lines(self, db_session, caplog):
        with caplog.at_level(logging.INFO):
            resolve_sections(db_session, _statement(_section("111")))
            resolve_sections(db_session, _statement(_section("111")))

        assert "Created account" in caplog.text
        assert "existing account" in caplog.text
