#!/usr/bin/env python3
"""
Lightweight AI Orchestrator for EOD Email Integration

Returns structured insights dictionary for alerts.py to format.
This module is optimized for:
- Fast execution (<5 seconds)
- Low memory usage (<100MB)
- Graceful failure (never blocks EOD email)
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
    ExecutionAnalyzer
)


def generate_ai_insights():
    """
    Generate AI insights for EOD email.

    This is the main entry point called by execute_trades.py.

    Returns:
        dict: Structured insights or None if failed
            {
                'available': bool,
                'narrative': str (AI-generated summary),
                'data': dict (analyzer results),
                'model': str,
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
        # Run analyzers (fast, <1 second total)
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
                'execution': {...}
            }
    """

    results = {}

    analyzers = [
        ('filters', FilterAnalyzer),
        ('performance', PerformanceAnalyzer),
        ('sectors', SectorAnalyzer),
        ('execution', ExecutionAnalyzer)
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
    Call Groq API for concise narrative.

    Args:
        analysis_results: Dictionary of analyzer results

    Returns:
        str: AI-generated narrative summary
    """

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return "AI analysis unavailable (API key not set)"

    # Build CONCISE prompt (<3000 tokens)
    prompt = f"""You are a trading analyst. Provide a brief daily summary for an email.

DATA:
{json.dumps(analysis_results, indent=1)}

Generate a CONCISE analysis with:
1. One-sentence summary
2. 2-3 key insights (bullet points)
3. 1-2 actionable recommendations

Keep total response under 200 words. Be direct and actionable.
Format as plain text (no markdown headers)."""

    try:
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            max_tokens=500,  # Short response
            temperature=0.3
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"AI analysis failed: {str(e)}"


# For testing
if __name__ == '__main__':
    insights = generate_ai_insights()
    print(json.dumps(insights, indent=2))
