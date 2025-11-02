#!/usr/bin/env python3
"""
Scalping Bot v2.0 Email Notification System
Sends email alerts when high-confidence trading signals are detected
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import json
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ScalpingEmailNotifier:
    """Email notification service for scalping trading signals"""

    def __init__(self, config_file='email_config.json'):
        """Initialize email notifier with configuration"""
        self.config_file = config_file
        self.enabled = False
        self.last_email_time = {}
        self.cooldown_seconds = 300  # 5 minutes default

        try:
            self.load_config(config_file)
            logger.info(f"✅ Email notifier initialized - Server: {self.smtp_server}:{self.smtp_port}")
        except Exception as e:
            logger.warning(f"⚠️ Email notifier not configured: {e}")
            self.enabled = False

    def load_config(self, config_file):
        """Load email configuration from JSON file"""
        with open(config_file, 'r') as f:
            config = json.load(f)

        # SMTP settings
        self.smtp_server = config['smtp_server']
        self.smtp_port = config['smtp_port']
        self.smtp_use_tls = config.get('smtp_use_tls', True)
        self.smtp_username = config['smtp_username']
        self.smtp_password = config['smtp_password']
        self.sender_email = config['sender_email']
        self.recipient_email = config['recipient_email']

        # Notification settings
        self.cooldown_seconds = config.get('alert_cooldown_minutes', 5) * 60
        self.send_on_signal = config.get('send_on_signal', True)
        self.send_on_trade_open = config.get('send_on_trade_open', True)
        self.send_on_trade_close = config.get('send_on_trade_close', True)
        self.send_on_error = config.get('send_on_error', False)

        self.enabled = True

    def should_send_email(self, email_type: str) -> bool:
        """Check if email should be sent based on cooldown"""
        if not self.enabled:
            return False

        now = datetime.now().timestamp()
        last_sent = self.last_email_time.get(email_type, 0)

        if (now - last_sent) < self.cooldown_seconds:
            minutes_remaining = (self.cooldown_seconds - (now - last_sent)) / 60
            logger.info(f"⏱️ Email cooldown active for {email_type} - {minutes_remaining:.1f} min remaining")
            return False

        return True

    def send_signal_notification(self, signal: Dict, side: str, current_price: float,
                                  confidence: float, conditions: list) -> bool:
        """
        Send email notification when high-confidence signal is detected

        Args:
            signal: Signal dictionary with stop_loss, take_profit, etc.
            side: 'LONG' or 'SHORT'
            current_price: Current BTC price
            confidence: Signal confidence percentage (0-100)
            conditions: List of conditions that triggered the signal

        Returns:
            bool: True if email sent successfully
        """
        if not self.send_on_signal:
            return False

        if not self.should_send_email(f'signal_{side}'):
            return False

        try:
            # Determine signal emoji and color
            emoji = "🟢" if side == "LONG" else "🔴"
            action = "BUY" if side == "LONG" else "SELL/SHORT"

            # Build subject
            subject = f"[BTC-SCALPING] {emoji} {confidence:.1f}% Signal - {action} Opportunity"

            # Build body
            body = self._build_signal_body(signal, side, current_price, confidence, conditions)

            # Send email
            success = self._send_email(subject, body)

            if success:
                self.last_email_time[f'signal_{side}'] = datetime.now().timestamp()
                logger.info(f"✅ Signal notification sent: {side} {confidence:.1f}%")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to send signal email: {e}")
            return False

    def _build_signal_body(self, signal: Dict, side: str, current_price: float,
                           confidence: float, conditions: list) -> str:
        """Build formatted email body for signal notification"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Extract signal data
        stop_loss = signal.get('stop_loss', 0)
        take_profit = signal.get('take_profit', 0)
        entry_price = signal.get('entry_price', current_price)

        # Calculate percentages
        if side == "LONG":
            sl_pct = ((entry_price - stop_loss) / entry_price) * 100
            tp_pct = ((take_profit - entry_price) / entry_price) * 100
        else:
            sl_pct = ((stop_loss - entry_price) / entry_price) * 100
            tp_pct = ((entry_price - take_profit) / entry_price) * 100

        # Calculate risk/reward
        risk_reward = abs(tp_pct / sl_pct) if sl_pct != 0 else 0

        body = f"""Bitcoin Scalping Bot v2.0 - Trading Signal Alert
{timestamp}

{'='*70}
🎯 HIGH CONFIDENCE SIGNAL DETECTED
{'='*70}

Signal Type:     {"🟢 LONG (BUY)" if side == "LONG" else "🔴 SHORT (SELL)"}
Confidence:      {confidence:.1f}% ⭐ (Above 65% threshold)
Market Regime:   {signal.get('market_regime', 'N/A')}

{'='*70}
💰 ENTRY DETAILS
{'='*70}
Entry Price:     ${entry_price:,.2f}
Current Price:   ${current_price:,.2f}

Stop Loss:       ${stop_loss:,.2f} ({sl_pct:+.2f}%)
Take Profit:     ${take_profit:,.2f} ({tp_pct:+.2f}%)

Risk/Reward:     1:{risk_reward:.2f}

{'='*70}
📊 SIGNAL CONDITIONS MET ({len(conditions)})
{'='*70}
"""

        # List all conditions that triggered
        for i, condition in enumerate(conditions, 1):
            body += f"{i}. {condition.replace('_', ' ').title()}\n"

        body += f"""
{'='*70}
💡 SUGGESTED POSITION SIZING
{'='*70}
Risk per Trade:  1-2% of capital
Position Size:   Calculate based on stop loss distance
Leverage:        5x (configured)

Example with $1,000 balance:
• Risk Amount:   $10-20 (1-2%)
• Position Size: $50-100 (5-10% of balance)
• With 5x Leverage: Up to $500 notional value

{'='*70}
⚠️ RISK MANAGEMENT CHECKLIST
{'='*70}
✓ Verify stop loss is set at ${stop_loss:,.2f}
✓ Verify take profit is set at ${take_profit:,.2f}
✓ Confirm position size matches risk tolerance
✓ Check market conditions (avoid high volatility news events)
✓ Monitor position actively (scalping = short-term trades)
✓ Close position within 3 minutes if momentum fails

{'='*70}
📈 TECHNICAL DETAILS
{'='*70}
"""

        # Add any additional signal metadata
        if 'rsi' in signal:
            body += f"RSI(14):         {signal['rsi']:.2f}\n"
        if 'ema_fast' in signal:
            body += f"EMA(5):          ${signal['ema_fast']:,.2f}\n"
        if 'ema_slow' in signal:
            body += f"EMA(21):         ${signal['ema_slow']:,.2f}\n"
        if 'volume_ratio' in signal:
            body += f"Volume Ratio:    {signal['volume_ratio']:.2f}x average\n"

        body += f"""
{'='*70}
⚠️ IMPORTANT DISCLAIMERS
{'='*70}
• This is an automated signal, NOT financial advice
• Past performance does not guarantee future results
• Only trade with capital you can afford to lose
• Stop trading after 3% daily loss (circuit breaker)
• This is paper trading mode - verify before live trading
• Always monitor positions actively

{'='*70}
📧 Notification Settings
{'='*70}
Cooldown:        {self.cooldown_seconds // 60} minutes between emails
Confidence Min:  65% (only high-quality signals)
Recipient:       {self.recipient_email}

---
Bitcoin Scalping Bot v2.0
Sent: {timestamp}
Mode: Paper Trading
"""

        return body

    def send_trade_notification(self, trade_type: str, side: str, entry_price: float,
                                 quantity: float, position_size_usd: float) -> bool:
        """
        Send email when trade is opened or closed

        Args:
            trade_type: 'OPEN' or 'CLOSE'
            side: 'LONG' or 'SHORT'
            entry_price: Trade entry price
            quantity: BTC quantity
            position_size_usd: Position size in USD
        """
        if trade_type == 'OPEN' and not self.send_on_trade_open:
            return False
        if trade_type == 'CLOSE' and not self.send_on_trade_close:
            return False

        if not self.should_send_email(f'trade_{trade_type}'):
            return False

        try:
            emoji = "🟢" if side == "LONG" else "🔴"
            subject = f"[BTC-SCALPING] {emoji} Trade {trade_type}: {side} ${position_size_usd:.2f}"

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            body = f"""Bitcoin Scalping Bot v2.0 - Trade {trade_type}
{timestamp}

{'='*70}
{'🚀 POSITION OPENED' if trade_type == 'OPEN' else '🏁 POSITION CLOSED'}
{'='*70}

Direction:       {emoji} {side}
Entry Price:     ${entry_price:,.2f}
Quantity:        {quantity:.6f} BTC
Position Size:   ${position_size_usd:,.2f}

{'='*70}
Bitcoin Scalping Bot v2.0
"""

            success = self._send_email(subject, body)

            if success:
                self.last_email_time[f'trade_{trade_type}'] = datetime.now().timestamp()
                logger.info(f"✅ Trade {trade_type} notification sent")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to send trade email: {e}")
            return False

    def _send_email(self, subject: str, body: str) -> bool:
        """Send email via SMTP"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'plain'))

            # Create SMTP session
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)

            if self.smtp_use_tls:
                server.starttls()

            # Login
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)

            # Send email
            server.sendmail(self.sender_email, self.recipient_email, msg.as_string())
            server.quit()

            return True

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

    def send_test_email(self) -> bool:
        """Send test email to verify configuration"""
        subject = "[BTC-SCALPING] 📧 Test Email - Notification System"

        body = f"""This is a test email from Bitcoin Scalping Bot v2.0

