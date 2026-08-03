"""add ingestion_run_logs table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-01

Added for the live worker-log-tail view on the Ingestion page: a user found run
progress hard to read without seeing what the worker was actually doing while a run
was in flight. See aidlc-docs/audit.md 2026-08-01 for the full history.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_run_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id"), nullable=False
        ),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("logger_name", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_ingestion_run_logs_run_id_id", "ingestion_run_logs", ["ingestion_run_id", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_run_logs_run_id_id", table_name="ingestion_run_logs")
    op.drop_table("ingestion_run_logs")
