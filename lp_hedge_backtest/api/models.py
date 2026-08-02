"""
SQLAlchemy ORM models — mirrors the MariaDB schema in SAAS_PLAN.md.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, Numeric,
    Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from api.database import Base


def _utcnow() -> datetime:
    """Return a naive UTC datetime (matches legacy datetime.utcnow() behaviour)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    address     = Column(String(42), primary_key=True)   # 0x…
    plan        = Column(Enum("free", "starter", "pro"), default="free", nullable=False)
    created_at  = Column(DateTime, default=_utcnow)
    last_seen   = Column(DateTime, nullable=True)

    bot_configs   = relationship("BotConfig",    back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class Nonce(Base):
    __tablename__ = "nonces"

    address    = Column(String(42), primary_key=True)
    nonce      = Column(String(64),  nullable=False)
    expires_at = Column(DateTime,    nullable=False)
    created_at = Column(DateTime,    default=_utcnow)


class BotConfig(Base):
    __tablename__ = "bot_configs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_address    = Column(String(42), ForeignKey("users.address", ondelete="CASCADE"), nullable=False)
    chain_id        = Column(Integer, nullable=False)
    nft_token_id    = Column(String(78), nullable=False)
    pair            = Column(String(20), nullable=False)
    lower_bound     = Column(Numeric(20, 8), nullable=False)
    upper_bound     = Column(Numeric(20, 8), nullable=False)
    trigger_pct     = Column(Numeric(5, 2), default=-0.50)
    hedge_ratio     = Column(Numeric(5, 2), default=50.00)
    hedge_exchange  = Column(String(20), default="hyperliquid")
    hl_api_key      = Column(Text, nullable=True)         # AES-256 encrypted
    hl_wallet_addr  = Column(String(42), nullable=True)
    mode            = Column(Enum("aragan", "avaro", "fury", "whale", "polymarket"), default="aragan")
    leverage        = Column(Integer, default=10)
    sl_pct          = Column(Numeric(5, 3), default=0.100)    # % above entry → close short
    tp_pct          = Column(Numeric(5, 3), nullable=True)    # optional fixed TP %
    trailing_stop   = Column(Boolean, default=True)
    auto_rearm      = Column(Boolean, default=True)
    # FURY-specific config (nullable — only used when mode='fury')
    fury_symbol     = Column(String(5),    nullable=True)     # 'BTC' | 'ETH'
    fury_rsi_period = Column(Integer,      nullable=True, default=9)
    fury_rsi_long_th  = Column(Numeric(5, 2), nullable=True, default=35.0)
    fury_rsi_short_th = Column(Numeric(5, 2), nullable=True, default=65.0)
    fury_leverage_max = Column(Integer,    nullable=True, default=12)
    fury_risk_pct   = Column(Numeric(5, 2), nullable=True, default=2.0)
    # WHALE-specific config (nullable — only used when mode='whale')
    whale_top_n              = Column(Integer,      nullable=True, default=50)
    whale_min_notional       = Column(Numeric(12, 2), nullable=True, default=50000)
    whale_poll_interval      = Column(Integer,      nullable=True, default=30)
    whale_custom_addresses   = Column(Text,         nullable=True)  # comma-separated
    whale_watch_assets       = Column(String(100),  nullable=True)  # comma-separated, e.g. "BTC,ETH"
    whale_use_websocket      = Column(Boolean,      nullable=True, default=False)
    whale_oi_spike_threshold = Column(Numeric(5, 3), nullable=True, default=0.030)
    # POLYMARKET-specific config (nullable — only used when mode='polymarket')
    polymarket_token_id    = Column(String(80), nullable=True)  # CLOB outcome token ID
    polymarket_side        = Column(String(8),  nullable=True, default="buy")
    polymarket_size_usd    = Column(Float,      nullable=True)  # USDC to spend on entry
    polymarket_entry_price = Column(Float,      nullable=True)  # null → market entry
    polymarket_tp_price    = Column(Float,      nullable=True)  # take-profit (0-1)
    polymarket_sl_price    = Column(Float,      nullable=True)  # stop-loss (0-1)
    paper_trade     = Column(Boolean, default=False)          # simulate trades, no real orders
    engine_v2       = Column(Boolean, default=False)          # True → launch live_hedge_bot_v2.py
    from_above_dist_pct = Column(Numeric(5, 2), default=5.00) # M2-47: max % below upper_bound for from_above entry
    use_funding_gate    = Column(Boolean,       default=False) # M2-44: gate entry when funding too adverse
    funding_gate_pct    = Column(Numeric(5, 3), default=0.050) # M2-44: threshold % per 1h (rate < -X% blocks entry)
    active          = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=_utcnow)
    updated_at      = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    user   = relationship("User",      back_populates="bot_configs")
    events = relationship("BotEvent",  back_populates="config", cascade="all, delete-orphan")


