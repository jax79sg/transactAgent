"""Seed script for nightly E2E (Playwright) fixtures -- CI only, never run against a
real deployment. Creates a login and a small set of known transactions directly via
SQLAlchemy, deliberately bypassing the real ingestion pipeline (Drive/Gemini/omlx),
which needs live external services this project's CI has no access to and no
business calling nightly. Categories come from the existing seed_categories()
(UNSURE + the whitelist) -- transaction fixtures below assume that's already run.

Idempotent by username/pdf_content_hash: safe to re-run against a database that
already has these fixtures (each nightly run gets a clean docker-compose volume
anyway, but idempotency costs nothing and avoids surprises if that ever changes).
"""

import hashlib
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from transactagent_db.models import BankStatement, Category, CategorySource, Transaction, User

E2E_USERNAME = "e2e_test"
E2E_PASSWORD = "E2e-Test-Password-2026"  # noqa: S105 -- CI-only fixture, not a real credential

_STATEMENT_DRIVE_FILE_ID = "e2e-fixture-statement"
_STATEMENT_CONTENT_HASH = hashlib.sha256(b"e2e-fixture-statement").hexdigest()

# (days_ago, description, category_name, out_flow, in_flow)
_FIXTURE_TRANSACTIONS: list[tuple[int, str, str, Decimal | None, Decimal | None]] = [
    (1, "NTUC FAIRPRICE", "Groceries", Decimal("45.20"), None),
    (2, "GRAB TRANSPORT", "Transport", Decimal("12.50"), None),
    (3, "SALARY", "Income", None, Decimal("5000.00")),
    (5, "NETFLIX SUBSCRIPTION", "Entertainment", Decimal("20.98"), None),
    (7, "UNKNOWN MERCHANT XYZ", "UNSURE", Decimal("33.33"), None),
]


def seed_e2e_fixtures(session: Session, *, hashed_password: str) -> None:
    """`hashed_password` must come from api_service.auth.security.hash_password --
    intentionally not imported here, since database/ has no dependency on
    api-service/ (kept the same direction as every other package boundary in this
    repo)."""
    if session.scalar(select(User).where(User.username == E2E_USERNAME)) is None:
        session.add(User(username=E2E_USERNAME, password_hash=hashed_password))

    statement = session.scalar(
        select(BankStatement).where(BankStatement.pdf_content_hash == _STATEMENT_CONTENT_HASH)
    )
    if statement is None:
        statement = BankStatement(
            drive_file_id=_STATEMENT_DRIVE_FILE_ID,
            pdf_content_hash=_STATEMENT_CONTENT_HASH,
            bank_name="E2E Fixture Bank",
        )
        session.add(statement)
        session.flush()  # need statement.id for the transactions below

    existing_descriptions = set(
        session.scalars(select(Transaction.description).where(Transaction.bank_statement_id == statement.id))
    )
    categories_by_name = {c.name: c for c in session.scalars(select(Category))}

    for days_ago, description, category_name, out_flow, in_flow in _FIXTURE_TRANSACTIONS:
        if description in existing_descriptions:
            continue
        category = categories_by_name[category_name]
        amount = out_flow if out_flow is not None else in_flow
        session.add(
            Transaction(
                bank_statement_id=statement.id,
                transaction_date=date.today() - timedelta(days=days_ago),
                description=description,
                out_flow=out_flow,
                in_flow=in_flow,
                currency="SGD",
                bank_name="E2E Fixture Bank",
                category_id=category.id,
                category_source=CategorySource.UNSURE if category_name == "UNSURE" else CategorySource.MANUAL,
                converted_amount_sgd=amount,
                conversion_is_approximate=False,
                conversion_unavailable=False,
            )
        )

    session.flush()


if __name__ == "__main__":
    import sys

    from sqlalchemy import create_engine

    from transactagent_db.migrate import build_database_url

    if len(sys.argv) != 2:
        print("Usage: python -m transactagent_db.seed_e2e_fixtures <bcrypt-hashed-password>", file=sys.stderr)
        print(
            "(Compute it with: python -c \"from api_service.auth.security import hash_password; "
            f'print(hash_password({E2E_PASSWORD!r}))"',
            file=sys.stderr,
        )
        sys.exit(1)

    engine = create_engine(build_database_url())
    with Session(engine) as session:
        seed_e2e_fixtures(session, hashed_password=sys.argv[1])
        session.commit()
        print(f"E2E fixtures ready: user {E2E_USERNAME!r}, {len(_FIXTURE_TRANSACTIONS)} transaction(s).")
