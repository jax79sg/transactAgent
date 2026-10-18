"""The CI-only e2e seed (Epic 13 added accounts to it): it creates the login, the fixture transactions and three
accounts, attaches the transactions to one of them, and is safe to run twice, including over a database seeded before
the accounts existed."""

from sqlalchemy import func, select

from transactagent_db.models import (
    Account,
    AccountKey,
    AccountType,
    BalanceAnchor,
    BankStatement,
    StatementAccount,
    Transaction,
    User,
)
from transactagent_db.seed_categories import seed_categories
from transactagent_db.seed_e2e_fixtures import E2E_USERNAME, seed_e2e_fixtures


def seeded(db_session):
    seed_categories(db_session)
    seed_e2e_fixtures(db_session, hashed_password="not-a-real-hash")
    db_session.flush()
    return db_session


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def account_named(db_session, name: str) -> Account:
    return db_session.scalar(select(Account).where(Account.name == name))


class TestSeedE2eFixtures:
    def test_it_creates_the_login_and_the_five_transactions_as_before(self, db_session):
        seeded(db_session)
        assert db_session.scalar(select(User).where(User.username == E2E_USERNAME)) is not None
        assert count(db_session, Transaction) == 5

    def test_it_creates_two_deposit_accounts_and_a_credit_card_with_no_balance_entered(self, db_session):
        seeded(db_session)
        types = {a.name: a.account_type for a in db_session.scalars(select(Account))}
        assert types == {
            "E2E Savings": AccountType.DEPOSIT,
            "E2E Current": AccountType.DEPOSIT,
            "E2E Card": AccountType.CREDIT_CARD,
        }
        assert count(db_session, BalanceAnchor) == 0  # so the Balances tab shows "Anchor required"
        assert count(db_session, AccountKey) == 3

    def test_every_fixture_transaction_belongs_to_the_savings_account(self, db_session):
        seeded(db_session)
        savings = account_named(db_session, "E2E Savings")
        section = db_session.scalar(select(StatementAccount).where(StatementAccount.account_id == savings.id))
        assert section is not None
        statement = db_session.scalar(select(BankStatement))
        assert section.bank_statement_id == statement.id
        linked = db_session.scalars(select(Transaction.statement_account_id)).all()
        assert linked == [section.id] * 5

    def test_running_it_twice_changes_nothing(self, db_session):
        seeded(db_session)
        before = [count(db_session, m) for m in (User, Account, AccountKey, StatementAccount, Transaction, BankStatement)]
        seed_e2e_fixtures(db_session, hashed_password="not-a-real-hash")
        db_session.flush()
        after = [count(db_session, m) for m in (User, Account, AccountKey, StatementAccount, Transaction, BankStatement)]
        assert after == before == [1, 3, 3, 1, 5, 1]

    def test_it_attaches_transactions_seeded_before_accounts_existed(self, db_session):
        seeded(db_session)
        # Put the database back as the earlier version of the seed left it: transactions with no account.
        for transaction in db_session.scalars(select(Transaction)):
            transaction.statement_account_id = None
        db_session.flush()

        seed_e2e_fixtures(db_session, hashed_password="not-a-real-hash")
        db_session.flush()

        section_id = db_session.scalar(select(StatementAccount.id))
        assert db_session.scalars(select(Transaction.statement_account_id)).all() == [section_id] * 5
