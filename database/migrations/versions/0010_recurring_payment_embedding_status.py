"""add recurring_payments.embedding_status

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-13

Epic 9 (Local Embedding-Based Semantic Similarity), added retroactively during
Ingestion Worker Service Functional Design after that stage surfaced a real gap:
nothing tracked when a RecurringPayment's name embedding should be computed/stored
for the `recurring_payment_names` vector-store collection (only Transaction had this
field, migration 0009). BR-25: same one-way pending -> completed transition as
Transaction.embedding_status (BR-24), but this field has a second write path -- the
API Service resets it to PENDING on create or on any name-changing update, since a
rename invalidates whatever embedding is already stored.

Reuses the `embeddingstatus` Postgres enum type created by 0009 (create_type=False,
same pattern that migration's own docstring establishes) rather than creating a
second, duplicate enum type for the same two values.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "embeddingstatus"


def upgrade() -> None:
    embedding_status_enum = postgresql.ENUM("pending", "completed", name=_ENUM_NAME, create_type=False)
    op.add_column(
        "recurring_payments",
        sa.Column(
            "embedding_status",
            embedding_status_enum,
            nullable=False,
            server_default="pending",
        ),
    )


def downgrade() -> None:
    op.drop_column("recurring_payments", "embedding_status")
