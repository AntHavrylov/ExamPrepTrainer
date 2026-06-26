"""add section_mode column to sessions

Revision ID: c3a1d8f2b9e4
Revises: 9b3e6f2c8a1d
Create Date: 2026-06-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a1d8f2b9e4'
down_revision: Union[str, Sequence[str], None] = '9b3e6f2c8a1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sessions',
        sa.Column('section_mode', sa.String(10), nullable=False, server_default='or'),
    )


def downgrade() -> None:
    op.drop_column('sessions', 'section_mode')
