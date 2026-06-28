"""
Performance metrics calculation module.
"""

import pandas as pd
import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _calc_ratios(returns, benchmark, risk_free_rate=0.02):
    """
    Core ratio-formula block shared by ``calculate_performance_metrics`` and
    the 1-year helpers.  Computes Sharpe, Sortino and (when *benchmark* is
    provided and distinct from *returns*) Information Ratio.

    Args:
        returns        (pd.Series): Daily returns for the period.
        benchmark      (pd.Series | None): Benchmark daily returns for the
                   *same* period, or ``None`` to skip Information Ratio.
        risk_free_rate (float): Annual risk-free rate (default 0.02).

    Returns:
        dict with keys "Sharpe Ratio", "Sortino Ratio",
        "Information Ratio" (or NaN when benchmark is omitted/identical).
    """
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1

    # Sharpe
    sharpe = (returns.mean() - daily_rf) / returns.std() * np.sqrt(252) \
        if returns.std() != 0 else np.nan

    # Sortino — annualises based on the actual number of days in the window
    downside = returns[returns < 0]
    n = max(len(returns), 1)
    ann_ret = (1 + returns).prod() - 1
    ann_ret = (1 + ann_ret) ** (252 / n) - 1
    sortino = (ann_ret - risk_free_rate) / (downside.std() * np.sqrt(252)) \
        if not downside.empty and downside.std() != 0 else np.nan

    # Information Ratio
    if benchmark is None or benchmark.equals(returns):
        ir = np.nan
    else:
        excess = returns.subtract(benchmark).dropna()
        ir = excess.mean() / excess.std() * np.sqrt(252) \
            if excess.std() != 0 else np.nan

    # Normalise sub-sorting noise so -0.00 never leaks into the report
    sharpe   = 0.0 if sharpe   is not None and abs(sharpe)   < 1e-9 else sharpe
    sortino  = 0.0 if sortino  is not None and abs(sortino)  < 1e-9 else sortino
    ir       = 0.0 if ir       is not None and abs(ir)       < 1e-9 else ir

    return {"Sharpe Ratio": sharpe, "Sortino Ratio": sortino, "Information Ratio": ir}


def _slice_1y(returns, series_to_anchor=None):
    """
    Return the subset of *returns* that covers the most recent 1-year
    calendar window (up to 252 trading days).

    The window is anchored at the most recent date of *series_to_anchor*
    (defaults to the last date of *returns*), then extends back exactly
    365 calendar days.  The result is capped at the most recent 252 data
    points to enforce the maximum lookback.

    Args:
        returns          (pd.Series): Daily returns to slice.
        series_to_anchor (pd.Series | None): Series whose last index entry
              anchors the window. Defaults to *returns*.

    Returns:
        pd.Series filtered to the 1-year window.
    """
    anchor = (returns if series_to_anchor is None else series_to_anchor).index.max()
    if anchor is None or pd.isnull(anchor):
        return returns.iloc[0:0]
    start = anchor - pd.DateOffset(years=1)
    window = returns.loc[start:]
    return window.tail(252)


def _ratio_metrics_1y(returns_full, benchmark_full, risk_free_rate=0.02):
    """Wrapper for backward compatibility."""
    return _ratio_metrics_horizon(returns_full, benchmark_full, 252, risk_free_rate)

def _ratio_metrics_horizon(returns_full, benchmark_full, days, risk_free_rate=0.02):
    """
    Compute Sharpe, Sortino, and (where applicable) Information Ratio for
    a specified window (in trading days).
    """
    anchor = benchmark_full.index.max()
    if anchor is None or pd.isnull(anchor):
        return {
            "Sharpe Ratio": np.nan,
            "Sortino Ratio": np.nan,
            "Information Ratio": np.nan,
        }
    
    start = anchor - pd.Timedelta(days=int(days * 1.5)) # Rough estimate, but slicing handles it
    bench_slice = benchmark_full.loc[start:].tail(days)
    port_slice = returns_full.loc[start:].tail(days)
    port_slice = port_slice.loc[port_slice.index.intersection(bench_slice.index)]

    if len(port_slice) < 2:
        return {
            "Sharpe Ratio": np.nan,
            "Sortino Ratio": np.nan,
            "Information Ratio": np.nan,
        }

    return _calc_ratios(
        port_slice,
        bench_slice if not bench_slice.equals(port_slice) else None,
        risk_free_rate=risk_free_rate,
    )


