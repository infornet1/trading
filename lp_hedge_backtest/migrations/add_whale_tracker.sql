-- ============================================================
-- Migration: add_whale_tracker
-- Adds whale-mode support to bot_configs and new whale event
-- types to bot_events.
--
-- Run with:
--   mysql -u <user> -p <database> < migrations/add_whale_tracker.sql
--
-- Safe to run multiple times (uses IF NOT EXISTS / MODIFY).
-- ============================================================

-- ── 1. Add whale config columns to bot_configs ────────────────

ALTER TABLE bot_configs
  ADD COLUMN IF NOT EXISTS whale_top_n            INT            DEFAULT 50    COMMENT 'Leaderboard top-N addresses to watch',
  ADD COLUMN IF NOT EXISTS whale_min_notional     DECIMAL(12,2)  DEFAULT 50000 COMMENT 'Minimum position notional USD to emit signal',
  ADD COLUMN IF NOT EXISTS whale_poll_interval    INT            DEFAULT 30    COMMENT 'Seconds between snapshot polls',
  ADD COLUMN IF NOT EXISTS whale_custom_addresses TEXT           DEFAULT NULL  COMMENT 'Comma-separated custom 0x addresses to monitor',
  ADD COLUMN IF NOT EXISTS whale_watch_assets     VARCHAR(100)   DEFAULT NULL  COMMENT 'Comma-separated asset filter, e.g. BTC,ETH';

-- ── 2. Extend the mode enum on bot_configs ────────────────────
-- MariaDB requires a full MODIFY COLUMN to add enum values.

ALTER TABLE bot_configs
  MODIFY COLUMN mode ENUM('aragan', 'avaro', 'fury', 'whale') NOT NULL DEFAULT 'aragan';

-- ── 3. Extend the event_type enum on bot_events ──────────────

ALTER TABLE bot_events
  MODIFY COLUMN event_type ENUM(
    'started',
    'hedge_opened',
    'breakeven',
    'tp_hit',
    'sl_hit',
    'trailing_stop',
    'stopped',
    'error',
    -- FURY events
    'fury_entry',
    'fury_sl',
    'fury_tp',
    'fury_circuit_breaker',
    -- WHALE events
    'whale_new_position',
    'whale_closed',
    'whale_size_increase',
    'whale_size_decrease',
    'whale_flip',
    'whale_snapshot',
    'whale_event'
  ) NOT NULL;

-- ── 4. Index for whale event queries ─────────────────────────
-- Speeds up GET /bots/{id}/whale-signals endpoint.

CREATE INDEX IF NOT EXISTS idx_bot_events_whale
  ON bot_events (config_id, event_type, ts DESC)
  COMMENT 'Supports whale-signals API query';

-- ── Done ──────────────────────────────────────────────────────
SELECT 'Migration add_whale_tracker applied successfully.' AS status;
