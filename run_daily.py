# run_daily.py
import fetch_openinsider as fio
from process_signals import cluster_and_score
from generate_report import render_report
from send_email import send

def main():
    df = fio.fetch_openinsider_recent()
    if df.empty:
        print("No data")
        return
    clusters = cluster_and_score(df)
    if clusters.empty:
        print("No clusters")
        return
    html, text = render_report(clusters)
    send(html, text, subject="Insider Cluster Report — Automated")
    print("Done")

if __name__ == "__main__":
    main()
