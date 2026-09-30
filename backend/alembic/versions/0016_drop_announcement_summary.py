"""drop announcements.summary（移除公告 AI 摘要功能）

Revision ID: 0016_drop_announcement_summary
Revises: 0015_add_announcements
Create Date: 2026-09-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_drop_announcement_summary"
down_revision: Union[str, None] = "0015_add_announcements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("announcements", "summary")


def downgrade() -> None:
    op.add_column(
        "announcements",
        sa.Column("summary", sa.String(length=500), nullable=True),
    )
