"""
Diagnostic script to explain Sortino spikes in the rolling chart.

Run from project root:
    source venv/bin/activate
    python3 Functions/port/engine/modules/efficiency/test_sortino_spike.py
"""

import sys
import numpy as np
import pandas as pd


def sortino_rolling(window_returns, risk_free_rate=0.02):
    """
    Exact Sortino formula used by both the chart and the table.
    """
    downside = window_returns[window_returns < 0]
    downside_std = downside.std()
    if pd.isna(downside_std) or downside_std == 0:
        return np.nan
    n = len(window_returns)
    ann_ret = (1 + window_returns).prod() - 1
    ann_ret = (1 + ann_ret) ** (252 / n) - 1
    return (ann_ret - risk_free_rate) / (downside_std * np.sqrt(252))


def diagnose_date(returns_series, target_date, calendar_days=365):
    """
    Print Sortino components for the window ending on target_date.
    """
    common_idx = returns_series.index
    common_idx = common_idx[common_idx <= target_date]
    if len(common_idx) == 0:
        print(f"No data up to {target_date.date()}")
        return

    end = common_idx[-1]
    start = end - pd.DateOffset(days=calendar_days)
    p_win = returns_series.loc[start:end]

    n = len(p_win)
    downside = p_win[p_win < 0]
    downside_std = downside.std()
    ann_ret = (1 + p_win).prod() - 1
    ann_ret_ann = (1 + ann_ret) ** (252 / n) - 1 if n > 0 else np.nan
    sortino = sortino_rolling(p_win)

    print(f"\n=== {end.date()} ===")
    print(f"Window: {start.date()} -> {end.date()}")
    print(f"Trading days: {n}")
    print(f"Downside days: {len(downside)}")
    print(f"Downside std: {downside_std:.6f}")
    print(f"Compound return: {ann_ret:.4%}")
    print(f"Annualized return: {ann_ret_ann:.4%}")
    print(f"Sortino numerator (ann_ret - 0.02): {ann_ret_ann - 0.02:.6f}")
    print(f"Sortino denominator (downside_std * sqrt(252)): {downside_std * np.sqrt(252):.6f}")
    print(f"Sortino: {sortino:.2f}")
    if len(downside) > 0:
        print(f"\nDownside returns (min 10 shown):")
        print(downside.head(10).to_string())
        print(f"\nDownside stats: min={downside.min():.6f}, max={downside.max():.6f}, mean={downside.mean():.6f}")
    else:
        print("\nNo downside days in this window!")


# ---------------------------------------------------------------------------
# Synthetic demonstration of the spike
# ---------------------------------------------------------------------------
def synthetic_spike_demo():
    """
    Show how near-zero downside std produces a sortino spike.
    """
    print("=" * 60)
    print("SYNTHETIC SPIKE DEMO")
    print("=" * 60)

    np.random.seed(42)
    dates = pd.bdate_range("2013-01-24", "2014-01-23")
    n = len(dates)

    # Case 1: Normal-ish returns
    rets1 = np.random.normal(0.0004, 0.012, n)
    s1 = pd.Series(rets1, index=dates)

    # Case 2: Same drift but almost no downside days
    rets2 = np.random.normal(0.0004, 0.012, n)
    neg_idx = np.random.choice(n, size=8, replace=False)
    rets2[neg_idx] = -0.0003  # tiny losses
    s2 = pd.Series(rets2, index=dates)
    print("\nCase 1: Normal downside distribution")
    diagnose_date(s1, pd.Timestamp("2014-01-23"))

    print("\nCase 2: Fewer, smaller downside days -> spike")
    diagnose_date(s2, pd.Timestamp("2014-01-23"))


if __name__ == "__main__":
    # Try to use real data if available
    try:
        from pathlib import Path
        sys_path_parent = str(Path(__file__).resolve().parent.parent.parent)
        import sys
        sys.path.insert(0, sys_path_parent)

        from engine.analyzer import PortfolioAnalyzer
        from data.provider_factory import get_market_data_provider
        from main import get_interactive_input

        print("Running with REAL portfolio data...")
        config = get_interactive_input(no_browser=True, etoro_username="jaynemesis", benchmark_ticker="SPY")
        analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())
        analyzer.run_analysis()

        returns_series = analyzer.returns.get("total")
        if returns_series is not None and len(returns_series) > 0:
            target = pd.Timestamp("2014-01-23")
            diagnose_date(returns_series, target)
        else:
            print("No returns series available, running synthetic demo.")
            synthetic_spike_demo()

    except Exception as e:
        import traceback
        print(f"Could not load real data ({type(e).__name__}: {e})")
        traceback.print_exc()
        print("Running synthetic demo instead.\n")
        synthetic_spike_demo()
