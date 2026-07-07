"""
Verify the Sortino spike is resolved.

Plots the full rolling Sortino series from the chart function
and marks 2014-01-23 so you can visually confirm the spike is gone.

Run:
    source venv/bin/activate
    python3 Functions/port/engine/modules/efficiency/verify_sortino_spike.py
"""

import sys
from pathlib import Path

# Match main.py path setup:
#   sys.path.insert(0, parent.parent.parent) -> project root  (for Functions.themes)
#   sys.path.insert(0, parent.parent)          -> Functions/port (for engine, config)
#   sys.path.insert(0, parent)                  -> Functions      (for data)
base = Path(__file__).resolve().parent.parent.parent  # Functions/port/engine
sys.path.insert(0, str(base.parent.parent.parent))  # project root
sys.path.insert(0, str(base.parent))       # Functions/port  (engine, config)
sys.path.insert(0, str(base.parent.parent)) # Functions       (data)

import numpy as np
import pandas as pd

# Reuse the same logic as the chart
SORTINO_COLOR = "#4e79a7"


def sortino_rolling(window_returns, risk_free_rate=0.02):
    """
    Exact Sortino formula used by the chart + table (with minimum n guard).
    """
    n = len(window_returns)
    if n < 60:
        return np.nan
    downside = window_returns[window_returns < 0]
    downside_std = downside.std()
    if pd.isna(downside_std) or downside_std == 0:
        return np.nan
    ann_ret = (1 + window_returns).prod() - 1
    ann_ret = (1 + ann_ret) ** (252 / n) - 1
    return (ann_ret - risk_free_rate) / (downside_std * np.sqrt(252))


