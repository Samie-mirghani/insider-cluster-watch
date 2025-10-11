# Insider Cluster Watch

Automated pipeline to detect and score insider open-market buys (Form 4), generate a daily HTML/plain-text email report with ranked signals, and optionally wire to brokers later. Built as a DIY-first, low-cost stack: Python scripts + GitHub Actions scheduler + SendGrid (or Gmail) for email. Start paper-only; no automatic trading.

> Repo owner: **Samie-Mirghani**

---

## Table of contents
1. [What this does](#what-this-does)  
2. [Project layout](#project-layout)  
3. [Prerequisites](#prerequisites)  
4. [Install & run locally](#install--run-locally)  
5. [Configuration / Environment variables](#configuration--environment-variables)  
6. [GitHub Actions — automated nightly job (step-by-step)](#github-actions---automated-nightly-job-step-by-step)  
7. [Email templates & customization](#email-templates--customization)  
8. [Testing & validation](#testing--validation)  
9. [Security & operational notes](#security--operational-notes)  
10. [Next steps / roadmap](#next-steps--roadmap)  
11. [License & attribution](#license--attribution)

---

## What this does
- Scrapes recent insider filings from OpenInsider (fast DIY) and normalizes them.  
- Filters for open-market buys and computes simple scores: cluster count and conviction.  
- Enriches candidates with light market data (via `yfinance`).  
- Creates an HTML + plain-text daily report and emails it (SendGrid/Gmail).  
- Runs automatically on a nightly schedule using GitHub Actions (or can be run locally).

This repo is intentionally **opinionated** and minimal — the goal is to get a reliable nightly signal email while you validate the strategy.

---

## Project layout

insider-cluster-watch/
├── fetch_openinsider.py # fetch raw recent filings
├── process_signals.py # filtering, cluster detection, scoring
├── generate_report.py # Jinja2 template rendering
├── templates/
│ └── email_template.html
├── send_email.py # SendGrid or Gmail SMTP wrapper
├── run_daily.py # orchestration entrypoint
├── requirements.txt
├── .github/
│ └── workflows/
│ └── nightly.yml # GitHub Actions workflow
├── README.md
├── .gitignore
└── data/ # optional local cache of raw/norm data


Files above are the expected canonical set. If your code filenames differ, update `run_daily.py` accordingly.

---

## Prerequisites
- Python 3.10+ (3.8+ should work but 3.10 recommended)  
- Git & a GitHub account (personal repo)  
- (Optional) SendGrid account or Gmail account for SMTP sending  
- (Optional) Alpaca account (paper trading) if you later decide to test execution

---

## Install & run locally

1. Clone your repo:
```bash
git clone git@github.com:<your-username>/insider-cluster-watch.git
cd insider-cluster-watch

