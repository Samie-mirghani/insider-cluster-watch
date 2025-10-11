# jobs/visualize.py
import pandas as pd
import matplotlib.pyplot as plt
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
BACKTEST_CSV = os.path.join(DATA_DIR, 'backtest_results.csv')
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'plots')
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)

def plot_rolling_hitrate(window=20):
    if not os.path.exists(BACKTEST_CSV):
        print("Backtest CSV not found; run backtest.py first.")
        return
    df = pd.read_csv(BACKTEST_CSV, parse_dates=['signal_date'])
    df = df.sort_values('signal_date')
    # pick a horizon to visualize (1m)
    df1m = df[df['horizon']=='1m'].copy()
    if df1m.empty:
        print("No 1m horizon results.")
        return
    df1m['hit'] = df1m['ticker_return'] > 0
    # compute rolling hit-rate
    df1m['rolling_hit'] = df1m['hit'].rolling(window=min(window, max(2, len(df1m)))).mean()
    plt.figure(figsize=(10,4))
    plt.plot(df1m['signal_date'], df1m['rolling_hit'], marker='o', linestyle='-')
    plt.title(f"Rolling {window}-signal Hit Rate (1m horizon)")
    plt.ylabel("Hit rate (proportion)")
    plt.xlabel("Signal date")
    plt.grid(True)
    out = os.path.join(OUT_DIR, f"rolling_hit_rate_{window}.png")
    plt.tight_layout()
    plt.savefig(out)
    plt.close()
    print(f"Saved rolling hit-rate to {out}")

def plot_cumulative_alpha():
    if not os.path.exists(BACKTEST_CSV):
        print("Backtest CSV not found; run backtest.py first.")
        return
    df = pd.read_csv(BACKTEST_CSV, parse_dates=['signal_date'])
    df = df.sort_values('signal_date')
    df1m = df[df['horizon']=='1m'].copy()
    if df1m.empty:
        print("No 1m horizon results.")
        return
    # cumulative alpha over time (simple cumulative sum of alpha)
    df1m['cum_alpha'] = df1m['alpha'].cumsum()
    plt.figure(figsize=(10,4))
    plt.plot(df1m['signal_date'], df1m['cum_alpha'], marker='o', linestyle='-')
    plt.title("Cumulative Alpha vs SPY (1m horizon)")
    plt.ylabel("Cumulative alpha (fractional)")
    plt.xlabel("Signal date")
    plt.grid(True)
    out = os.path.join(OUT_DIR, "cumulative_alpha_1m.png")
    plt.tight_layout()
    plt.savefig(out)
    plt.close()
    print(f"Saved cumulative alpha to {out}")

if __name__ == "__main__":
    plot_rolling_hitrate(window=20)
    plot_cumulative_alpha()
