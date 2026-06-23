"""add difficulty, hint, and explanation columns

Revision ID: 560abf3947e2
Revises: 334508385dd7
Create Date: 2026-06-23 16:56:32.325381

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '560abf3947e2'
down_revision: Union[str, Sequence[str], None] = '334508385dd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sessions',
        sa.Column('difficulty', sa.String(length=20), nullable=False, server_default='medium'),
    )
    op.add_column(
        'question_bank',
        sa.Column('difficulty', sa.String(length=20), nullable=False, server_default='medium'),
    )
    op.add_column('question_bank', sa.Column('hint', sa.Text(), nullable=False, server_default=''))
    op.add_column('question_bank', sa.Column('explanation', sa.Text(), nullable=False, server_default=''))
    op.add_column('attempts', sa.Column('hint', sa.Text(), nullable=True))
    op.add_column('attempts', sa.Column('explanation', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('attempts', 'explanation')
    op.drop_column('attempts', 'hint')
    op.drop_column('question_bank', 'explanation')
    op.drop_column('question_bank', 'hint')
    op.drop_column('question_bank', 'difficulty')
    op.drop_column('sessions', 'difficulty')
