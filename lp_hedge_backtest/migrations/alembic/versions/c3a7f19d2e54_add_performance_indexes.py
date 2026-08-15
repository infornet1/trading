"""add performance indexes

Revision ID: c3a7f19d2e54
Revises: b2c4d6e8f0a1
Create Date: 2026-08-15 08:55:00.000000

Additive only: creates indexes on growing tables used by the profitability
dashboard, admin overview, signal reconciler and expiry sweeper. No existing
data is modified.

- signal_executions(user_address)          — every /performance/* user query
- signal_executions(outcome, close_price)  — reconciler scan every 5 min
- bot_trades(user_address, closed_at)      — dashboard filter + sort
- bot_events(config_id, ts)                — event feeds, ORDER BY ts DESC
- signal_events(status, received_at)       — expiry sweeper + /signal-lab/signals
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3a7f19d2e54'
down_revision: Union[str, Sequence[str], None] = 'b2c4d6e8f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_signal_executions_user_address',
        'signal_executions', ['user_address'],
    )
    op.create_index(
        'ix_signal_executions_outcome_close',
        'signal_executions', ['outcome', 'close_price'],
    )
    op.create_index(
        'ix_bot_trades_user_closed',
        'bot_trades', ['user_address', 'closed_at'],
    )
    op.create_index(
        'ix_bot_events_config_ts',
        'bot_events', ['config_id', 'ts'],
    )
    op.create_index(
        'ix_signal_events_status_received',
        'signal_events', ['status', 'received_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_signal_events_status_received', table_name='signal_events')
    op.drop_index('ix_bot_events_config_ts', table_name='bot_events')
    op.drop_index('ix_bot_trades_user_closed', table_name='bot_trades')
    op.drop_index('ix_signal_executions_outcome_close', table_name='signal_executions')
    op.drop_index('ix_signal_executions_user_address', table_name='signal_executions')
