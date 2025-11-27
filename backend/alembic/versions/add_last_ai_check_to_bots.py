"""add last_ai_check to bots

Revision ID: add_last_ai_check
Revises:
Create Date: 2025-11-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_last_ai_check'
down_revision = None  # Will be set when run
branch_labels = None
depends_on = None


def upgrade():
    # Add last_ai_check column to bots table
    op.add_column('bots', sa.Column('last_ai_check', sa.DateTime(), nullable=True))


def downgrade():
    # Remove last_ai_check column from bots table
    op.drop_column('bots', 'last_ai_check')
