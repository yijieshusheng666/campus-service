"""添加简历照片字段

Revision ID: 0004_add_resume_photo
Revises: 0003_drop_jobs
Create Date: 2026-08-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_resume_photo"
down_revision: Union[str, None] = "0003_drop_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resumes", sa.Column("photo_path", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("resumes", "photo_path")
