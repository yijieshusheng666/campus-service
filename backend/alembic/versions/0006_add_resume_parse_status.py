"""简历表新增解析状态列

Revision ID: 0006_add_resume_parse_status
Revises: 0005_add_orders
Create Date: 2026-08-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_resume_parse_status"
down_revision: Union[str, None] = "0005_add_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column(
            "parse_status",
            sa.Enum("pending", "completed", "failed", name="parsestatus"),
            nullable=False,
            server_default="completed",
        ),
    )


def downgrade() -> None:
    op.drop_column("resumes", "parse_status")
