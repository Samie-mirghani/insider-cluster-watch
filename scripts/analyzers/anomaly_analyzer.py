"""Anomaly analyzer - detects unusual patterns vs 30-day baseline."""

import csv
import json
import statistics
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


class AnomalyAnalyzer:
    """
    Detect anomalies:
    - Unusual slippage (>2 std dev)
    - Unusual daily P&L (>2 std dev)
    - Loss streaks
    """

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """Detect today's anomalies vs 30-day baseline."""
        try:
            anomalies = []

            slippage_anomaly = self._check_slippage_anomaly()
            if slippage_anomaly:
                anomalies.append(slippage_anomaly)

            pnl_anomaly = self._check_pnl_anomaly()
            if pnl_anomaly:
                anomalies.append(pnl_anomaly)

            loss_streak = self._check_loss_streak()
            if loss_streak:
                anomalies.append(loss_streak)

            return {
                'anomalies_detected': len(anomalies),
                'anomalies': anomalies
            }
        except Exception as e:
            return {'error': str(e), 'traceback': traceback.format_exc()}

    def _check_slippage_anomaly(self):
        """Check if today's slippage is unusual."""
        exec_metrics_file = (
            self.base_dir / 'automated_trading' / 'data'
            / 'execution_metrics.json'
        )

        if not exec_metrics_file.exists():
            return None

        with open(exec_metrics_file, 'r') as f:
            metrics = json.load(f)

        # execution_metrics.py stores executions as a flat list with
        # 'date', 'slippage_pct', and 'filled' fields
        executions = metrics.get('executions', [])
        if not executions:
            return None

        today = datetime.now().strftime('%Y-%m-%d')

        # Collect slippage from filled orders only
        today_slippages = [
            e.get('slippage_pct', 0) for e in executions
            if e.get('date') == today and e.get('filled', True)
        ]
        historical_slippages = [
            e.get('slippage_pct', 0) for e in executions
            if e.get('date') != today and e.get('filled', True)
        ]

        if not today_slippages or len(historical_slippages) < 10:
            return None

        today_slippage = statistics.mean(today_slippages)
        mean = statistics.mean(historical_slippages)
        stdev = (
            statistics.stdev(historical_slippages)
            if len(historical_slippages) > 1 else 0
        )

        if stdev == 0:
            return None

        z_score = (today_slippage - mean) / stdev

        if abs(z_score) > 2:
            return {
                'type': 'slippage',
                'severity': 'high' if abs(z_score) > 3 else 'medium',
                'message': (
                    f"Slippage {today_slippage:.2f}% is "
                    f"{abs(z_score):.1f} std devs from normal ({mean:.2f}%)"
                ),
                'recommendation': 'Check liquidity and order timing'
            }

        return None

    def _load_closed_trades(self, days):
        """
        Load POSITION_CLOSED events from audit log for the last N days.

        Uses the same data source as all other analyzers (audit_log.jsonl)
        for consistency. Falls back to paper_trades.csv if audit log
        has insufficient data.

        Returns:
            list: List of {'date': str, 'pnl': float} dicts
        """
        audit_file = (
            self.base_dir / 'automated_trading' / 'data' / 'audit_log.jsonl'
        )
        cutoff_date = (
            datetime.now() - timedelta(days=days)
        ).strftime('%Y-%m-%d')

        trades = []

        # Primary source: audit log (live trades)
        if audit_file.exists():
            with open(audit_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line)
                        if event.get('event_type') != 'POSITION_CLOSED':
                            continue
                        timestamp = event.get('timestamp', '')
                        exit_date = timestamp[:10]
                        if exit_date < cutoff_date:
                            continue
                        data = event.get('data', {})
                        if not isinstance(data, dict):
                            data = {}
                        pnl = float(data.get('pnl', 0))
                        trades.append({'date': exit_date, 'pnl': pnl})
                    except Exception:
                        continue

        # Fallback: paper_trades.csv if audit log had no data
        if not trades:
            trades_file = self.base_dir / 'data' / 'paper_trades.csv'
            if trades_file.exists():
                with open(trades_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('action') != 'SELL':
                            continue
                        exit_date = row.get('exit_date', '')[:10]
                        if exit_date >= cutoff_date:
                            profit = float(row.get('profit', 0) or 0)
                            trades.append({
                                'date': exit_date,
                                'pnl': profit
                            })

        return trades

    def _check_pnl_anomaly(self):
        """Check if today's P&L is unusual vs 30-day baseline."""
        trades = self._load_closed_trades(days=30)

        if not trades:
            return None

        today = datetime.now().strftime('%Y-%m-%d')
        daily_pnl = defaultdict(float)
        for t in trades:
            daily_pnl[t['date']] += t['pnl']

        if len(daily_pnl) < 10:
            return None

        today_pnl = daily_pnl.get(today, 0)
        historical_pnls = [
            pnl for date, pnl in daily_pnl.items() if date != today
        ]

        if not historical_pnls:
            return None

        mean = statistics.mean(historical_pnls)
        stdev = (
            statistics.stdev(historical_pnls)
            if len(historical_pnls) > 1 else 0
        )

        if stdev == 0:
            return None

        z_score = (today_pnl - mean) / stdev

        if abs(z_score) > 2:
            direction = (
                'exceptional gain' if z_score > 0 else 'exceptional loss'
            )
            return {
                'type': 'pnl',
                'severity': 'high' if abs(z_score) > 3 else 'medium',
                'message': (
                    f"Daily P&L ${today_pnl:,.0f} is "
                    f"{abs(z_score):.1f} std devs from normal "
                    f"(${mean:,.0f}) - {direction}"
                ),
                'recommendation': 'Review what caused unusual performance'
            }

        return None

    def _check_loss_streak(self):
        """Check for concerning loss streaks in last 7 days."""
        trades = self._load_closed_trades(days=7)

        if not trades:
            return None

        trades.sort(key=lambda x: x['date'])

        current_streak = 0
        for trade in reversed(trades):
            if trade['pnl'] <= 0:
                current_streak += 1
            else:
                break

        if current_streak >= 4:
            return {
                'type': 'loss_streak',
                'severity': 'high' if current_streak >= 6 else 'medium',
                'message': (
                    f"Current loss streak: "
                    f"{current_streak} consecutive losses"
                ),
                'recommendation': (
                    'Consider reducing position sizes or pausing trading'
                )
            }

        return None
