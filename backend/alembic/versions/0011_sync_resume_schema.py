"""补齐 resumes 表缺失的列，并移除遗留的 vector_id

Revision ID: 0011_sync_resume_schema
Revises: 0010_add_user_is_admin
Create Date: 2026-09-11

── 这个迁移修复的是什么 ──────────────────────────────────────────

models/resume.py 里的 Resume 声明了 6 个列，但 0001_initial 建表时没有，
之后也没有任何迁移补过：

    parsed_location / parsed_job_title / parsed_sections
    edited_data     / suggestions     / suggestions_at

同时 0001 建的 vector_id 是「向量化知识库」年代的遗留，模型里早已不再声明，
这次一并移除。

── 为什么直到部署才暴露 ──────────────────────────────────────────

本地开发库当年是用 Base.metadata.create_all() 按【模型】建的，列是全的，
所以应用一直跑得好好的；服务器上的库是严格按【迁移链】从零建的，缺列。
于是同一个 commit，本地正常、线上 SELECT 一带这些列就报
    Unknown column 'resumes.parsed_location' in 'field list'
表现为 /auth/me 与 /resumes/mine 全部 500。

教训：**迁移链必须能从零建出与模型完全一致的库。** 本地靠 create_all 兜底
掩盖了漂移，直到换一台干净的机器才炸出来。检测手段：
    用一个空库跑 alembic upgrade head，再 alembic revision --autogenerate
    对比模型，有输出就说明漂移了。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0011_sync_resume_schema"
down_revision: Union[str, None] = "0010_add_user_is_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 列类型与模型一致：字符串/JSON 均可空（历史数据没有这些值）
    op.add_column("resumes", sa.Column("parsed_location", sa.String(length=200), nullable=True))
    op.add_column("resumes", sa.Column("parsed_job_title", sa.String(length=100), nullable=True))
    op.add_column("resumes", sa.Column("parsed_sections", mysql.JSON(), nullable=True))
    op.add_column("resumes", sa.Column("edited_data", mysql.JSON(), nullable=True))
    op.add_column("resumes", sa.Column("suggestions", mysql.JSON(), nullable=True))
    op.add_column("resumes", sa.Column("suggestions_at", sa.DateTime(), nullable=True))

    # 模型已不再声明该列（向量化功能整体移除），且表内无数据，删除安全
    op.drop_column("resumes", "vector_id")


def downgrade() -> None:
    op.add_column("resumes", sa.Column("vector_id", mysql.VARCHAR(length=64), nullable=True))
    op.drop_column("resumes", "suggestions_at")
    op.drop_column("resumes", "suggestions")
    op.drop_column("resumes", "edited_data")
    op.drop_column("resumes", "parsed_sections")
    op.drop_column("resumes", "parsed_job_title")
    op.drop_column("resumes", "parsed_location")
