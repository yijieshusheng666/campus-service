"""messages 增加 goods_id（私信商品卡片）

Revision ID: 0013_add_message_goods_id
Revises: 0012_add_refresh_tokens
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_add_message_goods_id"
down_revision: Union[str, None] = "0012_add_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("goods_id", sa.Integer(), nullable=True))
    # SET NULL：卖家删除商品时保留聊天记录，只断开引用
    op.create_foreign_key(
        "fk_messages_goods_id",
        "messages",
        "goods",
        ["goods_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_messages_goods_id", "messages", ["goods_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_goods_id", table_name="messages")
    op.drop_constraint("fk_messages_goods_id", "messages", type_="foreignkey")
    op.drop_column("messages", "goods_id")
