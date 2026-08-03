"""Idempotent seed script for the category whitelist (requirements.md Section 5).

Safe to run repeatedly: existing categories (matched by name) are left untouched,
missing ones are inserted. UNSURE is always inserted as the reserved fallback (BR-5).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from transactagent_db.models import Category

USER_SUPPLIED_CATEGORIES: list[str] = [
    "Baby",
    "Bills",
    "Car",
    "Cash",
    "Clothing",
    "Course",
    "Dining",
    "Entertainment",
    "Gift",
    "Groceries",
    "Household",
    "Income",
    "Insurance",
    "Interest",
    "Learning",
    "Loans",
    "Maid",
    "Medical",
    "Mother",
    "Online Shopping",
    "Pets",
    "Tax",
    "Transport",
    "Bank charges",
    "Hair",
    "Ling Tuition",
    "Gambling",
    "Claims",
    "Others",
    "Amber Park",
    "Preschool",
    "Gray Lane",
    "Petrol",
    "Parking",
    "Conservancy",
    "Car Loan",
    "Home Loan",
    "Mogi",
    "Ling allowance",
    "Wife",
    "Work",
    "Fraud",
    "RovingVets",
    "Electronics",
    "One Time",
]

RESERVED_CATEGORY_NAME = "UNSURE"


def seed_categories(session: Session) -> int:
    """Insert any missing whitelist categories. Returns the count of newly-inserted rows."""
    existing_names = set(session.scalars(select(Category.name)))
    inserted = 0

    for name in USER_SUPPLIED_CATEGORIES:
        if name not in existing_names:
            session.add(Category(name=name, active=True, is_reserved=False))
            inserted += 1

    if RESERVED_CATEGORY_NAME not in existing_names:
        session.add(Category(name=RESERVED_CATEGORY_NAME, active=True, is_reserved=True))
        inserted += 1

    session.flush()
    return inserted


if __name__ == "__main__":
    import os

    from sqlalchemy import create_engine

    from transactagent_db.migrate import build_database_url

    engine = create_engine(build_database_url())
    with Session(engine) as session:
        count = seed_categories(session)
        session.commit()
        print(f"Seeded {count} new categories ({len(USER_SUPPLIED_CATEGORIES) + 1} total in whitelist).")
