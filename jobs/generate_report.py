# jobs/generate_report.py
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import pandas as pd
import os

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')

def render_daily_html(cluster_df):
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    tmpl = env.get_template('daily_report.html')
    rows = cluster_df.to_dict(orient='records')
    html = tmpl.render(date=datetime.now().strftime("%B %d, %Y"), trades=rows)
    text = build_plain_text(rows)
    return html, text

def render_urgent_html(cluster_df):
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    tmpl = env.get_template('urgent_alert.html')
    rows = cluster_df.to_dict(orient='records')
    html = tmpl.render(date=datetime.now().strftime("%B %d, %Y"), urgent_trades=rows)
    text = build_plain_text(rows)
    return html, text

def build_plain_text(rows):
    lines = []
    lines.append(f"Insider Cluster Report — {datetime.now().strftime('%Y-%m-%d')}\n")
    for r in rows:
        lines.append(f"{r.get('ticker')}: cluster={r.get('cluster_count')} | total=${int(r.get('total_value',0)):,} | score={r.get('rank_score'):.2f}")
        lines.append(f"Action: {r.get('suggested_action')}")
        lines.append(f"Rationale: {r.get('rationale')}")
        lines.append("-"*40)
    return "\n".join(lines)
