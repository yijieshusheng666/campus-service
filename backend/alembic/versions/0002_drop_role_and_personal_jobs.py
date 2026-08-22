"""适配去掉角色与投递模块、岗位改为个人目标岗位

Revision ID: 0002_drop_role_and_personal_jobs
Revises: 0001_initial
Create Date: 2026-08-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_drop_role_and_personal_jobs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 删除投递表：drop_table 会自动删除其上的索引与外键约束
    op.drop_table("applications")

    # 2. 用户去掉角色字段
    op.drop_column("users", "role")

    # 3. 岗位改为个人目标岗位：recruiter_id -> user_id
    #    直接重命名列即可，索引随列保留（名称仍为 ix_jobs_recruiter_id，功能不受影响）
    op.alter_column("jobs", "recruiter_id", new_column_name="user_id", existing_type=sa.Integer())


def downgrade() -> None:
    # 3. 岗位列改回
    op.alter_column("jobs", "user_id", new_column_name="recruiter_id", existing_type=sa.Integer())

    # 2. 加回角色字段
    op.add_column(
        "users",
        sa.Column("role", sa.Enum("buyer", "seller", "recruiter", name="userrole"), nullable=False, server_default="buyer"),
    )

    # 1. 重建投递表
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("applied", "reviewing", "interview", "offered", "rejected", name="applicationstatus"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["applicant_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "applicant_id", name="uq_application_job_user"),
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_applications_applicant_id", "applications", ["applicant_id"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])