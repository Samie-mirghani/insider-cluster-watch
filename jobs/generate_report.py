# jobs/generate_report.py
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import pandas as pd
import os
import math

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')

def sanitize_dict_for_template(data):
    """
    Sanitize dictionary values before passing to Jinja2 templates.

    CRITICAL: Converts NaN, None, inf, and string "nan"/"null" to None to prevent
    'nan' from appearing in email templates.

    This is a defense-in-depth measure - data should already be sanitized by
    process_signals.sanitize_nan_values(), but this ensures no "nan" slips through.
    """
    if isinstance(data, list):
        return [sanitize_dict_for_template(item) for item in data]

    if not isinstance(data, dict):
        return data

    sanitized = {}
    for key, value in data.items():
        # Handle None
        if value is None:
            sanitized[key] = None
            continue

        # Handle nested dicts
        if isinstance(value, dict):
            sanitized[key] = sanitize_dict_for_template(value)
            continue

        # Handle lists
        if isinstance(value, (list, tuple)):
            sanitized[key] = value  # Keep lists as-is (insiders_data, etc.)
            continue

        # Handle string "nan", "null", "none", etc.
        if isinstance(value, str):
            if value.lower().strip() in ['nan', 'null', 'none', 'n/a', '']:
                sanitized[key] = None
            else:
                sanitized[key] = value
            continue

        # Handle numeric NaN/inf
        try:
            if pd.isna(value):
                sanitized[key] = None
            elif isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
                sanitized[key] = None
            else:
                sanitized[key] = value
        except (ValueError, TypeError):
            # If pd.isna() fails, keep as-is
            sanitized[key] = value

    return sanitized

def is_valid_value(value):
    """
    Jinja2 filter to check if a value is valid for display.

    Returns False for None, NaN, inf, empty strings, or string "nan"/"null".
    This is used in templates to conditionally display fields.
    """
    if value is None:
        return False

    if isinstance(value, str):
        if value.strip().lower() in ['nan', 'null', 'none', 'n/a', '', 'unknown']:
            return False

    try:
        if pd.isna(value):
            return False
        if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
            return False
    except (ValueError, TypeError):
        pass

    return True

def render_daily_html(cluster_df, portfolio=None, closed_positions=None, opened_positions=None):
    """
    Generate daily personal trading report with paper trading focus.

    Args:
        cluster_df: Signals detected today (DataFrame)
        portfolio: PaperTradingPortfolio instance (optional, for backward compatibility)
        closed_positions: List of (ticker, reason, exit_price) closed today
        opened_positions: List of tickers opened today

    Returns:
        (html, text): Tuple of HTML and plain text versions
    """
    # If no portfolio provided, fall back to old template
    if portfolio is None:
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        env.filters['is_valid'] = is_valid_value
        tmpl = env.get_template('daily_report.html')
        rows = cluster_df.to_dict(orient='records') if cluster_df is not None and not cluster_df.empty else []
        rows = sanitize_dict_for_template(rows)
        html = tmpl.render(date=datetime.now().strftime("%B %d, %Y"), trades=rows)
        text = build_plain_text(rows)
        return html, text

    # New personal trading dashboard template
    closed_positions = closed_positions or []
    opened_positions = opened_positions or []

    # Get portfolio stats
    stats = portfolio.get_performance_summary(validate=False)

    # Calculate today's P&L from session if available
    session_summary = portfolio.get_session_summary() if hasattr(portfolio, 'get_session_summary') else None
    today_pnl = session_summary.get('portfolio_change', 0) if session_summary else 0
    today_pnl_pct = session_summary.get('portfolio_change_pct', 0) if session_summary else 0

    # Get top 3 signals
    top_signals = []
    if cluster_df is not None and not cluster_df.empty:
        top_signals = cluster_df.head(3).to_dict(orient='records')
        top_signals = sanitize_dict_for_template(top_signals)

    # Build closed positions data
    closed_today = []
    for ticker, reason, exit_price in closed_positions:
        # Find matching trade in history
        trade_info = None
        for trade in reversed(portfolio.trade_history):
            if trade.get('ticker') == ticker and trade.get('action') == 'SELL':
                trade_info = trade
                break
        if trade_info:
            closed_today.append({
                'ticker': ticker,
                'reason': reason,
                'exit_price': exit_price,
                'entry_price': trade_info.get('entry_price', 0),
                'profit': trade_info.get('profit', 0),
                'pnl_pct': trade_info.get('pnl_pct', 0),
                'hold_days': trade_info.get('hold_days', 0),
                'entry_date': trade_info.get('entry_date')
            })

    # Build opened positions data
    opened_today = []
    for ticker in opened_positions:
        if ticker in portfolio.positions:
            pos = portfolio.positions[ticker]
            opened_today.append({
                'ticker': ticker,
                'shares': pos['shares'],
                'entry_price': pos['entry_price'],
                'cost_basis': pos.get('cost_basis', pos['shares'] * pos['entry_price']),
                'signal_score': pos.get('signal_score', 0),
                'stop_loss': pos.get('stop_loss', 0),
                'take_profit': pos.get('take_profit', 0),
                'sector': pos.get('sector', 'Unknown')
            })

    # Build open positions data with current prices
    open_positions = []
    for ticker, pos in portfolio.positions.items():
        current_price = portfolio._get_current_price(ticker, pos['entry_price'])
        unrealized_pnl = (current_price - pos['entry_price']) / pos['entry_price'] * 100
        days_held = (datetime.now() - pos['entry_date']).days
        open_positions.append({
            'ticker': ticker,
            'shares': pos['shares'],
            'entry_price': pos['entry_price'],
            'current_price': current_price,
            'unrealized_pnl': unrealized_pnl,
            'days_held': days_held,
            'stop_loss': pos.get('stop_loss', 0),
            'take_profit': pos.get('take_profit', 0)
        })

    # Calculate health check indicators
    health_checks = []
    win_rate_target = 55.0
    drawdown_limit = -10.0
    exposure_safe_limit = 50.0

    # Win rate check
    if stats['win_rate'] >= win_rate_target:
        health_checks.append({
            'status': 'ok',
            'message': f"Win rate above target ({stats['win_rate']:.1f}% > {win_rate_target}%)"
        })
    else:
        health_checks.append({
            'status': 'warning',
            'message': f"Win rate below target ({stats['win_rate']:.1f}% < {win_rate_target}%)"
        })

    # Drawdown check
    if stats['max_drawdown'] >= drawdown_limit:
        health_checks.append({
            'status': 'ok',
            'message': f"Drawdown within limits ({stats['max_drawdown']:.1f}% vs {drawdown_limit}%)"
        })
    else:
        health_checks.append({
            'status': 'warning',
            'message': f"Drawdown exceeds limits ({stats['max_drawdown']:.1f}% vs {drawdown_limit}%)"
        })

    # Exposure check
    if stats['exposure_pct'] <= exposure_safe_limit:
        health_checks.append({
            'status': 'ok',
            'message': f"Exposure at safe levels ({stats['exposure_pct']:.1f}%)"
        })
    else:
        health_checks.append({
            'status': 'warning',
            'message': f"Exposure elevated ({stats['exposure_pct']:.1f}%)"
        })

    # Position age warnings
    for ticker, pos in portfolio.positions.items():
        days_held = (datetime.now() - pos['entry_date']).days
        if days_held >= 21:
            health_checks.append({
                'status': 'warning',
                'message': f"Position {ticker} at {days_held} days (approaching review)"
            })

    # Render HTML
    html = _render_trading_dashboard_html(
        date=datetime.now().strftime("%B %d, %Y"),
        stats=stats,
        today_pnl=today_pnl,
        today_pnl_pct=today_pnl_pct,
        closed_today=closed_today,
        opened_today=opened_today,
        open_positions=open_positions,
        top_signals=top_signals,
        health_checks=health_checks,
        opened_tickers=opened_positions
    )

    # Build plain text version
    text = _build_trading_dashboard_text(
        date=datetime.now().strftime("%Y-%m-%d"),
        stats=stats,
        today_pnl=today_pnl,
        today_pnl_pct=today_pnl_pct,
        closed_today=closed_today,
        opened_today=opened_today,
        open_positions=open_positions,
        top_signals=top_signals,
        health_checks=health_checks,
        opened_tickers=opened_positions
    )

    return html, text


