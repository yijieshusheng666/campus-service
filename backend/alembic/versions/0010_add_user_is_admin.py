"""用户表新增管理员标记

Revision ID: 0010_add_user_is_admin
Revises: 0009_add_messages
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_add_user_is_admin"
down_revision: Union[str, None] = "0009_add_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default=False 是必须的：users 表里可能已有数据，
    # 加一个 NOT NULL 列而不给默认值，MySQL 会直接报错拒绝执行。
    # 保留 server_default（而不是建完就 drop）也是刻意的——
    # 将来直接用 SQL 插用户时同样有安全的默认值，不会意外造出管理员。
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
