import os
from jinja2 import Template
from .charts import (
    generate_rolling_metrics_line_chart,
    generate_3d_risk_trajectory,
    generate_rolling_metrics_table,
    generate_efficiency_metrics_strip,
    generate_security_efficiency_table
)


def render_efficiency_tab(returns_series, benchmark_returns, holdings_df, prices, metrics=None) -> str:
    """
    Renders the Efficiency tab HTML block.

    Args:
        returns_series (pd.Series): Total portfolio returns series.
        benchmark_returns (pd.Series): Benchmark returns series.
        holdings_df (pd.DataFrame, optional): Current portfolio holdings data.
        prices (pd.DataFrame): Historical price data.
        metrics (dict, optional): Pre-computed metrics dict (keys like '1Y', '5Y', 'All').

    Returns:
        str: Rendered HTML string for the Efficiency tab <div>.
    """
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    charts = {}
    
    charts['efficiency_metrics_strip'] = generate_efficiency_metrics_strip(returns_series, benchmark_returns, analyzer_metrics=metrics)
    charts['rolling_metrics_line'] = generate_rolling_metrics_line_chart(returns_series, benchmark_returns)
    charts['security_efficiency_table'] = generate_security_efficiency_table(returns_series, holdings_df, prices)
    charts['risk_trajectory_3d'] = generate_3d_risk_trajectory(returns_series, benchmark_returns)
    charts['rolling_metrics_table'] = generate_rolling_metrics_table(returns_series, benchmark_returns, analyzer_metrics=metrics)

    template = Template(template_src)
    return template.render(
        charts=charts,
    )
