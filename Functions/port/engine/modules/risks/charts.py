"""
Chart generation module: All Plotly visualizations for portfolio functions.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
from config import (
    RISK_DRAWDOWN_LOW,
    RISK_DRAWDOWN_MODERATE,
    RISK_DRAWDOWN_HIGH,
    RISK_VAR_LOW,
    RISK_VAR_MODERATE,
    RISK_VAR_HIGH,
    RISK_BETA_LOW,
    RISK_BETA_MARKET,
    RISK_BETA_MODERATE,
    RISK_BETA_HIGH,
    RISK_NA_COLOR,
    VAR_CHART_MAIN_BAR,
    VAR_CHART_TAIL_BAR,
    VAR_CHART_THRESHOLD,
    ES_BRACKET_LINE,
     CHART_TRANSPARENT,
     BG_CHART,
     TEXT_MUTED,
     TEXT_PRIMARY,
     CHART_GRID
)



def generate_risk_metrics_strip(metrics, total_series=None, ts_data=None):
    """
    Generates header strip with key risk metrics for the Risks tab.

    Args:
        metrics (dict): Performance metrics dict containing VaR, Beta, and multiple Max Drawdown values.
                        Expected keys: 'VaR (95%, 1-Year)', 'Beta', 'Max Drawdown',
                        'Max Drawdown 1M', 'Max Drawdown 1Y', 'Max Drawdown 5Y'.
        total_series (pd.Series, optional): Portfolio total value timeseries. Used to determine
                        if 1Y/5Y drawdowns are actual period values or since-inception fallbacks,
                        and to generate VaR density chart.
        ts_data (dict, optional): Time series data containing 'total' and 'benchmark' Series.
                        Used to generate rolling beta chart.

    Returns:
        str: HTML string with risk metrics cards display.
    """
    # Extract metrics with safe fallbacks
    var_95 = metrics.get('VaR (95%, 1-Year)', np.nan)
    beta = metrics.get('Beta', np.nan)
    max_dd_all = metrics.get('Max Drawdown', np.nan)
    max_dd_1m = metrics.get('Max Drawdown 1M', np.nan)
    max_dd_1y = metrics.get('Max Drawdown 1Y', np.nan)
    max_dd_5y = metrics.get('Max Drawdown 5Y', np.nan)

    # Format values as percentages
    def fmt_pct(val):
        if np.isnan(val):
            return "N/A"
        return f"{val*100:+.1f}%"

    def fmt_num(val):
        if np.isnan(val):
            return "N/A"
        return f"{val:.2f}"

    # Color helper for drawdowns (more negative = worse)
    def get_drawdown_color(val):
        if np.isnan(val):
            return RISK_NA_COLOR
        abs_val = abs(val)
        # Zones based on 50% scale: green <17.5%, orange 17.5-30%, red ≥30%
        if abs_val < 0.175:
            return RISK_DRAWDOWN_LOW
        elif abs_val < 0.30:
            return RISK_DRAWDOWN_MODERATE
        else:
            return RISK_DRAWDOWN_HIGH

    # Color helper for VaR (more negative = worse)
    def get_var_color(val):
        if np.isnan(val):
            return RISK_NA_COLOR
        abs_val = abs(val)
        return RISK_VAR_LOW if abs_val < 0.05 else RISK_VAR_MODERATE if abs_val < 0.10 else RISK_VAR_HIGH

    # Color helper for Beta (consistent with other metric colors)
    def get_beta_color(val):
        if np.isnan(val):
            return RISK_NA_COLOR
        if val < 0.8:
            return RISK_BETA_LOW
        elif val < 1.2:
            return RISK_BETA_MARKET
        elif val < 1.5:
            return RISK_BETA_MODERATE
        else:
            return RISK_BETA_HIGH

    var_color = get_var_color(var_95)
    beta_color = get_beta_color(beta)
    dd_1m_color = get_drawdown_color(max_dd_1m)
    dd_1y_color = get_drawdown_color(max_dd_1y)
    dd_5y_color = get_drawdown_color(max_dd_5y)

    # Generate rolling beta sparkline chart if time series data is available
    beta_sparkline_html = ""
    if ts_data is not None and 'total' in ts_data and 'benchmark' in ts_data:
        try:
            portfolio_ts = ts_data['total']
            benchmark_ts = ts_data['benchmark']
            
            if (portfolio_ts is not None and not portfolio_ts.empty and 
                benchmark_ts is not None and not benchmark_ts.empty and
                len(portfolio_ts) >= 30):
                
                # Calculate daily returns
                portfolio_returns = portfolio_ts.pct_change().dropna()
                benchmark_returns = benchmark_ts.pct_change().dropna()
                
                # Align the series
                common_index = portfolio_returns.index.intersection(benchmark_returns.index)
                if len(common_index) >= 30:
                    port_ret_aligned = portfolio_returns.loc[common_index]
                    bench_ret_aligned = benchmark_returns.loc[common_index]
                    
                    # Calculate rolling beta (1Y rolling ~ 252 trading days)
                    rolling_cov = port_ret_aligned.rolling(window=252).cov(bench_ret_aligned)
                    rolling_var_bench = bench_ret_aligned.rolling(window=252).var()
                    rolling_beta = rolling_cov / rolling_var_bench
                    
                    # Drop NaN values
                    rolling_beta = rolling_beta.dropna()
                    
                    if len(rolling_beta) > 0:
                        # Use 1Y rolling beta for the card value instead of since-inception
                        beta = rolling_beta.iloc[-1]
                        beta_color = get_beta_color(beta)
                    
                    if len(rolling_beta) >= 5:
                        # Create sparkline figure for rolling beta
                        fig_beta = go.Figure()
                        
                        # Determine color based on current beta value
                        spark_color = beta_color
                        
                        fig_beta.add_trace(go.Scatter(
                            x=rolling_beta.index,
                            y=rolling_beta.values,
                            mode='lines',
                            line=dict(width=2, color=spark_color),
                            showlegend=False,
                            hoverinfo='skip'
                        ))
                        
                        # Add endpoint marker
                        if len(rolling_beta) > 0:
                            fig_beta.add_trace(go.Scatter(
                                x=[rolling_beta.index[-1]],
                                y=[rolling_beta.values[-1]],
                                mode='markers',
                                marker=dict(size=6, color=spark_color),
                                showlegend=False,
                                hoverinfo='skip'
                            ))
                        
                        fig_beta.update_layout(
                            margin=dict(l=0, r=0, t=0, b=0),
                            height=80,
                            width=150,
                            paper_bgcolor=CHART_TRANSPARENT,
                            plot_bgcolor=CHART_TRANSPARENT,
                            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False, fixedrange=True),
                            yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False, fixedrange=True),
                            dragmode=False
                        )
                        
                        beta_sparkline_html = fig_beta.to_html(
                            full_html=False, 
                            include_plotlyjs=False, 
                            config={'staticPlot': True, 'displayModeBar': False}
                        )
        except Exception:
            beta_sparkline_html = ""

    # Determine if 1Y/5Y are fallbacks to inception
    len_series = len(total_series) if total_series is not None else 0
    label_1y = "1Y Max DD" if len_series >= 252 else "Since Inception Max DD"
    label_5y = "5Y Max DD" if len_series >= 1260 else "Since Inception Max DD"

    # Generate VaR density chart from 1-year rolling returns (similar to Monte Carlo Forward VaR)
    var_density_html = ""
    if total_series is not None and len(total_series) >= 252 and not np.isnan(var_95):
         try:
             # Use annualized daily returns (adjusted for yield) to match VaR calculation
             annual_yield = metrics.get('Estimated Yield', 0.0)
             daily_returns = total_series.pct_change().dropna()
             # Adjust for dividend yield if available
             daily_yield = (1 + annual_yield) ** (1/252) - 1 if annual_yield > 0 else 0.0
             adjusted_daily = daily_returns + daily_yield
             annualized_returns = adjusted_daily * np.sqrt(252)
             returns_pct = annualized_returns * 100  # Convert to percentage
             var_95_pct = var_95 * 100

             if len(annualized_returns) >= 10:
                 if returns_pct.nunique() > 1:
                     numeric_values = pd.to_numeric(returns_pct.values, errors='coerce')
                     numeric_values = numeric_values[~np.isnan(numeric_values)]

                     if len(numeric_values) > 1:
                         kde = stats.gaussian_kde(numeric_values)
                         data_min = numeric_values.min()
                         data_max = numeric_values.max()
                         plot_min = min(data_min, var_95_pct) - 1
                         plot_max = max(data_max, var_95_pct) + 1
                         x_range = np.linspace(plot_min, plot_max, 200)
                         y_density = kde(x_range)
                     else:
                         raise ValueError("Insufficient unique values")
                 else:
                     spike_center = returns_pct.iloc[0]
                     plot_min = min(spike_center - 1, var_95_pct - 1)
                     plot_max = max(spike_center + 1, var_95_pct + 1)
                     x_range = np.linspace(plot_min, plot_max, 200)
                     y_density = stats.norm.pdf(x_range, loc=spike_center, scale=0.05)

                 # Split into tail (<= var_95_pct) and body (> var_95_pct) for shading
                 tail_mask = x_range <= var_95_pct
                 x_tail = x_range[tail_mask]
                 y_tail = y_density[tail_mask]
                 x_body = x_range[~tail_mask]
                 y_body = y_density[~tail_mask]

                 fig_density = go.Figure()

                 # Body (line only, no fill)
                 fig_density.add_trace(go.Scatter(
                     x=x_body, y=y_body,
                     mode='lines',
                     line=dict(color=var_color, width=2),
                     showlegend=False,
                     fill='none'
                 ))

                 # Tail (line + filled shading)
                 fig_density.add_trace(go.Scatter(
                     x=x_tail, y=y_tail,
                     mode='lines',
                     line=dict(color=var_color, width=2),
                     showlegend=False,
                     fill='tozeroy',
                     fillcolor=f'rgba({int(var_color[1:3], 16)}, {int(var_color[3:5], 16)}, {int(var_color[5:7], 16)}, 0.3)'
                 ))

                 # Vertical line at VaR threshold
                 if not np.isnan(var_95_pct):
                     fig_density.add_vline(
                         x=var_95_pct,
                         line_width=2,
                         line_dash="dash",
                         line_color=var_color
                     )

                 y_max = y_density.max() if len(y_density) > 0 else 1.0
                 if y_max == 0:
                     y_max = 1.0

                 fig_density.update_layout(
                     margin=dict(l=0, r=0, t=0, b=0),
                     height=60,
                     width=120,
                     paper_bgcolor=CHART_TRANSPARENT,
                     plot_bgcolor=CHART_TRANSPARENT,
                     xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[x_range.min(), x_range.max()]),
                     yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[0, y_max*1.1])
                 )

                 var_density_html = fig_density.to_html(
                     full_html=False,
                     include_plotlyjs=False,
                     config={'staticPlot': True, 'displayModeBar': False}
                 )
         except Exception:
             var_density_html = ""

    # Helper to generate drawdown risk bar HTML (matches Forward Expected Drawdown in Monte Carlo tab)
    def generate_drawdown_bar(dd_value):
        """
        Creates a horizontal gradient bar with a marker indicating drawdown severity.
        Scale matches Monte Carlo Forward Expected Drawdown: left=worst (50% drawdown, red) to right=best (0% drawdown, green).
        Color zones: 0-25% DD (green), 25-40% DD (orange), 40-50% DD (red).
        """
        if np.isnan(dd_value):
            return ""
        # Convert drawdown (negative value e.g. -0.25) to positive magnitude
        dd_pct = abs(dd_value * 100)
        # Map to percentage position: 0% DD → 100% (right, best), 50% DD → 0% (left, worst)
        marker_pct = max(0, min(100, (1 - dd_pct / 50.0) * 100))

        return f'''
        <div class="dd-risk-bar-wrap">
            <div class="dd-risk-bar-track">
                <!-- Marker line -->
                <div class="dd-risk-marker" style="left: {marker_pct}%"></div>
                <!-- Marker arrow -->
                <div class="dd-risk-arrow-wrap" style="left: {marker_pct}%">
                    <div class="dd-risk-arrow"></div>
                </div>
            </div>
            <!-- Tick labels: left=worst (50%), right=best (0%) -->
            <div class="dd-risk-labels">
                <span>-50%</span>
                <span>-40%</span>
                <span>-30%</span>
                <span>-20%</span>
                <span>-10%</span>
                <span>0%</span>
            </div>
        </div>
        '''

    html = f"""
    <div class="metrics-container">
        <!-- VaR 95% 1-Year Card -->
        <div class="metrics-card" style="--bg-color: {var_color}20; --border-color: {var_color};">
            <div>
                <div class="metrics-card-label">VaR (95%, 1-Yr)</div>
                <div class="metrics-card-value" style="--text-color: {var_color};">{fmt_pct(var_95)}</div>
            </div>
            <div class="metrics-card-content">
                {var_density_html if var_density_html else ""}
            </div>
        </div>

         <!-- Portfolio Beta Card -->
         <div class="metrics-card" style="--bg-color: {beta_color}20; --border-color: {beta_color};">
             <div>
                <div class="metrics-card-label">Portfolio Beta (1-Yr)</div>
                <div class="metrics-card-value" style="--text-color: {beta_color};">{fmt_num(beta)}</div>
             </div>
             <div class="metrics-card-content">
                {beta_sparkline_html if beta_sparkline_html else ""}
             </div>
         </div>


         <!-- 1M Max Drawdown Card -->
         <div class="metrics-card" style="--bg-color: {dd_1m_color}20; --border-color: {dd_1m_color};">
             <div>
                <div class="metrics-card-label">1M Max Drawdown</div>
                <div class="metrics-card-value" style="--text-color: {dd_1m_color};">{fmt_pct(max_dd_1m)}</div>
             </div>
             <div class="metrics-card-content">
                {generate_drawdown_bar(max_dd_1m)}
             </div>
         </div>

          <!-- 1Y Max Drawdown Card -->
          <div class="metrics-card" style="--bg-color: {dd_1y_color}20; --border-color: {dd_1y_color};">
              <div>
                <div class="metrics-card-label">{label_1y}</div>
                <div class="metrics-card-value" style="--text-color: {dd_1y_color};">{fmt_pct(max_dd_1y)}</div>
              </div>
              <div class="metrics-card-content">
                {generate_drawdown_bar(max_dd_1y)}
              </div>
          </div>

          <!-- 5Y Max Drawdown Card -->
          <div class="metrics-card" style="--bg-color: {dd_5y_color}20; --border-color: {dd_5y_color};">
              <div>
                <div class="metrics-card-label">{label_5y}</div>
                <div class="metrics-card-value" style="--text-color: {dd_5y_color};">{fmt_pct(max_dd_5y)}</div>
              </div>
              <div class="metrics-card-content">
                {generate_drawdown_bar(max_dd_5y)}
              </div>
          </div>
    </div>
    """
    return html



def generate_var_es_analysis_charts(returns_series, horizon_name="DAILY"):
    """
    Generates VaR and ES analysis charts for a given returns series and horizon label.

    Args:
        returns_series (pd.Series): Series of returns.
        horizon_name (str): Label for horizon (e.g., "DAILY", "WEEKLY").

    Returns:
        str: HTML string with VaR and ES charts.
    """
    rets = returns_series.values
    if len(rets) < 5:
        return "<p>Insufficient data for " + horizon_name + " horizon.</p>"

    rets = rets[rets != 0]
    if len(rets) < 5:
        return "<p>Insufficient data for " + horizon_name + " horizon.</p>"

    # Calculations
    conf_95 = 0.95
    var_95 = np.percentile(rets, (1 - conf_95) * 100)
    es_95 = rets[rets <= var_95].mean()

    # Chart colors
    color_main = VAR_CHART_MAIN_BAR
    color_tail = VAR_CHART_TAIL_BAR
    color_var = VAR_CHART_THRESHOLD

    # Bin the data
    counts, bins = np.histogram(rets, bins=50)
    bin_centers = (bins[:-1] + bins[1:]) / 2

    # Left: VaR chart
    fig_var = go.Figure()
    fig_var.add_trace(go.Bar(
        x=bin_centers, y=counts,
        marker_color=[color_tail if b <= var_95 else color_main for b in bin_centers],
        opacity=0.7
    ))
    fig_var.add_vline(x=var_95, line_width=3, line_dash="dash", line_color=color_var)
    fig_var.add_annotation(
        x=var_95, y=max(counts) * 0.8,
        text=f"VaR (95%): {var_95*100:.1f}%",
        showarrow=True, arrowhead=2, ax=40, ay=-40,
        bgcolor=color_var, font=dict(color="black")
    )
    fig_var.update_layout(
        title=f"{horizon_name}: VaR (Threshold Focus)",
        title_font=dict(color=TEXT_MUTED),
        font=dict(color=TEXT_PRIMARY),
        xaxis_title="Return", yaxis_title="Frequency",
        xaxis_tickformat=".1%",
        xaxis_showgrid=True,
        yaxis_showgrid=True,
        xaxis_gridcolor=CHART_GRID,
        yaxis_gridcolor=CHART_GRID,
        xaxis_title_font=dict(color=TEXT_MUTED),
        yaxis_title_font=dict(color=TEXT_MUTED),
        xaxis_tickfont=dict(color=TEXT_MUTED),
        yaxis_tickfont=dict(color=TEXT_MUTED),
        plot_bgcolor=BG_CHART, paper_bgcolor=BG_CHART,
        height=350, showlegend=False, margin=dict(l=20, r=20, t=50, b=20)
    )

    # Right: ES chart
    fig_es = go.Figure()
    fig_es.add_trace(go.Bar(
        x=bin_centers, y=counts,
        marker_color=[color_tail if b <= var_95 else color_main for b in bin_centers],
        opacity=0.5
    ))
    fig_es.add_vline(x=es_95, line_width=4, line_color=color_tail)
    fig_es.add_vline(x=var_95, line_width=2, line_dash="dot", line_color=color_var)
    fig_es.add_shape(
        type="line", x0=es_95, y0=max(counts)*0.9, x1=var_95, y1=max(counts)*0.9,
        line=dict(color=ES_BRACKET_LINE, width=2)
    )
    fig_es.add_shape(
        type="line", x0=es_95, y0=max(counts)*0.85, x1=es_95, y1=max(counts)*0.95,
        line=dict(color=ES_BRACKET_LINE, width=2)
    )
    fig_es.add_shape(
        type="line", x0=var_95, y0=max(counts)*0.85, x1=var_95, y1=max(counts)*0.95,
        line=dict(color=ES_BRACKET_LINE, width=2)
    )
    fig_es.add_annotation(
        x=(es_95 + var_95)/2, y=max(counts)*0.95,
        text="Avg loss beyond VaR", showarrow=False,
        font=dict(size=10, color=ES_BRACKET_LINE), yshift=10
    )
    fig_es.add_annotation(
        x=es_95, y=max(counts) * 0.7,
        text=f"ES (95%): {es_95*100:.1f}%",
        showarrow=True, arrowhead=2, ax=-40, ay=-40,
        bgcolor=color_tail, font=dict(color="white")
    )
    fig_es.update_layout(
        title=f"{horizon_name}: ES (Tail Depth Focus)",
        title_font=dict(color=TEXT_MUTED),
        font=dict(color=TEXT_PRIMARY),
        xaxis_title="Return", yaxis_title="Frequency",
        xaxis_tickformat=".1%",
        xaxis_showgrid=True,
        yaxis_showgrid=True,
        xaxis_gridcolor=CHART_GRID,
        yaxis_gridcolor=CHART_GRID,
        xaxis_title_font=dict(color=TEXT_MUTED),
        yaxis_title_font=dict(color=TEXT_MUTED),
        xaxis_tickfont=dict(color=TEXT_MUTED),
        yaxis_tickfont=dict(color=TEXT_MUTED),
        plot_bgcolor=BG_CHART, paper_bgcolor=BG_CHART,
        height=350, showlegend=False, margin=dict(l=20, r=20, t=50, b=20)
    )

    html_header = f"""
    <div class="header-box">
        <div class="header-item"><span class="header-label">VaR (95%)</span><br/><span class="header-value">{var_95*100:+.1f}%</span></div>
        <div class="header-item"><span class="header-label">ES (95%)</span><br/><span class="header-value">{es_95*100:+.1f}%</span></div>
        <div class="header-item"><span class="header-label">HORIZON</span><br/><span class="header-value">{horizon_name}</span></div>
        <div class="header-item"><span class="header-label">CONFIDENCE</span><br/><span class="header-value">95%</span></div>
    </div>
    """

    return f"""
    {html_header}
    <div class="chart-row-container">
        <div class="chart-row-item">{fig_var.to_html(full_html=False, include_plotlyjs=False)}</div>
        <div class="chart-row-item">{fig_es.to_html(full_html=False, include_plotlyjs=False)}</div>
    </div>
    """