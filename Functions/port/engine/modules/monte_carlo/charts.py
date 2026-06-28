"""
Chart generation module: All Plotly visualizations for portfolio functions.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats
from config import (
    MC_BG,
    MC_GRID,
    MC_MEAN_PATH,
    MC_TAIL_RISK_FILL,
    MC_MAIN_DIST_FILL,
    MC_EXTREME_UP_FILL,
    TEXT_MUTED,
    MC_POSITIVE,
    MC_NEGATIVE,
    MC_NEUTRAL,
    MC_DRAWDOWN_LOW,
    MC_DRAWDOWN_MODERATE,
    MC_DRAWDOWN_HIGH,
    MC_CARD_CLASS_GREEN,
    MC_CARD_CLASS_RED,
    MC_CARD_CLASS_ORANGE,
)



def _card_class_for_color(color):
    if color == MC_CARD_CLASS_GREEN:
        return 'mc-card-green'
    elif color == MC_CARD_CLASS_RED:
        return 'mc-card-red'
    elif color == MC_CARD_CLASS_ORANGE:
        return 'mc-card-orange'
    return 'mc-card-gray'


def generate_monte_carlo_chart(mc_simulations):
    """
    Generates an interactive Plotly chart showing a subset of Monte Carlo simulation paths
    and the mean path, with Y-axis in percentage change from initial value.

    Args:
        mc_simulations (pd.DataFrame): DataFrame containing all Monte Carlo simulation paths.

    Returns:
        str: HTML string representing the generated Plotly chart.
    """
    fig = go.Figure()
    fig.update_layout(title="Monte Carlo Simulation: Portfolio Future Paths (% Change)", height=600)

    # Calculate percentage change from initial value for all paths
    initial_value_per_path = mc_simulations.iloc[0]  # This will be a Series if mc_simulations has multiple columns
    # Perform element-wise division and then subtract 1 and multiply by 100
    # Ensure that initial_value_per_path is correctly broadcasted or aligned
    mc_simulations_pct = (mc_simulations.div(initial_value_per_path, axis=1) - 1) * 100

    # Handle possible NaN values in simulation paths
    mc_simulations_pct = mc_simulations_pct.fillna(0)

    # Calculate percentiles
    p01 = mc_simulations_pct.quantile(0.01, axis=1)
    p05 = mc_simulations_pct.quantile(0.05, axis=1)
    p95 = mc_simulations_pct.quantile(0.95, axis=1)
    p99 = mc_simulations_pct.quantile(0.99, axis=1)

    # Add 1st-5th percentile (Tail Risk - Lower)
    fig.add_trace(go.Scatter(x=mc_simulations_pct.index, y=p01, mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(
        x=mc_simulations_pct.index, y=p05, mode='lines', line=dict(width=0),
        fill='tonexty', fillcolor=MC_TAIL_RISK_FILL, name='Tail Risk (1st-5th Pctl)', showlegend=True
    ))

    fig.add_trace(go.Scatter(x=mc_simulations_pct.index, y=p95, mode='lines', line=dict(width=0), fill='tonexty', fillcolor=MC_MAIN_DIST_FILL, name='Main Distribution (5th-95th Pctl)', showlegend=True))

    fig.add_trace(go.Scatter(x=mc_simulations_pct.index, y=p99, mode='lines', line=dict(width=0), fill='tonexty', fillcolor=MC_EXTREME_UP_FILL, name='Extreme Upside (95th-99th Pctl)', showlegend=True))

    mean_path_pct = mc_simulations_pct.mean(axis=1)
    fig.add_trace(go.Scatter(x=mean_path_pct.index, y=mean_path_pct, mode='lines', name='Mean Path', line=dict(color=MC_MEAN_PATH, width=2, dash='dash')))

    fig.update_layout(
        xaxis_title='Days into Future',
        yaxis_title='Portfolio Value (% Change)',
        yaxis_tickformat=".0f",
        yaxis_ticksuffix="%",
        plot_bgcolor=MC_BG,
        paper_bgcolor=MC_BG,
        font=dict(color=TEXT_MUTED),
        xaxis=dict(showgrid=True, gridcolor=MC_GRID, linecolor=MC_GRID),
        yaxis=dict(showgrid=True, gridcolor=MC_GRID, linecolor=MC_GRID)
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)



def generate_monte_carlo_metrics_strip(metrics, mc_simulations=None):
    """
    Generates header strip with key Monte Carlo simulation metrics.

    Args:
        metrics (dict): Performance metrics dict containing 'total' layer with MC keys.
        mc_simulations (pd.DataFrame, optional): Raw simulation paths for optional sparkline (not used).

    Returns:
        str: HTML string with 5 metric cards display.
    """
    if "total" not in metrics:
        return '<div class="mc-no-results">No Monte Carlo results available.</div>'

    m = metrics["total"]
    mean_return = m.get("MC_Mean_Final_Return", np.nan)
    var_95 = m.get("MC_VaR_95_Pct", np.nan)
    var_99 = m.get("MC_VaR_99_Pct", np.nan)
    upside_95 = m.get("MC_Expected_Upside_95_Pct", np.nan)
    expected_dd = m.get("MC_Expected_Drawdown_Pct", np.nan)

    # Formatting helper
    def fmt_pct(val):
        if np.isnan(val):
            return "N/A"
        return f"{val*100:+.2f}%"

    # Color helpers
    def get_mean_color(val):
        if np.isnan(val):
            return MC_NEUTRAL
        return MC_POSITIVE if val >= 0 else MC_NEGATIVE

    def get_upside_color(val):
        if np.isnan(val):
            return MC_NEUTRAL
        return MC_POSITIVE if val > 0 else MC_NEUTRAL

    def get_risk_color(val):
        if np.isnan(val):
            return MC_NEUTRAL
        abs_val = abs(val)
        return MC_POSITIVE if abs_val < 0.10 else MC_DRAWDOWN_MODERATE if abs_val < 0.20 else MC_NEGATIVE

    def get_dd_color(val):
        if np.isnan(val):
            return MC_NEUTRAL
        abs_val = abs(val)
        # Zones based on 50% scale: green <17.5%, orange 17.5-30%, red ≥30%
        if abs_val < 0.175:
            return MC_DRAWDOWN_LOW
        elif abs_val < 0.30:
            return MC_DRAWDOWN_MODERATE
        else:
            return MC_DRAWDOWN_HIGH

    mean_color = get_mean_color(mean_return)
    upside_color = get_upside_color(upside_95)
    var95_color = get_risk_color(var_95)
    var99_color = get_risk_color(var_99)
    dd_color = get_dd_color(expected_dd)

    mean_cls = _card_class_for_color(mean_color)
    upside_cls = _card_class_for_color(upside_color)
    var95_cls = _card_class_for_color(var95_color)
    var99_cls = _card_class_for_color(var99_color)
    dd_cls = _card_class_for_color(dd_color)

    # Optional sparkline: static histogram of final outcomes
    sparkline_html = ""
    var_density_html = ""
    upside_density_html = ""
    var99_density_html = ""
    if mc_simulations is not None and not mc_simulations.empty and len(mc_simulations) >= 2:
        try:
            final_values = mc_simulations.iloc[-1]
            initial_value = mc_simulations.iloc[0, 0]
            final_returns_pct = (final_values / initial_value - 1) * 100

            # Convert thresholds to percent for plotting (to match final_returns_pct scale)
            var_95_pct = var_95 * 100 if not np.isnan(var_95) else np.nan
            upside_95_pct = upside_95 * 100 if not np.isnan(upside_95) else np.nan
            var_99_pct = var_99 * 100 if not np.isnan(var_99) else np.nan

            # Histogram sparkline for Mean Return card
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(
                x=final_returns_pct.values,
                nbinsx=30,
                marker_color='rgba(31, 119, 180, 0.6)',
                showlegend=False
            ))
            fig_hist.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=60,
                width=120,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
                yaxis=dict(showgrid=False, showticklabels=False),
                bargap=0.1
            )
            sparkline_html = fig_hist.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

            # Density line chart with VaR marker and shaded tail for Forward 95% VaR card
            fig_density = go.Figure()

            # Compute KDE
            if final_returns_pct.nunique() > 1:
                # Ensure data is numeric
                numeric_values = pd.to_numeric(final_returns_pct.values, errors='coerce')
                # Drop any NaNs that might have been introduced
                numeric_values = numeric_values[~np.isnan(numeric_values)]

                kde = stats.gaussian_kde(numeric_values)
                x_min, x_max = numeric_values.min(), numeric_values.max()
                # Ensure range is non-zero
                if x_min == x_max:
                    x_min -= 1
                    x_max += 1
                x_range = np.linspace(x_min, x_max, 200)
                y_density = kde(x_range)
            else:
                # No variance: artificial spike
                spike_center = final_returns_pct.iloc[0]
                x_range = np.linspace(spike_center - 1, spike_center + 1, 200)
                # Create a narrow spike using normal distribution
                y_density = stats.norm.pdf(x_range, loc=spike_center, scale=0.05)

            # Split into tail (<= var_95_pct) and body (> var_95_pct) for shading
            tail_mask = x_range <= var_95_pct
            x_tail = x_range[tail_mask]
            y_tail = y_density[tail_mask]
            x_body = x_range[~tail_mask]
            y_body = y_density[~tail_mask]

            # Plot body (density line only, no fill)
            fig_density.add_trace(go.Scatter(
                x=x_body, y=y_body,
                mode='lines',
                line=dict(color=var95_color, width=2),
                showlegend=False,
                fill='none'
            ))

            # Plot tail (density line + filled shading)
            fig_density.add_trace(go.Scatter(
                x=x_tail, y=y_tail,
                mode='lines',
                line=dict(color=var95_color, width=2),
                showlegend=False,
                fill='tozeroy',
                fillcolor=f'rgba({int(var95_color[1:3], 16)}, {int(var95_color[3:5], 16)}, {int(var95_color[5:7], 16)}, 0.3)'
            ))

            # Add vertical line at VaR (only if valid)
            if not np.isnan(var_95_pct):
                fig_density.add_vline(
                    x=var_95_pct,
                    line_width=2,
                    line_dash="dash",
                    line_color=var95_color
                )

            y_max = y_density.max()
            if y_max == 0:
                y_max = 1.0  # Ensure a visible range even if density is 0

            fig_density.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=60,
                width=120,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[x_range.min(), x_range.max()]),
                yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[0, y_max*1.1])
            )

            var_density_html = fig_density.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})
        except Exception:
            var_density_html = ""

        # Density line chart with Expected Upside marker and shaded upper tail for 95% Expected Upside card
        try:
            if final_returns_pct.nunique() > 1:
                numeric_values = pd.to_numeric(final_returns_pct.values, errors='coerce')
                numeric_values = numeric_values[~np.isnan(numeric_values)]

                kde = stats.gaussian_kde(numeric_values)
                x_min, x_max = numeric_values.min(), numeric_values.max()
                if x_min == x_max:
                    x_min -= 1
                    x_max += 1
                x_range_upside = np.linspace(x_min, x_max, 200)
                y_density_upside = kde(x_range_upside)
            else:
                spike_center = final_returns_pct.iloc[0]
                x_range_upside = np.linspace(spike_center - 1, spike_center + 1, 200)
                y_density_upside = stats.norm.pdf(x_range_upside, loc=spike_center, scale=0.05)

            # Split into tail (>= upside_95_pct) and body (< upside_95_pct) for shading
            tail_mask_upside = x_range_upside >= upside_95_pct
            x_tail_upside = x_range_upside[tail_mask_upside]
            y_tail_upside = y_density_upside[tail_mask_upside]
            x_body_upside = x_range_upside[~tail_mask_upside]
            y_body_upside = y_density_upside[~tail_mask_upside]

            # Create figure for Expected Upside
            fig_upside = go.Figure()

            # Plot body (density line only, no fill)
            fig_upside.add_trace(go.Scatter(
                x=x_body_upside, y=y_body_upside,
                mode='lines',
                line=dict(color=upside_color, width=2),
                showlegend=False,
                fill='none'
            ))

            # Plot tail (density line + filled shading) - upper tail
            fig_upside.add_trace(go.Scatter(
                x=x_tail_upside, y=y_tail_upside,
                mode='lines',
                line=dict(color=upside_color, width=2),
                showlegend=False,
                fill='tozeroy',
                fillcolor=f'rgba({int(upside_color[1:3], 16)}, {int(upside_color[3:5], 16)}, {int(upside_color[5:7], 16)}, 0.3)'
            ))

            # Add vertical line at Expected Upside threshold (only if valid)
            if not np.isnan(upside_95_pct):
                fig_upside.add_vline(
                    x=upside_95_pct,
                    line_width=2,
                    line_dash="dash",
                    line_color=upside_color
                )

            y_max_upside = y_density_upside.max()
            if y_max_upside == 0:
                y_max_upside = 1.0

            fig_upside.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=60,
                width=120,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[x_range_upside.min(), x_range_upside.max()]),
                yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[0, y_max_upside*1.1])
            )

            upside_density_html = fig_upside.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})
        except Exception:
            upside_density_html = ""

        # Density line chart with VaR 99% marker and shaded tail for Forward 99% VaR card
        try:
            if final_returns_pct.nunique() > 1:
                numeric_values = pd.to_numeric(final_returns_pct.values, errors='coerce')
                numeric_values = numeric_values[~np.isnan(numeric_values)]

                kde = stats.gaussian_kde(numeric_values)
                x_min, x_max = numeric_values.min(), numeric_values.max()
                if x_min == x_max:
                    x_min -= 1
                    x_max += 1
                x_range_99 = np.linspace(x_min, x_max, 200)
                y_density_99 = kde(x_range_99)
            else:
                spike_center = final_returns_pct.iloc[0]
                x_range_99 = np.linspace(spike_center - 1, spike_center + 1, 200)
                y_density_99 = stats.norm.pdf(x_range_99, loc=spike_center, scale=0.05)

            # Split into tail (<= var_99_pct) and body (> var_99_pct) for shading
            tail_mask_99 = x_range_99 <= var_99_pct
            x_tail_99 = x_range_99[tail_mask_99]
            y_tail_99 = y_density_99[tail_mask_99]
            x_body_99 = x_range_99[~tail_mask_99]
            y_body_99 = y_density_99[~tail_mask_99]

            # Create figure for 99% VaR
            fig_99 = go.Figure()

            # Plot body (density line only, no fill)
            fig_99.add_trace(go.Scatter(
                x=x_body_99, y=y_body_99,
                mode='lines',
                line=dict(color=var99_color, width=2),
                showlegend=False,
                fill='none'
            ))

            # Plot tail (density line + filled shading) - left tail
            fig_99.add_trace(go.Scatter(
                x=x_tail_99, y=y_tail_99,
                mode='lines',
                line=dict(color=var99_color, width=2),
                showlegend=False,
                fill='tozeroy',
                fillcolor=f'rgba({int(var99_color[1:3], 16)}, {int(var99_color[3:5], 16)}, {int(var99_color[5:7], 16)}, 0.3)'
            ))

            # Add vertical line at 99% VaR threshold (only if valid)
            if not np.isnan(var_99_pct):
                fig_99.add_vline(
                    x=var_99_pct,
                    line_width=2,
                    line_dash="dash",
                    line_color=var99_color
                )

            y_max_99 = y_density_99.max()
            if y_max_99 == 0:
                y_max_99 = 1.0

            fig_99.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=60,
                width=120,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[x_range_99.min(), x_range_99.max()]),
                yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[0, y_max_99*1.1])
            )

            var99_density_html = fig_99.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})
        except Exception:
            var99_density_html = ""

    html = f'''
    <div class="mc-metric-wrapper">
        <!-- Mean Return Card (with static histogram) -->
        <div class="mc-metric-card {mean_cls}">
            <div class="mc-card-label">FWD Mean Return (1-Year)</div>
            <div class="mc-card-value">{fmt_pct(mean_return)}</div>
            {'<div class="mc-sparkline-wrap">' + sparkline_html + '</div>' if sparkline_html else '<div class="mc-sparkline-empty"></div>'}
        </div>

        <!-- 95% Expected Upside Card (with density chart showing upper tail) -->
        <div class="mc-metric-card {upside_cls}">
            <div class="mc-card-label">95% Expected Upside (1-Year)</div>
            <div class="mc-card-value">{fmt_pct(upside_95)}</div>
            {'<div class="mc-sparkline-wrap">' + upside_density_html + '</div>' if upside_density_html else '<div class="mc-sparkline-empty"></div>'}
        </div>

        <!-- 95% VaR Card -->
        <div class="mc-metric-card {var95_cls}">
            <div class="mc-card-label">Forward 95% VaR</div>
            <div class="mc-card-value">{fmt_pct(var_95)}</div>
            {'<div class="mc-sparkline-wrap">' + var_density_html + '</div>' if var_density_html else '<div class="mc-sparkline-empty"></div>'}
        </div>

        <!-- 99% VaR Card -->
        <div class="mc-metric-card {var99_cls}">
            <div class="mc-card-label">Forward 99% VaR</div>
            <div class="mc-card-value">{fmt_pct(var_99)}</div>
            {'<div class="mc-sparkline-wrap">' + var99_density_html + '</div>' if var99_density_html else '<div class="mc-sparkline-empty"></div>'}
        </div>

        <!-- Forward Expected Drawdown Card -->
        <div class="mc-metric-card {dd_cls}">
            <div class="mc-card-label">Forward Expected Drawdown</div>
            <div class="mc-card-value">{fmt_pct(expected_dd)}</div>
            <div class="dd-risk-bar-wrap">
                <div class="dd-risk-bar-track">
                    <div class="dd-risk-marker" style="left: {max(0, min(100, (1 - abs(expected_dd)/0.50) * 100))}%;"></div>
                    <div class="dd-risk-arrow-wrap" style="left: {max(0, min(100, (1 - abs(expected_dd)/0.50) * 100))}%;">
                        <div class="dd-risk-arrow"></div>
                    </div>
                </div>
                <div class="dd-risk-labels">
                    <span>-50%</span>
                    <span>-40%</span>
                    <span>-30%</span>
                    <span>-20%</span>
                    <span>-10%</span>
                    <span>0%</span>
                </div>
            </div>
        </div>
    </div>
    '''
    return html
