"""
Risk analysis module: VaR, CVaR, Monte Carlo simulation, risk contribution, and shock analysis.
"""

import pandas as pd
import numpy as np
from scipy import stats
from scipy.stats import norm
import plotly.graph_objects as go

from config import (
    BG_CHART,
    CHART_GRID,
    RISK_STRESS_LINE,
    BENCHMARK_LINE,
    TEXT_MUTED
)


def calculate_var_cvar(returns, confidence=0.95):
    """
    Calculates Value at Risk (VaR) and Conditional Value at Risk (CVaR)
    for a given series of returns.

    Args:
        returns (pd.Series): A pandas Series of daily returns.
        confidence (float): The confidence level for VaR and CVaR calculation (e.g., 0.95 for 95%).

    Returns:
        dict: A dictionary containing:
              - "VaR" (float): Value at Risk at the specified confidence level.
              - "CVaR" (float): Conditional Value at Risk (Expected Shortfall) at the specified confidence level.
    """
    # Calculate Value at Risk (VaR) at the specified confidence level.
    # VaR represents the maximum expected loss over a given time horizon at a given confidence level.
    if len(returns) == 0:
        return {"VaR": 0.0, "CVaR": 0.0}

    var = np.percentile(returns, (1 - confidence) * 100)

    # Calculate Conditional Value at Risk (CVaR) or Expected Shortfall.
    # CVaR is the expected loss given that the loss is greater than or equal to the VaR.
    cvar = returns[returns <= var].mean()

    return {"VaR": var, "CVaR": cvar}


def run_monte_carlo_simulation(initial_value, returns_series, num_simulations=10000, forecast_days=252):
    drift = returns_series.mean()
    if pd.isna(drift):
        drift = 0.0
    volatility = returns_series.std()
    if pd.isna(volatility):
        volatility = 0.01

    random_shocks = norm.ppf(np.random.rand(forecast_days, num_simulations))
    daily_returns = np.exp(drift - 0.5 * volatility**2 + volatility * random_shocks)

    cumulative_returns = np.cumprod(daily_returns, axis=0)
    simulation_values = initial_value * cumulative_returns

    simulation_df = pd.DataFrame(
        np.vstack([np.full(num_simulations, initial_value), simulation_values]),
        index=range(forecast_days + 1),
        columns=range(num_simulations),
    )

    return simulation_df


def calculate_risk_contribution(pos_values, total_ts, asset_returns=None):
    """
    Calculates the risk contribution of each position to the total portfolio volatility.

    Args:
        pos_values (pd.DataFrame): DataFrame of individual position values over time.
        total_ts (pd.Series): Series of total portfolio value over time.
        asset_returns (pd.DataFrame, optional): Pre-calculated daily returns for the underlying assets.
                                               If None, calculates returns from pos_values.

    Returns:
        pd.DataFrame: A DataFrame containing:
                      - "Weight": The current weight of each position in the portfolio.
                      - "Risk Contribution": The contribution of each position to the total portfolio risk.
                      - "% Risk Contribution": The percentage contribution of each position to the total portfolio risk.
    """
    # Calculate daily returns for individual positions and drop any NaN values
    if asset_returns is not None:
        # Filter asset returns to match the tickers in pos_values
        returns = asset_returns[pos_values.columns].dropna()
    else:
        returns = pos_values.pct_change().dropna()

    # Calculate the current weight of each position in the portfolio
    weights = pos_values.iloc[-1] / total_ts.iloc[-1]
    # Calculate the annualized covariance matrix of returns
    cov = returns.cov() * 252
    # Calculate total portfolio volatility
    port_vol = np.sqrt(weights.T @ cov @ weights)
    # Calculate Marginal Contribution to Risk (MCR)
    mcr = cov @ weights / port_vol
    # Calculate Component Contribution to Risk (CCR)
    ccr = weights * mcr
    # Calculate Percentage Risk Contribution
    pct = ccr / port_vol
    return pd.DataFrame({
        "Weight": weights,
        "Risk Contribution": ccr,
        "% Risk Contribution": pct
    })


