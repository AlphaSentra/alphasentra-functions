"""
Intel tab chart generators.
"""

from jinja2 import Template
import os


def _render_template(name: str, context: dict) -> str:
    template_path = os.path.join(os.path.dirname(__file__), name)
    if not os.path.exists(template_path):
        return ""
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()
    template = Template(template_src)
    return template.render(**context)


def generate_intel_metrics_strip(metrics: dict, holdings_df=None) -> str:
    context = {"metrics": metrics, "holdings_df": holdings_df}
    return _render_template("metrics_strip.html", context)


def generate_intel_performance_chart(metrics: dict, ts: dict, benchmark_ticker: str) -> str:
    context = {"metrics": metrics, "ts": ts, "benchmark_ticker": benchmark_ticker}
    return _render_template("performance.html", context)


def generate_intel_insights(metrics: dict, holdings_df=None, risk_df=None) -> str:
    context = {"metrics": metrics, "holdings_df": holdings_df, "risk_df": risk_df}
    return _render_template("insights.html", context)


def generate_intel_commentary(metrics: dict, holdings_df=None) -> str:
    context = {"metrics": metrics, "holdings_df": holdings_df}
    return _render_template("commentary.html", context)
