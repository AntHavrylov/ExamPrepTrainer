"""add session_length and target_question_count columns

Revision ID: 9b3e6f2c8a1d
Revises: 2a7c4f9e1b3d
Create Date: 2026-06-24 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b3e6f2c8a1d'
down_revision: Union[str, Sequence[str], None] = '2a7c4f9e1b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('session_length', sa.Integer(), nullable=False, server_default='5'))
    op.add_column(
        'sessions', sa.Column('target_question_count', sa.Integer(), nullable=False, server_default='5')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sessions', 'target_question_count')
    op.drop_column('users', 'session_length')
