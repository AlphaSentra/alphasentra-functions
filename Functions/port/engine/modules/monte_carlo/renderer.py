"""
Monte Carlo tab renderer: generates the Monte Carlo tab HTML block.
"""

from jinja2 import Template
import os


def render_monte_carlo_tab(charts: dict, metrics: dict, holdings_df=None) -> str:
    """
    Renders the Monte Carlo tab HTML block.

    Args:
        charts (dict): Dictionary of pre-rendered chart HTML strings.
        metrics (dict): Performance metrics dictionary.
        holdings_df (pd.DataFrame, optional): Current portfolio holdings.

    Returns:
        str: Rendered HTML string for the Monte Carlo tab <div>.
    """
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    template = Template(template_src)
    return template.render(
        charts=charts
    )
