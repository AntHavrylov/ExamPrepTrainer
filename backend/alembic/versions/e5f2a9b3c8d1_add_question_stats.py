"""add question stats columns

Revision ID: e5f2a9b3c8d1
Revises: d4b7e1f3c2a5
Create Date: 2026-06-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f2a9b3c8d1'
down_revision: Union[str, Sequence[str], None] = 'd4b7e1f3c2a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('question_bank', sa.Column('asked_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('question_bank', sa.Column('correct_answer_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('attempts', sa.Column('question_bank_id', sa.Integer(), sa.ForeignKey('question_bank.id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    op.drop_column('attempts', 'question_bank_id')
    op.drop_column('question_bank', 'correct_answer_count')
    op.drop_column('question_bank', 'asked_count')
