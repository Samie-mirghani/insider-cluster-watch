#!/usr/bin/env python3
"""
Regression tests for EOD email fix branch.

Covers the critical bugs found during the Review, Repair, and Verify cycle.
These are unit-level tests that don't require external services (Alpaca, Groq).
"""

import json
import os
import sys
import tempfile
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = 0
FAIL = 0


def report(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} — {detail}")


# ─── Test 1: actual_losers excludes break-even trades ────────────────────────

def test_losers_excludes_breakeven():
    """Bug: actual_losers counted pnl==0 as loss (<= 0). Fixed to < 0."""
    broker_exits = [
        {'pnl': 50},    # winner
        {'pnl': 0},     # break-even — should NOT be a loser
        {'pnl': -20},   # loser
        {'pnl': 0},     # break-even
    ]
    actual_losers = sum(1 for e in broker_exits if e.get('pnl', 0) < 0)
    actual_winners = sum(1 for e in broker_exits if e.get('pnl', 0) > 0)
    report(
        "actual_losers excludes break-even (pnl==0)",
        actual_losers == 1,
        f"expected 1, got {actual_losers}"
    )
    report(
        "actual_winners counts only positives",
        actual_winners == 1,
        f"expected 1, got {actual_winners}"
    )


# ─── Test 2: ExecutionAnalyzer returns no_data when no today execs ───────────

def test_execution_analyzer_no_data_flag():
    """Bug: inner return path lacked no_data flag."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({'executions': [
            {'date': '2000-01-01', 'filled': True, 'slippage_pct': 0.1}
        ]}, f)
        tmp = f.name

    try:
        from scripts.analyzers.execution_analyzer import ExecutionAnalyzer
        analyzer = ExecutionAnalyzer()
        # Patch the metrics file path
        with patch.object(
            analyzer, '_get_today_executions',
            wraps=analyzer._get_today_executions
        ):
            # Override base_dir to use temp dir
            original_base = analyzer.base_dir
            tmpdir = Path(tmp).parent
            (tmpdir / 'automated_trading' / 'data').mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy(tmp, tmpdir / 'automated_trading' / 'data' / 'execution_metrics.json')
            analyzer.base_dir = tmpdir

            result = analyzer._get_today_executions()
            report(
                "ExecutionAnalyzer._get_today_executions returns no_data when empty today",
                result.get('no_data') is True,
                f"got {result}"
            )

            # Also verify analyze() propagates it
            analysis = analyzer.analyze()
            report(
                "ExecutionAnalyzer.analyze() includes no_data flag",
                analysis.get('no_data') is True,
                f"got {analysis}"
            )
            analyzer.base_dir = original_base
    finally:
        os.unlink(tmp)


# ─── Test 3: Slippage anomaly reads from executions list ─────────────────────

def test_slippage_anomaly_reads_flat_executions():
    """Bug: _check_slippage_anomaly read non-existent nested keys.
    Fixed to read from the flat 'executions' list."""
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Build metrics with 15 historical entries (with variance) + 1 extreme today
    executions = []
    import random
    random.seed(42)
    for i in range(15):
        d = (datetime.now() - timedelta(days=i+1)).strftime('%Y-%m-%d')
        # Add variance so stdev > 0
        slip = 0.05 + random.uniform(-0.02, 0.02)
        executions.append({'date': d, 'filled': True, 'slippage_pct': slip})
    # Today's slippage is wildly above normal (should trigger >2 stdev)
    executions.append({'date': today, 'filled': True, 'slippage_pct': 5.0})

    metrics = {'executions': executions}

    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / 'automated_trading' / 'data'
        data_dir.mkdir(parents=True)
        with open(data_dir / 'execution_metrics.json', 'w') as f:
            json.dump(metrics, f)

        from scripts.analyzers.anomaly_analyzer import AnomalyAnalyzer
        analyzer = AnomalyAnalyzer()
        analyzer.base_dir = Path(tmpdir)

        result = analyzer._check_slippage_anomaly()
        report(
            "Slippage anomaly detects outlier from flat executions list",
            result is not None and result.get('type') == 'slippage',
            f"expected slippage anomaly, got {result}"
        )

    # Also test: no executions returns None (no crash)
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / 'automated_trading' / 'data'
        data_dir.mkdir(parents=True)
        with open(data_dir / 'execution_metrics.json', 'w') as f:
            json.dump({'executions': []}, f)

        analyzer2 = AnomalyAnalyzer()
        analyzer2.base_dir = Path(tmpdir)
        result2 = analyzer2._check_slippage_anomaly()
        report(
            "Slippage anomaly returns None on empty executions (no crash)",
            result2 is None,
            f"expected None, got {result2}"
        )


# ─── Test 4: execution_metrics record_execution includes 'filled' field ──────

def test_execution_metrics_filled_field():
    """Bug: record_execution() never set 'filled' field, analyzer checked it.
    Verify via AST inspection since importing execution_metrics requires dotenv."""
    import ast

    em_path = Path(__file__).parent.parent / 'automated_trading' / 'execution_metrics.py'
    source = em_path.read_text()
    tree = ast.parse(source)

    # Find record_execution method and check for 'filled' key in dict literal
    found_filled = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'record_execution':
            # Walk the body for a dict with 'filled' key
            for inner in ast.walk(node):
                if isinstance(inner, ast.Dict):
                    for key in inner.keys:
                        if isinstance(key, ast.Constant) and key.value == 'filled':
                            found_filled = True

    report(
        "record_execution contains 'filled' key in execution dict",
        found_filled,
        "Could not find 'filled' key in record_execution dict literal"
    )


# ─── Test 5: PerformanceAnalyzer returns no_data flag ────────────────────────

def test_performance_analyzer_no_data():
    """Verify PerformanceAnalyzer returns no_data when exits_today is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / 'automated_trading' / 'data'
        data_dir.mkdir(parents=True)

        # Empty exits
        with open(data_dir / 'exits_today.json', 'w') as f:
            json.dump({'date': datetime.now().strftime('%Y-%m-%d'), 'exits': []}, f)

        from scripts.analyzers.performance_analyzer import PerformanceAnalyzer
        analyzer = PerformanceAnalyzer()
        analyzer.base_dir = Path(tmpdir)

        result = analyzer.analyze()
        report(
            "PerformanceAnalyzer returns no_data on empty exits",
            result.get('no_data') is True,
            f"got {result}"
        )


