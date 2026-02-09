# automated_trading/alerts.py
"""
Alert System for Automated Trading

Sends email alerts for trading events with styling matching the existing pipeline.
Includes subtle distinction for LIVE vs PAPER trading.

Alert Levels:
- CRITICAL: Immediate attention required (circuit breaker, system error)
- WARNING: Review recommended (large loss, reconciliation issue)
- INFO: Informational only (trade executed, position closed)
"""

# Load .env file
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env')
from . import config
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from . import config
from .utils import (
    format_currency,
    format_percentage,
    format_datetime_for_display,
    log_audit_event
)

logger = logging.getLogger(__name__)


# Email styling constants (matching dashboard-v2.html)
COLORS = {
    'bg_main': '#0b1120',
    'bg_card': '#151e32',
    'primary': '#38bdf8',
    'success': '#00e676',
    'danger': '#ff5252',
    'warning': '#fbbf24',
    'text_main': '#f1f5f9',
    'text_muted': '#94a3b8',
    'border': '#334155',
    # Special color for LIVE trading indicator
    'live_accent': '#ff9800',  # Orange - subtle but distinguishing
    'paper_accent': '#38bdf8'  # Blue (primary)
}


class AlertSender:
    """
    Sends email alerts for trading events.

    Uses the same SMTP configuration as the existing pipeline.
    """

    def __init__(self):
        """Initialize alert sender."""
        self.gmail_user = config.GMAIL_USER
        self.gmail_password = config.GMAIL_APP_PASSWORD

        # Clean and validate recipient email
        raw_recipient = config.RECIPIENT_EMAIL
        if raw_recipient:
            # Strip whitespace and quotes
            self.recipient = raw_recipient.strip().strip('"').strip("'").strip()
            # Take first email if multiple provided (comma or semicolon separated)
            if ',' in self.recipient:
                self.recipient = self.recipient.split(',')[0].strip()
            elif ';' in self.recipient:
                self.recipient = self.recipient.split(';')[0].strip()
        else:
            self.recipient = None

        self.is_live = config.TRADING_MODE == 'live'

    def _get_mode_indicator(self) -> Tuple[str, str, str]:
        """
        Get the trading mode indicator for emails.

        Returns:
            Tuple of (emoji, label, color)
        """
        if self.is_live:
            return ('💰', 'LIVE TRADING', COLORS['live_accent'])
        else:
            return ('🧪', 'PAPER TRADING', COLORS['paper_accent'])

    def send_alert(
        self,
        subject: str,
        html_content: str,
        text_content: str,
        alert_level: str = 'INFO'
    ) -> bool:
        """
        Send an email alert.

        Args:
            subject: Email subject
            html_content: HTML body
            text_content: Plain text body
            alert_level: CRITICAL, WARNING, or INFO

        Returns:
            True if sent successfully
        """
        # Validate email configuration
        if not self.gmail_user:
            logger.error("GMAIL_USER not configured")
            return False
        if not self.gmail_password:
            logger.error("GMAIL_APP_PASSWORD not configured")
            return False
        if not self.recipient:
            logger.error("RECIPIENT_EMAIL not configured")
            return False

        # Validate recipient email format
        if '@' not in self.recipient or ' ' in self.recipient:
            logger.error(f"Invalid recipient email format: '{self.recipient}'")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.gmail_user
            msg['To'] = self.recipient

            # Attach plain text and HTML
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            msg.attach(part1)
            msg.attach(part2)

            # Send email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.gmail_user, self.gmail_password)
                server.sendmail(self.gmail_user, self.recipient, msg.as_string())

            log_audit_event('ALERT_SENT', {
                'subject': subject,
                'level': alert_level,
                'recipient': self.recipient
            })

            logger.info(f"✅ Alert sent successfully: {subject}")
            return True

        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"❌ Invalid recipient email address: {self.recipient}")
            logger.error(f"   SMTP error: {e}")
            log_audit_event('ALERT_FAILED', {
                'subject': subject,
                'error': f"Invalid recipient: {str(e)}"
            }, outcome='ERROR')
            return False

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ Gmail authentication failed - check GMAIL_USER and GMAIL_APP_PASSWORD")
            logger.error(f"   SMTP error: {e}")
            log_audit_event('ALERT_FAILED', {
                'subject': subject,
                'error': f"Authentication failed: {str(e)}"
            }, outcome='ERROR')
            return False

        except Exception as e:
            logger.error(f"❌ Failed to send alert: {e}")
            logger.error(f"   Subject: {subject}")
            logger.error(f"   Recipient: {self.recipient}")
            log_audit_event('ALERT_FAILED', {
                'subject': subject,
                'recipient': self.recipient,
                'error': str(e)
            }, outcome='ERROR')
            return False

    # =========================================================================
    # Trade Alerts
    # =========================================================================

    def send_trade_executed_alert(
        self,
        ticker: str,
        action: str,
        shares: int,
        price: float,
        total_value: float,
        reason: Optional[str] = None,
        pnl: Optional[float] = None,
        pnl_pct: Optional[float] = None
    ) -> bool:
        """
        Send alert when a trade is executed.

        Args:
            ticker: Stock ticker
            action: BUY or SELL
            shares: Number of shares
            price: Execution price
            total_value: Total trade value
            reason: Trade reason (for sells)
            pnl: Profit/loss (for sells)
            pnl_pct: P&L percentage (for sells)
        """
        mode_emoji, mode_label, mode_color = self._get_mode_indicator()
        timestamp = format_datetime_for_display(datetime.now())

        if action == 'BUY':
            action_emoji = '📈'
            action_color = COLORS['success']
            subject = f"{mode_emoji} {ticker}: BUY {shares} shares @ ${price:.2f}"
        else:
            action_emoji = '📉' if pnl and pnl < 0 else '✅'
            action_color = COLORS['success'] if pnl and pnl >= 0 else COLORS['danger']
            pnl_str = f" | P&L: {format_currency(pnl)} ({format_percentage(pnl_pct)})" if pnl is not None else ""
            subject = f"{mode_emoji} {ticker}: SOLD {shares} shares @ ${price:.2f}{pnl_str}"

        html = self._render_trade_alert_html(
            ticker=ticker,
            action=action,
            shares=shares,
            price=price,
            total_value=total_value,
            reason=reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
            timestamp=timestamp,
            mode_label=mode_label,
            mode_color=mode_color,
            action_emoji=action_emoji,
            action_color=action_color
        )

        text = self._render_trade_alert_text(
            ticker=ticker,
            action=action,
            shares=shares,
            price=price,
            total_value=total_value,
            reason=reason,
            pnl=pnl,
            pnl_pct=pnl_pct,
            timestamp=timestamp,
            mode_label=mode_label
        )

        return self.send_alert(subject, html, text, 'INFO')

    def _render_trade_alert_html(
        self,
        ticker: str,
        action: str,
        shares: int,
        price: float,
        total_value: float,
        reason: Optional[str],
        pnl: Optional[float],
        pnl_pct: Optional[float],
        timestamp: str,
        mode_label: str,
        mode_color: str,
        action_emoji: str,
        action_color: str
    ) -> str:
        """Render HTML for trade alert."""
        pnl_section = ""
        if action == 'SELL' and pnl is not None:
            pnl_color = COLORS['success'] if pnl >= 0 else COLORS['danger']
            pnl_sign = '+' if pnl >= 0 else ''
            pnl_section = f'''
            <tr>
                <td style="padding: 15px 0; border-top: 1px solid {COLORS['border']};">
                    <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                            <td width="50%" style="text-align: center;">
                                <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">PROFIT/LOSS</div>
                                <div style="font-size: 24px; font-weight: 700; color: {pnl_color};">{pnl_sign}${pnl:,.2f}</div>
                            </td>
                            <td width="50%" style="text-align: center;">
                                <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">RETURN</div>
                                <div style="font-size: 24px; font-weight: 700; color: {pnl_color};">{pnl_sign}{pnl_pct:.2f}%</div>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            '''

        reason_line = f"<div style='font-size: 13px; color: {COLORS['text_muted']}; margin-top: 10px;'>Reason: {reason}</div>" if reason else ""

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background: {COLORS['bg_main']}; color: {COLORS['text_main']}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: {COLORS['bg_main']};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px;">

                    <!-- Mode Indicator Banner -->
                    <tr>
                        <td style="background: {mode_color}; padding: 8px; text-align: center; border-radius: 8px 8px 0 0;">
                            <span style="color: #000; font-weight: 700; font-size: 12px; letter-spacing: 1px;">{mode_label}</span>
                        </td>
                    </tr>

                    <!-- Header -->
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 25px; text-align: center; border: 1px solid {COLORS['border']};">
                            <div style="font-size: 48px; margin-bottom: 10px;">{action_emoji}</div>
                            <h1 style="margin: 0; font-size: 28px; font-weight: 800; color: {COLORS['primary']};">
                                {action} EXECUTED
                            </h1>
                            <p style="margin: 10px 0 0 0; color: {COLORS['text_muted']}; font-size: 13px;">{timestamp}</p>
                        </td>
                    </tr>

                    <!-- Trade Details -->
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 25px; border: 1px solid {COLORS['border']}; border-top: none;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="text-align: center; padding-bottom: 20px;">
                                        <div style="font-size: 36px; font-weight: 800; color: {COLORS['primary']}; font-family: 'Courier New', monospace;">{ticker}</div>
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td width="33%" style="text-align: center; padding: 10px;">
                                                    <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">SHARES</div>
                                                    <div style="font-size: 20px; font-weight: 700; color: {COLORS['text_main']};">{shares}</div>
                                                </td>
                                                <td width="33%" style="text-align: center; padding: 10px;">
                                                    <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">PRICE</div>
                                                    <div style="font-size: 20px; font-weight: 700; color: {COLORS['text_main']};">${price:.2f}</div>
                                                </td>
                                                <td width="33%" style="text-align: center; padding: 10px;">
                                                    <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">TOTAL</div>
                                                    <div style="font-size: 20px; font-weight: 700; color: {action_color};">${total_value:,.2f}</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                {pnl_section}
                            </table>
                            {reason_line}
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px; text-align: center;">
                            <p style="margin: 0; font-size: 11px; color: {COLORS['text_muted']};">
                                Insider Cluster Watch — Automated Trading System
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    def _render_trade_alert_text(
        self,
        ticker: str,
        action: str,
        shares: int,
        price: float,
        total_value: float,
        reason: Optional[str],
        pnl: Optional[float],
        pnl_pct: Optional[float],
        timestamp: str,
        mode_label: str
    ) -> str:
        """Render plain text for trade alert."""
        lines = [
            f"{'='*50}",
            f"[{mode_label}] TRADE EXECUTED",
            f"{'='*50}",
            "",
            f"Action: {action}",
            f"Ticker: {ticker}",
            f"Shares: {shares}",
            f"Price: ${price:.2f}",
            f"Total: ${total_value:,.2f}",
        ]

        if reason:
            lines.append(f"Reason: {reason}")

        if pnl is not None:
            pnl_sign = '+' if pnl >= 0 else ''
            lines.append("")
            lines.append(f"P&L: {pnl_sign}${pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)")

        lines.extend([
            "",
            f"Time: {timestamp}",
            f"{'='*50}",
            "Insider Cluster Watch — Automated Trading System"
        ])

        return "\n".join(lines)

    # =========================================================================
    # Circuit Breaker Alerts
    # =========================================================================

    def send_circuit_breaker_alert(
        self,
        reason: str,
        daily_pnl: float,
        portfolio_value: float,
        action_taken: str
    ) -> bool:
        """
        Send CRITICAL alert when circuit breaker triggers.
        """
        mode_emoji, mode_label, mode_color = self._get_mode_indicator()
        timestamp = format_datetime_for_display(datetime.now())

        subject = f"🚨 {mode_emoji} CIRCUIT BREAKER TRIGGERED - Trading Halted"

        html = self._render_circuit_breaker_html(
            reason=reason,
            daily_pnl=daily_pnl,
            portfolio_value=portfolio_value,
            action_taken=action_taken,
            timestamp=timestamp,
            mode_label=mode_label,
            mode_color=mode_color
        )

        text = self._render_circuit_breaker_text(
            reason=reason,
            daily_pnl=daily_pnl,
            portfolio_value=portfolio_value,
            action_taken=action_taken,
            timestamp=timestamp,
            mode_label=mode_label
        )

        return self.send_alert(subject, html, text, 'CRITICAL')

    def _render_circuit_breaker_html(
        self,
        reason: str,
        daily_pnl: float,
        portfolio_value: float,
        action_taken: str,
        timestamp: str,
        mode_label: str,
        mode_color: str
    ) -> str:
        """Render HTML for circuit breaker alert."""
        pnl_pct = (daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0

        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background: {COLORS['bg_main']}; color: {COLORS['text_main']}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: {COLORS['bg_main']};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px;">

                    <!-- Mode Indicator Banner -->
                    <tr>
                        <td style="background: {mode_color}; padding: 8px; text-align: center; border-radius: 8px 8px 0 0;">
                            <span style="color: #000; font-weight: 700; font-size: 12px; letter-spacing: 1px;">{mode_label}</span>
                        </td>
                    </tr>

                    <!-- Critical Alert Header -->
                    <tr>
                        <td style="background: {COLORS['danger']}; padding: 25px; text-align: center;">
                            <div style="font-size: 48px; margin-bottom: 10px;">🚨</div>
                            <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #fff;">
                                CIRCUIT BREAKER TRIGGERED
                            </h1>
                            <p style="margin: 10px 0 0 0; color: rgba(255,255,255,0.8); font-size: 14px;">
                                Trading has been HALTED
                            </p>
                        </td>
                    </tr>

                    <!-- Details -->
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 25px; border: 1px solid {COLORS['border']};">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="padding-bottom: 20px;">
                                        <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase; margin-bottom: 5px;">REASON</div>
                                        <div style="font-size: 16px; font-weight: 600; color: {COLORS['danger']};">{reason}</div>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding-bottom: 20px;">
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td width="50%" style="padding: 10px;">
                                                    <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">DAILY P&L</div>
                                                    <div style="font-size: 24px; font-weight: 700; color: {COLORS['danger']};">${daily_pnl:,.2f}</div>
                                                    <div style="font-size: 14px; color: {COLORS['danger']};">({pnl_pct:.2f}%)</div>
                                                </td>
                                                <td width="50%" style="padding: 10px;">
                                                    <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">PORTFOLIO VALUE</div>
                                                    <div style="font-size: 24px; font-weight: 700; color: {COLORS['text_main']};">${portfolio_value:,.2f}</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="background: rgba(255,82,82,0.1); padding: 15px; border-radius: 8px;">
                                        <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase; margin-bottom: 5px;">ACTION TAKEN</div>
                                        <div style="font-size: 14px; color: {COLORS['text_main']};">{action_taken}</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px; text-align: center;">
                            <p style="margin: 0; font-size: 13px; color: {COLORS['text_muted']};">
                                Time: {timestamp}
                            </p>
                            <p style="margin: 10px 0 0 0; font-size: 11px; color: {COLORS['text_muted']};">
                                Insider Cluster Watch — Automated Trading System
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    def _render_circuit_breaker_text(
        self,
        reason: str,
        daily_pnl: float,
        portfolio_value: float,
        action_taken: str,
        timestamp: str,
        mode_label: str
    ) -> str:
        """Render plain text for circuit breaker alert."""
        pnl_pct = (daily_pnl / portfolio_value * 100) if portfolio_value > 0 else 0

        return f"""{'='*50}
🚨 [{mode_label}] CIRCUIT BREAKER TRIGGERED
{'='*50}

TRADING HAS BEEN HALTED

Reason: {reason}

Daily P&L: ${daily_pnl:,.2f} ({pnl_pct:.2f}%)
Portfolio Value: ${portfolio_value:,.2f}

Action Taken: {action_taken}

Time: {timestamp}

{'='*50}
Insider Cluster Watch — Automated Trading System
"""

    # =========================================================================
    # Reconciliation Alerts
    # =========================================================================

    def send_reconciliation_alert(
        self,
        discrepancies: List[Dict[str, Any]]
    ) -> bool:
        """
        Send WARNING alert when position reconciliation fails.
        """
        mode_emoji, mode_label, mode_color = self._get_mode_indicator()
        timestamp = format_datetime_for_display(datetime.now())

        subject = f"⚠️ {mode_emoji} Position Reconciliation Failed - {len(discrepancies)} Discrepancies"

        html = self._render_reconciliation_html(
            discrepancies=discrepancies,
            timestamp=timestamp,
            mode_label=mode_label,
            mode_color=mode_color
        )

        text = self._render_reconciliation_text(
            discrepancies=discrepancies,
            timestamp=timestamp,
            mode_label=mode_label
        )

        return self.send_alert(subject, html, text, 'WARNING')

    def _render_reconciliation_html(
        self,
        discrepancies: List[Dict],
        timestamp: str,
        mode_label: str,
        mode_color: str
    ) -> str:
        """Render HTML for reconciliation alert."""
        discrepancy_rows = ""
        for d in discrepancies:
            discrepancy_rows += f'''
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid {COLORS['border']};">
                    <span style="font-weight: 700; color: {COLORS['primary']};">{d.get('ticker', 'N/A')}</span>
                </td>
                <td style="padding: 10px; border-bottom: 1px solid {COLORS['border']}; color: {COLORS['text_muted']};">
                    {d.get('type', 'Unknown')}
                </td>
                <td style="padding: 10px; border-bottom: 1px solid {COLORS['border']};">
                    Local: {d.get('local_qty', 0)} | Broker: {d.get('broker_qty', 0)}
                </td>
            </tr>
            '''

        return f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin: 0; padding: 0; background: {COLORS['bg_main']}; color: {COLORS['text_main']}; font-family: -apple-system, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: {COLORS['bg_main']};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px;">
                    <tr>
                        <td style="background: {mode_color}; padding: 8px; text-align: center; border-radius: 8px 8px 0 0;">
                            <span style="color: #000; font-weight: 700; font-size: 12px;">{mode_label}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="background: {COLORS['warning']}; padding: 20px; text-align: center;">
                            <div style="font-size: 36px;">⚠️</div>
                            <h1 style="margin: 10px 0 0 0; font-size: 20px; color: #000;">RECONCILIATION FAILED</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 20px; border: 1px solid {COLORS['border']};">
                            <p style="color: {COLORS['text_muted']}; margin: 0 0 15px 0;">
                                Position state does not match broker. Manual review required.
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" style="font-size: 13px;">
                                <tr style="background: rgba(255,255,255,0.05);">
                                    <th style="padding: 10px; text-align: left; color: {COLORS['text_muted']};">Ticker</th>
                                    <th style="padding: 10px; text-align: left; color: {COLORS['text_muted']};">Type</th>
                                    <th style="padding: 10px; text-align: left; color: {COLORS['text_muted']};">Quantities</th>
                                </tr>
                                {discrepancy_rows}
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: {COLORS['text_muted']};">{timestamp}</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    def _render_reconciliation_text(
        self,
        discrepancies: List[Dict],
        timestamp: str,
        mode_label: str
    ) -> str:
        """Render plain text for reconciliation alert."""
        lines = [
            f"{'='*50}",
            f"[{mode_label}] RECONCILIATION FAILED",
            f"{'='*50}",
            "",
            "Position state does not match broker. Manual review required.",
            "",
            "Discrepancies:"
        ]

        for d in discrepancies:
            lines.append(f"  - {d.get('ticker', 'N/A')}: {d.get('type', 'Unknown')}")
            lines.append(f"    Local: {d.get('local_qty', 0)} | Broker: {d.get('broker_qty', 0)}")

        lines.extend([
            "",
            f"Time: {timestamp}",
            f"{'='*50}"
        ])

        return "\n".join(lines)

    # =========================================================================
    # Batch Trade Alerts (Email Volume Reduction)
    # =========================================================================

    def send_morning_trades_batch_alert(
        self,
        trades: List[Dict[str, Any]],
        summary: Dict[str, Any]
    ) -> bool:
        """
        Send ONE consolidated email for all morning trades.

        This replaces individual trade alerts to reduce email volume.

        Args:
            trades: List of executed trades with details
            summary: Overall execution summary

        Returns:
            True if sent successfully
        """
        if not trades:
            logger.info("No morning trades to alert")
            return True

        mode_emoji, mode_label, mode_color = self._get_mode_indicator()
        timestamp = format_datetime_for_display(datetime.now())
        total_value = sum(t['total_value'] for t in trades)

        subject = f"{mode_emoji} Morning Trades: {len(trades)} positions opened (${total_value:,.0f})"

        html = self._render_morning_batch_html(
            trades=trades,
            summary=summary,
            timestamp=timestamp,
            mode_label=mode_label,
            mode_color=mode_color
        )

        text = self._render_morning_batch_text(
            trades=trades,
            summary=summary,
            timestamp=timestamp,
            mode_label=mode_label
        )

        return self.send_alert(subject, html, text, 'INFO')

    def _render_morning_batch_html(
        self,
        trades: List[Dict],
        summary: Dict,
        timestamp: str,
        mode_label: str,
        mode_color: str
    ) -> str:
        """Render HTML for morning batch alert."""
        total_value = sum(t['total_value'] for t in trades)

        # Build trade rows
        trade_rows = ""
        for t in trades:
            trade_rows += f'''
            <tr style="border-bottom: 1px solid {COLORS['border']};">
                <td style="padding: 12px; font-weight: 700; color: {COLORS['primary']}; font-family: 'Courier New', monospace;">
                    {t['ticker']}
                </td>
                <td style="padding: 12px; text-align: right; color: {COLORS['text_main']};">
                    {t['shares']}
                </td>
                <td style="padding: 12px; text-align: right; color: {COLORS['text_main']};">
                    ${t['price']:.2f}
                </td>
                <td style="padding: 12px; text-align: right; font-weight: 600; color: {COLORS['success']};">
                    ${t['total_value']:,.0f}
                </td>
            </tr>
            '''

        return f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin: 0; padding: 0; background: {COLORS['bg_main']}; color: {COLORS['text_main']}; font-family: -apple-system, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: {COLORS['bg_main']};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px;">
                    <tr>
                        <td style="background: {mode_color}; padding: 8px; text-align: center; border-radius: 8px 8px 0 0;">
                            <span style="color: #000; font-weight: 700; font-size: 12px;">{mode_label}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 25px; text-align: center; border: 1px solid {COLORS['border']};">
                            <div style="font-size: 48px; margin-bottom: 10px;">📈</div>
                            <h1 style="margin: 0; font-size: 24px; color: {COLORS['primary']};">Morning Trades Executed</h1>
                            <p style="margin: 10px 0 0 0; color: {COLORS['text_muted']}; font-size: 13px;">{timestamp}</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 25px; border: 1px solid {COLORS['border']}; border-top: none;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 20px;">
                                <tr>
                                    <td width="33%" style="text-align: center; padding: 10px;">
                                        <div style="font-size: 28px; font-weight: 700; color: {COLORS['success']};">{len(trades)}</div>
                                        <div style="font-size: 12px; color: {COLORS['text_muted']};">POSITIONS</div>
                                    </td>
                                    <td width="33%" style="text-align: center; padding: 10px;">
                                        <div style="font-size: 28px; font-weight: 700; color: {COLORS['success']};">${total_value:,.0f}</div>
                                        <div style="font-size: 12px; color: {COLORS['text_muted']};">DEPLOYED</div>
                                    </td>
                                    <td width="33%" style="text-align: center; padding: 10px;">
                                        <div style="font-size: 28px; font-weight: 700; color: {COLORS['text_muted']};">{summary.get('queued_for_later', 0)}</div>
                                        <div style="font-size: 12px; color: {COLORS['text_muted']};">QUEUED</div>
                                    </td>
                                </tr>
                            </table>

                            <table width="100%" cellpadding="0" cellspacing="0" style="font-size: 13px; border: 1px solid {COLORS['border']}; border-radius: 8px;">
                                <tr style="background: rgba(56, 189, 248, 0.1);">
                                    <th style="padding: 12px; text-align: left; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;">Ticker</th>
                                    <th style="padding: 12px; text-align: right; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;">Shares</th>
                                    <th style="padding: 12px; text-align: right; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;">Price</th>
                                    <th style="padding: 12px; text-align: right; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;">Value</th>
                                </tr>
                                {trade_rows}
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px; text-align: center;">
                            <p style="margin: 0; font-size: 11px; color: {COLORS['text_muted']};">
                                Insider Cluster Watch — Automated Trading System
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    def _render_morning_batch_text(
        self,
        trades: List[Dict],
        summary: Dict,
        timestamp: str,
        mode_label: str
    ) -> str:
        """Render plain text for morning batch alert."""
        total_value = sum(t['total_value'] for t in trades)

        lines = [
            f"{'='*50}",
            f"[{mode_label}] MORNING TRADES EXECUTED",
            f"{'='*50}",
            "",
            f"Positions Opened: {len(trades)}",
            f"Capital Deployed: ${total_value:,.0f}",
            f"Queued for Later: {summary.get('queued_for_later', 0)}",
            "",
            "Trades:",
            ""
        ]

        for t in trades:
            lines.append(f"  {t['ticker']:<6} {t['shares']:>4} shares @ ${t['price']:.2f} = ${t['total_value']:,.0f}")

        lines.extend([
            "",
            f"Time: {timestamp}",
            f"{'='*50}",
            "Insider Cluster Watch — Automated Trading System"
        ])

        return "\n".join(lines)

    def send_intraday_redeployment_alert(
        self,
        ticker: str,
        shares: int,
        price: float,
        total_value: float,
        reason: str = "Capital Redeployment"
    ) -> bool:
        """
        Send alert for intraday capital redeployment.

        This is separate from morning trades and only sent when
        a position is sold mid-day and capital is redeployed.

        Args:
            ticker: Stock ticker
            shares: Number of shares
            price: Execution price
            total_value: Total trade value
            reason: Redeployment reason

        Returns:
            True if sent successfully
        """
        mode_emoji, mode_label, mode_color = self._get_mode_indicator()
        timestamp = format_datetime_for_display(datetime.now())

        subject = f"{mode_emoji} Intraday Redeployment: {ticker} - {shares} shares @ ${price:.2f}"

        html = self._render_redeployment_html(
            ticker=ticker,
            shares=shares,
            price=price,
            total_value=total_value,
            reason=reason,
            timestamp=timestamp,
            mode_label=mode_label,
            mode_color=mode_color
        )

        text = self._render_redeployment_text(
            ticker=ticker,
            shares=shares,
            price=price,
            total_value=total_value,
            reason=reason,
            timestamp=timestamp,
            mode_label=mode_label
        )

        return self.send_alert(subject, html, text, 'INFO')

    def _render_redeployment_html(
        self,
        ticker: str,
        shares: int,
        price: float,
        total_value: float,
        reason: str,
        timestamp: str,
        mode_label: str,
        mode_color: str
    ) -> str:
        """Render HTML for intraday redeployment alert."""
        return f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin: 0; padding: 0; background: {COLORS['bg_main']}; color: {COLORS['text_main']}; font-family: -apple-system, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: {COLORS['bg_main']};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px;">
                    <tr>
                        <td style="background: {mode_color}; padding: 8px; text-align: center; border-radius: 8px 8px 0 0;">
                            <span style="color: #000; font-weight: 700; font-size: 12px;">{mode_label}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="background: {COLORS['warning']}; padding: 20px; text-align: center;">
                            <div style="font-size: 36px; margin-bottom: 10px;">🔄</div>
                            <h1 style="margin: 0; font-size: 20px; color: #000; font-weight: 700;">INTRADAY REDEPLOYMENT</h1>
                            <p style="margin: 5px 0 0 0; color: rgba(0,0,0,0.7); font-size: 12px;">Capital redeployed mid-day</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 25px; text-align: center; border: 1px solid {COLORS['border']};">
                            <div style="font-size: 36px; font-weight: 800; color: {COLORS['primary']}; font-family: 'Courier New', monospace; margin-bottom: 20px;">
                                {ticker}
                            </div>
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td width="33%" style="text-align: center; padding: 10px;">
                                        <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">SHARES</div>
                                        <div style="font-size: 20px; font-weight: 700; color: {COLORS['text_main']};">{shares}</div>
                                    </td>
                                    <td width="33%" style="text-align: center; padding: 10px;">
                                        <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">PRICE</div>
                                        <div style="font-size: 20px; font-weight: 700; color: {COLORS['text_main']};">${price:.2f}</div>
                                    </td>
                                    <td width="33%" style="text-align: center; padding: 10px;">
                                        <div style="font-size: 12px; color: {COLORS['text_muted']}; text-transform: uppercase;">TOTAL</div>
                                        <div style="font-size: 20px; font-weight: 700; color: {COLORS['success']};">${total_value:,.0f}</div>
                                    </td>
                                </tr>
                            </table>
                            <div style="margin-top: 20px; padding: 15px; background: rgba(251, 191, 36, 0.1); border-radius: 8px;">
                                <div style="font-size: 11px; color: {COLORS['text_muted']}; text-transform: uppercase; margin-bottom: 5px;">REASON</div>
                                <div style="font-size: 13px; color: {COLORS['text_main']};">{reason}</div>
                            </div>
                            <p style="margin: 15px 0 0 0; color: {COLORS['text_muted']}; font-size: 12px;">{timestamp}</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px; text-align: center;">
                            <p style="margin: 0; font-size: 11px; color: {COLORS['text_muted']};">
                                Insider Cluster Watch — Automated Trading System
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    def _render_redeployment_text(
        self,
        ticker: str,
        shares: int,
        price: float,
        total_value: float,
        reason: str,
        timestamp: str,
        mode_label: str
    ) -> str:
        """Render plain text for intraday redeployment alert."""
        return f"""{'='*50}
[{mode_label}] INTRADAY REDEPLOYMENT
{'='*50}

Capital redeployed mid-day

Ticker: {ticker}
Shares: {shares}
Price: ${price:.2f}
Total: ${total_value:,.0f}

Reason: {reason}

Time: {timestamp}

{'='*50}
Insider Cluster Watch — Automated Trading System
"""

    # =========================================================================
    # Daily Summary Alert
    # =========================================================================

    def send_daily_summary_alert(
        self,
        portfolio_value: float,
        daily_pnl: float,
        trades_executed: int,
        open_positions: int,
        circuit_breaker_status: Dict[str, Any],
        exits_today: Optional[List[Dict[str, Any]]] = None,
        ai_insights: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send daily summary alert at end of trading day.

        Now includes exit details (positions closed) and AI insights to reduce email volume.
        """
        mode_emoji, mode_label, mode_color = self._get_mode_indicator()
        date_str = datetime.now().strftime('%B %d, %Y')

        subject = f"{mode_emoji} Daily Summary: ${daily_pnl:+,.2f} | {date_str}"

        # Simplified HTML for daily summary
        pnl_color = COLORS['success'] if daily_pnl >= 0 else COLORS['danger']
        pnl_sign = '+' if daily_pnl >= 0 else ''

        # Build exits section if any
        exits_html = ""
        exits_text = ""
        if exits_today:
            exits_rows = ""
            for e in exits_today:
                exit_pnl = e.get('pnl', 0)
                exit_color = COLORS['success'] if exit_pnl >= 0 else COLORS['danger']
                exit_sign = '+' if exit_pnl >= 0 else ''
                exits_rows += f'''
                <tr style="border-bottom: 1px solid {COLORS['border']};">
                    <td style="padding: 10px; font-weight: 700; color: {COLORS['primary']}; font-family: 'Courier New', monospace;">
                        {e.get('ticker', 'N/A')}
                    </td>
                    <td style="padding: 10px; color: {COLORS['text_muted']}; font-size: 12px;">
                        {e.get('reason', 'N/A')}
                    </td>
                    <td style="padding: 10px; text-align: right; font-weight: 600; color: {exit_color};">
                        {exit_sign}${exit_pnl:,.2f}
                    </td>
                </tr>
                '''

            exits_html = f'''
            <tr>
                <td style="background: {COLORS['bg_card']}; padding: 25px; border: 1px solid {COLORS['border']}; border-top: none;">
                    <h2 style="margin: 0 0 15px 0; font-size: 16px; color: {COLORS['primary']};">Positions Closed Today</h2>
                    <table width="100%" cellpadding="0" cellspacing="0" style="font-size: 13px; border: 1px solid {COLORS['border']}; border-radius: 8px;">
                        <tr style="background: rgba(56, 189, 248, 0.1);">
                            <th style="padding: 10px; text-align: left; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;">Ticker</th>
                            <th style="padding: 10px; text-align: left; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;">Reason</th>
                            <th style="padding: 10px; text-align: right; color: {COLORS['text_muted']}; font-size: 11px; text-transform: uppercase;">P&L</th>
                        </tr>
                        {exits_rows}
                    </table>
                </td>
            </tr>
            '''

            exits_text = "\n\nPositions Closed Today:\n"
            for e in exits_today:
                exit_pnl = e.get('pnl', 0)
                exit_sign = '+' if exit_pnl >= 0 else ''
                exits_text += f"  {e.get('ticker', 'N/A'):<6} {e.get('reason', 'N/A'):<20} {exit_sign}${exit_pnl:,.2f}\n"

        # Build AI insights section
        ai_html = ""
        ai_text = ""
        if ai_insights and ai_insights.get('available'):
            data = ai_insights.get('data', {})
            narrative = ai_insights.get('narrative', '')

            # Build data points for HTML
            ai_data_rows = ""

            # Filters
            filters = data.get('filters', {})
            if not filters.get('error'):
                ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">Filter Blocks:</td>
                    <td style="padding: 8px; color: {COLORS['text_main']}; font-weight: 600;">{filters.get('total_blocks_today', 0)} signals blocked</td>
                </tr>
                '''
                if filters.get('key_rejection'):
                    key_rej = filters['key_rejection']
                    ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">Key Rejection:</td>
                    <td style="padding: 8px; color: {COLORS['warning']};">{key_rej.get('reason', 'N/A')}</td>
                </tr>
                '''

            # Sectors
            sectors = data.get('sectors', {})
            if not sectors.get('error') and sectors.get('warning'):
                ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">Risk Alert:</td>
                    <td style="padding: 8px; color: {COLORS['danger']}; font-weight: 600;">&#9888;&#65039; {sectors['warning']}</td>
                </tr>
                '''

            # Execution - only show when real data exists
            execution = data.get('execution', {})
            if not execution.get('error') and not execution.get('no_data') and execution.get('orders_today', 0) > 0:
                quality_score = execution.get('quality_score', 0)
                quality_color = COLORS['success'] if quality_score >= 8 else COLORS['warning'] if quality_score >= 6 else COLORS['danger']
                ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">Execution Quality:</td>
                    <td style="padding: 8px; color: {quality_color}; font-weight: 600;">{quality_score}/10</td>
                </tr>
                '''

            # Historical comparison - only show when real data exists
            historical = data.get('historical', {})
            if not historical.get('error') and not historical.get('insufficient_data') and historical.get('sample_size_30d', 0) > 0:
                wr = historical.get('win_rate', {})
                wr_delta = wr.get('delta', 0)
                wr_color = COLORS['success'] if wr_delta >= 0 else COLORS['danger']
                ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">Win Rate vs 30d Avg:</td>
                    <td style="padding: 8px; color: {wr_color}; font-weight: 600;">{wr.get('today', 0)}% vs {wr.get('avg_30d', 0)}% ({wr_delta:+.1f}%)</td>
                </tr>
                '''

            # Trends
            trends = data.get('trends', {})
            if not trends.get('error') and not trends.get('insufficient_data'):
                wr_trend = trends.get('win_rate_trend', {})
                if wr_trend.get('significance') != 'none':
                    trend_dir = wr_trend.get('direction', 'stable')
                    trend_color = COLORS['success'] if trend_dir == 'improving' else COLORS['danger'] if trend_dir == 'declining' else COLORS['text_main']
                    ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">7-Day Win Rate Trend:</td>
                    <td style="padding: 8px; color: {trend_color}; font-weight: 600;">{trend_dir.capitalize()} ({wr_trend.get('change', 0):+.1f}%)</td>
                </tr>
                '''

            # Attribution
            attribution = data.get('attribution', {})
            if not attribution.get('error') and not attribution.get('insufficient_data'):
                best = attribution.get('best_sector')
                worst = attribution.get('worst_sector')
                if best:
                    ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">Best Sector (30d):</td>
                    <td style="padding: 8px; color: {COLORS['success']}; font-weight: 600;">{best.get('sector', 'N/A')} (${best.get('pnl', 0):+,.0f}, {best.get('trades', 0)} trades)</td>
                </tr>
                '''
                if worst and worst.get('pnl', 0) < 0:
                    ai_data_rows += f'''
                <tr>
                    <td style="padding: 8px; color: {COLORS['text_muted']};">Worst Sector (30d):</td>
                    <td style="padding: 8px; color: {COLORS['danger']}; font-weight: 600;">{worst.get('sector', 'N/A')} (${worst.get('pnl', 0):+,.0f}, {worst.get('trades', 0)} trades)</td>
                </tr>
                '''

            # Anomalies warning section
            anomalies = data.get('anomalies', {})
            anomaly_html = ""
            if anomalies.get('anomalies_detected', 0) > 0:
                anomaly_items = ""
                for anomaly in anomalies.get('anomalies', [])[:2]:
                    severity = anomaly.get('severity', 'medium')
                    sev_color = COLORS['danger'] if severity == 'high' else COLORS['warning']
                    anomaly_items += f'''
                    <div style="padding: 8px 12px; margin-bottom: 5px; background: rgba(239, 68, 68, 0.1); border-radius: 4px; border-left: 3px solid {sev_color};">
                        <span style="color: {sev_color}; font-weight: 600; font-size: 12px;">[{severity.upper()}]</span>
                        <span style="color: {COLORS['text_main']}; font-size: 13px;"> {str(anomaly.get('message', 'Unknown')).replace(chr(10), '<br>')}</span>
                    </div>
                    '''
                anomaly_html = f'''
                    <div style="margin-top: 15px;">
                        <h3 style="margin: 0 0 10px 0; font-size: 14px; color: {COLORS['warning']};">&#9888;&#65039; Anomalies Detected ({anomalies.get('anomalies_detected', 0)})</h3>
                        {anomaly_items}
                    </div>
                '''

            ai_html = f'''
            <tr>
                <td style="background: {COLORS['bg_card']}; padding: 25px; border: 1px solid {COLORS['border']}; border-top: none;">
                    <h2 style="margin: 0 0 15px 0; font-size: 16px; color: {COLORS['primary']};">AI Analysis &amp; Insights</h2>

                    <!-- AI Narrative -->
                    <div style="background: rgba(56, 189, 248, 0.1); padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                        <p style="margin: 0; color: {COLORS['text_main']}; font-size: 14px; line-height: 1.6;">{narrative.replace(chr(10), '<br>')}</p>
                    </div>

                    <!-- Key Metrics -->
                    <table width="100%" cellpadding="0" cellspacing="0" style="font-size: 13px;">
                        {ai_data_rows}
                    </table>

                    {anomaly_html}

                    <p style="margin: 15px 0 0 0; font-size: 11px; color: {COLORS['text_muted']}; text-align: center;">
                        Powered by Groq ({ai_insights.get('model', 'N/A')})
                    </p>
                </td>
            </tr>
            '''

            # Text version
            ai_text = f"\n\n{'='*60}\nAI ANALYSIS & INSIGHTS\n{'='*60}\n\n{narrative}\n\n"

            # Add data points
            if not filters.get('error'):
                ai_text += f"Filter Blocks: {filters.get('total_blocks_today', 0)} signals blocked\n"
                if filters.get('key_rejection'):
                    ai_text += f"  Key rejection: {filters['key_rejection'].get('reason', 'N/A')}\n"

            if not sectors.get('error') and sectors.get('warning'):
                ai_text += f"\n  Risk: {sectors['warning']}\n"

            if not execution.get('error') and not execution.get('no_data') and execution.get('orders_today', 0) > 0:
                ai_text += f"\nExecution Quality: {execution.get('quality_score', 0)}/10\n"

            # Historical comparison - only when real data exists
            if not historical.get('error') and not historical.get('insufficient_data') and historical.get('sample_size_30d', 0) > 0:
                wr = historical.get('win_rate', {})
                ai_text += f"\nHistorical: Win rate {wr.get('status', 'unknown')} avg by {abs(wr.get('delta', 0)):.1f}%\n"

            # Trends
            if not trends.get('error') and not trends.get('insufficient_data'):
                wr_trend = trends.get('win_rate_trend', {})
                if wr_trend.get('significance') != 'none':
                    ai_text += f"Trend: Win rate {wr_trend.get('direction', 'stable')} ({wr_trend.get('change', 0):+.1f}%)\n"

            # Anomalies
            if anomalies.get('anomalies_detected', 0) > 0:
                ai_text += f"\n  ANOMALIES DETECTED: {anomalies.get('anomalies_detected', 0)}\n"
                for anomaly in anomalies.get('anomalies', [])[:2]:
                    ai_text += f"   - {anomaly.get('message', 'Unknown')}\n"

            ai_text += f"\nPowered by Groq ({ai_insights.get('model', 'N/A')})\n"

        html = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin: 0; padding: 0; background: {COLORS['bg_main']}; color: {COLORS['text_main']}; font-family: -apple-system, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background: {COLORS['bg_main']};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px;">
                    <tr>
                        <td style="background: {mode_color}; padding: 8px; text-align: center; border-radius: 8px 8px 0 0;">
                            <span style="color: #000; font-weight: 700; font-size: 12px;">{mode_label}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="background: {COLORS['bg_card']}; padding: 25px; text-align: center; border: 1px solid {COLORS['border']};">
                            <h1 style="margin: 0; font-size: 24px; color: {COLORS['primary']};">Daily Summary</h1>
                            <p style="margin: 5px 0 20px 0; color: {COLORS['text_muted']};">{date_str}</p>

                            <div style="font-size: 36px; font-weight: 800; color: {pnl_color}; margin: 20px 0;">
                                {pnl_sign}${daily_pnl:,.2f}
                            </div>
                            <div style="font-size: 14px; color: {COLORS['text_muted']};">Daily P&L</div>

                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 25px; border-top: 1px solid {COLORS['border']}; padding-top: 20px;">
                                <tr>
                                    <td width="33%" style="text-align: center;">
                                        <div style="font-size: 24px; font-weight: 700;">${portfolio_value:,.2f}</div>
                                        <div style="font-size: 12px; color: {COLORS['text_muted']};">Portfolio Value</div>
                                    </td>
                                    <td width="33%" style="text-align: center;">
                                        <div style="font-size: 24px; font-weight: 700;">{trades_executed}</div>
                                        <div style="font-size: 12px; color: {COLORS['text_muted']};">Trades Today</div>
                                    </td>
                                    <td width="33%" style="text-align: center;">
                                        <div style="font-size: 24px; font-weight: 700;">{open_positions}</div>
                                        <div style="font-size: 12px; color: {COLORS['text_muted']};">Open Positions</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    {exits_html}
                    {ai_html}
                    <tr>
                        <td style="padding: 20px; text-align: center;">
                            <p style="margin: 0; font-size: 11px; color: {COLORS['text_muted']};">
                                Insider Cluster Watch — Automated Trading System
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

        text = f"""{'='*50}
[{mode_label}] DAILY SUMMARY - {date_str}
{'='*50}

Daily P&L: {pnl_sign}${daily_pnl:,.2f}
Portfolio Value: ${portfolio_value:,.2f}
Trades Today: {trades_executed}
Open Positions: {open_positions}
{exits_text}
{ai_text}
{'='*50}
Insider Cluster Watch — Automated Trading System
"""

        return self.send_alert(subject, html, text, 'INFO')


def create_alert_sender() -> AlertSender:
    """Create and return an AlertSender instance."""
    return AlertSender()


if __name__ == '__main__':
    # Test alert sender
    sender = AlertSender()
    print(f"Alert sender configured for: {config.TRADING_MODE} trading")
    print(f"Recipient: {config.RECIPIENT_EMAIL}")