def _get_star_rating(score):
    """Return star rating based on signal score."""
    if score >= 15:
        return "⭐⭐⭐"
    elif score >= 10:
        return "⭐⭐"
    else:
        return "⭐"


def _format_currency(value):
    """Format currency value for display."""
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "$0"
    if value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value/1_000:.1f}K"
    else:
        return f"${value:,.0f}"


def _render_trading_dashboard_html(date, stats, today_pnl, today_pnl_pct, closed_today,
                                    opened_today, open_positions, top_signals,
                                    health_checks, opened_tickers):
    """Render the personal trading dashboard HTML email."""

    # Color scheme from dashboard-v2.html
    bg_main = "#0b1120"
    bg_card = "#151e32"
    primary = "#38bdf8"
    success = "#00e676"
    danger = "#ff5252"
    warning = "#fbbf24"
    text_main = "#f1f5f9"
    text_muted = "#94a3b8"
    border = "#334155"

    # Determine P&L colors
    total_return_color = success if stats['total_return_pct'] >= 0 else danger
    today_pnl_color = success if today_pnl >= 0 else danger

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Trading Report - {date}</title>
</head>
<body style="margin: 0; padding: 0; background: {bg_main}; color: {text_main}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6;">

    <!-- Main Container -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_main};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 700px;">

                    <!-- Header -->
                    <tr>
                        <td style="padding: 20px 0; text-align: center;">
                            <h1 style="margin: 0; font-size: 28px; font-weight: 800; color: {primary};">📊 Daily Trading Report</h1>
                            <p style="margin: 10px 0 0 0; color: {text_muted}; font-size: 14px;">{date}</p>
                        </td>
                    </tr>

                    <!-- Section 1: Portfolio Performance (MOST PROMINENT) -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: 1px solid {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 18px; font-weight: 700; color: {primary};">💰 Portfolio Performance</h2>

                                        <!-- Main Stats Row -->
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td width="50%" style="padding: 10px;">
                                                    <div style="font-size: 12px; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;">Portfolio Value</div>
                                                    <div style="font-size: 32px; font-weight: 800; color: {text_main};">${stats['current_value']:,.2f}</div>
                                                    <div style="font-size: 16px; font-weight: 600; color: {total_return_color};">
                                                        {'+' if stats['total_return_pct'] >= 0 else ''}{stats['total_return_pct']:.1f}% total return
                                                    </div>
                                                </td>
                                                <td width="50%" style="padding: 10px;">
                                                    <div style="font-size: 12px; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;">Today's P&L</div>
                                                    <div style="font-size: 32px; font-weight: 800; color: {today_pnl_color};">
                                                        {'+' if today_pnl >= 0 else ''}${today_pnl:,.2f}
                                                    </div>
                                                    <div style="font-size: 16px; font-weight: 600; color: {today_pnl_color};">
                                                        ({'+' if today_pnl_pct >= 0 else ''}{today_pnl_pct:.1f}%)
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>

                                        <!-- Secondary Stats -->
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 20px; border-top: 1px solid {border}; padding-top: 20px;">
                                            <tr>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Cash</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {text_main};">${stats['cash']:,.2f}</div>
                                                    <div style="font-size: 12px; color: {text_muted};">({(stats['cash']/stats['current_value']*100) if stats['current_value'] > 0 else 0:.1f}%)</div>
                                                </td>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Win Rate</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {success if stats['win_rate'] >= 55 else warning};">{stats['win_rate']:.1f}%</div>
                                                    <div style="font-size: 12px; color: {text_muted};">({stats['winning_trades']}W / {stats['losing_trades']}L)</div>
                                                </td>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Open Positions</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {text_main};">{stats['open_positions']}</div>
                                                    <div style="font-size: 12px; color: {text_muted};">({stats['exposure_pct']:.1f}% exposure)</div>
                                                </td>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Max Drawdown</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {danger if stats['max_drawdown'] < -10 else warning if stats['max_drawdown'] < -5 else success};">{stats['max_drawdown']:.1f}%</div>
                                                    <div style="font-size: 12px; color: {text_muted};">limit: -10%</div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Section 2: Today's Trading Activity -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: 1px solid {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 18px; font-weight: 700; color: {primary};">📈 Today's Trading Activity</h2>
'''

    # Closed positions section
    if closed_today:
        html += f'''
                                        <div style="margin-bottom: 20px;">
                                            <h3 style="margin: 0 0 15px 0; font-size: 14px; font-weight: 600; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px;">Positions Closed</h3>
'''
        for pos in closed_today:
            pnl_color = success if pos['profit'] >= 0 else danger
            pnl_icon = "✅" if pos['profit'] >= 0 else "❌"
            entry_date_str = pos['entry_date'].strftime('%b %d') if hasattr(pos['entry_date'], 'strftime') else str(pos['entry_date'])[:10] if pos['entry_date'] else 'N/A'
            html += f'''
                                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: rgba(255,255,255,0.03); border-radius: 8px; margin-bottom: 10px;">
                                                <tr>
                                                    <td style="padding: 15px;">
                                                        <div style="display: flex; justify-content: space-between; align-items: center;">
                                                            <span style="font-size: 16px; font-weight: 700; color: {text_main};">{pnl_icon} CLOSED: <span style="color: {primary}; font-family: 'Courier New', monospace;">{pos['ticker']}</span></span>
                                                            <span style="font-size: 16px; font-weight: 700; color: {pnl_color};">{'+' if pos['profit'] >= 0 else ''}${pos['profit']:.2f} ({'+' if pos['pnl_pct'] >= 0 else ''}{pos['pnl_pct']:.1f}%)</span>
                                                        </div>
                                                        <div style="font-size: 13px; color: {text_muted}; margin-top: 8px;">
                                                            Entry: ${pos['entry_price']:.2f} on {entry_date_str} → Exit: ${pos['exit_price']:.2f}<br>
                                                            Hold: {pos['hold_days']} days | Reason: {pos['reason']}
                                                        </div>
                                                    </td>
                                                </tr>
                                            </table>
'''
        html += '''
                                        </div>
'''

    # Opened positions section
    if opened_today:
        html += f'''
                                        <div style="margin-bottom: 10px;">
                                            <h3 style="margin: 0 0 15px 0; font-size: 14px; font-weight: 600; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px;">Positions Opened</h3>
'''
        for pos in opened_today:
            # Find cluster info for this ticker
            cluster_count = 0
            for sig in top_signals:
                if sig.get('ticker') == pos['ticker']:
                    cluster_count = sig.get('cluster_count', 0)
                    break

            stop_pct = (pos['stop_loss'] / pos['entry_price'] - 1) * 100 if pos['entry_price'] > 0 else -5
            target_pct = (pos['take_profit'] / pos['entry_price'] - 1) * 100 if pos['entry_price'] > 0 else 8
            position_pct = (pos['cost_basis'] / stats['current_value'] * 100) if stats['current_value'] > 0 else 0

            html += f'''
                                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: rgba(0,230,118,0.05); border-left: 3px solid {success}; border-radius: 8px; margin-bottom: 10px;">
                                                <tr>
                                                    <td style="padding: 15px;">
                                                        <div style="font-size: 16px; font-weight: 700; color: {text_main};">
                                                            🆕 OPENED: <span style="color: {primary}; font-family: 'Courier New', monospace;">{pos['ticker']}</span> | {pos['shares']} shares @ ${pos['entry_price']:.2f}
                                                        </div>
                                                        <div style="font-size: 13px; color: {text_muted}; margin-top: 8px;">
                                                            Signal Score: {pos['signal_score']:.1f} {_get_star_rating(pos['signal_score'])} | Cluster: {cluster_count} insiders<br>
                                                            Stop: ${pos['stop_loss']:.2f} ({stop_pct:.1f}%) | Target: ${pos['take_profit']:.2f} (+{target_pct:.1f}%)<br>
                                                            Position Size: ${pos['cost_basis']:.2f} ({position_pct:.1f}% of portfolio)
                                                        </div>
                                                    </td>
                                                </tr>
                                            </table>
'''
        html += '''
                                        </div>
'''

    # No trades message
    if not closed_today and not opened_today:
        html += f'''
                                        <div style="text-align: center; padding: 30px; color: {text_muted};">
                                            <p style="margin: 0; font-size: 14px;">No trades executed today - all positions holding</p>
                                        </div>
'''

    html += '''
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
'''

    # Section 3: Open Positions Overview
    if open_positions:
        html += f'''
                    <!-- Section 3: Open Positions -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: 1px solid {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 18px; font-weight: 700; color: {primary};">🎯 Open Positions ({len(open_positions)})</h2>
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
'''
        for pos in open_positions:
            pnl_color = success if pos['unrealized_pnl'] > 0 else danger if pos['unrealized_pnl'] < 0 else text_main
            html += f'''
                                            <tr>
                                                <td style="padding: 10px 0; border-bottom: 1px solid {border};">
                                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                                        <tr>
                                                            <td width="30%">
                                                                <span style="font-size: 16px; font-weight: 700; color: {primary}; font-family: 'Courier New', monospace;">{pos['ticker']}</span>
                                                            </td>
                                                            <td width="25%" style="font-size: 13px; color: {text_muted};">
                                                                {pos['shares']} @ ${pos['entry_price']:.2f}
                                                            </td>
                                                            <td width="25%" style="text-align: right;">
                                                                <span style="font-size: 14px; color: {text_main};">${pos['current_price']:.2f}</span>
                                                                <span style="font-size: 14px; font-weight: 600; color: {pnl_color};">
                                                                    ({'+' if pos['unrealized_pnl'] >= 0 else ''}{pos['unrealized_pnl']:.1f}%)
                                                                </span>
                                                            </td>
                                                            <td width="20%" style="text-align: right; font-size: 12px; color: {text_muted};">
                                                                {pos['days_held']} days
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
'''
        html += '''
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
'''

    # Section 4: Top Signals Detected Today
    html += f'''
                    <!-- Section 4: Top Signals -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: 1px solid {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 18px; font-weight: 700; color: {primary};">🔍 Top Signals Detected</h2>
'''

    if top_signals:
        for i, sig in enumerate(top_signals, 1):
            ticker = sig.get('ticker', 'N/A')
            score = sig.get('rank_score') or 0  # Handle None
            cluster_count = sig.get('cluster_count') or 0  # Handle None
            total_value = sig.get('total_value') or 0  # Handle None
            sector = sig.get('sector', 'Unknown')
            price = sig.get('currentPrice') or 0  # Handle None
            pattern = sig.get('pattern_detected', 'None')

            # Check if this signal was traded
            was_traded = ticker in opened_tickers

            html += f'''
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: rgba(255,255,255,0.03); border-radius: 8px; margin-bottom: 10px;">
                                            <tr>
                                                <td style="padding: 15px;">
                                                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                                        <div>
                                                            <span style="font-size: 18px; font-weight: 800; color: {primary}; font-family: 'Courier New', monospace;">{i}. {ticker}</span>
                                                            <span style="font-size: 14px; color: {text_muted}; margin-left: 10px;">Score: {score:.1f} {_get_star_rating(score)}</span>
                                                        </div>
                                                        <div>
                                                            {"<span style='background: " + success + "; color: #0b1120; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 700;'>✅ TRADED</span>" if was_traded else "<span style='background: " + text_muted + "; color: #0b1120; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 700;'>⏭️ SKIPPED</span>"}
                                                        </div>
                                                    </div>
                                                    <div style="font-size: 13px; color: {text_muted}; margin-top: 8px; line-height: 1.6;">
                                                        Cluster: {cluster_count} insiders bought {_format_currency(total_value)}<br>
                                                        Sector: {sector if sector and sector not in ['nan', 'None', None, 'Unknown'] else 'N/A'} | Price: ${price:.2f}<br>
                                                        Pattern: {pattern if pattern and pattern not in ['nan', 'None', None, ''] else 'None'}
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>
'''
    else:
        html += f'''
                                        <div style="text-align: center; padding: 30px; color: {text_muted};">
                                            <p style="margin: 0; font-size: 14px;">No insider clusters detected today</p>
                                        </div>
'''

    html += '''
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
'''

    # Section 5: Portfolio Health Check
    html += f'''
                    <!-- Section 5: Health Check -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: 1px solid {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 15px 0; font-size: 18px; font-weight: 700; color: {primary};">🏥 Portfolio Health</h2>
'''

    has_warnings = any(h['status'] == 'warning' for h in health_checks)
    ok_checks = [h for h in health_checks if h['status'] == 'ok']
    warning_checks = [h for h in health_checks if h['status'] == 'warning']

    if not has_warnings:
        html += f'''
                                        <div style="color: {success}; font-size: 14px;">
                                            <p style="margin: 0;">✅ All systems healthy</p>
                                        </div>
'''
    else:
        for check in ok_checks:
            html += f'''
                                        <div style="color: {success}; font-size: 13px; margin-bottom: 5px;">
                                            ✅ {check['message']}
                                        </div>
'''
        for check in warning_checks:
            html += f'''
                                        <div style="color: {warning}; font-size: 13px; margin-bottom: 5px;">
                                            ⚠️ {check['message']}
                                        </div>
'''

    html += f'''
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px 0 20px 0; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: {text_muted};">
                                <strong style="color: {primary};">Insider Cluster Watch</strong> — Paper Trading Dashboard
                            </p>
                            <p style="margin: 10px 0 0 0; font-size: 11px; color: {text_muted};">
                                This is a simulated paper trading report. No real money is at risk.
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
'''

    return html


def _build_trading_dashboard_text(date, stats, today_pnl, today_pnl_pct, closed_today,
                                   opened_today, open_positions, top_signals,
                                   health_checks, opened_tickers):
    """Build plain text version of the trading dashboard."""

    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"📊 DAILY TRADING REPORT — {date}")
    lines.append(f"{'='*60}")
    lines.append("")

    # Portfolio Performance
    lines.append("💰 PORTFOLIO PERFORMANCE")
    lines.append("-"*40)
    lines.append(f"Portfolio Value: ${stats['current_value']:,.2f} ({'+' if stats['total_return_pct'] >= 0 else ''}{stats['total_return_pct']:.1f}% total return)")
    lines.append(f"Today's P&L:     {'+' if today_pnl >= 0 else ''}${today_pnl:,.2f} ({'+' if today_pnl_pct >= 0 else ''}{today_pnl_pct:.1f}%)")
    lines.append(f"Cash:            ${stats['cash']:,.2f} ({(stats['cash']/stats['current_value']*100) if stats['current_value'] > 0 else 0:.1f}%)")
    lines.append(f"Win Rate:        {stats['win_rate']:.1f}% ({stats['winning_trades']}W / {stats['losing_trades']}L)")
    lines.append(f"Open Positions:  {stats['open_positions']} ({stats['exposure_pct']:.1f}% exposure)")
    lines.append(f"Max Drawdown:    {stats['max_drawdown']:.1f}%")
    lines.append("")

    # Today's Trading Activity
    lines.append("📈 TODAY'S TRADING ACTIVITY")
    lines.append("-"*40)

    if closed_today:
        lines.append("Positions Closed:")
        for pos in closed_today:
            pnl_icon = "✅" if pos['profit'] >= 0 else "❌"
            entry_date_str = pos['entry_date'].strftime('%b %d') if hasattr(pos['entry_date'], 'strftime') else str(pos['entry_date'])[:10] if pos['entry_date'] else 'N/A'
            lines.append(f"  {pnl_icon} {pos['ticker']}: {'+' if pos['profit'] >= 0 else ''}${pos['profit']:.2f} ({'+' if pos['pnl_pct'] >= 0 else ''}{pos['pnl_pct']:.1f}%)")
            lines.append(f"     Entry: ${pos['entry_price']:.2f} on {entry_date_str} → Exit: ${pos['exit_price']:.2f}")
            lines.append(f"     Hold: {pos['hold_days']} days | Reason: {pos['reason']}")
        lines.append("")

    if opened_today:
        lines.append("Positions Opened:")
        for pos in opened_today:
            cluster_count = 0
            for sig in top_signals:
                if sig.get('ticker') == pos['ticker']:
                    cluster_count = sig.get('cluster_count', 0)
                    break
            lines.append(f"  🆕 {pos['ticker']}: {pos['shares']} shares @ ${pos['entry_price']:.2f}")
            lines.append(f"     Signal Score: {pos['signal_score']:.1f} | Cluster: {cluster_count} insiders")
            lines.append(f"     Stop: ${pos['stop_loss']:.2f} | Target: ${pos['take_profit']:.2f}")
        lines.append("")

    if not closed_today and not opened_today:
        lines.append("No trades executed today - all positions holding")
        lines.append("")

    # Open Positions
    if open_positions:
        lines.append("🎯 OPEN POSITIONS")
        lines.append("-"*40)
        for pos in open_positions:
            pnl_str = f"{'+' if pos['unrealized_pnl'] >= 0 else ''}{pos['unrealized_pnl']:.1f}%"
            lines.append(f"  {pos['ticker']}: {pos['shares']} @ ${pos['entry_price']:.2f} | Current: ${pos['current_price']:.2f} ({pnl_str}) | {pos['days_held']} days")
        lines.append("")

    # Top Signals
    lines.append("🔍 TOP SIGNALS DETECTED")
    lines.append("-"*40)
    if top_signals:
        for i, sig in enumerate(top_signals, 1):
            ticker = sig.get('ticker', 'N/A')
            score = sig.get('rank_score') or 0  # Handle None
            cluster_count = sig.get('cluster_count') or 0  # Handle None
            total_value = sig.get('total_value') or 0  # Handle None
            was_traded = ticker in opened_tickers
            status = "✅ TRADED" if was_traded else "⏭️ SKIPPED"
            lines.append(f"  {i}. {ticker} | Score: {score:.1f} | {status}")
            lines.append(f"     Cluster: {cluster_count} insiders bought {_format_currency(total_value)}")
    else:
        lines.append("  No insider clusters detected today")
    lines.append("")

    # Health Check
    lines.append("🏥 PORTFOLIO HEALTH")
    lines.append("-"*40)
    has_warnings = any(h['status'] == 'warning' for h in health_checks)
    if not has_warnings:
        lines.append("  ✅ All systems healthy")
    else:
        for check in health_checks:
            icon = "✅" if check['status'] == 'ok' else "⚠️"
            lines.append(f"  {icon} {check['message']}")

    lines.append("")
    lines.append(f"{'='*60}")
    lines.append("Insider Cluster Watch — Paper Trading Dashboard")
    lines.append("This is a simulated paper trading report. No real money is at risk.")
    lines.append(f"{'='*60}")

    return "\n".join(lines)


def _render_simple_no_activity_report(total_transactions=0, buy_count=0, sell_count=0):
    """
    Simplified no-activity report for when paper trading is disabled.
    Shows only signal detection status and market activity summary.
    """
    date = datetime.now().strftime("%B %d, %Y")
    date_short = datetime.now().strftime("%Y-%m-%d")

    # Color scheme matching dashboard-v2.html spec
    bg_main = "#0a1929"
    bg_card = "rgba(255, 255, 255, 0.05)"
    primary = "#00D9FF"
    text_main = "#ffffff"
    text_muted = "#94a3b8"
    border = f"1px solid rgba(0, 217, 255, 0.2)"

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Trading Report - {date}</title>
</head>
<body style="margin: 0; padding: 0; background: {bg_main}; color: {text_main}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_main};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 800px;">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 20px 0; text-align: center;">
                            <h1 style="margin: 0; font-size: 28px; font-weight: 800; color: {primary};">📊 Daily Trading Report</h1>
                            <p style="margin: 10px 0 0 0; color: {text_muted}; font-size: 14px;">{date}</p>
                        </td>
                    </tr>

                    <!-- No Signals Detected -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: rgba(0,217,255,0.1); border: 1px solid {primary}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 40px 25px; text-align: center;">
                                        <h2 style="margin: 0 0 15px 0; font-size: 20px; font-weight: 700; color: {primary};">🔍 INSIDER SIGNAL DETECTION</h2>
                                        <div style="font-size: 48px; margin-bottom: 15px;">❌</div>
                                        <p style="margin: 0 0 10px 0; font-size: 16px; font-weight: 600; color: {text_main};">No insider clusters detected today</p>
                                        <p style="margin: 0 0 20px 0; font-size: 14px; color: {text_muted};">System ran successfully but found no qualified clusters meeting criteria</p>

                                        <div style="text-align: left; max-width: 500px; margin: 0 auto;">
                                            <p style="margin: 10px 0; font-size: 13px; color: {text_muted};">
                                                <strong style="color: {text_main};">Requirements:</strong><br>
                                                • Minimum 3 insiders buying<br>
                                                • Minimum $50k per insider<br>
                                                • Score above threshold (8.0+)
                                            </p>
                                            <p style="margin: 10px 0; font-size: 13px; color: {text_muted};">
                                                <strong style="color: {text_main};">Market Activity Summary:</strong><br>
                                                • Total Form 4 filings scanned: {total_transactions}<br>
                                                • Buy transactions: {buy_count}<br>
                                                • Sell transactions: {sell_count}
                                            </p>
                                            <p style="margin: 15px 0 0 0; font-size: 13px; color: {text_muted};">
                                                <strong style="color: {primary};">Next detection: Tomorrow at 7:00 AM ET</strong>
                                            </p>
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px 0 20px 0; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: {text_muted};">
                                <strong style="color: {primary};">Insider Cluster Watch</strong> — Signal Detection System
                            </p>
                            <p style="margin: 10px 0 0 0; font-size: 11px; color: {text_muted};">
                                Monitoring insider buying activity for qualified clusters
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    # Plain text version
    text_lines = [
        f"{'='*60}",
        f"📊 DAILY TRADING REPORT — {date_short}",
        f"{'='*60}",
        "",
        "🔍 INSIDER SIGNAL DETECTION",
        "-"*40,
        "  ❌ No insider clusters detected today",
        "",
        "  System ran successfully but found no qualified clusters meeting criteria:",
        "    • Minimum 3 insiders buying",
        "    • Minimum $50k per insider",
        "    • Score above threshold (8.0+)",
        "",
        "  Market Activity Summary:",
        f"    • Total Form 4 filings scanned: {total_transactions}",
        f"    • Buy transactions: {buy_count}",
        f"    • Sell transactions: {sell_count}",
        "",
        "  Next detection: Tomorrow at 7:00 AM ET",
        "",
        f"{'='*60}",
        "Insider Cluster Watch — Signal Detection System",
        "Monitoring insider buying activity for qualified clusters",
        f"{'='*60}",
    ]

    text = "\n".join(text_lines)
    return html, text


def render_no_activity_html(
    portfolio,
    total_transactions=0,
    buy_count=0,
    sell_count=0,
    closed_positions=None,
    opened_positions=None
):
    """
    Generate no-activity report (no signals, but may have trading activity)

    Args:
        portfolio: PaperTradingPortfolio instance (can be None if paper trading disabled)
        total_transactions: Total Form 4 filings scanned
        buy_count: Number of buy transactions
        sell_count: Number of sell transactions
        closed_positions: List of (ticker, reason, exit_price) closed today
        opened_positions: List of tickers opened (usually empty)

    Returns:
        (html, text): HTML and plain text versions
    """
    closed_positions = closed_positions or []
    opened_positions = opened_positions or []

    # Handle case when paper trading is disabled
    if portfolio is None:
        return _render_simple_no_activity_report(
            total_transactions=total_transactions,
            buy_count=buy_count,
            sell_count=sell_count
        )

    # Get portfolio stats
    stats = portfolio.get_performance_summary(validate=False)

    # Calculate today's P&L from session if available
    session_summary = portfolio.get_session_summary() if hasattr(portfolio, 'get_session_summary') else None
    today_pnl = session_summary.get('portfolio_change', 0) if session_summary else 0
    today_pnl_pct = session_summary.get('portfolio_change_pct', 0) if session_summary else 0

    # Build closed positions data
    closed_today = []
    for ticker, reason, exit_price in closed_positions:
        # Find matching trade in history
        trade_info = None
        for trade in reversed(portfolio.trade_history):
            if trade.get('ticker') == ticker and trade.get('action') == 'SELL':
                trade_info = trade
                break
        if trade_info:
            closed_today.append({
                'ticker': ticker,
                'reason': reason,
                'exit_price': exit_price,
                'entry_price': trade_info.get('entry_price', 0),
                'profit': trade_info.get('profit', 0),
                'pnl_pct': trade_info.get('pnl_pct', 0),
                'hold_days': trade_info.get('hold_days', 0),
                'entry_date': trade_info.get('entry_date')
            })

    # Build open positions data with current prices
    open_positions = []
    for ticker, pos in portfolio.positions.items():
        current_price = portfolio._get_current_price(ticker, pos['entry_price'])
        unrealized_pnl = (current_price - pos['entry_price']) / pos['entry_price'] * 100
        days_held = (datetime.now() - pos['entry_date']).days
        open_positions.append({
            'ticker': ticker,
            'shares': pos['shares'],
            'entry_price': pos['entry_price'],
            'current_price': current_price,
            'unrealized_pnl': unrealized_pnl,
            'days_held': days_held
        })

    # Render HTML and text
    html = _render_no_activity_html_email(
        date=datetime.now().strftime("%B %d, %Y"),
        stats=stats,
        today_pnl=today_pnl,
        today_pnl_pct=today_pnl_pct,
        closed_today=closed_today,
        open_positions=open_positions,
        total_transactions=total_transactions,
        buy_count=buy_count,
        sell_count=sell_count
    )

    text = _build_no_activity_text(
        date=datetime.now().strftime("%Y-%m-%d"),
        stats=stats,
        today_pnl=today_pnl,
        today_pnl_pct=today_pnl_pct,
        closed_today=closed_today,
        open_positions=open_positions,
        total_transactions=total_transactions,
        buy_count=buy_count,
        sell_count=sell_count
    )

    return html, text


def _render_no_activity_html_email(date, stats, today_pnl, today_pnl_pct, closed_today,
                                     open_positions, total_transactions, buy_count, sell_count):
    """Render the no-activity HTML email matching dashboard-v2.html theme."""

    # Color scheme matching dashboard-v2.html spec
    bg_main = "#0a1929"
    bg_card = "rgba(255, 255, 255, 0.05)"
    primary = "#00D9FF"
    success = "#00FF88"
    danger = "#FF4444"
    text_main = "#ffffff"
    text_muted = "#94a3b8"
    border = f"1px solid rgba(0, 217, 255, 0.2)"

    # Determine P&L colors
    total_return_color = success if stats['total_return_pct'] >= 0 else danger
    today_pnl_color = success if today_pnl >= 0 else danger

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Trading Report - {date}</title>
</head>
<body style="margin: 0; padding: 0; background: {bg_main}; color: {text_main}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6;">

    <!-- Main Container -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_main};">
        <tr>
            <td align="center" style="padding: 20px;">
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: 800px;">

                    <!-- Header -->
                    <tr>
                        <td style="padding: 20px 0; text-align: center;">
                            <h1 style="margin: 0; font-size: 28px; font-weight: 800; color: {primary};">📊 Daily Trading Report</h1>
                            <p style="margin: 10px 0 0 0; color: {text_muted}; font-size: 14px;">{date}</p>
                        </td>
                    </tr>

                    <!-- Section 1: Portfolio Performance (MOST PROMINENT) -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 700; color: {primary};">💰 PAPER TRADING PERFORMANCE</h2>

                                        <!-- Main Stats Row -->
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td width="50%" style="padding: 10px;">
                                                    <div style="font-size: 12px; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;">Portfolio Value</div>
                                                    <div style="font-size: 2.5rem; font-weight: 700; color: {text_main};">${stats['current_value']:,.2f}</div>
                                                    <div style="font-size: 16px; font-weight: 600; color: {total_return_color};">
                                                        {'+' if stats['total_return_pct'] >= 0 else ''}{stats['total_return_pct']:.1f}% total return
                                                    </div>
                                                </td>
                                                <td width="50%" style="padding: 10px;">
                                                    <div style="font-size: 12px; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;">Today's P&L</div>
                                                    <div style="font-size: 2.5rem; font-weight: 700; color: {today_pnl_color};">
                                                        {'+' if today_pnl >= 0 else ''}${today_pnl:,.2f}
                                                    </div>
                                                    <div style="font-size: 16px; font-weight: 600; color: {today_pnl_color};">
                                                        ({'+' if today_pnl_pct >= 0 else ''}{today_pnl_pct:.1f}%)
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>

                                        <!-- Secondary Stats -->
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 20px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 20px;">
                                            <tr>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Cash</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {text_main};">${stats['cash']:,.2f}</div>
                                                    <div style="font-size: 12px; color: {text_muted};">({(stats['cash']/stats['current_value']*100) if stats['current_value'] > 0 else 0:.1f}%)</div>
                                                </td>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Win Rate</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {text_main};">{stats['win_rate']:.1f}%</div>
                                                    <div style="font-size: 12px; color: {text_muted};">({stats['winning_trades']}W / {stats['losing_trades']}L)</div>
                                                </td>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Open Positions</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {text_main};">{stats['open_positions']}</div>
                                                    <div style="font-size: 12px; color: {text_muted};"></div>
                                                </td>
                                                <td width="25%" align="center" style="padding: 10px;">
                                                    <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">Exposure</div>
                                                    <div style="font-size: 18px; font-weight: 700; color: {text_main};">{stats['exposure_pct']:.1f}%</div>
                                                    <div style="font-size: 12px; color: {text_muted};"></div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Section 2: Today's Trading Activity -->
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 700; color: {primary};">📈 TODAY'S TRADING ACTIVITY</h2>
'''

    # Closed positions section
    if closed_today:
        html += f'''
                                        <div style="margin-bottom: 20px;">
                                            <h3 style="margin: 0 0 15px 0; font-size: 14px; font-weight: 600; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px;">Positions Closed ({len(closed_today)})</h3>
'''
        for pos in closed_today:
            pnl_color = success if pos['profit'] >= 0 else danger
            pnl_icon = "✅" if pos['profit'] >= 0 else "❌"
            entry_date_str = pos['entry_date'].strftime('%b %d') if hasattr(pos['entry_date'], 'strftime') else str(pos['entry_date'])[:10] if pos['entry_date'] else 'N/A'
            html += f'''
                                            <div style="background: rgba(255,255,255,0.03); border-radius: 8px; padding: 15px; margin-bottom: 10px;">
                                                <div style="margin-bottom: 8px;">
                                                    <span style="font-size: 16px; font-weight: 700; color: {text_main};">{pnl_icon} {pos['ticker']}</span>
                                                    <span style="float: right; font-size: 16px; font-weight: 700; color: {pnl_color};">{'+' if pos['profit'] >= 0 else ''}${pos['profit']:.2f} ({'+' if pos['pnl_pct'] >= 0 else ''}{pos['pnl_pct']:.1f}%)</span>
                                                </div>
                                                <div style="font-size: 13px; color: {text_muted};">
                                                    {pos['reason']} | Hold: {pos['hold_days']} days
                                                </div>
                                            </div>
'''
        html += '''
                                        </div>
'''

    # Opened positions section
    if opened_positions:
        html += f'''
                                        <div style="margin-bottom: 10px;">
                                            <h3 style="margin: 0 0 15px 0; font-size: 14px; font-weight: 600; color: {text_muted}; text-transform: uppercase; letter-spacing: 1px;">Positions Opened ({len(opened_positions)})</h3>
'''
        for ticker in opened_positions:
            html += f'''
                                            <div style="background: rgba(0,255,136,0.05); border-left: 3px solid {success}; border-radius: 8px; padding: 15px; margin-bottom: 10px;">
                                                <span style="font-size: 16px; font-weight: 700; color: {text_main};">🆕 {ticker}</span>
                                            </div>
'''
        html += '''
                                        </div>
'''

    # No trades message
    if not closed_today and not opened_positions:
        html += f'''
                                        <div style="text-align: center; padding: 30px; color: {text_muted};">
                                            <p style="margin: 0; font-size: 14px;">No trades executed today - all positions holding</p>
                                        </div>
'''

    html += '''
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
'''

    # Section 3: Open Positions Overview
    if open_positions:
        html += f'''
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 700; color: {primary};">🎯 OPEN POSITIONS ({len(open_positions)})</h2>
'''
        for pos in open_positions:
            pnl_color = success if pos['unrealized_pnl'] > 0 else danger if pos['unrealized_pnl'] < 0 else text_main
            html += f'''
                                        <div style="padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,0.1);">
                                            <div style="margin-bottom: 4px;">
                                                <span style="font-size: 16px; font-weight: 700; color: {primary};">{pos['ticker']}</span>
                                                <span style="float: right; font-size: 14px; font-weight: 600; color: {pnl_color};">
                                                    ${pos['current_price']:.2f} ({'+' if pos['unrealized_pnl'] >= 0 else ''}{pos['unrealized_pnl']:.1f}%)
                                                </span>
                                            </div>
                                            <div style="font-size: 13px; color: {text_muted};">
                                                {pos['shares']} shares @ ${pos['entry_price']:.2f} | {pos['days_held']} days
                                            </div>
                                        </div>
'''
        html += '''
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
'''
    else:
        html += f'''
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: {bg_card}; border: {border}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <h2 style="margin: 0 0 20px 0; font-size: 20px; font-weight: 700; color: {primary};">🎯 OPEN POSITIONS</h2>
                                        <div style="text-align: center; padding: 20px; color: {text_muted};">
                                            <p style="margin: 0; font-size: 14px;">No open positions - portfolio fully in cash</p>
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
'''

    # Section 4: No Signals Detected (Informational, Not Negative)
    html += f'''
                    <tr>
                        <td style="padding: 10px 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background: rgba(0,217,255,0.1); border: 1px solid {primary}; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 25px; text-align: center;">
                                        <h2 style="margin: 0 0 15px 0; font-size: 20px; font-weight: 700; color: {primary};">🔍 INSIDER SIGNAL DETECTION</h2>
                                        <div style="font-size: 48px; margin-bottom: 15px;">❌</div>
                                        <p style="margin: 0 0 10px 0; font-size: 16px; font-weight: 600; color: {text_main};">No insider clusters detected today</p>
                                        <p style="margin: 0 0 20px 0; font-size: 14px; color: {text_muted};">System ran successfully but found no qualified clusters meeting criteria</p>

                                        <div style="text-align: left; max-width: 500px; margin: 0 auto;">
                                            <p style="margin: 10px 0; font-size: 13px; color: {text_muted};">
                                                <strong style="color: {text_main};">Requirements:</strong><br>
                                                • Minimum 3 insiders buying<br>
                                                • Minimum $50k per insider<br>
                                                • Score above threshold (8.0+)
                                            </p>
                                            <p style="margin: 10px 0; font-size: 13px; color: {text_muted};">
                                                <strong style="color: {text_main};">Market Activity Summary:</strong><br>
                                                • Total Form 4 filings scanned: {total_transactions}<br>
                                                • Buy transactions: {buy_count}<br>
                                                • Sell transactions: {sell_count}
                                            </p>
                                            <p style="margin: 15px 0 0 0; font-size: 13px; color: {text_muted};">
                                                <strong style="color: {primary};">Next detection: Tomorrow at 7:00 AM ET</strong>
                                            </p>
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px 0 20px 0; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: {text_muted};">
                                <strong style="color: {primary};">Insider Cluster Watch</strong> — Paper Trading Dashboard
                            </p>
                            <p style="margin: 10px 0 0 0; font-size: 11px; color: {text_muted};">
                                This is a simulated paper trading report. No real money is at risk.
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
'''

    return html


def _build_no_activity_text(date, stats, today_pnl, today_pnl_pct, closed_today,
                              open_positions, total_transactions, buy_count, sell_count):
    """Build plain text version of the no-activity report."""

    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"📊 DAILY TRADING REPORT — {date}")
    lines.append(f"{'='*60}")
    lines.append("")

    # Portfolio Performance
    lines.append("💰 PAPER TRADING PERFORMANCE")
    lines.append("-"*40)
    lines.append(f"Portfolio Value: ${stats['current_value']:,.2f} ({'+' if stats['total_return_pct'] >= 0 else ''}{stats['total_return_pct']:.1f}% total return)")
    lines.append(f"Today's P&L:     {'+' if today_pnl >= 0 else ''}${today_pnl:,.2f} ({'+' if today_pnl_pct >= 0 else ''}{today_pnl_pct:.1f}%)")
    lines.append(f"Cash:            ${stats['cash']:,.2f} ({(stats['cash']/stats['current_value']*100) if stats['current_value'] > 0 else 0:.1f}%)")
    lines.append(f"Win Rate:        {stats['win_rate']:.1f}% ({stats['winning_trades']}W / {stats['losing_trades']}L)")
    lines.append(f"Open Positions:  {stats['open_positions']}")
    lines.append("")

    # Today's Trading Activity
    lines.append("📈 TODAY'S TRADING ACTIVITY")
    lines.append("-"*40)

    if closed_today:
        lines.append(f"Positions Closed ({len(closed_today)}):")
        for pos in closed_today:
            pnl_icon = "✅" if pos['profit'] >= 0 else "❌"
            lines.append(f"  {pnl_icon} {pos['ticker']}: {'+' if pos['profit'] >= 0 else ''}${pos['profit']:.2f} ({'+' if pos['pnl_pct'] >= 0 else ''}{pos['pnl_pct']:.1f}%) | {pos['reason']}")
        lines.append("")

    if opened_positions:
        lines.append(f"Positions Opened ({len(opened_positions)}):")
        for ticker in opened_positions:
            lines.append(f"  🆕 {ticker}")
        lines.append("")

    if not closed_today and not opened_positions:
        lines.append("No trades executed today - all positions holding")
        lines.append("")

    # Open Positions
    if open_positions:
        lines.append(f"🎯 OPEN POSITIONS ({len(open_positions)})")
        lines.append("-"*40)
        for pos in open_positions:
            pnl_str = f"{'+' if pos['unrealized_pnl'] >= 0 else ''}{pos['unrealized_pnl']:.1f}%"
            lines.append(f"  {pos['ticker']}: {pos['shares']} @ ${pos['entry_price']:.2f} | Current: ${pos['current_price']:.2f} ({pnl_str}) | {pos['days_held']} days")
        lines.append("")
    else:
        lines.append("🎯 OPEN POSITIONS")
        lines.append("-"*40)
        lines.append("  No open positions - portfolio fully in cash")
        lines.append("")

    # No Signals Detected
    lines.append("🔍 INSIDER SIGNAL DETECTION")
    lines.append("-"*40)
    lines.append("  ❌ No insider clusters detected today")
    lines.append("")
    lines.append("  System ran successfully but found no qualified clusters meeting criteria:")
    lines.append("    • Minimum 3 insiders buying")
    lines.append("    • Minimum $50k per insider")
    lines.append("    • Score above threshold (8.0+)")
    lines.append("")
    lines.append("  Market Activity Summary:")
    lines.append(f"    • Total Form 4 filings scanned: {total_transactions}")
    lines.append(f"    • Buy transactions: {buy_count}")
    lines.append(f"    • Sell transactions: {sell_count}")
    lines.append("")
    lines.append("  Next detection: Tomorrow at 7:00 AM ET")
    lines.append("")

    lines.append(f"{'='*60}")
    lines.append("Insider Cluster Watch — Paper Trading Dashboard")
    lines.append("This is a simulated paper trading report. No real money is at risk.")
    lines.append(f"{'='*60}")

    return "\n".join(lines)

def build_plain_text(rows):
    lines = []
    lines.append(f"Insider Cluster Report — {datetime.now().strftime('%Y-%m-%d')}\n")
    for r in rows:
        # Build ticker line with multi-signal indicators
        ticker_line = f"{r.get('ticker')}: cluster={r.get('cluster_count')} | total=${int(r.get('total_value',0)):,} | score={r.get('rank_score'):.2f}"

        # Add multi-signal tier indicator
        if r.get('multi_signal_tier') == 'tier1':
            ticker_line += " 🔥 TIER 1 (3+ SIGNALS)"
        elif r.get('multi_signal_tier') == 'tier2':
            ticker_line += " ⚡ TIER 2 (2 SIGNALS)"

        # Add politician flag
        if r.get('has_politician_signal'):
            ticker_line += " 🏛️ POLITICIAN"

        lines.append(ticker_line)

        # Show insiders with track records if available
        if r.get('insiders_with_track_record') and r.get('insiders_with_track_record') != '':
            lines.append(f"Insiders: {r.get('insiders_with_track_record')}")
        elif r.get('insiders') and r.get('insiders') != '':
            lines.append(f"Insiders: {r.get('insiders')}")
        else:
            lines.append("Insiders: N/A")

        lines.append(f"Action: {r.get('suggested_action')}")
        lines.append(f"Rationale: {r.get('rationale')}")
        lines.append("-"*40)
    return "\n".join(lines)