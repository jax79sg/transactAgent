"""add oauth_credentials table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-01

Added retroactively during Unit 3 (Ingestion Worker Service) NFR Requirements: the
approved Functional Design left the Google OAuth connection mechanism (US-1.1)
underspecified, since Unit 3 has no browser-facing interface of its own to run an
interactive OAuth flow. Resolved as: Unit 2 exposes /drive/connect + /drive/callback,
storing the resulting refresh token here for Unit 3 to consume. See aidlc-docs/audit.md
2026-08-01 for the full history.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("provider", name="uq_oauth_credentials_provider"),
    )


def downgrade() -> None:
    op.drop_table("oauth_credentials")
