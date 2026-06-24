"""add language column to users and question_bank

Revision ID: 2a7c4f9e1b3d
Revises: 1c67eb322967
Create Date: 2026-06-24 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a7c4f9e1b3d'
down_revision: Union[str, Sequence[str], None] = '1c67eb322967'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('language', sa.String(length=10), nullable=False, server_default='en'))
    op.add_column(
        'question_bank', sa.Column('language', sa.String(length=10), nullable=False, server_default='en')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('question_bank', 'language')
    op.drop_column('users', 'language')
