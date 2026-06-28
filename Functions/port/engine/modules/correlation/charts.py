"""
Chart generation module: All Plotly visualizations for portfolio functions.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.cluster import hierarchy
from config import (
    POSITIVE_RETURN_CARD, BREAKDOWN_NEUTRAL_ORANGE, NEUTRAL_GRAY, TERM_CARD_BAR, MC_GRID, TEXT_MUTED,
    CLUSTER_EDGE_COLOR, CLUSTER_NODE_BORDER, CLUSTER_PALETTE, PRIMARY_TEXT,
    CHART_GRID, BG_CHART, METRIC_CARD_LABEL_TEXT, FONT_PRIMARY,
    CORR_DIST_BAR_FILL, CORR_DIST_BAR_EDGE, CORR_DIST_MARKER_LINE, CORR_DIST_BG, CHART_TRANSPARENT,
    CORR_COLOR_NA, CORR_COLOR_STRONG_POSITIVE, CORR_COLOR_MODERATE, CORR_COLOR_WEAK_POSITIVE, CORR_COLOR_NEGATIVE,
    CORR_PERCENTILE_EXTREME, CORR_PERCENTILE_SOMEWHAT_EXTREME, CORR_PERCENTILE_NORMAL,
    CORR_VOL_HIGH, CORR_VOL_MODERATE, CORR_VOL_LOW,
    _NEUTRAL_1000, _BRAND_PRIMARY, _SEMANTIC_WARNING,
)



def generate_rolling_correlation_chart(ts_data):
    """
    Generates rolling correlation chart showing 30D, 90D, and 1Y rolling correlations
    between portfolio and benchmark.

    Args:
        ts_data (dict): Time series data containing 'total' and 'benchmark' Series

    Returns:
        str: HTML string with Plotly chart
    """
    if ts_data["benchmark"].empty or len(ts_data["total"]) < 30:
        return "<p class=\"corr-insufficient\">Insufficient data for rolling correlation analysis.</p>"

    # Calculate daily returns
    portfolio_returns = ts_data["total"].pct_change().dropna()
    benchmark_returns = ts_data["benchmark"].pct_change().dropna()

    # Align the series
    common_index = portfolio_returns.index.intersection(benchmark_returns.index)
    if len(common_index) < 30:
        return "<p class=\"corr-insufficient-pad-40\">Insufficient overlapping data for rolling correlation analysis.</p>"

    port_ret_aligned = portfolio_returns.loc[common_index]
    bench_ret_aligned = benchmark_returns.loc[common_index]

    # Calculate rolling correlations
    corr_30d = port_ret_aligned.rolling(window=30).corr(bench_ret_aligned).dropna()
    corr_90d = port_ret_aligned.rolling(window=90).corr(bench_ret_aligned).dropna()
    corr_1y = port_ret_aligned.rolling(window=252).corr(bench_ret_aligned).dropna()

    # Create the figure
    fig = go.Figure()

    # Add traces with thicker lines in Bloomberg-style colors: black, blue, purple
    fig.add_trace(go.Scatter(
        x=corr_30d.index, y=corr_30d,
        name="30D",
        line=dict(width=3, color=_NEUTRAL_1000)
    ))

    fig.add_trace(go.Scatter(
        x=corr_90d.index, y=corr_90d,
        name="90D",
        line=dict(width=3, color=_BRAND_PRIMARY)
    ))

    fig.add_trace(go.Scatter(
        x=corr_1y.index, y=corr_1y,
        name="1Y",
        line=dict(width=3, color=_SEMANTIC_WARNING)
    ))

    # Calculate dynamic y-axis range for better readability
    all_corr_values = pd.concat([corr_30d, corr_90d, corr_1y])
    corr_min = all_corr_values.min()
    corr_max = all_corr_values.max()
    # Add small padding
    y_range = [corr_min - 0.05, corr_max + 0.05]
    # Ensure it doesn't exceed [-1, 1]
    y_range = [max(-1, y_range[0]), min(1, y_range[1])]

    fig.update_layout(
        title="Rolling Correlation to Benchmark",
        font=dict(color=TEXT_MUTED),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_rangeslider_visible=True,
        xaxis=dict(
            showgrid=True,
            gridcolor=CHART_GRID
        ),
        yaxis=dict(
            title="Correlation",
            range=y_range,
            tickformat=".2f",
            showgrid=True,
            gridcolor=CHART_GRID
        ),
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        showlegend=True,
        height=400
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)



def generate_correlation_metrics_strip(ts_data):
    """
    Generates header strip with key correlation metrics, including mini sparkline charts.

    Args:
        ts_data (dict): Time series data containing 'total' and 'benchmark' Series

    Returns:
        str: HTML string with metrics display including embedded charts
    """
    if ts_data["benchmark"].empty or len(ts_data["total"]) < 30:
        return "<div class=\"corr-insufficient-pad-20\">Insufficient data for correlation metrics.</div>"

    # Calculate daily returns
    portfolio_returns = ts_data["total"].pct_change().dropna()
    benchmark_returns = ts_data["benchmark"].pct_change().dropna()

    # Align the series
    common_index = portfolio_returns.index.intersection(benchmark_returns.index)
    if len(common_index) < 30:
        return "<div class=\"corr-insufficient-pad-20\">Insufficient overlapping data for correlation metrics.</div>"

    port_ret_aligned = portfolio_returns.loc[common_index]
    bench_ret_aligned = benchmark_returns.loc[common_index]

    # Calculate rolling correlations
    corr_22d = port_ret_aligned.rolling(window=22).corr(bench_ret_aligned).dropna()
    corr_90d = port_ret_aligned.rolling(window=90).corr(bench_ret_aligned).dropna()
    corr_1y = port_ret_aligned.rolling(window=252).corr(bench_ret_aligned).dropna()

    # Calculate metrics
    current_corr = port_ret_aligned.corr(bench_ret_aligned)
    corr_1m = corr_22d.iloc[-1] if not corr_22d.empty else np.nan
    corr_1y_final = corr_1y.iloc[-1] if not corr_1y.empty else np.nan

    # Correlation percentile vs history (using 1Y rolling)
    percentile = (corr_1y <= current_corr).mean() * 100 if not corr_1y.empty else np.nan

    # Correlation volatility (stability proxy)
    corr_vol = corr_1y.std() if not corr_1y.empty else np.nan

    # Format values for display
    def fmt(val):
        if np.isnan(val):
            return "N/A"
        if isinstance(val, float):
            return f"{val:.2f}"
        return str(val)

    # Individual formatted display strings
    current_corr_display = f"{current_corr:.2f}" if not np.isnan(current_corr) else "N/A"
    corr_1m_display = f"{corr_1m:.2f}" if not np.isnan(corr_1m) else "N/A"
    corr_1y_display = f"{corr_1y_final:.2f}" if not np.isnan(corr_1y_final) else "N/A"
    percentile_display = f"{percentile:.0f}%ile" if not np.isnan(percentile) else "N/A"
    corr_vol_display = f"{corr_vol:.2f}" if not np.isnan(corr_vol) else "N/A"

    # Color helpers
    def get_corr_color(value):
        if np.isnan(value):
            return CORR_COLOR_NA
        if value > 0.7:
            return CORR_COLOR_STRONG_POSITIVE
        elif value > 0.3:
            return CORR_COLOR_MODERATE
        elif value >= 0:
            return CORR_COLOR_WEAK_POSITIVE
        else:
            return CORR_COLOR_NEGATIVE

    def get_percentile_color(value):
        if np.isnan(value):
            return CORR_COLOR_NA
        if value < 20 or value > 80:
            return CORR_PERCENTILE_EXTREME
        elif value < 40 or value > 60:
            return CORR_PERCENTILE_SOMEWHAT_EXTREME
        else:
            return CORR_PERCENTILE_NORMAL

    def get_vol_color(value):
        if np.isnan(value):
            return CORR_COLOR_NA
        if value > 0.1:
            return CORR_VOL_HIGH
        elif value > 0.05:
            return CORR_VOL_MODERATE
        else:
            return CORR_VOL_LOW

    # Helper to generate a mini sparkline chart
    def generate_sparkline(series, color):
        if series is None or len(series) < 2:
            return ""
        try:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=series.index,
                y=series.values,
                mode='lines',
                line=dict(width=2, color=color),
                showlegend=False,
                hoverinfo='skip'
            ))
            # Add endpoint marker
            if len(series) > 0:
                fig.add_trace(go.Scatter(
                    x=[series.index[-1]],
                    y=[series.values[-1]],
                    mode='markers',
                    marker=dict(size=4, color=color),
                    showlegend=False,
                    hoverinfo='skip'
                ))
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=80,
                width=150,
                paper_bgcolor=CHART_TRANSPARENT,
                plot_bgcolor=CHART_TRANSPARENT,
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False, fixedrange=True),
                yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False, fixedrange=True),
                dragmode=False
            )
            return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})
        except Exception:
            return ""

    # Generate sparklines for each metric
    spark_current = generate_sparkline(corr_1y, get_corr_color(current_corr)) if not corr_1y.empty else ""
    spark_1m = generate_sparkline(corr_22d, get_corr_color(corr_1m)) if not corr_22d.empty else ""
    spark_1y = generate_sparkline(corr_1y, get_corr_color(corr_1y_final)) if not corr_1y.empty else ""

    # Percentile sparkline (showing how percentile has evolved over last N periods)
    if len(corr_1y) > 30:
        # Calculate running percentile over a rolling window
        percentiles_hist = pd.Series(index=corr_1y.index, dtype=float)
        for i in range(30, len(corr_1y)):
            window = corr_1y.iloc[:i]
            percentiles_hist.iloc[i] = (window <= corr_1y.iloc[i]).mean() * 100
        percentiles_hist = percentiles_hist.dropna()
        spark_percentile = generate_sparkline(percentiles_hist, get_percentile_color(percentile)) if not percentiles_hist.empty else ""
    else:
        spark_percentile = ""

    # Volatility sparkline (rolling std of correlation)
    if len(corr_1y) > 30:
        corr_vol_hist = corr_1y.rolling(window=30).std()
        spark_vol = generate_sparkline(corr_vol_hist, get_vol_color(corr_vol)) if not corr_vol_hist.empty else ""
    else:
        spark_vol = ""

    current_color = get_corr_color(current_corr)
    corr_1m_color = get_corr_color(corr_1m)
    corr_1y_color = get_corr_color(corr_1y_final)
    percentile_color = get_percentile_color(percentile)
    vol_color = get_vol_color(corr_vol)

    html = f"""
    <div class="corr-metrics-row" style="font-family: {FONT_PRIMARY};">
        <!-- Current Correlation Card -->
        <div class="corr-card" style="--card-bg: {current_color}20; --card-border: {current_color}; --card-color: {current_color};">
            <div class="corr-card-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Current Correlation</div>
            <div class="corr-card-value">{fmt(current_corr)}</div>
            {'<div class="corr-sparkline-wrap">' + spark_current + '</div>' if spark_current else '<div class="corr-sparkline-wrap"></div>'}
        </div>

        <!-- 1M Rolling Card -->
        <div class="corr-card" style="--card-bg: {corr_1m_color}20; --card-border: {corr_1m_color}; --card-color: {corr_1m_color};">
            <div class="corr-card-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">1M Rolling</div>
            <div class="corr-card-value">{fmt(corr_1m)}</div>
            {'<div class="corr-sparkline-wrap">' + spark_1m + '</div>' if spark_1m else '<div class="corr-sparkline-wrap"></div>'}
        </div>

        <!-- 1Y Rolling Card -->
        <div class="corr-card" style="--card-bg: {corr_1y_color}20; --card-border: {corr_1y_color}; --card-color: {corr_1y_color};">
            <div class="corr-card-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">1Y Rolling</div>
            <div class="corr-card-value">{fmt(corr_1y_final)}</div>
            {'<div class="corr-sparkline-wrap">' + spark_1y + '</div>' if spark_1y else '<div class="corr-sparkline-wrap"></div>'}
        </div>

        <!-- Percentile Card -->
        <div class="corr-card" style="--card-bg: {percentile_color}20; --card-border: {percentile_color}; --card-color: {percentile_color};">
            <div class="corr-card-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Percentile vs History</div>
            <div class="corr-card-value">{percentile_display}</div>
            <div class="corr-percentile-bar-wrap">
                <div class="corr-percentile-bar-track">
                    <div class="corr-percentile-marker" style="--percentile-pos: {percentile}%;"></div>
                    <div class="corr-percentile-arrow" style="--percentile-pos: {percentile}%;"></div>
                </div>
                <div class="corr-percentile-ticks">
                    <span>0%</span>
                    <span>20%</span>
                    <span>40%</span>
                    <span>50%</span>
                    <span>60%</span>
                    <span>80%</span>
                    <span>100%</span>
                </div>
            </div>
        </div>

        <!-- Correlation Volatility Card -->
        <div class="corr-card" style="--card-bg: {vol_color}20; --card-border: {vol_color}; --card-color: {vol_color};">
            <div class="corr-card-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Correlation Volatility</div>
            <div class="corr-card-value">{corr_vol_display}</div>
            {'<div class="corr-sparkline-wrap">' + spark_vol + '</div>' if spark_vol else '<div class="corr-sparkline-wrap"></div>'}
        </div>
    </div>
    """
    return html


def generate_timeframe_correlation_panel(ts_data):
    """
    Generates Bloomberg-style timeframe correlation visualization with term curve and compact metric cards.

    Args:
        ts_data (dict): Time series data containing 'total' and 'benchmark' Series

    Returns:
        str: HTML string with Plotly chart and HTML cards
    """
    if ts_data["benchmark"].empty or len(ts_data["total"]) < 30:
        return "<div class=\"corr-insufficient-pad-20\">Insufficient data for timeframe analysis.</div>"

    # Calculate daily returns
    portfolio_returns = ts_data["total"].pct_change().dropna()
    benchmark_returns = ts_data["benchmark"].pct_change().dropna()

    # Align the series
    common_index = portfolio_returns.index.intersection(benchmark_returns.index)
    if len(common_index) < 30:
        return "<div class=\"corr-insufficient-pad-20\">Insufficient overlapping data for timeframe analysis.</div>"

    port_ret_aligned = portfolio_returns.loc[common_index]
    bench_ret_aligned = benchmark_returns.loc[common_index]

    # Calculate rolling correlations for 1Y
    rolling_1y = port_ret_aligned.rolling(window=252).corr(bench_ret_aligned).dropna()
    historical_min = rolling_1y.min()
    historical_max = rolling_1y.max()

    # Calculate correlations for different timeframes
    daily_corr = port_ret_aligned.corr(bench_ret_aligned)

    # Weekly (5 trading days)
    weekly_port = (1 + port_ret_aligned).resample('W').prod() - 1
    weekly_bench = (1 + bench_ret_aligned).resample('W').prod() - 1
    weekly_corr = weekly_port.corr(weekly_bench)

    # Monthly
    monthly_port = (1 + port_ret_aligned).resample('ME').prod() - 1
    monthly_bench = (1 + bench_ret_aligned).resample('ME').prod() - 1
    monthly_corr = monthly_port.corr(monthly_bench)

    # Yearly
    yearly_corr = rolling_1y.iloc[-1] if not rolling_1y.empty else np.nan

    timeframes = ['1D', '1W', '1M', '1Y']
    correlations = [daily_corr, weekly_corr, monthly_corr, yearly_corr]

    # Regime classification matching correlation metrics strip
    def get_regime(corr):
        if corr > 0.7:
            return 'Strong', POSITIVE_RETURN_CARD
        elif corr > 0.3:
            return 'Moderate', BREAKDOWN_NEUTRAL_ORANGE
        else:
            return 'Weak', NEUTRAL_GRAY

    regimes = [get_regime(c)[0] for c in correlations]
    regime_colors = [get_regime(c)[1] for c in correlations]

    # Create figure for term curve
    fig = go.Figure()

    # Term curve with historical bands
    fig.add_trace(go.Scatter(
        x=timeframes,
        y=correlations,
        mode='lines+markers',
        name='Current',
        line=dict(color=TERM_CARD_BAR, width=3),
        marker=dict(size=10, color=TERM_CARD_BAR),
        hovertemplate='%{x}: %{y:.3f}<extra></extra>'
    ))

    # Historical range error bars
    fig.add_trace(go.Scatter(
        x=timeframes,
        y=correlations,
        mode='markers',
        error_y=dict(
            type='data',
            symmetric=False,
            array=[historical_max - c for c in correlations],
            arrayminus=[c - historical_min for c in correlations],
            thickness=2,
            width=4,
            color=MC_GRID
        ),
        showlegend=False,
        hoverinfo='skip'
    ))

    # Regime indicators
    for i, (tf, corr, regime) in enumerate(zip(timeframes, correlations, regimes)):
        fig.add_trace(go.Scatter(
            x=[tf],
            y=[corr + 0.02],
            mode='text',
            text=regime[0],  # H, M, L
            textfont=dict(color=TEXT_MUTED, size=12, family='Arial Black'),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Annotate inflection if yearly correlation is low
    if yearly_corr < 0.5:
        fig.add_annotation(
            x='1Y',
            y=yearly_corr - 0.05,
            text=f'Fall to {yearly_corr:.2f}',
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=30,
            font=dict(size=10, color='darkred')
        )

    # Layout
    fig.update_layout(
        title='Correlation Term Structure',
        title_font=dict(size=16, family='Arial', color=TEXT_MUTED),
        xaxis=dict(title='Timeframe', showgrid=False, title_font=dict(color=TEXT_MUTED)),
        yaxis=dict(title='Correlation', autorange=True, showgrid=True, gridcolor=CHART_GRID, gridwidth=0.5, title_font=dict(color=TEXT_MUTED)),
        height=300,
        showlegend=False,
        font=dict(size=10, family='Arial', color=TEXT_MUTED),
        margin=dict(l=40, r=40, t=60, b=40),
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
    )

    # Generate Plotly HTML
    plotly_html = fig.to_html(full_html=False, include_plotlyjs=False)

    # Create Bloomberg-style metric cards
    cards_html = '<div class="term-cards-row">'
    for tf, corr, regime, color in zip(timeframes, correlations, regimes, regime_colors):
        intensity = (corr - historical_min) / (historical_max - historical_min) if historical_max > historical_min else 0.5
        cards_html += f'''
        <div class="term-card" style="--card-border-color: {color};">
            <div class="term-card-title">{tf}</div>
            <div class="term-card-value">{corr:.2f}</div>
            <div class="term-card-regime">{regime.upper()}</div>
            <div class="term-card-bar" style="--intensity: {intensity * 100}%;"></div>
        </div>
        '''
    cards_html += '</div>'

    return plotly_html + cards_html


def generate_correlation_distribution_chart(ts_data):
    """
    Generates histogram of rolling correlation values with current value marker.

    Args:
        ts_data (dict): Time series data containing 'total' and 'benchmark' Series

    Returns:
        str: HTML string with Plotly histogram
    """
    if ts_data["benchmark"].empty or len(ts_data["total"]) < 252:
        return "<p class=\"corr-insufficient-pad-40\">Insufficient data for correlation distribution analysis.</p>"

    # Calculate daily returns
    portfolio_returns = ts_data["total"].pct_change().dropna()
    benchmark_returns = ts_data["benchmark"].pct_change().dropna()

    # Align the series
    common_index = portfolio_returns.index.intersection(benchmark_returns.index)
    if len(common_index) < 252:
        return "<p class=\"corr-insufficient-pad-40\">Insufficient overlapping data for correlation distribution analysis.</p>"

    port_ret_aligned = portfolio_returns.loc[common_index]
    bench_ret_aligned = benchmark_returns.loc[common_index]

    # Calculate 1Y rolling correlations
    rolling_corr = port_ret_aligned.rolling(window=252).corr(bench_ret_aligned).dropna()
    current_corr = port_ret_aligned.corr(bench_ret_aligned)

    # Create histogram
    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=rolling_corr,
        nbinsx=40,
        marker=dict(
            color=CORR_DIST_BAR_FILL,
            line=dict(width=0, color=CORR_DIST_BAR_EDGE)
        ),
        showlegend=False
    ))

    # Add current value marker (only if current_corr is valid)
    if not np.isnan(current_corr):
        fig.add_vline(x=current_corr, line_width=2, line_color=CORR_DIST_MARKER_LINE, annotation_text=f"Current: {current_corr:.2f}")

    fig.update_layout(
        title="Distribution of 1Y Rolling Correlations",
        font=dict(color=TEXT_MUTED),
        xaxis_title="Correlation",
        yaxis_title="Frequency",
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False,
        plot_bgcolor=CORR_DIST_BG,
        paper_bgcolor=CORR_DIST_BG,
        xaxis=dict(
            showgrid=True,
            gridcolor=CHART_GRID,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=CHART_GRID,
        ),
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)


def generate_stability_score(ts_data):
    """
    Generates stability score based on correlation volatility.

    Args:
        ts_data (dict): Time series data containing 'total' and 'benchmark' Series

    Returns:
        str: Stability score text ("Low", "Medium", "High")
    """
    if ts_data["benchmark"].empty or len(ts_data["total"]) < 252:
        return "N/A"

    # Calculate daily returns
    portfolio_returns = ts_data["total"].pct_change().dropna()
    benchmark_returns = ts_data["benchmark"].pct_change().dropna()

    # Align the series
    common_index = portfolio_returns.index.intersection(benchmark_returns.index)
    if len(common_index) < 252:
        return "N/A"

    port_ret_aligned = portfolio_returns.loc[common_index]
    bench_ret_aligned = benchmark_returns.loc[common_index]

    # Calculate 1Y rolling correlations and their volatility
    rolling_corr = port_ret_aligned.rolling(window=252).corr(bench_ret_aligned).dropna()
    corr_vol = rolling_corr.std()

    # Determine stability level
    if corr_vol < 0.1:
        return "High"
    elif corr_vol < 0.2:
        return "Medium"
    else:
        return "Low"


def generate_regime_indicator(ts_data):
    """
    Generates current correlation regime based on percentile bands.

    Args:
        ts_data (dict): Time series data containing 'total' and 'benchmark' Series

    Returns:
        str: Regime text ("Low", "Normal", "High")
    """
    if ts_data["benchmark"].empty or len(ts_data["total"]) < 252:
        return "N/A"

    # Calculate daily returns
    portfolio_returns = ts_data["total"].pct_change().dropna()
    benchmark_returns = ts_data["benchmark"].pct_change().dropna()

    # Align the series
    common_index = portfolio_returns.index.intersection(benchmark_returns.index)
    if len(common_index) < 252:
        return "N/A"

    port_ret_aligned = portfolio_returns.loc[common_index]
    bench_ret_aligned = benchmark_returns.loc[common_index]

    # Calculate current correlation and historical percentiles
    current_corr = port_ret_aligned.corr(bench_ret_aligned)
    rolling_corr = port_ret_aligned.rolling(window=252).corr(bench_ret_aligned).dropna()

    percentile = (rolling_corr <= current_corr).mean()

    # Determine regime
    if percentile < 0.2:
        return "Low"
    elif percentile > 0.8:
        return "High"
    else:
        return "Normal"


def generate_correlation_cluster_network(corr_matrix, n_clusters=None):
    """
    Generates a network visualization of asset correlations with hierarchical clustering.
    Assets are grouped into clusters based on their correlation patterns.

    Args:
        corr_matrix (pd.DataFrame): Correlation matrix of asset returns.
        n_clusters (int, optional): Number of clusters to detect. If None, auto-detects
                                    using simple heuristic (min(4, n_assets//2)).

    Returns:
        str: HTML string with the network graph (Plotly).
    """
    if corr_matrix.empty or len(corr_matrix) < 3:
        return "<p class=\"corr-insufficient-pad-40\">At least 3 assets required for cluster analysis.</p>"

    tickers = corr_matrix.index.tolist()
    n_assets = len(tickers)

    # Compute distance matrix from correlation: distance = 1 - correlation
    # Set diagonal to 0 (self-distance) after transformation
    distance_matrix = 1 - corr_matrix.values
    np.fill_diagonal(distance_matrix, 0)

    try:
        from scipy.spatial.distance import squareform
        condensed_dist = squareform(distance_matrix, checks=False)

        # Hierarchical clustering using Ward's method
        linkage_matrix = hierarchy.linkage(condensed_dist, method='ward')

        # Determine number of clusters
        if n_clusters is None:
            n_clusters = max(2, min(4, n_assets // 2))

        # Get cluster labels
        cluster_labels = hierarchy.fcluster(linkage_matrix, n_clusters, criterion='maxclust')

        # Build lines for strong correlations
        edge_x = []
        edge_y = []

        # PCA-based 2D projection for asset similarity visualization
        # Center the correlation matrix
        corr_vals = corr_matrix.values
        corr_centered = corr_vals - np.mean(corr_vals, axis=0)

        # SVD for 2D projection
        U, S, Vt = np.linalg.svd(corr_centered)
        # Get first two components
        projection = U[:, :2] * np.sqrt(S[:2])

        pos = {tickers[i]: projection[i] for i in range(n_assets)}

        # Add edges for correlations above threshold (without networkx)
        corr_threshold = 0.5
        for i in range(n_assets):
            for j in range(i + 1, n_assets):
                corr = corr_matrix.iloc[i, j]
                if corr >= corr_threshold:
                    x0, y0 = pos[tickers[i]]
                    x1, y1 = pos[tickers[j]]
                    edge_x.extend([x0, x1, None])
                    edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=1.0, color=CLUSTER_EDGE_COLOR),
            hoverinfo='none',
            mode='lines',
            showlegend=False
        )

        node_x = []
        node_y = []
        node_text = []
        node_colors = []

        cluster_palette = CLUSTER_PALETTE

        for ticker in tickers:
            x, y = pos[ticker]
            node_x.append(x)
            node_y.append(y)
            idx = tickers.index(ticker)
            cluster_id = int(cluster_labels[idx]) - 1
            node_colors.append(cluster_palette[cluster_id % len(cluster_palette)])
            node_text.append(f"{ticker}<br>Cluster: {cluster_labels[idx]}")

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            text=tickers,
            textposition="top center",
            textfont=dict(size=12, color=PRIMARY_TEXT, family='Arial Black'),
            marker=dict(
                size=20,
                color=node_colors,
                line=dict(width=2, color=CLUSTER_NODE_BORDER)
            ),
            hoverinfo='text',
            showlegend=False
        )

        fig = go.Figure(data=[edge_trace, node_trace])
        fig.update_layout(
            title=f"Asset Correlation Clustered Scatter (PCA Projection)",
            font=dict(color=TEXT_MUTED),
            title_x=0.5,
            showlegend=False,
            hovermode='closest',
            margin=dict(b=40, l=40, r=40, t=50),
            xaxis=dict(showgrid=True, gridcolor=CHART_GRID, zeroline=False, showticklabels=False, showline=False),
            yaxis=dict(showgrid=True, gridcolor=CHART_GRID, zeroline=False, showticklabels=False, showline=False),
            height=700,
            plot_bgcolor=BG_CHART,
            paper_bgcolor=BG_CHART,
        )

        return fig.to_html(full_html=False, include_plotlyjs=False)

    except Exception as e:
        return f"<p class=\"corr-insufficient-pad-40\">Cluster analysis unavailable: {str(e)}</p>"