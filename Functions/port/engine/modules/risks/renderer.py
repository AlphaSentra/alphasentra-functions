"""
Risks tab renderer: generates the Risks tab HTML block.
"""

from jinja2 import Template
import os


def render_risks_tab(charts: dict, metrics: dict, holdings_df=None, position_values=None, shock_level=0.20) -> str:
    """
    Renders the Risks tab HTML block.

    Args:
        charts (dict): Dictionary of pre-rendered chart HTML strings.
        metrics (dict): Performance metrics dictionary.
        holdings_df (pd.DataFrame, optional): Current portfolio holdings.
        position_values (dict, optional): Current position values.
        shock_level (float): Shock level as a decimal (e.g. 0.20 for 20%).

    Returns:
        str: Rendered HTML string for the Risks tab <div>.
    """
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    shock_level_pct = int(shock_level * 100)

    template = Template(template_src)
    return template.render(
        charts=charts,
        metrics=metrics,
        shock_level_pct=shock_level_pct
    )
