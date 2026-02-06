#!/usr/bin/env python3
"""
Lightweight AI Orchestrator for EOD Email Integration

Returns structured insights dictionary for alerts.py to format.
This module is optimized for:
- Fast execution (<5 seconds)
- Low memory usage (<100MB)
- Graceful failure (never blocks EOD email)
- Groq free tier: <3,000 tokens input, <800 tokens output
"""

import os
import sys
import json
from pathlib import Path

# Groq import
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.analyzers import (
    FilterAnalyzer,
    PerformanceAnalyzer,
    SectorAnalyzer,
    ExecutionAnalyzer,
    HistoricalAnalyzer,
    TrendAnalyzer,
    AttributionAnalyzer,
    AnomalyAnalyzer
)


def generate_ai_insights():
    """
    Generate AI insights for EOD email.

    This is the main entry point called by execute_trades.py.

    Returns:
        dict: Structured insights dictionary
            {
                'available': bool,
                'narrative': str (AI-generated summary, if available),
                'data': dict (analyzer results, if available),
                'model': str (if available),
                'reason': str (if unavailable)
            }
    """

    # If Groq not available, return minimal insights
    if not GROQ_AVAILABLE:
        return {
            'available': False,
            'reason': 'Groq SDK not installed'
        }

    try:
        # Run analyzers (fast, <2 seconds total)
        analysis_results = _run_analyzers()

        # Generate narrative (Groq API, ~2 seconds)
        narrative = _generate_narrative(analysis_results)

        # Return structured insights
        return {
            'available': True,
            'narrative': narrative,
            'data': analysis_results,
            'model': 'llama-3.3-70b-versatile'
        }

    except Exception as e:
        # Graceful failure - return None
        return {
            'available': False,
            'reason': str(e)
        }


def _run_analyzers():
    """
    Run all analyzers and collect results.

    Returns:
        dict: Results from all analyzers
            {
                'filters': {...},
                'performance': {...},
                'sectors': {...},
                'execution': {...},
                'historical': {...},
                'trends': {...},
                'attribution': {...},
                'anomalies': {...}
            }
    """

    results = {}

    analyzers = [
        ('filters', FilterAnalyzer),
        ('performance', PerformanceAnalyzer),
        ('sectors', SectorAnalyzer),
        ('execution', ExecutionAnalyzer),
        ('historical', HistoricalAnalyzer),
        ('trends', TrendAnalyzer),
        ('attribution', AttributionAnalyzer),
        ('anomalies', AnomalyAnalyzer)
    ]

    for name, AnalyzerClass in analyzers:
        try:
            analyzer = AnalyzerClass()
            results[name] = analyzer.analyze()
        except Exception as e:
            results[name] = {'error': str(e)}

    return results


def _generate_narrative(analysis_results):
    """
    Call Groq API with enriched insights for concise narrative.

    Sends only computed insights (not raw data) to stay within
    Groq free tier limits (~2,500 input + ~600 output = ~3,100 tokens).

    Args:
        analysis_results: Dictionary of analyzer results

    Returns:
        str: AI-generated narrative summary
    """

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return "AI analysis unavailable (API key not set)"

    # Extract computed insights for concise prompt
    perf = analysis_results.get('performance', {})
    filters = analysis_results.get('filters', {})
    sectors = analysis_results.get('sectors', {})
    historical = analysis_results.get('historical', {})
    trends = analysis_results.get('trends', {})
    attribution = analysis_results.get('attribution', {})
    anomalies = analysis_results.get('anomalies', {})

    # Build anomalies text concisely
    anomaly_text = "None detected"
    anomaly_list = anomalies.get('anomalies', [])
    if anomaly_list:
        anomaly_text = "; ".join(
            a.get('message', '') for a in anomaly_list[:2]
        )

    # Safely extract nested values (guard against None)
    best_sector = attribution.get('best_sector') or {}
    worst_sector = attribution.get('worst_sector') or {}
    wr_trend = trends.get('win_rate_trend') or {}
    pnl_trend_data = trends.get('pnl_trend') or {}
    win_rate = historical.get('win_rate') or {}
    daily_pnl = historical.get('daily_pnl') or {}

    # Build CONCISE but INFORMATION-RICH prompt
    prompt = f"""You are a quantitative trading analyst. Provide today's analysis with historical context.

TODAY'S METRICS:
- Exits: {perf.get('exits_today', 0)}
- Filters blocked: {filters.get('total_blocks_today', 0)}
- Top sector: {sectors.get('top_sector', 'N/A')} ({sectors.get('top_sector_pct', 0)}%)

HISTORICAL CONTEXT (30-day):
- Win rate: Today {win_rate.get('today', 0)}% vs Avg {win_rate.get('avg_30d', 0)}% ({win_rate.get('status', 'unknown')})
- Daily P&L: Today ${daily_pnl.get('today', 0)} vs Avg ${daily_pnl.get('avg_30d', 0)} ({daily_pnl.get('status', 'unknown')})

TRENDS (7-day):
- Win rate: {wr_trend.get('direction', 'stable')} ({wr_trend.get('change', 0):+.1f}%)
- P&L: {pnl_trend_data.get('direction', 'stable')} ({pnl_trend_data.get('change', 0):+.1f}%)

ATTRIBUTION (30-day):
- Best sector: {best_sector.get('sector', 'N/A')} (${best_sector.get('pnl', 0):+,.0f})
- Worst sector: {worst_sector.get('sector', 'N/A')} (${worst_sector.get('pnl', 0):+,.0f})

ANOMALIES:
{anomaly_text}

TASK: Write a concise analysis (under 200 words):

VERDICT: [one sentence - how today went vs expectations]

KEY INSIGHTS (2-3 bullets):
- [Historical context insight]
- [Trend insight]
- [Attribution or anomaly insight]

PRIORITY ACTIONS (1-2 specific):
1. [HIGH/MEDIUM] [specific action with target numbers]

Format exactly as shown. Be quantitative and actionable."""

    try:
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            max_tokens=600,  # Concise output
            temperature=0.3
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"AI analysis failed: {str(e)}"


# For testing
if __name__ == '__main__':
    insights = generate_ai_insights()
    print(json.dumps(insights, indent=2))
