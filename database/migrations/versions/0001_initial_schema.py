"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-01

"""
from typing import Sequence, Union

from alembic import op

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The original 8 tables this migration creates. Deliberately scoped (not
# Base.metadata.create_all() unfiltered) so that later migrations (e.g. 0002, which
# adds oauth_credentials) can add new tables to models.py without 0001 trying to
# create them too when run against a fresh database — Base.metadata always reflects
# *every* currently-defined model, not just the ones that existed when 0001 was written.
_INITIAL_TABLE_NAMES = frozenset(
    {
        "users",
        "categories",
        "bank_statements",
        "transactions",
        "fx_rate_cache",
        "ingestion_runs",
        "ingestion_run_files",
        "recategorization_jobs",
    }
)


def upgrade() -> None:
    # Creates the initial schema directly from the SQLAlchemy models (single source of
    # truth in transactagent_db/models.py) rather than hand-duplicating every
    # op.create_table() call, to avoid the two definitions drifting apart. Subsequent
    # migrations (0002+) use standard incremental op.* calls as the schema evolves.
    bind = op.get_bind()
    initial_tables = [t for name, t in Base.metadata.tables.items() if name in _INITIAL_TABLE_NAMES]
    Base.metadata.create_all(bind=bind, tables=initial_tables, checkfirst=True)

    # BR-10: at most one ingestion_runs row may have status 'queued' or 'running' at a
    # time. Expressed as a Postgres partial unique index on a constant expression (all
    # qualifying rows index to the same value "true", so a second one collides) — not
    # representable via standard SQLAlchemy Table/Column metadata, so it's added here
    # as raw SQL rather than declared in models.py.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_ingestion_runs_single_active
        ON ingestion_runs ((true))
        WHERE status IN ('queued', 'running')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_ingestion_runs_single_active")
    bind = op.get_bind()
    initial_tables = [t for name, t in Base.metadata.tables.items() if name in _INITIAL_TABLE_NAMES]
    Base.metadata.drop_all(bind=bind, tables=initial_tables, checkfirst=True)
