"""新增快递代拿表

Revision ID: 0008_add_errands
Revises: 0007_add_interviews
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_add_errands"
down_revision: Union[str, None] = "0007_add_interviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "errands",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "runner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pickup_location", sa.String(200), nullable=False),
        sa.Column("package_info", sa.String(200), nullable=False),
        sa.Column("dropoff_location", sa.String(200), nullable=False),
        sa.Column("reward", sa.Numeric(10, 2), nullable=False),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(100), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "delivered", "completed", "cancelled", name="errandstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_errands_user_id", "errands", ["user_id"])
    op.create_index("ix_errands_runner_id", "errands", ["runner_id"])
    op.create_index("ix_errands_status", "errands", ["status"])


def downgrade() -> None:
    op.drop_table("errands")
