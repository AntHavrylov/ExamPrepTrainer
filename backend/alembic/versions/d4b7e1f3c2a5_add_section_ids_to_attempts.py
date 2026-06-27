"""add section_ids column to attempts

Revision ID: d4b7e1f3c2a5
Revises: 2a7c4f9e1b3d
Create Date: 2026-06-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4b7e1f3c2a5'
down_revision: Union[str, Sequence[str], None] = 'c3a1d8f2b9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('attempts', sa.Column('section_ids', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('attempts', 'section_ids')
