#!/usr/bin/env python3
"""
Supervisor Email Notifier - Sends email alerts and reports
Sends daily summaries, crash alerts, and weekly digests
"""

import os
import sys
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class SupervisorEmailNotifier:
    """Send email notifications for supervisor events"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize email notifier"""
        if config_path is None:
            # Try multiple locations
            possible_configs = [
                Path("/var/www/dev/trading/supervisor/email_config.json"),
                Path("/var/www/dev/trading/email_config.json"),
                Path("/var/www/dev/trading/scalping_v2/email_config.json"),
            ]

            for config in possible_configs:
                if config.exists():
                    config_path = str(config)
                    break

        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                self.config = json.load(f)
                # Normalize config keys (handle both sender_password and smtp_password)
                if 'smtp_password' in self.config and 'sender_password' not in self.config:
                    self.config['sender_password'] = self.config['smtp_password']
                if 'smtp_username' in self.config and 'sender_email' not in self.config:
                    self.config['sender_email'] = self.config['smtp_username']
        else:
            # Default configuration
            self.config = {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'sender_email': os.getenv('EMAIL_SENDER', ''),
                'sender_password': os.getenv('EMAIL_PASSWORD', ''),
                'recipient_email': os.getenv('EMAIL_RECIPIENT', 'perdomo.gustavo@gmail.com')
            }

    def send_email(self, subject: str, body_html: str, body_text: str = None) -> bool:
        """Send an email notification"""

        if not self.config.get('sender_email') or not self.config.get('sender_password'):
            print("⚠️  Email credentials not configured")
            return False

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config['sender_email']
            msg['To'] = self.config['recipient_email']

            # Add text and HTML parts
            if body_text:
                part1 = MIMEText(body_text, 'plain')
                msg.attach(part1)

            part2 = MIMEText(body_html, 'html')
            msg.attach(part2)

            # Send email
            with smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port']) as server:
                server.starttls()
                server.login(self.config['sender_email'], self.config['sender_password'])
                server.send_message(msg)

            print(f"✅ Email sent: {subject}")
            return True

        except Exception as e:
            print(f"❌ Failed to send email: {e}")
            return False

    def send_crash_alert(self, bot_name: str, restart_successful: bool, error_details: str = None):
        """Send immediate alert when bot crashes"""

        status_emoji = "✅" if restart_successful else "❌"
        status_text = "RESTARTED" if restart_successful else "RESTART FAILED"

        subject = f"🚨 Bot Supervisor Alert: {bot_name} {status_text}"

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .alert {{ background: #ff4444; color: white; padding: 20px; border-radius: 5px; }}
                .success {{ background: #44ff44; color: black; }}
                .warning {{ background: #ffaa44; color: black; }}
                .info {{ background: #f0f0f0; padding: 15px; margin: 10px 0; border-left: 4px solid #0066cc; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
                h2 {{ margin-top: 0; }}
            </style>
        </head>
        <body>
            <div class="alert {'success' if restart_successful else ''}">
                <h2>{status_emoji} Bot Supervisor Alert</h2>
                <p><strong>Bot:</strong> {bot_name}</p>
                <p><strong>Status:</strong> {status_text}</p>
                <p class="timestamp"><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>

            <div class="info">
                <h3>What Happened?</h3>
                <p>The supervisor detected that <strong>{bot_name}</strong> stopped running.</p>
                {'<p>✅ The bot was automatically restarted successfully.</p>' if restart_successful else
                 '<p>❌ Attempted to restart but failed. Manual intervention required!</p>'}
            </div>

            {f'<div class="info"><h3>Error Details:</h3><pre>{error_details}</pre></div>' if error_details else ''}

            <div class="info">
                <h3>Next Steps:</h3>
                {'<p>✅ No action required. Bot is back online and monitoring market conditions.</p>' if restart_successful else '''
                <ol>
                    <li>SSH into the server</li>
                    <li>Check bot logs: <code>journalctl -u {service} -n 100</code></li>
                    <li>Check system resources: <code>df -h && free -h</code></li>
                    <li>Manual restart: <code>systemctl restart {service}</code></li>
                </ol>
                '''}
            </div>

            <hr>
            <p style="color: #666; font-size: 0.8em;">
                Sent by Bot Supervisor System<br>
                Server: freescout.ueipab.edu.ve<br>
                Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </body>
        </html>
        """

        text = f"""
BOT SUPERVISOR ALERT

Bot: {bot_name}
Status: {status_text}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

What Happened?
The supervisor detected that {bot_name} stopped running.
{'The bot was automatically restarted successfully.' if restart_successful else 'Attempted to restart but FAILED. Manual intervention required!'}

{f'Error Details:\n{error_details}\n' if error_details else ''}

Sent by Bot Supervisor System
        """

        return self.send_email(subject, html, text)

    def send_daily_report(self, report_data: Dict):
        """Send comprehensive daily report"""

        market = report_data.get('market_conditions', {})
        bots = report_data.get('bots', {})
        timestamp = report_data.get('timestamp', datetime.now().isoformat())

        # Count issues
        total_issues = sum(len(bot.get('issues', [])) for bot in bots.values())
        all_healthy = all(bot.get('healthy', False) for bot in bots.values())

        status_emoji = "✅" if all_healthy and total_issues == 0 else "⚠️"

        subject = f"{status_emoji} Daily Bot Supervisor Report - {datetime.now().strftime('%Y-%m-%d')}"

        # Generate bot status rows
        bot_rows = ""
        for bot_key, bot_info in bots.items():
            name = bot_key.replace('_', ' ').title()
            status = "✅ Healthy" if bot_info.get('healthy') else "⚠️ Issues"
            running = "🟢 Running" if bot_info.get('running') else "🔴 Stopped"
            issues = len(bot_info.get('issues', []))

            bot_rows += f"""
            <tr>
                <td>{name}</td>
                <td>{running}</td>
                <td>{status}</td>
                <td>{issues}</td>
            </tr>
            """

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                          color: white; padding: 30px; border-radius: 10px; text-align: center; }}
                .section {{ background: #f9f9f9; padding: 20px; margin: 20px 0;
                           border-radius: 5px; border-left: 4px solid #667eea; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th {{ background: #667eea; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background: #f0f0f0; }}
                .metric {{ display: inline-block; margin: 10px 20px; }}
                .metric-value {{ font-size: 2em; font-weight: bold; color: #667eea; }}
                .metric-label {{ color: #666; font-size: 0.9em; }}
                .good {{ color: #44ff44; }}
                .warning {{ color: #ffaa44; }}
                .bad {{ color: #ff4444; }}
                .footer {{ text-align: center; color: #666; font-size: 0.8em; margin-top: 30px;
                          padding-top: 20px; border-top: 1px solid #ddd; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🤖 Bot Supervisor Daily Report</h1>
                <p>{datetime.now().strftime('%A, %B %d, %Y')}</p>
            </div>

            <div class="section">
                <h2>📊 Market Conditions</h2>
                <div class="metric">
                    <div class="metric-value">${market.get('btc_price', 0):,.2f}</div>
                    <div class="metric-label">BTC Price</div>
                </div>
                <div class="metric">
                    <div class="metric-value" style="color: {'#44ff44' if market.get('adx', 0) > 25 else '#ffaa44'}">{market.get('adx', 0):.1f}</div>
                    <div class="metric-label">ADX (Trend Strength)</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{market.get('regime', 'Unknown').title()}</div>
                    <div class="metric-label">Market Regime</div>
                </div>
                <div class="metric">
                    <div class="metric-value" style="color: {'#44ff44' if market.get('tradeable') else '#ff4444'}">
                        {'✅ Yes' if market.get('tradeable') else '❌ No'}
                    </div>
                    <div class="metric-label">Tradeable</div>
                </div>
            </div>

            <div class="section">
                <h2>🤖 Bot Health Status</h2>
                <table>
                    <tr>
                        <th>Bot</th>
                        <th>Process</th>
                        <th>Health</th>
                        <th>Issues</th>
                    </tr>
                    {bot_rows}
                </table>
            </div>

            <div class="section">
                <h2>📋 Summary</h2>
                <ul>
                    <li><strong>All Bots Running:</strong> {'✅ Yes' if all(b.get('running') for b in bots.values()) else '⚠️ Some stopped'}</li>
                    <li><strong>All Bots Healthy:</strong> {'✅ Yes' if all_healthy else '⚠️ Issues detected'}</li>
                    <li><strong>Total Issues:</strong> {total_issues}</li>
                    <li><strong>Market Conditions:</strong> {market.get('regime', 'Unknown').title()} ({'Tradeable' if market.get('tradeable') else 'Not Tradeable'})</li>
                </ul>
            </div>

            {'<div class="section"><h2>⚠️ Issues Detected</h2><ul>' +
             ''.join(f'<li><strong>{bot_key}:</strong> {", ".join(bot_info.get("issues", []))}</li>'
                     for bot_key, bot_info in bots.items() if bot_info.get('issues')) +
             '</ul></div>' if total_issues > 0 else ''}

            <div class="section">
                <h2>🎯 Supervisor Activity</h2>
                <p>The supervisor has been monitoring your bots continuously:</p>
                <ul>
                    <li>✅ Quick health checks every 5 minutes</li>
                    <li>✅ Full supervision every 15 minutes</li>
                    <li>✅ State cleanup every 6 hours</li>
                    <li>✅ Market condition analysis</li>
                </ul>
                <p>{'<strong>No crashes or restarts in the past 24 hours.</strong>' if total_issues == 0 else '<strong>See issues above for details.</strong>'}</p>
            </div>

            <div class="footer">
                <p>
                    <strong>Bot Supervisor System</strong><br>
                    Server: freescout.ueipab.edu.ve<br>
                    Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                    <br>
                    <a href="https://dev.ueipab.edu.ve:5900">View ADX Dashboard</a> |
                    <a href="https://dev.ueipab.edu.ve:5900/scalping/">View Scalping Dashboard</a>
                </p>
            </div>
        </body>
        </html>
        """

        text = f"""
BOT SUPERVISOR DAILY REPORT
{datetime.now().strftime('%Y-%m-%d')}

MARKET CONDITIONS
-----------------
BTC Price: ${market.get('btc_price', 0):,.2f}
ADX: {market.get('adx', 0):.1f}
Regime: {market.get('regime', 'Unknown').title()}
Tradeable: {'Yes' if market.get('tradeable') else 'No'}

BOT HEALTH STATUS
-----------------
"""
        for bot_key, bot_info in bots.items():
            name = bot_key.replace('_', ' ').title()
            status = "Healthy" if bot_info.get('healthy') else "Issues"
            running = "Running" if bot_info.get('running') else "Stopped"
            text += f"{name}: {running} - {status}\n"

        text += f"\nTotal Issues: {total_issues}\n"

        if total_issues > 0:
            text += "\nISSUES DETECTED:\n"
            for bot_key, bot_info in bots.items():
                if bot_info.get('issues'):
                    text += f"  {bot_key}: {', '.join(bot_info.get('issues'))}\n"

        text += "\n" + "="*50 + "\nSent by Bot Supervisor System\n"

        return self.send_email(subject, html, text)

    def send_weekly_digest(self, weekly_data: Dict):
        """Send weekly performance digest"""

        subject = f"📊 Weekly Bot Performance Digest - Week of {datetime.now().strftime('%Y-%m-%d')}"

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                          color: white; padding: 30px; border-radius: 10px; text-align: center; }}
                .section {{ background: #f9f9f9; padding: 20px; margin: 20px 0;
                           border-radius: 5px; border-left: 4px solid #f5576c; }}
                .metric {{ display: inline-block; margin: 10px 20px; text-align: center; }}
                .metric-value {{ font-size: 2em; font-weight: bold; color: #f5576c; }}
                .metric-label {{ color: #666; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Weekly Performance Digest</h1>
                <p>Week of {datetime.now().strftime('%B %d, %Y')}</p>
            </div>

            <div class="section">
                <h2>🎯 Supervisor Statistics</h2>
                <div class="metric">
                    <div class="metric-value">{weekly_data.get('total_checks', 0)}</div>
                    <div class="metric-label">Total Health Checks</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{weekly_data.get('restarts', 0)}</div>
                    <div class="metric-label">Bot Restarts</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{weekly_data.get('uptime_pct', 99.9):.1f}%</div>
                    <div class="metric-label">Uptime</div>
                </div>
            </div>

            <div class="section">
                <h2>📈 Bot Performance</h2>
                <p><strong>Scalping v2:</strong> {weekly_data.get('scalping_signals', 0)} signals generated</p>
                <p><strong>ADX v2:</strong> {weekly_data.get('adx_trades', 0)} trades executed</p>
            </div>

            <div class="section">
                <h2>💡 Insights</h2>
                <ul>
                    <li>Market was tradeable {weekly_data.get('tradeable_days', 0)} out of 7 days</li>
                    <li>Average ADX: {weekly_data.get('avg_adx', 0):.1f}</li>
                    <li>System uptime: {weekly_data.get('uptime_pct', 99.9):.1f}%</li>
                </ul>
            </div>

            <p style="text-align: center; color: #666; margin-top: 30px;">
                Sent by Bot Supervisor System
            </p>
        </body>
        </html>
        """

        return self.send_email(subject, html)

    def send_test_email(self):
        """Send a test email to verify configuration"""

        subject = "✅ Bot Supervisor Email Test"

        html = """
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background: #4CAF50; color: white; padding: 20px; border-radius: 5px;">
                <h2>✅ Email Configuration Working!</h2>
                <p>This is a test email from the Bot Supervisor System.</p>
            </div>
            <p style="margin-top: 20px;">
                If you received this email, your supervisor email notifications are properly configured.
            </p>
            <p style="color: #666; font-size: 0.9em;">
                Test sent at: {0}
            </p>
        </body>
        </html>
        """.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        text = f"""
EMAIL CONFIGURATION TEST

This is a test email from the Bot Supervisor System.
If you received this, email notifications are working correctly!

Test sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """

        return self.send_email(subject, html, text)


def main():
    """CLI interface for email notifier"""

    notifier = SupervisorEmailNotifier()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  supervisor_email_notifier.py --test")
        print("  supervisor_email_notifier.py --crash <bot_name> <success>")
        print("  supervisor_email_notifier.py --daily <report_json_file>")
        sys.exit(1)

    command = sys.argv[1]

    if command == '--test':
        print("Sending test email...")
        success = notifier.send_test_email()
        sys.exit(0 if success else 1)

    elif command == '--crash':
        bot_name = sys.argv[2] if len(sys.argv) > 2 else "Unknown Bot"
        success = sys.argv[3].lower() == 'true' if len(sys.argv) > 3 else False
        notifier.send_crash_alert(bot_name, success)

    elif command == '--daily':
        if len(sys.argv) > 2:
            report_file = sys.argv[2]
            with open(report_file, 'r') as f:
                report_data = json.load(f)
            notifier.send_daily_report(report_data)
        else:
            print("Error: Report JSON file path required")
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