class BotEvent(Base):
    __tablename__ = "bot_events"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    config_id     = Column(Integer, ForeignKey("bot_configs.id", ondelete="CASCADE"), nullable=False)
    event_type    = Column(
        Enum(
            "started", "hedge_opened", "breakeven", "tp_hit", "sl_hit",
            "trailing_stop", "stopped", "error", "reentry_guard_cleared",
            # LP safety events
            "lp_removed", "lp_burned",
            # V2 recovery
            "orphan_recovered",
            # V2 circuit breaker
            "circuit_breaker",
            # FURY events
            "fury_entry", "fury_sl", "fury_tp", "fury_circuit_breaker",
            # WHALE events
            "whale_new_position", "whale_closed", "whale_size_increase",
            "whale_size_decrease", "whale_flip", "whale_snapshot", "whale_event",
            # POLYMARKET events
            "poly_entry", "poly_tp", "poly_sl",
        ),
        nullable=False,
    )
    price_at_event = Column(Numeric(20, 8), nullable=True)
    pnl            = Column(Numeric(20, 8), nullable=True)
    details        = Column(JSON, nullable=True)
    ts             = Column(DateTime, default=_utcnow)

    config = relationship("BotConfig", back_populates="events")


class TelegramLink(Base):
    """
    Maps wallet ↔ Telegram chat_id for push alerts.
    Multi-wallet: one chat_id can link many wallets; one wallet can notify many chats.
    Composite unique prevents duplicate (chat, wallet) pairs.
    """
    __tablename__ = "telegram_links"
    __table_args__ = (
        UniqueConstraint("telegram_chat_id", "user_address", name="uq_chat_wallet"),
    )

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    user_address     = Column(String(42), nullable=False)
    telegram_chat_id = Column(BigInteger, nullable=False)
    linked_at        = Column(DateTime,   default=_utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_address    = Column(String(42), ForeignKey("users.address", ondelete="CASCADE"), nullable=False)
    plan            = Column(Enum("starter", "pro"), nullable=False)
    active_until    = Column(DateTime, nullable=False)
    amount_usdc     = Column(Numeric(12, 2), nullable=True)
    payment_tx_hash = Column(String(66), nullable=True)
    created_at      = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="subscriptions")


# ── Signal Lab ────────────────────────────────────────────────────────────

class SignalSource(Base):
    """Admin-managed Telegram channel threads feeding the Signal Lab."""
    __tablename__ = "signal_sources"

    id         = Column(Integer,    primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False)          # "Short-Term", "Bitcoin Daily Signals"
    channel_id = Column(BigInteger,  nullable=False)          # 1951769926
    thread_id  = Column(Integer,     nullable=True)           # 7, 22, or 29
    purpose    = Column(Enum("signals", "lp_range"), nullable=False)
    active     = Column(Boolean, default=True)
    added_at   = Column(DateTime, default=_utcnow)

    events = relationship("SignalEvent", back_populates="source", cascade="all, delete-orphan")


class SignalEvent(Base):
    """Every parsed trading signal from a Telegram signal source."""
    __tablename__ = "signal_events"

    id          = Column(Integer,      primary_key=True, autoincrement=True)
    source_id   = Column(Integer,      ForeignKey("signal_sources.id"), nullable=False)
    pair        = Column(String(20),   nullable=True)          # "ETH/USDT"
    direction   = Column(Enum("long", "short"), nullable=True)
    leverage    = Column(Integer,      nullable=True)
    entry       = Column(Numeric(20,8), nullable=True)
    stoploss    = Column(Numeric(20,8), nullable=True)
    targets     = Column(JSON,         nullable=True)          # list[float]
    size_pct    = Column(Numeric(5,2), nullable=True)
    raw_text    = Column(Text,         nullable=True)
    status      = Column(
        Enum("pending", "executed", "expired", "stopped", "tp_hit", "cancelled"),
        default="pending",
    )
    msg_id      = Column(BigInteger,   nullable=False)         # Telegram message ID
    received_at = Column(DateTime,     nullable=False)
    updated_at  = Column(DateTime,     default=_utcnow, onupdate=_utcnow)

    source     = relationship("SignalSource",   back_populates="events")
    executions = relationship("SignalExecution", back_populates="signal", cascade="all, delete-orphan")


