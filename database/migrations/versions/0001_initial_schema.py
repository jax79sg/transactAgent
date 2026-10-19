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
    # `accounts` and `statement_accounts` are created here only so that transactions'
    # CURRENT definition (it has a composite foreign key to statement_accounts, which in
    # turn references accounts -- both added by 0019) can be created at all on a fresh
    # database. Both are dropped again below, so 0019 remains the single source of truth
    # for creating them. See the comment below the create_all call for the same
    # reasoning applied to the columns.
    # `duplicate_comparisons` is the Epic 14 (0020) equivalent: ingestion_run_files'
    # current definition has a foreign key to it. Same treatment, below.
    temporarily_created = [
        Base.metadata.tables["accounts"],
        Base.metadata.tables["statement_accounts"],
        Base.metadata.tables["duplicate_comparisons"],
    ]
    Base.metadata.create_all(bind=bind, tables=[*initial_tables, *temporarily_created], checkfirst=True)

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

    # Same fix for Epic 13 (found 2026-10-02 by running `alembic upgrade head` against a
    # fresh database after adding the feature -- the unit tests, which build their schema
    # straight from the models, could not catch it): transactions' current definition also
    # carries a column added by 0019, `statement_account_id`, which is part of a composite
    # foreign key to the `statement_accounts` table, which does not exist yet at this point
    # in the chain. `accounts` and `statement_accounts` were created above only so that
    # CREATE TABLE could succeed; drop the column first (this also removes the composite
    # foreign key and the column's index, since they depend on it), then the two temporary
    # tables and the enum type, so 0019 remains the single source of truth for all of it.
    # (Revised 2026-10-03 for the several-accounts-per-PDF design: bank_statements itself
    # gained nothing, so nothing is dropped from it.)
    op.drop_column("transactions", "statement_account_id")  # actually added by 0019
    op.drop_table("statement_accounts")
    op.drop_table("accounts")
    op.execute("DROP TYPE IF EXISTS accounttype")

    # Same fix for Epic 14 (0020): ingestion_run_files' current definition carries a column
    # added by 0020, `duplicate_comparison_id`, a foreign key to `duplicate_comparisons`,
    # which does not exist yet at this point in the chain. Dropping the column also drops
    # its foreign key, its index, and the CHECK that compares it with the outcome. The
    # second CHECK names only columns that already exist, so dropping the column would
    # leave it behind and 0020 would then fail on "already exists": drop it by name. Then
    # the temporary table, so 0020 remains the single source of truth for all of it. (The
    # outcome enum was created above with its current values, so 0020's ADD VALUE IF NOT
    # EXISTS is a safe no-op on a fresh database.)
    op.drop_column("ingestion_run_files", "duplicate_comparison_id")  # actually added by 0020
    op.drop_constraint("ck_ingestion_run_files_probable_duplicate_has_no_statement", "ingestion_run_files", type_="check")
    op.drop_table("duplicate_comparisons")

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
