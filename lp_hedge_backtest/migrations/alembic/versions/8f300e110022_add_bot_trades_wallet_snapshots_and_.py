"""add bot_trades, wallet_snapshots and signal execution pnl columns

Revision ID: 8f300e110022
Revises: 
Create Date: 2026-07-16 14:15:27.226505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f300e110022'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add profitability dashboard tables and columns.

    This migration is intentionally minimal: it only creates new tables
    and adds nullable columns to an existing table. No existing columns,
    indexes, or defaults on live tables are modified.
    """
    op.create_table(
        'wallet_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_address', sa.String(length=42), nullable=False),
        sa.Column('wallet_addr', sa.String(length=42), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('balance_usdc', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('margin_used_usdc', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('snapshot_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_wallet_snapshots_snapshot_at'), 'wallet_snapshots', ['snapshot_at'], unique=False)
    op.create_index(op.f('ix_wallet_snapshots_user_address'), 'wallet_snapshots', ['user_address'], unique=False)
    op.create_index(op.f('ix_wallet_snapshots_wallet_addr'), 'wallet_snapshots', ['wallet_addr'], unique=False)

    op.create_table(
        'bot_trades',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=True),
        sa.Column('user_address', sa.String(length=42), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('pair', sa.String(length=20), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=True),
        sa.Column('entry_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('exit_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('size_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('realized_pnl_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('fees_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('funding_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('il_offset_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('net_pnl_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('exit_reason', sa.String(length=30), nullable=True),
        sa.Column('is_estimate', sa.Boolean(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['config_id'], ['bot_configs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bot_trades_config_id'), 'bot_trades', ['config_id'], unique=False)
    op.create_index(op.f('ix_bot_trades_user_address'), 'bot_trades', ['user_address'], unique=False)

    op.add_column('signal_executions', sa.Column('realized_pnl_usd', sa.Numeric(precision=20, scale=4), nullable=True))
    op.add_column('signal_executions', sa.Column('fees_usd', sa.Numeric(precision=20, scale=4), nullable=True))
    op.add_column('signal_executions', sa.Column('closed_at', sa.DateTime(), nullable=True))
    op.add_column('signal_executions', sa.Column('exit_reason', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Reverse the migration."""
    op.drop_column('signal_executions', 'exit_reason')
    op.drop_column('signal_executions', 'closed_at')
    op.drop_column('signal_executions', 'fees_usd')
    op.drop_column('signal_executions', 'realized_pnl_usd')

    op.drop_index(op.f('ix_bot_trades_user_address'), table_name='bot_trades')
    op.drop_index(op.f('ix_bot_trades_config_id'), table_name='bot_trades')
    op.drop_table('bot_trades')

    op.drop_index(op.f('ix_wallet_snapshots_wallet_addr'), table_name='wallet_snapshots')
    op.drop_index(op.f('ix_wallet_snapshots_user_address'), table_name='wallet_snapshots')
    op.drop_index(op.f('ix_wallet_snapshots_snapshot_at'), table_name='wallet_snapshots')
    op.drop_table('wallet_snapshots')
