"""add polymarket bot mode

Revision ID: b2c4d6e8f0a1
Revises: 8f300e110022
Create Date: 2026-08-02 14:05:00.000000

Additive only: extends two ENUM columns and adds nullable polymarket_*
config columns to bot_configs. No existing data is modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, Sequence[str], None] = '8f300e110022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_MODES = ('aragan', 'avaro', 'fury', 'whale')
_NEW_MODES = _OLD_MODES + ('polymarket',)

_OLD_EVENTS = (
    'started', 'hedge_opened', 'breakeven', 'tp_hit', 'sl_hit',
    'trailing_stop', 'stopped', 'error', 'reentry_guard_cleared',
    'lp_removed', 'lp_burned',
    'orphan_recovered',
    'circuit_breaker',
    'fury_entry', 'fury_sl', 'fury_tp', 'fury_circuit_breaker',
    'whale_new_position', 'whale_closed', 'whale_size_increase',
    'whale_size_decrease', 'whale_flip', 'whale_snapshot', 'whale_event',
)
_NEW_EVENTS = _OLD_EVENTS + ('poly_entry', 'poly_tp', 'poly_sl')


def upgrade() -> None:
    op.alter_column(
        'bot_configs', 'mode',
        existing_type=sa.Enum(*_OLD_MODES),
        type_=sa.Enum(*_NEW_MODES),
        existing_nullable=True,
    )
    op.add_column('bot_configs', sa.Column('polymarket_token_id', sa.String(length=80), nullable=True))
    op.add_column('bot_configs', sa.Column('polymarket_side', sa.String(length=8), nullable=True, server_default='buy'))
    op.add_column('bot_configs', sa.Column('polymarket_size_usd', sa.Float(), nullable=True))
    op.add_column('bot_configs', sa.Column('polymarket_entry_price', sa.Float(), nullable=True))
    op.add_column('bot_configs', sa.Column('polymarket_tp_price', sa.Float(), nullable=True))
    op.add_column('bot_configs', sa.Column('polymarket_sl_price', sa.Float(), nullable=True))
    op.alter_column(
        'bot_events', 'event_type',
        existing_type=sa.Enum(*_OLD_EVENTS),
        type_=sa.Enum(*_NEW_EVENTS),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'bot_events', 'event_type',
        existing_type=sa.Enum(*_NEW_EVENTS),
        type_=sa.Enum(*_OLD_EVENTS),
        existing_nullable=False,
    )
    op.drop_column('bot_configs', 'polymarket_sl_price')
    op.drop_column('bot_configs', 'polymarket_tp_price')
    op.drop_column('bot_configs', 'polymarket_entry_price')
    op.drop_column('bot_configs', 'polymarket_size_usd')
    op.drop_column('bot_configs', 'polymarket_side')
    op.drop_column('bot_configs', 'polymarket_token_id')
    op.alter_column(
        'bot_configs', 'mode',
        existing_type=sa.Enum(*_NEW_MODES),
        type_=sa.Enum(*_OLD_MODES),
        existing_nullable=True,
    )
