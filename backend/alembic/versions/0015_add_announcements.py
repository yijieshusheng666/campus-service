"""add announcements 表（平台公告）

Revision ID: 0015_add_announcements
Revises: 0014_add_email_verifications
Create Date: 2026-09-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_add_announcements"
down_revision: Union[str, None] = "0014_add_email_verifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "publisher_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_announcements_publisher_id", "announcements", ["publisher_id"])
    op.create_index("ix_announcements_is_pinned", "announcements", ["is_pinned"])
    op.create_index("ix_announcements_is_online", "announcements", ["is_online"])


def downgrade() -> None:
    op.drop_index("ix_announcements_is_online", table_name="announcements")
    op.drop_index("ix_announcements_is_pinned", table_name="announcements")
    op.drop_index("ix_announcements_publisher_id", table_name="announcements")
    op.drop_table("announcements")
