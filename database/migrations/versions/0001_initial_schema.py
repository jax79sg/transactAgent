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

    # The filtering above (_INITIAL_TABLE_NAMES) only solves half of the drift problem:
    # it stops 0001 from creating *tables* that were only introduced by a later
    # migration, but Base.metadata.tables still reflects each of these 8 tables' full,
    # CURRENT column set -- including columns added to an already-initial table by a
    # later migration's own op.add_column(). On every real deployment so far this went
    # unnoticed because the database was created back when 0001 was still accurate and
    # evolved incrementally from there; it only surfaces when migrating a genuinely
    # fresh database from scratch (found via a real Kubernetes deployment attempt,
    # 2026-08-21 -- `alembic upgrade head` against an empty database failed at 0005
    # with "column cancel_requested_at already exists", since create_all() above had
    # already created it as part of the CURRENT ingestion_runs model). Each of the 3
    # columns below is added by its own later migration (0005/0009/0011) -- drop them
    # here so those migrations' own op.add_column() calls remain the single source of
    # truth for how/when each one is actually added, and the full chain is reproducible
    # from empty. (No matching DROP TYPE needed: 0009's embedding_status enum type is
    # created with checkfirst=True, so a type that already exists from create_all()
    # above is a safe no-op there; the other two columns aren't enum-typed at all.)
    op.drop_column("ingestion_runs", "cancel_requested_at")  # actually added by 0005
    op.drop_column("transactions", "embedding_status")  # actually added by 0009
    op.drop_column("transactions", "llm_suggested_category_id")  # actually added by 0011

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
