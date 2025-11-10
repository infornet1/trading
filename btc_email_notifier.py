#!/usr/bin/env python3
"""
Bitcoin Trading Alert Email Notification System
Sends email alerts for trading opportunities detected by BTC monitor
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import json

logger = logging.getLogger('BTCEmailNotifier')


class BTCEmailNotifier:
    """Email notification service for Bitcoin trading alerts"""

    def __init__(self, config_file='email_config.json'):
        """Initialize email notifier with configuration"""
        self.load_config(config_file)
        logger.info(f"Email service initialized - Server: {self.smtp_server}:{self.smtp_port}")

    def load_config(self, config_file):
        """Load email configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            # Default configuration
            config = {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_use_tls": True,
                "sender_email": "finanzas@ueipab.edu.ve",
                "smtp_username": "finanzas@ueipab.edu.ve",
                "smtp_password": "hcoe hawe gwwn mcvc",
                "recipient_email": "perdomo.gustavo@gmail.com",
                "send_on_oversold": True,
                "send_on_overbought": True,
                "send_on_ema_cross": True,
                "send_on_support_resistance": True,
                "send_on_rapid_change": True,
                "alert_cooldown_minutes": 15
            }

        self.smtp_server = config.get('smtp_server')
        self.smtp_port = config.get('smtp_port')
        self.smtp_use_tls = config.get('smtp_use_tls', True)
        self.smtp_username = config.get('smtp_username')
        self.smtp_password = config.get('smtp_password')
        self.sender_email = config.get('sender_email')
        self.recipient_email = config.get('recipient_email')

        # Alert preferences
        self.alert_preferences = {
            'RSI_OVERSOLD': config.get('send_on_oversold', True),
            'RSI_OVERBOUGHT': config.get('send_on_overbought', True),
            'EMA_BULLISH_CROSS': config.get('send_on_ema_cross', True),
            'EMA_BEARISH_CROSS': config.get('send_on_ema_cross', True),
            'NEAR_SUPPORT': config.get('send_on_support_resistance', True),
            'NEAR_RESISTANCE': config.get('send_on_support_resistance', True),
            'RAPID_PRICE_CHANGE': config.get('send_on_rapid_change', True)
        }

        self.alert_cooldown = config.get('alert_cooldown_minutes', 15) * 60  # Convert to seconds
        self.last_alert_time = {}

    def should_send_alert(self, alert_type: str) -> bool:
        """Check if alert should be sent based on preferences and cooldown"""
        # Check if alert type is enabled
        if not self.alert_preferences.get(alert_type, True):
            return False

        # Check cooldown period
        now = datetime.now().timestamp()
        last_sent = self.last_alert_time.get(alert_type, 0)

        if (now - last_sent) < self.alert_cooldown:
            return False

        return True

    def send_alert_email(self, alerts: list, price_data: dict, indicators: dict) -> bool:
        """
        Send trading alert email

        Args:
            alerts: List of alert dictionaries
            price_data: Current price information
            indicators: Technical indicator values

        Returns:
            bool: True if email sent successfully
        """
        if not alerts:
            return False

        # Filter alerts based on preferences and cooldown
        alerts_to_send = [
            alert for alert in alerts
            if self.should_send_alert(alert['type'])
        ]

        if not alerts_to_send:
            logger.info("No alerts to send after filtering")
            return False

        try:
            # Check for conflicting signals
            buy_signals = [a for a in alerts_to_send if a['type'] in ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS']]
            sell_signals = [a for a in alerts_to_send if a['type'] in ['RSI_OVERBOUGHT', 'NEAR_RESISTANCE', 'EMA_BEARISH_CROSS']]

            has_conflict = len(buy_signals) > 0 and len(sell_signals) > 0

            # Determine subject based on severity and conflicts
            if has_conflict:
                subject_prefix = "⚠️ CONFLICTING SIGNALS - DO NOT TRADE"
            else:
                high_priority = any(a['severity'] == 'HIGH' for a in alerts_to_send)
                subject_prefix = "🚨 HIGH PRIORITY" if high_priority else "📊 Trading Alert"

            subject = f"[BTC-SCALPING] {subject_prefix} - {len(alerts_to_send)} Signal(s) Detected"

            # Build email body
            body = self._build_alert_body(alerts_to_send, price_data, indicators, has_conflict)

            # Send email
            success = self._send_email(subject, body)

            if success:
                # Update last alert times
                for alert in alerts_to_send:
                    self.last_alert_time[alert['type']] = datetime.now().timestamp()
                logger.info(f"Alert email sent: {len(alerts_to_send)} alerts")

            return success

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    def _build_alert_body(self, alerts: list, price_data: dict, indicators: dict, has_conflict: bool = False) -> str:
        """Build formatted email body with alert details"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        current_price = price_data.get('price', 0)

        # Group alerts by action type
        buy_signals = []
        sell_signals = []
        warning_signals = []

        for alert in alerts:
            alert_type = alert['type']
            if alert_type in ['RSI_OVERSOLD', 'NEAR_SUPPORT', 'EMA_BULLISH_CROSS']:
                buy_signals.append(alert)
            elif alert_type in ['RSI_OVERBOUGHT', 'NEAR_RESISTANCE', 'EMA_BEARISH_CROSS']:
                sell_signals.append(alert)
            else:
                warning_signals.append(alert)

        body = f"""Bitcoin Scalping Trading Alert - {timestamp}

{'='*70}
💰 CURRENT MARKET STATUS
{'='*70}
Price: ${current_price:,.2f}
"""

        if price_data.get('price_change_24h') is not None:
            change = price_data['price_change_24h']
            emoji = "📈" if change >= 0 else "📉"
            body += f"24h Change: {emoji} {change:.2f}%\n"

        body += f"\n📊 TECHNICAL INDICATORS:\n"
        if indicators.get('rsi'):
            body += f"   RSI(14): {indicators['rsi']:.2f}\n"
        if indicators.get('ema_fast') and indicators.get('ema_slow'):
            trend = "Bullish" if indicators['ema_fast'] > indicators['ema_slow'] else "Bearish"
            body += f"   EMA(5): ${indicators['ema_fast']:,.2f}\n"
            body += f"   EMA(15): ${indicators['ema_slow']:,.2f} - {trend}\n"
        if indicators.get('support') and indicators.get('resistance'):
            support = indicators['support']
            resistance = indicators['resistance']
            body += f"   Support: ${support:,.2f}\n"
            body += f"   Resistance: ${resistance:,.2f}\n"

            # Calculate room to move
            room_to_resistance = ((resistance - current_price) / current_price) * 100
            room_to_support = ((current_price - support) / current_price) * 100
            body += f"   Room to Resistance: {room_to_resistance:.2f}%\n"
            body += f"   Room to Support: {room_to_support:.2f}%\n"

        # CONFLICT WARNING
        if has_conflict:
            body += f"\n{'='*70}\n"
            body += f"⚠️  WARNING: CONFLICTING SIGNALS DETECTED\n"
            body += f"{'='*70}\n"
            body += f"🚫 DO NOT TRADE - Both BUY and SELL signals are present!\n\n"
            body += f"Why this happens:\n"
            body += f"• Price is squeezed between support and resistance\n"
            body += f"• Not enough room for profit target (need 0.5% minimum)\n"
            body += f"• High risk of whipsaw (getting stopped both ways)\n"
            body += f"• Market indecision - wait for clear breakout\n\n"
            body += f"RECOMMENDED ACTION:\n"
            body += f"• SIT OUT and wait for clarity\n"
            body += f"• Wait for breakout ABOVE resistance (LONG signal)\n"
            body += f"• Wait for breakdown BELOW support (SHORT signal)\n"
            body += f"• Missing a trade is better than a losing trade\n\n"

        # Buy signals
        if buy_signals and not has_conflict:
            body += f"\n{'='*70}\n"
            body += f"🟢 BUY SIGNALS ({len(buy_signals)})\n"
            body += f"{'='*70}\n"
            for alert in buy_signals:
                body += f"• [{alert['type']}] {alert['message']}\n"

            body += f"\n💡 SUGGESTED ACTION:\n"
            body += f"   → Consider LONG position\n"
            body += f"   → Entry: ${current_price:,.2f}\n"
            body += f"   → Stop Loss: ${current_price * 0.997:,.2f} (-0.3%)\n"
            body += f"   → Take Profit: ${current_price * 1.005:,.2f} (+0.5%)\n"
            body += f"   → Risk: 1% of capital max\n"

        # Sell signals
        if sell_signals and not has_conflict:
            body += f"\n{'='*70}\n"
            body += f"🔴 SELL SIGNALS ({len(sell_signals)})\n"
            body += f"{'='*70}\n"
            for alert in sell_signals:
                body += f"• [{alert['type']}] {alert['message']}\n"

            body += f"\n💡 SUGGESTED ACTION:\n"
            body += f"   → Consider SHORT position or take profits\n"
            body += f"   → Entry: ${current_price:,.2f}\n"
            body += f"   → Stop Loss: ${current_price * 1.003:,.2f} (+0.3%)\n"
            body += f"   → Take Profit: ${current_price * 0.995:,.2f} (-0.5%)\n"
            body += f"   → Risk: 1% of capital max\n"

        # Warning signals
        if warning_signals:
            body += f"\n{'='*70}\n"
            body += f"⚠️  MARKET ALERTS ({len(warning_signals)})\n"
            body += f"{'='*70}\n"
            for alert in warning_signals:
                body += f"• [{alert['type']}] {alert['message']}\n"

        body += f"\n{'='*70}\n"
        body += f"⚠️  RISK MANAGEMENT REMINDERS:\n"
        body += f"{'='*70}\n"
        body += f"• Only risk 1-2% of capital per trade\n"
        body += f"• Always use stop-loss orders\n"
        body += f"• Account for exchange fees (0.1-0.4%)\n"
        body += f"• Stop trading after 3-5% daily loss\n"
        body += f"• This is NOT financial advice - DYOR\n"

        body += f"\n{'='*70}\n"
        body += f"📧 Alert Settings:\n"
        body += f"   Cooldown: {self.alert_cooldown // 60} minutes between similar alerts\n"
        body += f"   Recipient: {self.recipient_email}\n"
        body += f"\n---\n"
        body += f"Bitcoin Scalping Monitor\n"
        body += f"Sent: {timestamp}\n"

        return body

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

            # Login if credentials provided
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)

            # Send email
            server.sendmail(self.sender_email, self.recipient_email, msg.as_string())
            server.quit()

            logger.info(f"Email sent successfully to {self.recipient_email}")
            return True

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            return False

    def send_test_email(self) -> bool:
        """Send test email to verify configuration"""
        subject = "[BTC-SCALPING] 📧 Test Email - System Configuration"

        body = f"""This is a test email from the Bitcoin Scalping Monitor.

System Information:
• SMTP Server: {self.smtp_server}:{self.smtp_port}
• Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• Recipient: {self.recipient_email}

If you received this email, the notification system is working correctly.

Alert Preferences:
• RSI Oversold: {'Enabled' if self.alert_preferences.get('RSI_OVERSOLD') else 'Disabled'}
• RSI Overbought: {'Enabled' if self.alert_preferences.get('RSI_OVERBOUGHT') else 'Disabled'}
• EMA Crossovers: {'Enabled' if self.alert_preferences.get('EMA_BULLISH_CROSS') else 'Disabled'}
• Support/Resistance: {'Enabled' if self.alert_preferences.get('NEAR_SUPPORT') else 'Disabled'}
• Rapid Price Changes: {'Enabled' if self.alert_preferences.get('RAPID_PRICE_CHANGE') else 'Disabled'}

Alert Cooldown: {self.alert_cooldown // 60} minutes between similar alerts

System Status: Email configuration verified ✅

---
Bitcoin Scalping Monitor
"""

        return self._send_email(subject, body)


# CLI interface for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        print("Sending test email...")
        email_service = BTCEmailNotifier()
        success = email_service.send_test_email()

        if success:
            print("✅ Test email sent successfully!")
        else:
            print("❌ Failed to send test email")
            sys.exit(1)
    else:
        print("Usage: python btc_email_notifier.py test")
        print("This will send a test email to verify configuration.")
