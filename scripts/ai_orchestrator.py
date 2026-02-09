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


def generate_ai_insights(broker_context=None):
    """
    Generate AI insights for EOD email.

    This is the main entry point called by execute_trades.py.

    Args:
        broker_context: Optional dict with real Alpaca-sourced metrics:
            {
                'daily_pnl': float,
                'portfolio_value': float,
                'trades_today': int,
                'open_positions': int,
                'exits_today': list of exit dicts,
            }

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

        # Inject broker context so narrative uses real Alpaca data
        if broker_context:
            analysis_results['broker'] = broker_context

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

    Uses broker_context (real Alpaca data) as the primary source of truth
    for today's P&L and trade counts, falling back to analyzer data for
    historical context. This prevents the narrative from contradicting
    the email header when local audit logs are empty.

    Args:
        analysis_results: Dictionary of analyzer results (includes 'broker' key)

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
    broker = analysis_results.get('broker', {})

    # Use broker (Alpaca) data as primary source for today's metrics
    # This is the source of truth - audit log may be empty
    actual_daily_pnl = broker.get('daily_pnl', 0)
    actual_trades = broker.get('trades_today', 0)
    actual_portfolio = broker.get('portfolio_value', 0)
    actual_positions = broker.get('open_positions', 0)

    # Compute today's exits from broker context (real data)
    broker_exits = broker.get('exits_today', [])
    actual_exits = len(broker_exits)
    actual_winners = sum(1 for e in broker_exits if e.get('pnl', 0) > 0)
    actual_losers = sum(1 for e in broker_exits if e.get('pnl', 0) < 0)

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
    daily_pnl_hist = historical.get('daily_pnl') or {}

    # Determine data availability for historical sections
    has_historical = bool(
        not historical.get('error')
        and not historical.get('insufficient_data')
        and historical.get('sample_size_30d', 0) > 0
    )
    has_trends = bool(
        not trends.get('error')
        and not trends.get('insufficient_data')
    )
    has_attribution = bool(
        not attribution.get('error')
        and not attribution.get('insufficient_data')
        and best_sector
    )

    # Build historical context section - honest about data availability
    if has_historical:
        historical_text = (
            f"- Win rate: Today {win_rate.get('today', 0)}% vs "
            f"Avg {win_rate.get('avg_30d', 0)}% ({win_rate.get('status', 'unknown')})\n"
            f"- Daily P&L: Today ${daily_pnl_hist.get('today', 0)} vs "
            f"Avg ${daily_pnl_hist.get('avg_30d', 0)} ({daily_pnl_hist.get('status', 'unknown')})"
        )
    else:
        historical_text = "- Insufficient historical trade data for 30-day comparison"

    if has_trends:
        trends_text = (
            f"- Win rate: {wr_trend.get('direction', 'stable')} "
            f"({wr_trend.get('change', 0):+.1f}%)\n"
            f"- P&L: {pnl_trend_data.get('direction', 'stable')} "
            f"({pnl_trend_data.get('change', 0):+.1f}%)"
        )
    else:
        trends_text = "- Insufficient data for 7-day trend analysis"

    if has_attribution:
        attribution_text = (
            f"- Best sector: {best_sector.get('sector', 'N/A')} "
            f"(${best_sector.get('pnl', 0):+,.0f}, {best_sector.get('trades', 0)} trades)\n"
            f"- Worst sector: {worst_sector.get('sector', 'N/A')} "
            f"(${worst_sector.get('pnl', 0):+,.0f}, {worst_sector.get('trades', 0)} trades)"
        )
    else:
        attribution_text = "- Insufficient closed-trade data for sector attribution"

    # Build CONCISE but INFORMATION-RICH prompt with real broker data
    prompt = f"""You are a quantitative trading analyst. Provide today's analysis.
IMPORTANT: Use the CONFIRMED broker data below as ground truth. Do NOT contradict these numbers.
If historical data is marked as insufficient, acknowledge it honestly — do NOT invent metrics.

CONFIRMED TODAY (from broker):
- Daily P&L: ${actual_daily_pnl:+,.2f}
- Portfolio Value: ${actual_portfolio:,.2f}
- Trades Executed: {actual_trades}
- Positions Closed: {actual_exits} ({actual_winners} wins, {actual_losers} losses)
- Open Positions: {actual_positions}
- Filters blocked: {filters.get('total_blocks_today', 0)}
- Top sector (open): {sectors.get('top_sector', 'N/A')} ({sectors.get('top_sector_pct', 0)}%)

HISTORICAL CONTEXT (30-day):
{historical_text}

TRENDS (7-day):
{trends_text}

ATTRIBUTION (30-day):
{attribution_text}

ANOMALIES:
{anomaly_text}

TASK: Write a concise analysis (under 200 words):

VERDICT: [one sentence - how today went, referencing the confirmed daily P&L]

KEY INSIGHTS (2-3 bullets):
- [Today's performance insight using confirmed data]
- [Historical/trend insight if data available, or note data gap]
- [Risk or anomaly insight]

PRIORITY ACTIONS (1-2 specific):
1. [HIGH/MEDIUM] [specific action with target numbers]

Format exactly as shown. Be quantitative and actionable. Never fabricate numbers."""

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