def calculate_performance_metrics(returns_series, benchmark_returns, risk_free_rate=0.02, annual_yield=0.0, benchmark_yield=0.0):

    """
    Calculates a suite of performance metrics for a given series of returns,
    including risk-adjusted returns and drawdown metrics.

    Args:
        returns_series (pd.Series): A pandas Series of daily returns for the portfolio or asset.
        benchmark_returns (pd.Series): A pandas Series of daily returns for the benchmark.
        risk_free_rate (float): The annual risk-free rate (default is 0.02, or 2%).
        annual_yield (float): The annual yield (dividends/coupons) - no longer included in performance.
        benchmark_yield (float): The annual yield of the benchmark - no longer included in performance.

    Returns:
        dict: A dictionary containing the calculated performance metrics:
              - "Annualized Return" (float)
              - "Cumulative Return" (float)
              - "Volatility" (float): Annualized standard deviation of returns.
              - "Sharpe Ratio" (float)
              - "Sortino Ratio" (float)
              - "Max Drawdown" (float)
              - "Beta" (float or NaN): Sensitivity to benchmark, NaN if insufficient common data.
              - "Market Exposure Effect (Cum.)" (float or NaN): The return derived solely from benchmark exposure (Beta).
              - "Alpha (Risk-Adj) Annualized" (float or NaN): Jensen's Alpha per year.
              - "Alpha (Risk-Adj) Cumulative" (float or NaN): Total excess return over the whole period due to alpha.
              - "Outperformance Annualized" (float or NaN): Simple difference in annual returns.
              - "Outperformance Cumulative" (float or NaN): Simple difference in returns.
              - "Information Ratio" (float or NaN): Excess return per unit of tracking error.
    """
    # Convert annual risk-free rate to a daily rate
    daily_rf = (1 + risk_free_rate) ** (1/252) - 1
    # Calculate cumulative return
    cum_ret = (1 + returns_series).prod() - 1
    n_days = len(returns_series)

    if n_days == 0:
        return {
            "Annualized Return": 0.0,
            "Cumulative Return": 0.0,
            "Volatility": 0.0,
            "Sharpe Ratio": 0.0,
            "Sortino Ratio": 0.0,
            "Max Drawdown": 0.0,
            "Beta": np.nan,
            "Market Exposure Effect (Cum.)": np.nan,
            "Alpha (Risk-Adj) Annualized": np.nan,
            "Alpha (Risk-Adj) Cumulative": np.nan,
            "Outperformance Annualized": np.nan,
            "Outperformance Cumulative": np.nan,
            "Information Ratio": np.nan
        }

    # Calculate annualized return
    ann_ret = (1 + cum_ret) ** (252/n_days) - 1
    # Calculate annualized volatility
    vol = returns_series.std() * np.sqrt(252)

    # ------------------------------------------------------------------
    # Risk-adjusted ratios — delegated to the shared helper so the
    # formula lives in exactly one place.
    # ------------------------------------------------------------------
    ratios = _calc_ratios(returns_series, benchmark_returns, risk_free_rate)
    sharpe  = ratios["Sharpe Ratio"]
    sortino = ratios["Sortino Ratio"]
    information_ratio = ratios["Information Ratio"]

    # Calculate cumulative product for drawdown
    cumulative = (1 + returns_series).cumprod()
    # Find the running maximum for drawdown calculation
    peak = cumulative.cummax()
    # Calculate drawdown
    drawdown = (cumulative - peak) / peak
    # Determine the maximum drawdown
    max_dd = drawdown.min()
    # Find common dates between portfolio and benchmark returns for relative metrics
    common = returns_series.index.intersection(benchmark_returns.index)

    # Initialize variables to handle cases where common data is insufficient
    beta = np.nan
    market_effect_cum = np.nan
    alpha_ann = np.nan
    alpha_cum = np.nan
    outperformance_ann = np.nan
    outperformance_cum = np.nan

    # Calculate Beta, Alpha, and Outperformance only if sufficient common data exists
    if len(common) > 30:  # A reasonable threshold for statistical significance
        y = returns_series.loc[common]
        x = benchmark_returns.loc[common]
        # Perform linear regression to get beta (slope)
        slope, intercept, r, p, stderr = stats.linregress(x, y)
        # Use slope if it is within a reasonable range [-5, 5], otherwise assume neutral market beta of 1.0
        if abs(slope) > 5.0:
            beta = 1.0
        else:
            beta = slope
        # Calculate annualized benchmark return for the COMMON period (geometric)
        benchmark_cum_common = (1 + x).prod() - 1
        benchmark_ann_common = (1 + benchmark_cum_common)**(252/len(x)) - 1

        # Calculate portfolio annualized return for the SAME common period (geometric)
        y_cum_common = (1 + y).prod() - 1
        y_ann_common = (1 + y_cum_common)**(252/len(y)) - 1

        # Calculate Annualized Jensen's Alpha
        alpha_ann = y_ann_common - (risk_free_rate + beta * (benchmark_ann_common - risk_free_rate))

        # Calculate Market Exposure Effect (Beta-driven part of return)
        # Market Effect = Beta * (Benchmark_Cum - RiskFree_Cum)
        risk_free_cum = (1 + risk_free_rate)**(len(y)/252) - 1
        market_effect_cum = beta * (benchmark_cum_common - risk_free_cum)

        # Calculate Cumulative Jensen's Alpha
        # Total_Cum = RiskFree_Cum + Market_Effect_Cum + Alpha_Cum
        alpha_cum = y_cum_common - (risk_free_cum + market_effect_cum)

        # Simple Outperformance
        outperformance_ann = y_ann_common - benchmark_ann_common
        outperformance_cum = y_cum_common - benchmark_cum_common
    else:
        beta = np.nan
        alpha_ann = np.nan
        alpha_cum = np.nan
        outperformance_ann = np.nan
        outperformance_cum = np.nan

    return {
        "Annualized Return": ann_ret,
        "Cumulative Return": cum_ret,
        "Volatility": vol,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
        "Max Drawdown": max_dd,
        "Beta": beta,
        "Market Exposure Effect (Cum.)": market_effect_cum,
        "Alpha (Risk-Adj) Annualized": alpha_ann,
        "Alpha (Risk-Adj) Cumulative": alpha_cum,
        "Outperformance Annualized": outperformance_ann,
        "Outperformance Cumulative": outperformance_cum,
        "Information Ratio": information_ratio
    }