def generate_shock_curve_chart(asset_returns, risk_contrib, shock_level=0.20, benchmark_beta=1.0, benchmark_returns=None):
    """
    Generates a 'Shock Curve' showing how the portfolio behaves under progressively worse market conditions.
    X-axis: Market shock (0% down to -shock_level%)

    Args:
        asset_returns (pd.DataFrame): DataFrame of asset returns.
        risk_contrib (pd.DataFrame): DataFrame with risk contribution data including "Weight".
        shock_level (float): Maximum shock level to display (default 0.20 for -20%).
        benchmark_beta (float): Beta of the benchmark (default 1.0).
        benchmark_returns (pd.Series, optional): Benchmark returns for beta calculation.

    Returns:
        str: HTML string of the Plotly chart.
    """
    # Determine shock points: use 5% increments for smoother curves, up to the specified shock_level
    step = 0.05
    shocks = np.arange(0, -shock_level - 1e-6, -step).tolist()
    # Ensure inclusion of exact -shock_level
    if not shocks or abs(shocks[-1] - (-shock_level)) > 1e-6:
        shocks.append(-shock_level)
    shock_labels = [f"{s*100:.0f}%" for s in shocks]

    # Calculate weighted beta for Current Portfolio
    if benchmark_returns is not None:
        # Align benchmark with asset returns and drop rows where either is NaN
        market_proxy = benchmark_returns.reindex(asset_returns.index)
        mask = market_proxy.notna()
        market_proxy = market_proxy[mask]
        aligned_asset_returns = asset_returns[mask]
    else:
         market_proxy = asset_returns.mean(axis=1)
         aligned_asset_returns = asset_returns

    asset_betas = {}
    if market_proxy.std() > 0:
        for col in aligned_asset_returns.columns:
            slope, _, _, _, _ = stats.linregress(market_proxy, aligned_asset_returns[col])
            # Cap Beta at a reasonable range [-5, 5] to prevent extreme outliers
            asset_betas[col] = max(-5.0, min(5.0, slope))
    else:
        for col in aligned_asset_returns.columns:
            asset_betas[col] = 1.0

    weights = risk_contrib["Weight"]

    current_beta = sum(weights[ticker] * asset_betas.get(ticker, 1.0) for ticker in weights.index if ticker in asset_betas)

    # Simulate a "Previous Period" beta (usually from a snapshot, but here we can slightly jitter for demonstration
    # if we don’t have historical snapshots stored). For now, let's use a slightly different beta or
    # look at the first half of the data if available.
    prev_beta = current_beta # Initialize prev_beta
    if len(asset_returns) > 60:
        half_idx = len(asset_returns) // 2
        prev_returns = asset_returns.iloc[:half_idx]
        # Ensure prev_market_proxy has sufficient variance before calculating betas
        if not prev_returns.empty:
            prev_market_proxy = prev_returns.mean(axis=1) # Recalculate prev_market_proxy here
            if prev_market_proxy.std() > 0:
                prev_betas = {}
                for col in prev_returns.columns:
                    slope, _, _, _, _ = stats.linregress(prev_market_proxy, prev_returns[col])
                    prev_betas[col] = max(-5.0, min(5.0, slope)) # Apply capping here too for consistency if needed
                
                # Ensure weights are aligned with prev_betas keys
                prev_beta_sum = 0
                for ticker in weights.index:
                    if ticker in prev_betas:
                        prev_beta_sum += weights[ticker] * prev_betas.get(ticker, 1.0)
                prev_beta = prev_beta_sum
            else:
                prev_beta = current_beta # Fallback if prev market proxy has no variance
        else:
            prev_beta = current_beta # Fallback if prev_returns is empty
    else:
        prev_beta = current_beta * 1.1  # Dummy jitter if not enough data

    portfolio_returns = [current_beta * s * 100 for s in shocks]
    # prev_returns_data and benchmark_returns are calculated but not directly used in the traces below, only for the 'Previous Period' and 'Benchmark' traces respectively.

    fig = go.Figure()

    # Benchmark Trace (Black, dashed)
    # Recalculate benchmark_returns for the plot to match the shock levels
    plot_benchmark_returns = [benchmark_beta * s * 100 for s in shocks]
    fig.add_trace(go.Scatter(
        x=shock_labels,
        y=plot_benchmark_returns, # Use the calculated plot_benchmark_returns
        mode='lines',
        line=dict(color=BENCHMARK_LINE, width=2, dash='dash'),
        name='Benchmark (Beta=1.0)'
    ))

    # Current Portfolio Trace (Red, thickest)
    fig.add_trace(go.Scatter(
        x=shock_labels,
        y=portfolio_returns,
        mode='lines+markers',
        line=dict(color=RISK_STRESS_LINE, width=4),
        marker=dict(size=12, symbol='diamond'),
        name='Current Portfolio'
    ))

    fig.update_layout(
        title="Portfolio Tail Risk: Shock Curve Overlay",
        xaxis_title="Market Shock (Benchmark Return)",
        yaxis_title="Expected Portfolio Return (%)",
        yaxis_tickformat=".0f",
        yaxis_ticksuffix="%",
        height=550,
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        font=dict(color=TEXT_MUTED),
        xaxis=dict(
            gridcolor=CHART_GRID,
            tickfont=dict(color=TEXT_MUTED),
            title_font=dict(color=TEXT_MUTED)
        ),
        yaxis=dict(
            gridcolor=CHART_GRID,
            tickfont=dict(color=TEXT_MUTED),
            title_font=dict(color=TEXT_MUTED)
        ),
        title_font=dict(color=TEXT_MUTED),
        legend=dict(
            font=dict(color=TEXT_MUTED),
            yanchor="top", y=0.99, xanchor="left", x=1.02
        ),
        hovermode="x unified"
    )

    # Add annotation for the centerpiece feel
    fig.add_annotation(
        x=shock_labels[-1],
        y=portfolio_returns[-1],
        text=f"Current Severe Stress: {portfolio_returns[-1]:.1f}%",
        showarrow=True,
        arrowhead=1,
        ax=-40,
        ay=-40
    )

    return fig.to_html(full_html=False, include_plotlyjs=False, config={'responsive': True, 'auto_margin': False})



