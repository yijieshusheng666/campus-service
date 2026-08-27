"""新增 AI 模拟面试表

Revision ID: 0007_add_interviews
Revises: 0006_add_resume_parse_status
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_add_interviews"
down_revision: Union[str, None] = "0006_add_resume_parse_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mock_interviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resume_id",
            sa.Integer(),
            sa.ForeignKey("resumes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_position", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ongoing", "completed", name="interviewstatus"),
            nullable=False,
            server_default="ongoing",
        ),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mock_interviews_user_id", "mock_interviews", ["user_id"])
    op.create_index("ix_mock_interviews_status", "mock_interviews", ["status"])

    op.create_table(
        "interview_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "interview_id",
            sa.Integer(),
            sa.ForeignKey("mock_interviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_interview_messages_interview_id", "interview_messages", ["interview_id"])


def downgrade() -> None:
    op.drop_table("interview_messages")
    op.drop_table("mock_interviews")
