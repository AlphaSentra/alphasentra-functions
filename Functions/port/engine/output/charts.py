"""
Chart generation module: Dispatcher for all portfolio visualizations.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from config import (
    BG_CHART, CHART_GRID, TEXT_MUTED, HEATMAP_NEGATIVE_CELL, HEATMAP_NEUTRAL_CELL, HEATMAP_POSITIVE_CELL, HEATMAP_DIAGONAL_CELL
)

# Import tab-specific chart generators
from engine.modules.overview.charts import (
    generate_performance_barchart,
    generate_main_performance_chart,
    generate_overview_metrics_strip
)
from engine.modules.correlation.charts import (
    generate_rolling_correlation_chart,
    generate_correlation_metrics_strip,
    generate_timeframe_correlation_panel,
    generate_correlation_distribution_chart,
    generate_stability_score,
    generate_regime_indicator,
    generate_correlation_cluster_network
)
from engine.modules.risks.charts import generate_risk_metrics_strip

def generate_charts(ts_data, risk_contrib, corr_matrix, benchmark_ticker, annual_yield=0.0, metrics=None, holdings_df=None):
    """
    Dispatcher that aggregates charts from all modules for the output engine.
    """
    charts = {}

    # 1. Main Portfolio Performance Chart (from Overview)
    charts["value"] = generate_main_performance_chart(ts_data, benchmark_ticker, annual_yield)
    charts["overview_metrics_strip"] = generate_overview_metrics_strip(ts_data["total"], annual_yield)

    # 2. Performance Bar Chart (from Overview)
    charts["performance_barchart"] = generate_performance_barchart(ts_data, benchmark_ticker, annual_yield, include_yield_toggle=(annual_yield > 0))

    # 3. Portfolio Allocation Pie Chart
    if not risk_contrib.empty and "Weight" in risk_contrib.columns:
        weights = risk_contrib["Weight"]
        pie = px.pie(values=weights, names=weights.index, height=600, title="Portfolio Allocation by Weight")
        charts["allocation"] = pie.to_html(full_html=False, include_plotlyjs=False)
    else:
        charts["allocation"] = "<p class='no-data-message'>No allocation data available.</p>"

    # 5. Correlation Heatmap (Full Matrix)
    if not corr_matrix.empty and len(corr_matrix) > 0:
        corr_clean = corr_matrix.copy()
        corr_clean = corr_clean.replace(-2.0, 1.0)

        # Create text matrix for annotations, hide diagonal text
        text_matrix = np.vectorize(lambda x: f"{x:.2f}")(corr_clean.values)
        np.fill_diagonal(text_matrix, "")

        # Custom colorscale: green (-1) -> white (0.1) -> red (1.0)
        colorscale = [
            [0.0, HEATMAP_NEGATIVE_CELL],
            [0.55, HEATMAP_NEUTRAL_CELL],
            [0.999, HEATMAP_POSITIVE_CELL],
            [1.0, HEATMAP_DIAGONAL_CELL]
        ]

        fig_corr_full = go.Figure(data=go.Heatmap(
            z=corr_clean.values,
            x=corr_clean.columns,
            y=corr_clean.index,
            colorscale=colorscale,
            zmid=0,
            zmin=-1,
            zmax=1,
            xgap=0,
            ygap=0,
            colorbar=dict(
                title=dict(text="Correlation", side="right"),
                tickformat=".2f"
            ),
            text=text_matrix,
            texttemplate="%{text}",
            hoverinfo='text',
            showscale=True
        ))

        n_tickers = len(corr_clean)
        fig_height = max(800, 120 + n_tickers * 30)

        fig_corr_full.update_layout(
            title="Full Portfolio Correlation Matrix",
            height=fig_height,
            font=dict(color=TEXT_MUTED),
            plot_bgcolor=BG_CHART,
            paper_bgcolor=BG_CHART,
            xaxis=dict(
                tickangle=-45,
                tickfont=dict(size=10),
                showgrid=True,
                gridcolor=CHART_GRID,
            ),
            yaxis=dict(
                tickfont=dict(size=10),
                autorange='reversed',
                scaleanchor="x",
                showgrid=True,
                gridcolor=CHART_GRID,
            ),
            margin=dict(l=180, r=60, t=50, b=180)
        )

        charts["corr_matrix_full"] = fig_corr_full.to_html(full_html=False, include_plotlyjs=False, config={'responsive': True, 'auto_margin': False})
    else:
        charts["corr_matrix_full"] = "<p class='no-data-message'>No correlation data available.</p>"

    # 6. Risk Contribution Chart
    # The column name from analyzer.py is 'Risk Contribution'
    if not risk_contrib.empty and "Risk Contribution" in risk_contrib.columns:
        fig_risk = px.bar(risk_contrib, x=risk_contrib.index, y="Risk Contribution", title="Risk Contribution by Asset")
        fig_risk.update_layout(font=dict(color=TEXT_MUTED))
        charts["risk_contribution"] = fig_risk.to_html(full_html=False, include_plotlyjs=False)
    else:
        charts["risk_contribution"] = "<p class='no-data-message'>No risk contribution data available.</p>"

    # 7. Correlation Tab Charts & Commentary
    charts["correlation_metrics_strip"] = generate_correlation_metrics_strip(ts_data)
    charts["rolling_correlation"] = generate_rolling_correlation_chart(ts_data)
    charts["timeframe_correlation"] = generate_timeframe_correlation_panel(ts_data)
    charts["stability_score"] = generate_stability_score(ts_data)
    charts["regime_indicator"] = generate_regime_indicator(ts_data)
    charts["correlation_distribution"] = generate_correlation_distribution_chart(ts_data)
    charts["corr_cluster_network"] = generate_correlation_cluster_network(corr_matrix)
    
    # 8. Risks Metrics Strip
    # Construct a flat metrics dictionary for the risk strip from different horizons
    if metrics:
        one_year = metrics.get("1Y", {})
        one_month = metrics.get("1M", {})
        five_year = metrics.get("5Y", {})
        
        risk_metrics = one_year.copy()
        risk_metrics["Max Drawdown 1M"] = one_month.get("Max Drawdown", np.nan)
        risk_metrics["Max Drawdown 1Y"] = one_year.get("Max Drawdown", np.nan)
        risk_metrics["Max Drawdown 5Y"] = five_year.get("Max Drawdown", np.nan)
    else:
        risk_metrics = {}
        
    charts["risk_metrics_strip"] = generate_risk_metrics_strip(risk_metrics, ts_data.get("total"), ts_data)

    # Note: Monte Carlo, Risks, and Breakdown metrics are handled directly in analyzer.py
    # to ensure they use the correct data objects (mc_simulations, etc.)

    return charts
