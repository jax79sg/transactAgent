"""probable duplicate statement detection: remembered files, comparisons, pairs, removal jobs, scan state

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-03

Epic 14 (Probable Duplicate Statement Detection). See
aidlc-docs/inception/requirements/probable-duplicate-statements-requirements.md and
aidlc-docs/construction/database/functional-design/ (BR-39..BR-52).

Purely additive -- no existing column, row, or constraint is changed. Every existing run
file keeps its outcome and gets a NULL comparison link. Ships with detection switched
off; nothing here changes what a normal ingestion run does.

(Reworked in place on 2026-10-04: `duplicate_pairs` gained the required `removal_allowed`
column, BR-53. Like 0019's rework, this was possible because 0020 had only ever run in
disposable test databases; the live database was at 0018 and nothing was committed.)

Six new tables, created from Base.metadata (same technique as 0004/0013/0019, which also
avoids the known SQLAlchemy/Alembic double-CREATE-TYPE bug for the new enum types).
Every constraint, including BR-45's partial unique index and BR-43's COLLATE "C" ordering
check, is declared on the models, so that technique creates them here too and the unit
tests exercise the real constraints.

`ingestion_run_files.outcome` gains `skipped_probable_duplicate`. PostgreSQL does not let
a value added to an enum be used in the transaction that added it, and the two CHECK
constraints created below mention the new value, so the value is added inside
autocommit_block() (committing it) before anything uses it. Precedent for the value
itself: 0005.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from transactagent_db.models import Base

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Dependency order: each table's foreign keys point at tables earlier in the list.
_NEW_TABLE_NAMES = [
    "duplicate_comparisons",
    "duplicate_comparison_rows",
    "known_files",
    "duplicate_pairs",
    "statement_removal_jobs",
    "duplicate_scan_state",
]
_NEW_ENUM_TYPES = [
    "knownfilestate",
    "duplicatepairstatus",
    "statementremovaljobstatus",
    "comparisonside",
    "comparisonrowmarker",
]
_COMPARISON_FK = "fk_ingestion_run_files_duplicate_comparison_id"
_IFF_CHECK = "ck_ingestion_run_files_probable_duplicate_iff_comparison"
_NO_STATEMENT_CHECK = "ck_ingestion_run_files_probable_duplicate_has_no_statement"


def upgrade() -> None:
    # Must be committed before the CHECK constraints below can mention it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE ingestionrunfileoutcome ADD VALUE IF NOT EXISTS 'skipped_probable_duplicate'")

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in _NEW_TABLE_NAMES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    op.add_column(
        "ingestion_run_files",
        sa.Column("duplicate_comparison_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        _COMPARISON_FK,
        "ingestion_run_files",
        "duplicate_comparisons",
        ["duplicate_comparison_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_ingestion_run_files_duplicate_comparison_id", "ingestion_run_files", ["duplicate_comparison_id"])
    op.create_check_constraint(
        _IFF_CHECK,
        "ingestion_run_files",
        "(outcome = 'skipped_probable_duplicate') = (duplicate_comparison_id IS NOT NULL)",
    )
    op.create_check_constraint(
        _NO_STATEMENT_CHECK,
        "ingestion_run_files",
        "outcome != 'skipped_probable_duplicate' OR bank_statement_id IS NULL",
    )


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE (see 0005), so the enum value stays. A
    # run file still using it could not be read back by the pre-0020 models, so refuse
    # rather than leave such rows behind.
    in_use = op.get_bind().execute(
        sa.text("SELECT count(*) FROM ingestion_run_files WHERE outcome = 'skipped_probable_duplicate'")
    ).scalar()
    if in_use:
        raise RuntimeError(
            f"Cannot downgrade 0020: {in_use} ingestion_run_files row(s) have outcome "
            "'skipped_probable_duplicate'. Delete those rows (or restore a backup taken before "
            "the feature was used) first."
        )

    op.drop_constraint(_NO_STATEMENT_CHECK, "ingestion_run_files", type_="check")
    op.drop_constraint(_IFF_CHECK, "ingestion_run_files", type_="check")
    op.drop_index("ix_ingestion_run_files_duplicate_comparison_id", table_name="ingestion_run_files")
    op.drop_constraint(_COMPARISON_FK, "ingestion_run_files", type_="foreignkey")
    op.drop_column("ingestion_run_files", "duplicate_comparison_id")

    bind = op.get_bind()
    for name in reversed(_NEW_TABLE_NAMES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
    for enum_name in _NEW_ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
