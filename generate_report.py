# generate_report.py
from jinja2 import Environment, FileSystemLoader
import pandas as pd
from datetime import datetime

def render_report(cluster_df, template_path='templates'):
    env = Environment(loader=FileSystemLoader(template_path))
    tmpl = env.get_template('email_template.html')
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    html = tmpl.render(date=now, rows=cluster_df.to_dict(orient='records'))
    text = []
    text.append(f"Insider Cluster Report — {now}\n")
    for r in cluster_df.to_dict(orient='records'):
        text.append(f"{r['ticker']}: cluster_count={r['cluster_count']} total_value=${int(r['total_value']):,} rank={r['rank_score']:.2f}")
    return html, "\n".join(text)

def generate_html_report(data, urgent=False):
    env = Environment(loader=FileSystemLoader("templates"))
    template_name = "urgent_alert.html" if urgent else "daily_report.html"
    template = env.get_template(template_name)
    return template.render(
        date=datetime.now().strftime("%B %d, %Y"),
        trades=data if not urgent else None,
        urgent_trades=data if urgent else None
    )

