"""Centralized feature flags and runtime configuration.

Values are read from environment variables. This module is safe to import
anywhere in the API package.
"""

import os


# ── Feature flags ───────────────────────────────────────────────────────────

PERFORMANCE_DASHBOARD_ENABLED = (
    os.getenv("PERFORMANCE_DASHBOARD_ENABLED", "false").strip().lower()
    in ("1", "true", "yes")
)


# ── Wallet snapshot cadence (seconds) ───────────────────────────────────────

WALLET_SNAPSHOT_INTERVAL_SECS = int(os.getenv("WALLET_SNAPSHOT_INTERVAL_SECS", "900"))