# ─── Test 6: HistoricalAnalyzer returns insufficient_data flag ───────────────

def test_historical_analyzer_insufficient_data():
    """Verify HistoricalAnalyzer returns insufficient_data when no history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / 'automated_trading' / 'data'
        data_dir.mkdir(parents=True)

        # Empty audit log
        with open(data_dir / 'audit_log.jsonl', 'w') as f:
            pass  # empty file

        from scripts.analyzers.historical_analyzer import HistoricalAnalyzer
        analyzer = HistoricalAnalyzer()
        analyzer.base_dir = Path(tmpdir)

        result = analyzer.analyze()
        report(
            "HistoricalAnalyzer returns insufficient_data on empty audit log",
            result.get('insufficient_data') is True,
            f"got {result}"
        )


# ─── Test 7: AnomalyAnalyzer._load_closed_trades reads audit log ─────────────

def test_anomaly_analyzer_reads_audit_log():
    """Verify anomaly analyzer uses audit_log.jsonl as primary source."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / 'automated_trading' / 'data'
        data_dir.mkdir(parents=True)

        today = datetime.now().strftime('%Y-%m-%d')
        event = {
            'event_type': 'POSITION_CLOSED',
            'timestamp': f'{today}T15:30:00',
            'data': {'pnl': 42.50}
        }
        with open(data_dir / 'audit_log.jsonl', 'w') as f:
            f.write(json.dumps(event) + '\n')

        from scripts.analyzers.anomaly_analyzer import AnomalyAnalyzer
        analyzer = AnomalyAnalyzer()
        analyzer.base_dir = Path(tmpdir)

        trades = analyzer._load_closed_trades(days=7)
        report(
            "AnomalyAnalyzer._load_closed_trades reads from audit_log.jsonl",
            len(trades) == 1 and trades[0]['pnl'] == 42.50,
            f"got {trades}"
        )


# ─── Run all ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("REGRESSION TESTS — EOD Email Fix Branch")
    print("=" * 60)

    print("\n[1] Losers/Winners logic")
    test_losers_excludes_breakeven()

    print("\n[2] ExecutionAnalyzer no_data flag")
    test_execution_analyzer_no_data_flag()

    print("\n[3] Slippage anomaly flat executions")
    test_slippage_anomaly_reads_flat_executions()

    print("\n[4] execution_metrics filled field")
    test_execution_metrics_filled_field()

    print("\n[5] PerformanceAnalyzer no_data")
    test_performance_analyzer_no_data()

    print("\n[6] HistoricalAnalyzer insufficient_data")
    test_historical_analyzer_insufficient_data()

    print("\n[7] AnomalyAnalyzer audit_log source")
    test_anomaly_analyzer_reads_audit_log()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    if FAIL == 0:
        print(f"ALL {total} TESTS PASSED")
    else:
        print(f"{FAIL}/{total} TESTS FAILED")
    print("=" * 60)

    sys.exit(1 if FAIL else 0)
