"""
Sector Relative Analysis Module

Provides sector-based timing signals and concentration tracking for insider trading pipeline.
Maps stocks to sector ETFs, calculates relative performance vs SPY, and identifies
contrarian opportunities or momentum plays.

Features:
- Sector ETF mapping (XLK, XLE, XLF, etc.)
- Multi-timeframe analysis (30/60/90 days)
- Timing signals (UPGRADE for contrarian, NOTE for late momentum)
- Portfolio concentration tracking
- Daily caching for lightweight GitHub Actions execution
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Sector to ETF mapping
SECTOR_ETFS = {
    'Technology': 'XLK',
    'Healthcare': 'XLV',
    'Financials': 'XLF',
    'Financial Services': 'XLF',  # Alternative name
    'Energy': 'XLE',
    'Consumer Cyclical': 'XLY',
    'Consumer Defensive': 'XLP',
    'Industrials': 'XLI',
    'Real Estate': 'XLRE',
    'Utilities': 'XLU',
    'Communication Services': 'XLC',
    'Communication': 'XLC',  # Alternative name
    'Basic Materials': 'XLB',
    'Materials': 'XLB',  # Alternative name
}

# Concentration thresholds
HIGH_CONCENTRATION_THRESHOLD = 0.40  # 40% in one sector
WARNING_CONCENTRATION_THRESHOLD = 0.30  # 30% in one sector

# Performance thresholds for timing signals
CONTRARIAN_THRESHOLD = -0.10  # Sector down 10%+ vs SPY = upgrade
MOMENTUM_THRESHOLD = 0.10     # Sector up 10%+ vs SPY = note
STRONG_THRESHOLD = 0.15       # Very strong move


class SectorAnalyzer:
    """Analyzes sector relative performance and provides timing signals."""

    def __init__(self, cache_dir='data', cache_hours=24):
        """
        Initialize sector analyzer.

        Args:
            cache_dir: Directory to store cache files
            cache_hours: Hours to keep cache valid (default 24)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / 'sector_performance_cache.json'
        self.cache_hours = cache_hours
        self.performance_data = None
        self._load_cache()

    def _load_cache(self):
        """Load cached sector performance data if valid."""
        if not self.cache_file.exists():
            logger.info("No sector performance cache found")
            return

        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)

            # Check cache age
            cache_time = datetime.fromisoformat(cache['timestamp'])
            age_hours = (datetime.now() - cache_time).total_seconds() / 3600

            if age_hours < self.cache_hours:
                self.performance_data = cache['data']
                logger.info(f"Loaded sector performance cache (age: {age_hours:.1f}h)")
            else:
                logger.info(f"Cache expired (age: {age_hours:.1f}h)")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self):
        """Save sector performance data to cache."""
        if self.performance_data is None:
            return

        try:
            cache = {
                'timestamp': datetime.now().isoformat(),
                'data': self.performance_data
            }
            self.cache_dir.mkdir(exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
            logger.info("Saved sector performance cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def update_sector_performance(self):
        """
        Fetch and cache sector ETF performance vs SPY.
        Called once per day to minimize API calls.

        Returns:
            dict: Performance data for all sector ETFs
        """
        logger.info("Updating sector performance data...")

        # Get all unique ETFs to fetch
        etfs = list(set(SECTOR_ETFS.values()))
        etfs.append('SPY')  # Add benchmark

        performance = {}

        # Fetch data for each ETF
        for etf in etfs:
            try:
                ticker = yf.Ticker(etf)
                hist = ticker.history(period='6mo')  # Get 6 months for all timeframes

                if hist.empty:
                    logger.warning(f"No data for {etf}")
                    continue

                current_price = hist['Close'].iloc[-1]

                # Calculate returns for different timeframes
                returns = {}
                for days in [30, 60, 90]:
                    try:
                        if len(hist) >= days:
                            past_price = hist['Close'].iloc[-days]
                            returns[f'{days}d'] = (current_price / past_price) - 1.0
                        else:
                            returns[f'{days}d'] = None
                    except Exception as e:
                        logger.warning(f"Failed to calculate {days}d return for {etf}: {e}")
                        returns[f'{days}d'] = None

                performance[etf] = {
                    'current_price': float(current_price),
                    'returns': returns,
                    'last_updated': datetime.now().isoformat()
                }

            except Exception as e:
                logger.error(f"Failed to fetch data for {etf}: {e}")
                performance[etf] = None

        self.performance_data = performance
        self._save_cache()

        return performance

    def get_sector_performance(self):
        """
        Get cached sector performance or update if needed.

        Returns:
            dict: Performance data for all sector ETFs
        """
        if self.performance_data is None:
            self.update_sector_performance()

        return self.performance_data

    def get_stock_sector(self, ticker):
        """
        Get sector for a stock using yfinance.

        Args:
            ticker: Stock ticker symbol

        Returns:
            str: Sector name or 'Unknown'
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Try different keys that might contain sector info
            sector = info.get('sector') or info.get('sectorKey') or info.get('sectorDisp')

            if sector:
                return sector

            logger.warning(f"No sector found for {ticker}")
            return 'Unknown'

        except Exception as e:
            logger.error(f"Failed to get sector for {ticker}: {e}")
            return 'Unknown'

    def analyze_signal_sector(self, ticker, sector=None):
        """
        Analyze sector relative performance for a signal.

        Args:
            ticker: Stock ticker symbol
            sector: Sector name (optional, will fetch if not provided)

        Returns:
            dict: Sector analysis with timing signals
        """
        # Get sector if not provided
        if sector is None or sector == 'Unknown':
            sector = self.get_stock_sector(ticker)

        # Get ETF for this sector
        sector_etf = SECTOR_ETFS.get(sector)

        if not sector_etf:
            logger.warning(f"No ETF mapping for sector: {sector}")
            return {
                'sector': sector,
                'sector_etf': None,
                'relative_performance_30d': None,
                'relative_performance_60d': None,
                'relative_performance_90d': None,
                'sector_signal': 'UNKNOWN',
                'sector_context': 'No sector ETF mapping available'
            }

        # Get performance data
        performance = self.get_sector_performance()

        if not performance or sector_etf not in performance or 'SPY' not in performance:
            logger.warning("Performance data not available")
            return {
                'sector': sector,
                'sector_etf': sector_etf,
                'relative_performance_30d': None,
                'relative_performance_60d': None,
                'relative_performance_90d': None,
                'sector_signal': 'UNKNOWN',
                'sector_context': 'Performance data unavailable'
            }

        # Calculate relative performance vs SPY
        sector_data = performance.get(sector_etf)
        spy_data = performance.get('SPY')

        if not sector_data or not spy_data:
            return {
                'sector': sector,
                'sector_etf': sector_etf,
                'relative_performance_30d': None,
                'relative_performance_60d': None,
                'relative_performance_90d': None,
                'sector_signal': 'UNKNOWN',
                'sector_context': 'Incomplete performance data'
            }

        # Calculate relative performance for each timeframe
        rel_perf = {}
        for period in ['30d', '60d', '90d']:
            sector_ret = sector_data['returns'].get(period)
            spy_ret = spy_data['returns'].get(period)

            if sector_ret is not None and spy_ret is not None:
                rel_perf[period] = sector_ret - spy_ret
            else:
                rel_perf[period] = None

        # Generate timing signal based on 30-day relative performance
        sector_signal, sector_context = self._generate_timing_signal(
            rel_perf['30d'],
            sector,
            sector_etf
        )

        return {
            'sector': sector,
            'sector_etf': sector_etf,
            'relative_performance_30d': rel_perf['30d'],
            'relative_performance_60d': rel_perf['60d'],
            'relative_performance_90d': rel_perf['90d'],
            'sector_signal': sector_signal,
            'sector_context': sector_context
        }

    def _generate_timing_signal(self, rel_perf_30d, sector, sector_etf):
        """
        Generate timing signal based on sector relative performance.

        Args:
            rel_perf_30d: 30-day relative performance vs SPY
            sector: Sector name
            sector_etf: Sector ETF ticker

        Returns:
            tuple: (signal, context_message)
        """
        if rel_perf_30d is None:
            return 'NEUTRAL', 'Sector performance data unavailable'

        perf_pct = rel_perf_30d * 100  # Convert to percentage

        # Strong contrarian opportunity
        if rel_perf_30d <= -STRONG_THRESHOLD:
            return 'STRONG_UPGRADE', (
                f"🎯 STRONG CONTRARIAN: {sector} ({sector_etf}) down "
                f"{abs(perf_pct):.1f}% vs SPY (30d) - high conviction on insider buying"
            )

        # Contrarian opportunity
        elif rel_perf_30d <= CONTRARIAN_THRESHOLD:
            return 'UPGRADE', (
                f"⬆️ CONTRARIAN: {sector} ({sector_etf}) down "
                f"{abs(perf_pct):.1f}% vs SPY (30d) - sector weakness + insider buying"
            )

        # Strong momentum (potentially late)
        elif rel_perf_30d >= STRONG_THRESHOLD:
            return 'CAUTION', (
                f"⚠️ LATE MOMENTUM: {sector} ({sector_etf}) up "
                f"{perf_pct:.1f}% vs SPY (30d) - sector already strong, proceed with caution"
            )

        # Moderate momentum
        elif rel_perf_30d >= MOMENTUM_THRESHOLD:
            return 'NOTE', (
                f"📈 MOMENTUM: {sector} ({sector_etf}) up "
                f"{perf_pct:.1f}% vs SPY (30d) - sector strength, consider momentum play"
            )

        # Neutral
        else:
            return 'NEUTRAL', (
                f"Sector {sector} ({sector_etf}) at {perf_pct:+.1f}% vs SPY (30d)"
            )

    def analyze_portfolio_concentration(self, signals_df):
        """
        Analyze sector concentration across active signals.

        Args:
            signals_df: DataFrame with signals containing 'sector' column

        Returns:
            dict: Concentration analysis with warnings
        """
        if signals_df.empty or 'sector' not in signals_df.columns:
            return {
                'total_signals': 0,
                'sector_breakdown': {},
                'warnings': [],
                'recommendation': None
            }

        # Count signals by sector
        sector_counts = signals_df['sector'].value_counts()
        total_signals = len(signals_df)

        # Calculate percentages
        sector_breakdown = {}
        warnings = []

        for sector, count in sector_counts.items():
            if sector == 'Unknown':
                continue

            pct = count / total_signals
            sector_breakdown[sector] = {
                'count': int(count),
                'percentage': pct
            }

            # Check for high concentration
            if pct >= HIGH_CONCENTRATION_THRESHOLD:
                warnings.append(
                    f"⚠️ HIGH CONCENTRATION: {sector} ({count} signals, "
                    f"{pct*100:.1f}%) - Consider skipping next {sector} signal"
                )
            elif pct >= WARNING_CONCENTRATION_THRESHOLD:
                warnings.append(
                    f"⚡ ELEVATED CONCENTRATION: {sector} ({count} signals, "
                    f"{pct*100:.1f}%) - Monitor sector diversification"
                )

        # Generate recommendation
        recommendation = None
        if warnings:
            most_concentrated = max(sector_breakdown.items(),
                                   key=lambda x: x[1]['percentage'])
            sector_name = most_concentrated[0]
            recommendation = (
                f"Consider diversifying away from {sector_name}. "
                f"Look for opportunities in underrepresented sectors."
            )

        return {
            'total_signals': total_signals,
            'sector_breakdown': sector_breakdown,
            'warnings': warnings,
            'recommendation': recommendation
        }

    def enhance_signals_with_sector_analysis(self, signals_df):
        """
        Add sector analysis columns to signals DataFrame.

        Args:
            signals_df: DataFrame with signals

        Returns:
            DataFrame: Enhanced signals with sector analysis
        """
        if signals_df.empty:
            return signals_df

        logger.info(f"Enhancing {len(signals_df)} signals with sector analysis...")

        # Ensure we have fresh performance data
        if self.performance_data is None:
            self.update_sector_performance()

        # Add sector analysis for each signal
        sector_data = []
        for _, row in signals_df.iterrows():
            ticker = row['ticker']
            sector = row.get('sector', 'Unknown')

            analysis = self.analyze_signal_sector(ticker, sector)
            sector_data.append(analysis)

        # Convert to DataFrame and merge
        sector_df = pd.DataFrame(sector_data)

        # Update sector if we got better data
        if 'sector' in sector_df.columns:
            signals_df['sector'] = sector_df['sector']

        # Add new columns
        for col in ['sector_etf', 'relative_performance_30d',
                    'relative_performance_60d', 'relative_performance_90d',
                    'sector_signal', 'sector_context']:
            if col in sector_df.columns:
                signals_df[col] = sector_df[col]

        logger.info("Sector analysis complete")

        return signals_df

    def get_sector_summary(self):
        """
        Get summary of all sector performances.

        Returns:
            list: Summary of sector performances sorted by performance
        """
        performance = self.get_sector_performance()

        if not performance or 'SPY' not in performance:
            return []

        spy_data = performance['SPY']
        spy_ret_30d = spy_data['returns'].get('30d', 0)

        # Create summary for each sector
        summary = []
        for sector, etf in SECTOR_ETFS.items():
            if etf not in performance or performance[etf] is None:
                continue

            etf_data = performance[etf]
            etf_ret_30d = etf_data['returns'].get('30d')

            if etf_ret_30d is None:
                continue

            rel_perf = etf_ret_30d - spy_ret_30d

            summary.append({
                'sector': sector,
                'etf': etf,
                'return_30d': etf_ret_30d * 100,
                'relative_30d': rel_perf * 100,
                'vs_spy': 'Outperform' if rel_perf > 0 else 'Underperform'
            })

        # Sort by relative performance
        summary.sort(key=lambda x: x['relative_30d'], reverse=True)

        return summary


def format_sector_concentration_report(concentration_analysis):
    """
    Format sector concentration analysis for email reports.

    Args:
        concentration_analysis: Output from analyze_portfolio_concentration()

    Returns:
        str: Formatted HTML report section
    """
    if not concentration_analysis or concentration_analysis['total_signals'] == 0:
        return ""

    html_parts = ["<h3>📊 Sector Concentration Analysis</h3>"]
    html_parts.append(f"<p>Total Active Signals: {concentration_analysis['total_signals']}</p>")

    # Breakdown table
    if concentration_analysis['sector_breakdown']:
        html_parts.append("<table border='1' cellpadding='5' cellspacing='0'>")
        html_parts.append("<tr><th>Sector</th><th>Count</th><th>Percentage</th></tr>")

        # Sort by percentage descending
        sorted_sectors = sorted(
            concentration_analysis['sector_breakdown'].items(),
            key=lambda x: x[1]['percentage'],
            reverse=True
        )

        for sector, data in sorted_sectors:
            pct = data['percentage'] * 100
            html_parts.append(
                f"<tr><td>{sector}</td><td>{data['count']}</td>"
                f"<td>{pct:.1f}%</td></tr>"
            )

        html_parts.append("</table>")

    # Warnings
    if concentration_analysis['warnings']:
        html_parts.append("<h4>⚠️ Concentration Warnings</h4>")
        html_parts.append("<ul>")
        for warning in concentration_analysis['warnings']:
            html_parts.append(f"<li>{warning}</li>")
        html_parts.append("</ul>")

    # Recommendation
    if concentration_analysis['recommendation']:
        html_parts.append(f"<p><strong>Recommendation:</strong> {concentration_analysis['recommendation']}</p>")

    return "\n".join(html_parts)


# Convenience function for direct use
def analyze_signal_sector(ticker, sector=None):
    """
    Quick analysis of a single signal's sector timing.

    Args:
        ticker: Stock ticker
        sector: Optional sector name

    Returns:
        dict: Sector analysis
    """
    analyzer = SectorAnalyzer()
    return analyzer.analyze_signal_sector(ticker, sector)


if __name__ == '__main__':
    # Test the analyzer
    analyzer = SectorAnalyzer()

    # Update performance data
    print("Updating sector performance...")
    analyzer.update_sector_performance()

    # Get sector summary
    print("\n=== Sector Performance Summary ===")
    summary = analyzer.get_sector_summary()
    for item in summary:
        print(f"{item['sector']:25s} ({item['etf']})  "
              f"{item['return_30d']:+6.2f}%  (vs SPY: {item['relative_30d']:+6.2f}%)")

    # Test with sample tickers
    print("\n=== Sample Stock Analysis ===")
    test_tickers = ['AAPL', 'JPM', 'XOM', 'JNJ']
    for ticker in test_tickers:
        analysis = analyzer.analyze_signal_sector(ticker)
        print(f"\n{ticker}:")
        print(f"  Sector: {analysis['sector']} ({analysis.get('sector_etf', 'N/A')})")
        print(f"  30d Rel Perf: {analysis.get('relative_performance_30d', 'N/A')}")
        print(f"  Signal: {analysis['sector_signal']}")
        print(f"  Context: {analysis['sector_context']}")
