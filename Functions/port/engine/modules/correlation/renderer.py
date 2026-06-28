"""
Correlation tab renderer: generates the Correlation tab HTML block.
"""

from jinja2 import Template
import os


def render_correlation_tab(charts: dict) -> str:
    """
    Renders the Correlation tab HTML block.

    Args:
        charts (dict): Dictionary of pre-rendered chart HTML strings.

    Returns:
        str: Rendered HTML string for the Correlation tab <div>.
    """
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    # The commentary is usually passed in via charts.correlation_commentary
    # but we can also generate it if needed. For now, we follow the pattern in html.py
    
    template = Template(template_src)
    return template.render(
        charts=charts
    )
