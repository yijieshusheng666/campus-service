"""add email_verifications 表（邮箱验证码）

Revision ID: 0014_add_email_verifications
Revises: 0013_add_message_goods_id
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_add_email_verifications"
down_revision: Union[str, None] = "0013_add_message_goods_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_email_verifications_email", "email_verifications", ["email"])
    op.create_index(
        "ix_email_verifications_email_purpose_created",
        "email_verifications",
        ["email", "purpose", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_verifications_email_purpose_created", table_name="email_verifications")
    op.drop_index("ix_email_verifications_email", table_name="email_verifications")
    op.drop_table("email_verifications")
