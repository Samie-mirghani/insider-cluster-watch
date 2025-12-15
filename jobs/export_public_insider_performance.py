#!/usr/bin/env python3
"""
Export public-safe insider performance data for website display.

This script generates a JSON file containing top-performing insiders
for display on the GitHub Pages dashboard. Only includes aggregated
statistics - no sensitive data.

Called by: daily pipeline (jobs/main.py)
Outputs to: docs/insider_performance_public.json
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add jobs directory to path
sys.path.insert(0, os.path.dirname(__file__))

from insider_performance_tracker import InsiderPerformanceTracker


def export_public_data():
    """
    Export top performers to public JSON file.

    Returns:
        Dict with export stats
    """
    print("\n" + "="*70)
    print("EXPORTING PUBLIC INSIDER PERFORMANCE DATA")
    print("="*70)

    try:
        # Initialize tracker
        tracker = InsiderPerformanceTracker()

        if not tracker.profiles:
            print("⚠️  No insider profiles to export")

            # Create minimal empty file
            empty_data = {
                'last_updated': datetime.now().isoformat(),
                'status': 'EMPTY',
                'message': 'No insider performance data available yet. Run bootstrap to initialize.',
                'total_insiders_tracked': 0,
                'qualified_performers': 0,
                'top_performers': []
            }

            # Save to docs/
            output_path = Path(__file__).parent.parent / 'docs' / 'insider_performance_public.json'
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                json.dump(empty_data, f, indent=2)

            print(f"✅ Created empty data file: {output_path}")
            return {'status': 'empty', 'count': 0}

        # Get top performers (score >= 60, min 5 trades)
        print(f"Total profiles loaded: {len(tracker.profiles):,}")

        # Filter for qualified performers
        qualified = {}
        for name, profile in tracker.profiles.items():
            score = profile.get('overall_score', 0)
            trades = profile.get('total_trades', 0)

            if score >= 60 and trades >= 5:
                qualified[name] = profile

        print(f"Qualified performers (score ≥60, trades ≥5): {len(qualified)}")

        if not qualified:
            print("⚠️  No qualified performers found")

            # Create file with explanation
            no_qualified_data = {
                'last_updated': datetime.now().isoformat(),
                'status': 'NO_QUALIFIED',
                'message': 'No insiders meet qualification criteria (score ≥60, trades ≥5)',
                'total_insiders_tracked': len(tracker.profiles),
                'qualified_performers': 0,
                'top_performers': []
            }

            output_path = Path(__file__).parent.parent / 'docs' / 'insider_performance_public.json'
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                json.dump(no_qualified_data, f, indent=2)

            print(f"✅ Exported (no qualified): {output_path}")
            return {'status': 'no_qualified', 'count': 0}

        # Sort by score (primary), then by avg_return_90d (tiebreaker)
        sorted_performers = sorted(
            qualified.items(),
            key=lambda x: (
                x[1].get('overall_score', 0),
                x[1].get('avg_return_90d', 0)
            ),
            reverse=True
        )

        # Take top 15 instead of top 5
        top_performers = sorted_performers[:15]

        print(f"\nTop 15 performers:")
        for name, profile in top_performers:
            score = profile.get('overall_score', 0)
            win_rate = profile.get('win_rate_90d', 0)
            avg_return = profile.get('avg_return_90d', 0)
            trades = profile.get('total_trades', 0)
            print(f"  • {name[:40]:<40} Score: {score:>5.1f} | WR: {win_rate:>5.1f}% | Avg: {avg_return:>+6.1f}% | Trades: {trades}")

        # Format for public display
        public_data = {
            'last_updated': datetime.now().isoformat(),
            'status': 'OK',
            'total_insiders_tracked': len(tracker.profiles),
            'qualified_performers': len(qualified),
            'top_performers': []
        }

        for name, profile in top_performers:
            performer = {
                'name': name,
                'score': round(profile.get('overall_score', 0), 1),
                'win_rate': round(profile.get('win_rate_90d', 0), 1),
                'avg_return': round(profile.get('avg_return_90d', 0), 1),
                'total_trades': profile.get('total_trades', 0),
                'best_trade': round(profile.get('best_return_90d', 0), 1) if profile.get('best_return_90d') else None,
                'worst_trade': round(profile.get('worst_return_90d', 0), 1) if profile.get('worst_return_90d') else None,
                'sharpe_ratio': round(profile.get('sharpe_90d', 0), 2) if profile.get('sharpe_90d') else None
            }
            public_data['top_performers'].append(performer)

        # Save to docs/ for GitHub Pages
        output_path = Path(__file__).parent.parent / 'docs' / 'insider_performance_public.json'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(public_data, f, indent=2, default=str)

        print(f"\n✅ Exported {len(top_performers)} top performers")
        print(f"   Output: {output_path}")
        print("="*70 + "\n")

        return {
            'status': 'success',
            'count': len(top_performers),
            'qualified': len(qualified),
            'total': len(tracker.profiles)
        }

    except Exception as e:
        print(f"❌ Error exporting insider performance data: {e}")
        import traceback
        traceback.print_exc()

        # Create error file
        error_data = {
            'last_updated': datetime.now().isoformat(),
            'status': 'ERROR',
            'message': f'Export failed: {str(e)}',
            'total_insiders_tracked': 0,
            'qualified_performers': 0,
            'top_performers': []
        }

        output_path = Path(__file__).parent.parent / 'docs' / 'insider_performance_public.json'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(error_data, f, indent=2)

        return {'status': 'error', 'message': str(e)}


if __name__ == "__main__":
    result = export_public_data()

    # Exit with error code if export failed
    if result.get('status') == 'error':
        sys.exit(1)

    sys.exit(0)