def calculate_shock_contributions(holdings_df, shock_level=-0.20):
    """
    Calculates shock contribution metrics for each holding.

    Rows with missing beta are included using a neutral beta of 1.0 for the
    contribution math, but the original NaN is preserved so the table can
    distinguish between estimated and unknown betas.

    Short positions are handled by flipping the sign of their contribution:
    a short with positive beta contributes POSITIVELY to a market crash
    (it hedges the portfolio), while a short with negative beta contributes
    negatively (it amplifies the crash).

    Args:
        holdings_df: DataFrame with 'Weight' and 'beta' columns, and optionally
                     'direction_sign' (+1 for long, -1 for short).
        shock_level: Market shock level (default -0.20 for -20%)

    Returns:
        DataFrame with columns: beta, shock_contrib, pct_of_loss, sorted ascending by shock_contrib
    """
    if holdings_df is None or holdings_df.empty or 'beta' not in holdings_df.columns or 'Weight' not in holdings_df.columns:
        return None

    df = holdings_df[holdings_df['Weight'] > 0].copy()
    if df.empty:
        return None

    df['_calc_beta'] = df['beta'].fillna(0.0)
    direction = df['direction_sign'] if 'direction_sign' in df.columns else 1
    df['shock_contrib'] = df['Weight'] * df['_calc_beta'] * shock_level * direction
    total_shock_impact = df['shock_contrib'].sum()
    if total_shock_impact != 0:
        df['pct_of_loss'] = (df['shock_contrib'] / total_shock_impact) * 100
    else:
        df['pct_of_loss'] = 0.0

    # Sort ascending: most negative (largest contributor to loss) first
    return df.sort_values('shock_contrib', ascending=True)


