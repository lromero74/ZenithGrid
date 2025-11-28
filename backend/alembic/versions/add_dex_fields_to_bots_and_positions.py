"""add dex fields to bots and positions

Revision ID: add_dex_fields
Revises: add_last_ai_check
Create Date: 2025-11-27

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_dex_fields'
down_revision = 'add_last_ai_check'
branch_labels = None
depends_on = None


def upgrade():
    # Add DEX fields to bots table
    op.add_column('bots', sa.Column('exchange_type', sa.String(), nullable=False, server_default='cex'))
    op.add_column('bots', sa.Column('chain_id', sa.Integer(), nullable=True))
    op.add_column('bots', sa.Column('dex_router', sa.String(), nullable=True))
    op.add_column('bots', sa.Column('wallet_private_key', sa.String(), nullable=True))
    op.add_column('bots', sa.Column('rpc_url', sa.String(), nullable=True))
    op.add_column('bots', sa.Column('wallet_address', sa.String(), nullable=True))

    # Add DEX fields to positions table
    op.add_column('positions', sa.Column('exchange_type', sa.String(), nullable=False, server_default='cex'))
    op.add_column('positions', sa.Column('chain_id', sa.Integer(), nullable=True))
    op.add_column('positions', sa.Column('dex_router', sa.String(), nullable=True))
    op.add_column('positions', sa.Column('wallet_address', sa.String(), nullable=True))


def downgrade():
    # Remove DEX fields from positions table
    op.drop_column('positions', 'wallet_address')
    op.drop_column('positions', 'dex_router')
    op.drop_column('positions', 'chain_id')
    op.drop_column('positions', 'exchange_type')

    # Remove DEX fields from bots table
    op.drop_column('bots', 'wallet_address')
    op.drop_column('bots', 'rpc_url')
    op.drop_column('bots', 'wallet_private_key')
    op.drop_column('bots', 'dex_router')
    op.drop_column('bots', 'chain_id')
    op.drop_column('bots', 'exchange_type')
