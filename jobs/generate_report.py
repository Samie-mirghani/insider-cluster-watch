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

def render_daily_html(cluster_df):
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    # Add custom filter for checking valid values
    env.filters['is_valid'] = is_valid_value
    tmpl = env.get_template('daily_report.html')
    rows = cluster_df.to_dict(orient='records')
    # CRITICAL: Sanitize all dict values to prevent "nan" from appearing in emails
    rows = sanitize_dict_for_template(rows)
    html = tmpl.render(date=datetime.now().strftime("%B %d, %Y"), trades=rows)
    text = build_plain_text(rows)
    return html, text

def render_urgent_html(cluster_df):
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    # Add custom filter for checking valid values
    env.filters['is_valid'] = is_valid_value
    tmpl = env.get_template('urgent_alert.html')
    rows = cluster_df.to_dict(orient='records')
    # CRITICAL: Sanitize all dict values to prevent "nan" from appearing in emails
    rows = sanitize_dict_for_template(rows)
    html = tmpl.render(date=datetime.now().strftime("%B %d, %Y"), urgent_trades=rows)
    text = build_plain_text(rows)
    return html, text

def render_no_activity_html(total_transactions=0, buy_count=0, sell_warning_html=""):
    """
    Render the enhanced no-activity report template.
    """
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    tmpl = env.get_template('no_activity_report.html')
    html = tmpl.render(
        date=datetime.now().strftime("%B %d, %Y"),
        total_transactions=total_transactions,
        buy_count=buy_count,
        sell_warning_html=sell_warning_html
    )
    
    # Plain text version
    text_lines = [
        f"Daily Insider Trade Report — {datetime.now().strftime('%Y-%m-%d')}",
        "=" * 60,
        "",
        "📭 NO SIGNIFICANT ACTIVITY TODAY",
        "",
        f"Transactions Analyzed: {total_transactions}",
        f"Buy Transactions: {buy_count}",
        "",
        "Why No Signals?",
        "Our system requires:",
        "  • Multiple insiders buying the same stock (cluster)",
        "  • Meaningful purchase amounts ($100k+)",
        "  • C-suite involvement for urgent alerts",
        "  • Open-market purchases (not options/routine)",
        "",
        "What's Next?",
        "Your system is monitoring correctly. We'll alert you when",
        "significant insider buying clusters are detected.",
        "",
        "Next report: Tomorrow at 7:05 AM ET",
        "=" * 60
    ]
    
    text = "\n".join(text_lines)
    return html, text

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