"""
SQLAlchemy ORM models — mirrors the MariaDB schema in SAAS_PLAN.md.
"""

from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Numeric,
    Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from api.database import Base


class User(Base):
    __tablename__ = "users"

    address     = Column(String(42), primary_key=True)   # 0x…
    plan        = Column(Enum("free", "starter", "pro"), default="free", nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    last_seen   = Column(DateTime, nullable=True)

    bot_configs   = relationship("BotConfig",    back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class Nonce(Base):
    __tablename__ = "nonces"

    address    = Column(String(42), primary_key=True)
    nonce      = Column(String(64),  nullable=False)
    expires_at = Column(DateTime,    nullable=False)
    created_at = Column(DateTime,    default=datetime.utcnow)


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
    mode            = Column(Enum("aragan", "avaro", "fury", "whale"), default="aragan")
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
    paper_trade     = Column(Boolean, default=False)          # simulate trades, no real orders
    active          = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
            # FURY events
            "fury_entry", "fury_sl", "fury_tp", "fury_circuit_breaker",
            # WHALE events
            "whale_new_position", "whale_closed", "whale_size_increase",
            "whale_size_decrease", "whale_flip", "whale_snapshot", "whale_event",
        ),
        nullable=False,
    )
    price_at_event = Column(Numeric(20, 8), nullable=True)
    pnl            = Column(Numeric(20, 8), nullable=True)
    details        = Column(JSON, nullable=True)
    ts             = Column(DateTime, default=datetime.utcnow)

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
    linked_at        = Column(DateTime,   default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_address    = Column(String(42), ForeignKey("users.address", ondelete="CASCADE"), nullable=False)
    plan            = Column(Enum("starter", "pro"), nullable=False)
    active_until    = Column(DateTime, nullable=False)
    amount_usdc     = Column(Numeric(12, 2), nullable=True)
    payment_tx_hash = Column(String(66), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")