System Configuration:
• SMTP Server: {self.smtp_server}:{self.smtp_port}
• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• Recipient: {self.recipient_email}

✅ If you received this email, the notification system is working correctly.

Notification Preferences:
• Signal Alerts: {'Enabled' if self.send_on_signal else 'Disabled'}
• Trade Open: {'Enabled' if self.send_on_trade_open else 'Disabled'}
• Trade Close: {'Enabled' if self.send_on_trade_close else 'Disabled'}
• Error Alerts: {'Enabled' if self.send_on_error else 'Disabled'}

Cooldown: {self.cooldown_seconds // 60} minutes between similar emails

---
Bitcoin Scalping Bot v2.0
Paper Trading Mode
"""

        return self._send_email(subject, body)


# CLI interface for testing
if __name__ == "__main__":
    import sys
    import os

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        print("🧪 Sending test email...")

        # Try to find email_config.json in parent directory
        config_path = 'email_config.json'
        if not os.path.exists(config_path):
            config_path = '../../email_config.json'

        try:
            notifier = ScalpingEmailNotifier(config_path)
            if notifier.enabled:
                success = notifier.send_test_email()
                if success:
                    print("✅ Test email sent successfully!")
                else:
                    print("❌ Failed to send test email")
                    sys.exit(1)
            else:
                print("❌ Email notifier not enabled - check configuration")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    else:
        print("Usage: python email_notifier.py test")
        print("This will send a test email to verify configuration.")