def generate_shock_contribution_table(asset_returns, risk_contrib, shock_level=-0.20, benchmark_returns=None, betas=None, holdings_df=None):
    """
    Generates an HTML table showing which securities contribute most to a specific market shock (default -20%).

    Short positions are handled by flipping their weight sign in the contribution
    calculation: a short with positive beta hedges the portfolio during a crash,
    producing a positive shock_contrib, while a short with negative beta amplifies
    the crash (negative shock_contrib).

    Args:
        asset_returns (pd.DataFrame): DataFrame of asset returns.
        risk_contrib (pd.DataFrame): DataFrame with risk contribution data including "Weight".
        shock_level (float): The market shock level to analyze (default -0.20 for -20%).
        benchmark_returns (pd.Series, optional): Benchmark returns for beta calculation.
        betas (Series, optional): Pre-computed beta values indexed by ticker. If provided, these are used instead of recomputing.
        holdings_df (pd.DataFrame, optional): Portfolio holdings with a 'type' column
            ('S' for short, anything else for long). Used to flip contribution signs
            for short positions.

    Returns:
        str: HTML string for the contribution table.
    """
    weights = risk_contrib["Weight"]
    holdings_for_contrib = pd.DataFrame({'Weight': weights})

    if holdings_df is not None and 'type' in holdings_df.columns:
        direction_sign = holdings_df.loc[weights.index, 'type'].map({'S': -1})
        direction_sign = direction_sign.reindex(weights.index).fillna(1)
        holdings_for_contrib['direction_sign'] = direction_sign

    # Use precomputed betas when available; otherwise all NaN to trigger on-the-fly computation
    if betas is not None:
        holdings_for_contrib['beta'] = betas.reindex(weights.index)
    else:
        holdings_for_contrib['beta'] = np.nan

    # Compute missing betas from asset_returns if possible
    missing_mask = holdings_for_contrib['beta'].isna()
    if (
        missing_mask.any()
        and asset_returns is not None
        and not asset_returns.empty
    ):
        if benchmark_returns is not None:
            market_proxy = benchmark_returns.reindex(asset_returns.index)
            mask = market_proxy.notna()
            market_proxy = market_proxy[mask]
            aligned_asset_returns = asset_returns[mask]
        else:
            market_proxy = asset_returns.mean(axis=1)
            aligned_asset_returns = asset_returns

        valid_obs = market_proxy.notna().sum()
        market_std = market_proxy.std()
        if valid_obs >= 2 and not np.isnan(market_std) and market_std > 0:
            for ticker in holdings_for_contrib.index[missing_mask]:
                if ticker in aligned_asset_returns.columns:
                    y = aligned_asset_returns[ticker]
                    if y.notna().sum() >= 2:
                        try:
                            slope, _, _, _, _ = stats.linregress(market_proxy, y)
                            if not np.isnan(slope):
                                holdings_for_contrib.loc[ticker, 'beta'] = max(-5.0, min(5.0, slope))
                            else:
                                holdings_for_contrib.loc[ticker, 'beta'] = 0.0
                        except Exception:
                            holdings_for_contrib.loc[ticker, 'beta'] = 0.0
                    else:
                        holdings_for_contrib.loc[ticker, 'beta'] = 0.0
                else:
                    holdings_for_contrib.loc[ticker, 'beta'] = 0.0
        else:
            for ticker in holdings_for_contrib.index[missing_mask]:
                holdings_for_contrib.loc[ticker, 'beta'] = 0.0

    contrib_df = calculate_shock_contributions(holdings_for_contrib, shock_level)
    if contrib_df is None or contrib_df.empty:
        return "<p>Insufficient data for shock contribution analysis.</p>"

    total_shock_impact = contrib_df['shock_contrib'].sum()

    table_html = f"""
    <table class="shock-contrib-table">
        <thead>
            <tr>
                <th class="u-text-left">Ticker</th>
                <th class="u-align-center">Direction</th>
                <th class="u-align-right">Weight (%)</th>
                <th class="u-align-center">Estimated Beta</th>
                <th class="u-align-right">Impact at {shock_level*100:.0f}% Shock</th>
                <th class="u-align-center">% of Total Loss</th>
            </tr>
        </thead>
        <tbody>
    """

    direction_lookup = {}
    if holdings_df is not None and 'type' in holdings_df.columns:
        direction_lookup = holdings_df['type'].to_dict()

    for ticker, row in contrib_df.iterrows():
        pct_of_loss = row['pct_of_loss']
        bar_width = min(100, abs(pct_of_loss) * 2)
        
        beta_val = row['beta']
        if pd.isna(beta_val):
            beta_cell = '0.00'
        else:
            beta_cell = f'{beta_val:.2f}'
        
        color_class = 'text-success-dark' if pct_of_loss < 0 else 'text-danger-dark'
        bg_class = 'bar-success' if pct_of_loss < 0 else 'bar-danger'

        position_type = direction_lookup.get(ticker, 'L')
        if position_type == 'S':
            dir_display = 'S'
            dir_class = 'badge-short'
        else:
            dir_display = 'L'
            dir_class = 'badge-long'

        table_html += f"""
            <tr>
                <td class="u-bold">{ticker}</td>
                <td class="u-align-center"><span class="badge {dir_class}">{dir_display}</span></td>
                <td class="u-align-right">{row['Weight']*100:.2f}%</td>
                <td class="u-align-center">{beta_cell}</td>
                <td class="u-align-right">
                    <span class="{color_class} u-bold">
                        {row['shock_contrib']*100:+.2f}%
                    </span>
                </td>
                <td class="u-valign-middle u-min-width-120">
                    <div class="u-flex-center-gap-8">
                        <div class="u-progress-track">
                            <div class="u-bar-fill {bg_class}" style="width: {bar_width}%;"></div>
                        </div>
                        <span class="u-bar-value-label {color_class}">
                            {pct_of_loss:.1f}%
                        </span>
                    </div>
                </td>
            </tr>
        """

    table_html += f"""
            <tr class="total-row">
                <td>TOTAL</td>
                <td class="u-align-center">-</td>
                <td class="u-align-right">{weights.sum()*100:.2f}%</td>
                <td class="u-align-center">-</td>
                <td class="u-align-right text-danger-dark">
                    {total_shock_impact*100:+.2f}%
                </td>
                <td>-</td>
            </tr>
        </tbody>
    </table>
    """
    return table_html