def main():
    from engine.analyzer import PortfolioAnalyzer
    from data.provider_factory import get_market_data_provider
    from main import get_interactive_input

    config = get_interactive_input(no_browser=True, etoro_username="jaynemesis", benchmark_ticker="")
    analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())
    analyzer.run_analysis()

    returns_series = analyzer.returns.get("total")
    bmk = analyzer.benchmark_ticker
    benchmark_series = analyzer.prices.get(bmk)
    benchmark_returns = benchmark_series.pct_change().dropna() if benchmark_series is not None else None
    print(f"Benchmark ticker: {bmk}")
    print(f"Prices columns sample: {list(analyzer.prices.columns[:5])}")
    print(f"Returns series length: {len(returns_series) if returns_series is not None else 0}")

    common_idx = returns_series.index.intersection(benchmark_returns.index)
    calendar_days = 365

    # Compute rolling Sortino using calendar-day window (same as chart/table)
    port = returns_series.loc[common_idx]

    rolling_sortino = port.rolling(window=f"{calendar_days}D").apply(sortino_rolling, raw=False)
    rolling_sortino = rolling_sortino.dropna()

    # Also compute Sharpe and IR with guard
    daily_rf = (1 + 0.02) ** (1/252) - 1  # match chart code
    rolling_mean = port.rolling(window=f"{calendar_days}D").mean()
    rolling_std = port.rolling(window=f"{calendar_days}D").std()
    rolling_sharpe = ((rolling_mean - daily_rf) / rolling_std) * np.sqrt(252)
    rolling_sharpe = rolling_sharpe.where(port.rolling(window=f"{calendar_days}D").count() >= 60)

    rolling_ir = pd.Series(index=port.index, dtype=float)
    if benchmark_returns is not None and not benchmark_returns.empty:
        common_idx = port.index.intersection(benchmark_returns.index)
        if len(common_idx) > calendar_days:
            excess = (port.loc[common_idx] - benchmark_returns.loc[common_idx]).dropna()
            rolling_excess_mean = excess.rolling(window=f"{calendar_days}D").mean()
            rolling_excess_std = excess.rolling(window=f"{calendar_days}D").std()
            rolling_ir = (rolling_excess_mean / rolling_excess_std) * np.sqrt(252)
            rolling_ir = rolling_ir.where(excess.rolling(window=f"{calendar_days}D").count() >= 60)

    print(f"Series length: {len(rolling_sortino)}")
    print(f"Date range: {rolling_sortino.index[0].date()} -> {rolling_sortino.index[-1].date()}")
    print(f"Max Sortino: {rolling_sortino.max():.2f} on {rolling_sortino.idxmax().date()}")
    print(f"Min Sortino: {rolling_sortino.min():.2f} on {rolling_sortino.idxmin().date()}")
    if not rolling_sharpe.dropna().empty:
        print(f"Max Sharpe: {rolling_sharpe.max():.2f} on {rolling_sharpe.idxmax().date()}")
        print(f"Min Sharpe: {rolling_sharpe.min():.2f} on {rolling_sharpe.idxmin().date()}")
    if not rolling_ir.dropna().empty:
        print(f"Max IR: {rolling_ir.max():.2f} on {rolling_ir.idxmax().date()}")
        print(f"Min IR: {rolling_ir.min():.2f} on {rolling_ir.idxmin().date()}")

    target = pd.Timestamp("2014-01-23")
    if target in rolling_sortino.index:
        val = rolling_sortino.loc[target]
        print(f"\nSortino on 2014-01-23: {val:.2f}")
        # Print window details
        end = target
        start = end - pd.DateOffset(days=365)
        p_win = port.loc[start:end]
        n = len(p_win)
        downside = p_win[p_win < 0]
        downside_std = downside.std()
        ann_ret = (1 + p_win).prod() - 1
        ann_ret_ann = (1 + ann_ret) ** (252 / n) - 1
        print(f"  Window: {start.date()} -> {end.date()}, n={n}")
        print(f"  Downside days: {len(downside)}")
        print(f"  Downside std: {downside_std:.6f}")
        print(f"  Downside values (first 15):")
        print(downside.head(15).to_string())
        print(f"  Downside min={downside.min():.6f}, max={downside.max():.6f}, mean={downside.mean():.6f}")
    else:
        nearest_idx = rolling_sortino.index[rolling_sortino.index <= target]
        if len(nearest_idx) > 0:
            val = rolling_sortino.loc[nearest_idx[-1]]
            print(f"\nSortino nearest to 2014-01-23 ({nearest_idx[-1].date()}): {val:.2f}")

    # Also compute with the OLD 252-day window for comparison
    rolling_sortino_old = port.rolling(window=252).apply(sortino_rolling, raw=False).dropna()
    if target in rolling_sortino_old.index:
        val_old = rolling_sortino_old.loc[target]
        print(f"OLD chart (window=252) Sortino on 2014-01-23: {val_old:.2f}")
    else:
        nearest_old = rolling_sortino_old.index[rolling_sortino_old.index <= target]
        if len(nearest_old) > 0:
            val_old = rolling_sortino_old.loc[nearest_old[-1]]
            print(f"OLD chart (window=252) Sortino near 2014-01-23 ({nearest_old[-1].date()}): {val_old:.2f}")

    # Print top 5 highest Sortino values from old vs new
    print("\nTop 5 spikes:")
    print("  Sortino (new):")
    for date, val in rolling_sortino.nlargest(5).items():
        print(f"    {date.date()}: {val:.2f}")
    print("  Sharpe (new):")
    for date, val in rolling_sharpe.nlargest(5).items():
        n_val = port.rolling(window=f"{calendar_days}D").count().loc[date]
        std_val = rolling_std.loc[date]
        mean_val = rolling_mean.loc[date]
        print(f"    {date.date()}: {val:.2f}  (n={n_val:.0f}, mean={mean_val:.6f}, std={std_val:.6f})")
    print("  IR (new):")
    for date, val in rolling_ir.nlargest(5).items():
        print(f"    {date.date()}: {val:.2f}")
    print("  OLD chart Sortino spikes (window=252):")
    for date, val in rolling_sortino_old.nlargest(5).items():
        print(f"    {date.date()}: {val:.2f}")


if __name__ == "__main__":
    main()
