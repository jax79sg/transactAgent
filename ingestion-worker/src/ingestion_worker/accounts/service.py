"""Account Resolver Component (WR-48..WR-50, Epic 13): decides which account each
account section of an extracted statement belongs to, creating the account if it is new.

Called by the orchestrator once per statement, after extraction succeeded and before the
statement is recorded. Runs inside the file's database transaction, so a file that fails
afterwards leaves no orphan account (see orchestrator/pipeline.py). Makes no external
calls.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session
from transactagent_db.models import Account, AccountType

from ingestion_worker.accounts import repository
from ingestion_worker.accounts.normalize import (
    bank_key,
    default_account_name,
    display_bank_name,
    normalize_identifier,
)
from ingestion_worker.extraction.schemas import (
    ExtractedAccountType,
    RawAccountSection,
    RawExtractedStatement,
)

logger = logging.getLogger(__name__)


@dataclass
class ResolvedSection:
    section: RawAccountSection
    account: Account
    was_created: bool


def _to_account_type(extracted: ExtractedAccountType) -> AccountType:
    return AccountType(extracted.value)


def _apply_type_rules(account: Account, extracted: ExtractedAccountType) -> None:
    """WR-50. A user-corrected type is never changed (BR-34). Otherwise `unknown` may be
    upgraded to a known type; if two KNOWN types disagree the existing one is kept and a
    warning is logged, so one misread month can never flip an account in or out of
    balances."""
    if account.type_user_set:
        return
    incoming = _to_account_type(extracted)
    if incoming == AccountType.UNKNOWN:
        return
    if account.account_type == AccountType.UNKNOWN:
        account.account_type = incoming
        logger.info("Account '%s': type set to %s from this statement", account.name, incoming.value)
    elif account.account_type != incoming:
        logger.warning(
            "Account '%s': this statement reads as a %s account but it is recorded as %s; keeping %s",
            account.name, incoming.value, account.account_type.value, account.account_type.value,
        )


def _collapse(existing: ResolvedSection, extra: RawAccountSection, account_name: str) -> None:
    """BR-37: two sections of one PDF that resolve to the same account are the same
    account. Combine their transactions; keep the first non-null closing balance and warn
    (never error) if a later one conflicts."""
    merged = existing.section
    balance, balance_date = merged.closing_balance, merged.closing_balance_date
    if extra.closing_balance is not None:
        if balance is None:
            balance, balance_date = extra.closing_balance, extra.closing_balance_date
        elif (extra.closing_balance, extra.closing_balance_date) != (balance, balance_date):
            logger.warning(
                "Account '%s' appears twice in this statement with different closing balances; keeping the first",
                account_name,
            )
    existing.section = merged.model_copy(
        update={
            "transactions": [*merged.transactions, *extra.transactions],
            "closing_balance": balance,
            "closing_balance_date": balance_date,
        }
    )


def resolve_sections(db: Session, statement: RawExtractedStatement) -> list[ResolvedSection]:
    key = bank_key(statement.bank_name)
    display = display_bank_name(statement.bank_name)
    by_account: dict = {}

    for section in statement.sections:
        identifier = normalize_identifier(section.account_identifier)
        account = repository.find_account_by_key(db, key, identifier, section.currency)
        was_created = False
        if account is None:
            account = repository.create_account_with_key(
                db,
                name=default_account_name(display, identifier),
                bank_name=display,
                account_type=_to_account_type(section.account_type),
                currency=section.currency,
                bank_key=key,
                account_identifier=identifier,
            )
            was_created = True
            logger.info("Created account '%s' (%s, %s)", account.name, account.account_type.value, account.currency)
        else:
            _apply_type_rules(account, section.account_type)
            logger.info("Linked a section of this statement to existing account '%s'", account.name)

        if account.id in by_account:
            _collapse(by_account[account.id], section, account.name)
        else:
            by_account[account.id] = ResolvedSection(section=section, account=account, was_created=was_created)

    return list(by_account.values())