class SignalExecution(Base):
    """Records when a user executes a signal."""
    __tablename__ = "signal_executions"

    id             = Column(Integer,     primary_key=True, autoincrement=True)
    signal_id      = Column(Integer,     ForeignKey("signal_events.id"), nullable=False)
    user_address   = Column(String(42),  nullable=False)
    hl_wallet_addr = Column(String(42),  nullable=True)
    hl_order_id       = Column(String(100), nullable=True)
    fill_price        = Column(Numeric(20, 8), nullable=True)
    close_price       = Column(Numeric(20, 8), nullable=True)
    sl_order_id       = Column(String(100),  nullable=True)
    tp1_order_id      = Column(String(100),  nullable=True)
    tp2_order_id      = Column(String(100),  nullable=True)
    breakeven_applied = Column(Boolean,      default=False)
    exec_leverage     = Column(Integer,      nullable=True)   # override used at execute time
    exec_size_usdt    = Column(Numeric(12,2), nullable=True)  # override used at execute time
    executed_at       = Column(DateTime,     default=_utcnow)
    outcome           = Column(Enum("pending", "filled", "failed"), default="pending")
    # Profitability dashboard fields (nullable until fills are reconciled)
    realized_pnl_usd  = Column(Numeric(20, 4), nullable=True)
    fees_usd          = Column(Numeric(20, 4), nullable=True)
    closed_at         = Column(DateTime, nullable=True)
    exit_reason       = Column(String(20), nullable=True)

    signal = relationship("SignalEvent", back_populates="executions")


class BotTrade(Base):
    """Normalized closed round-trips for the profitability dashboard."""
    __tablename__ = "bot_trades"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    config_id       = Column(Integer, ForeignKey("bot_configs.id", ondelete="CASCADE"), index=True)
    user_address    = Column(String(42), index=True, nullable=False)
    mode            = Column(String(20), nullable=False)          # aragan, avaro, fury, whale
    pair            = Column(String(20), nullable=False)
    side            = Column(String(10), nullable=True)           # short / long
    entry_price     = Column(Numeric(20, 8), nullable=True)
    exit_price      = Column(Numeric(20, 8), nullable=True)
    size_usd        = Column(Numeric(20, 4), nullable=True)
    realized_pnl_usd = Column(Numeric(20, 4), nullable=True)
    fees_usd        = Column(Numeric(20, 4), nullable=True)
    funding_usd     = Column(Numeric(20, 4), nullable=True)
    il_offset_usd   = Column(Numeric(20, 4), nullable=True)       # LP value change during hedge
    net_pnl_usd     = Column(Numeric(20, 4), nullable=True)       # realized_pnl + il_offset - fees - funding
    exit_reason     = Column(String(30), nullable=True)           # tp_hit, sl_hit, trailing_stop, manual, expiry
    is_estimate     = Column(Boolean, default=False)              # true if derived from incomplete event data
    opened_at       = Column(DateTime, nullable=True)
    closed_at       = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=_utcnow)


class WalletSnapshot(Base):
    """Periodic wallet balance snapshots used to build the equity curve."""
    __tablename__ = "wallet_snapshots"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_address    = Column(String(42), index=True, nullable=False)
    wallet_addr     = Column(String(42), index=True, nullable=True)
    source          = Column(String(20), nullable=False)          # bot, signal_lab
    balance_usdc    = Column(Numeric(20, 4), nullable=True)
    margin_used_usdc = Column(Numeric(20, 4), nullable=True)
    snapshot_at     = Column(DateTime, index=True, default=_utcnow)


class SignalWallet(Base):
    """Registered wallets for signal copy trading (separate from LP bot configs)."""
    __tablename__ = "signal_wallets"

    id             = Column(Integer,    primary_key=True, autoincrement=True)
    label          = Column(String(100), nullable=False)
    hl_wallet_addr = Column(String(42),  unique=True, nullable=False)
    hl_secret_key  = Column(Text,        nullable=False)   # Fernet-encrypted private key
    user_address   = Column(String(42),  nullable=True)    # SIWE address of owner (null = admin-registered)
    auto_execute   = Column(Boolean,     default=False)
    active         = Column(Boolean,     default=True)
    created_at     = Column(DateTime,    default=_utcnow)


class SignalUserDefault(Base):
    """Per-user per-coin execution defaults for Signal Lab (leverage + size)."""
    __tablename__ = "signal_user_defaults"
    __table_args__ = (
        UniqueConstraint("user_address", "coin", name="uq_sud_user_coin"),
    )

    id           = Column(Integer,      primary_key=True, autoincrement=True)
    user_address = Column(String(42),   nullable=False)
    coin         = Column(String(20),   nullable=False)
    leverage     = Column(Integer,      nullable=True)
    size_usdt    = Column(Numeric(12,2), nullable=True)
    created_at   = Column(DateTime,     default=_utcnow)
    updated_at   = Column(DateTime,     default=_utcnow, onupdate=_utcnow)
