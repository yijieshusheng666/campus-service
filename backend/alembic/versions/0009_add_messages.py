"""新增私信表

Revision ID: 0009_add_messages
Revises: 0008_add_errands
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_add_messages"
down_revision: Union[str, None] = "0008_add_errands"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "sender_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "receiver_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    # 会话查询与未读统计的核心路径
    op.create_index(
        "ix_messages_sender_receiver_id", "messages", ["sender_id", "receiver_id", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_messages_sender_receiver_id", table_name="messages")
    op.drop_table("messages")
