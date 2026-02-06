#!/usr/bin/env python3
"""
Test AI Analysis System

Tests all analyzers and the AI orchestrator to ensure they work correctly
before integrating into the EOD email workflow.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_data_files():
    """Check data files exist."""
    print("Testing data file access...")

    required = [
        'data/signals_history.csv',
        'data/approved_signals.json',
        'automated_trading/data/audit_log.jsonl',
    ]

    optional = [
        'automated_trading/data/exits_today.json',
        'automated_trading/data/live_positions.json',
        'automated_trading/data/execution_metrics.json',
    ]

    base = Path(__file__).parent.parent
    for file in required:
        path = base / file
        status = "✅" if path.exists() else "❌"
        print(f"  {status} {file}")

    for file in optional:
        path = base / file
        status = "✅" if path.exists() else "⚠️ "
        print(f"  {status} {file} (optional)")


def test_analyzers():
    """Test each analyzer with detailed output."""
    print("\nTesting analyzers...")

    from scripts.analyzers import (
        FilterAnalyzer, PerformanceAnalyzer,
        SectorAnalyzer, ExecutionAnalyzer
    )

    for name, Analyzer in [
        ('FilterAnalyzer', FilterAnalyzer),
        ('PerformanceAnalyzer', PerformanceAnalyzer),
        ('SectorAnalyzer', SectorAnalyzer),
        ('ExecutionAnalyzer', ExecutionAnalyzer)
    ]:
        try:
            result = Analyzer().analyze()

            # Check for errors
            if 'error' in result:
                print(f"  ❌ {name}: {result['error']}")
                if 'traceback' in result:
                    print(f"     Traceback: {result['traceback'][:200]}")
            else:
                print(f"  ✅ {name}")

                # Show key metrics
                if name == 'FilterAnalyzer':
                    print(f"     Total blocks: {result.get('total_blocks_today', 0)}")
                elif name == 'PerformanceAnalyzer':
                    print(f"     Exits today: {result.get('exits_today', 0)}")
                elif name == 'SectorAnalyzer':
                    print(f"     Positions: {result.get('total_positions', 0)}")
                    print(f"     Top sector: {result.get('top_sector', 'N/A')} ({result.get('top_sector_pct', 0)}%)")
                elif name == 'ExecutionAnalyzer':
                    print(f"     Orders today: {result.get('orders_today', 0)}")

        except Exception as e:
            import traceback
            print(f"  ❌ {name}: {e}")
            print(f"     {traceback.format_exc()[:200]}")


def test_orchestrator():
    """Test AI orchestrator."""
    print("\nTesting AI orchestrator...")

    from scripts.ai_orchestrator import generate_ai_insights

    try:
        insights = generate_ai_insights()
        if insights.get('available'):
            print(f"  ✅ AI insights generated")
            print(f"  Model: {insights.get('model')}")
            print(f"\n  Narrative Preview:")
            narrative = insights.get('narrative', '')
            # Print first 200 chars
            print(f"  {narrative[:200]}..." if len(narrative) > 200 else f"  {narrative}")
        else:
            print(f"  ⚠️  AI unavailable: {insights.get('reason')}")
    except Exception as e:
        print(f"  ❌ Orchestrator failed: {e}")


if __name__ == '__main__':
    print("="*60)
    print("AI ANALYSIS SYSTEM TEST")
    print("="*60)

    test_data_files()
    test_analyzers()
    test_orchestrator()

    print("\n" + "="*60)
    print("✅ Tests complete")
    print("="*60)
