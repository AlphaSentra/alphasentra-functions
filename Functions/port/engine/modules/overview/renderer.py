"""
Overview tab renderer: generates the Overview tab HTML block.
"""

from jinja2 import Template
import os
from config import (
    POSITIVE_RETURN_CARD,
    NEGATIVE_RETURN_CARD,
    BUTTON_TEXT,
    ZERO_RETURN_CELL_BG,
    ZERO_RETURN_CELL_TEXT,
    NONZERO_RETURN_CELL_TEXT,
    FONT_PRIMARY,
)



def render_overview_tab(metrics, charts, holdings_df=None, inception_date=None, include_yield=True, overview_ai_interpretation="") -> str:
    """
    Renders the Overview tab HTML block.
    """
    if inception_date is not None:
        inception_date = inception_date.strftime('%Y-%m-%d')

    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    template = Template(template_src)
    return template.render(
        charts=charts,
        metrics=metrics,
        inception_date=inception_date,
        include_yield=include_yield,
        overview_ai_interpretation=overview_ai_interpretation,
        POSITIVE_RETURN_CARD=POSITIVE_RETURN_CARD,
        NEGATIVE_RETURN_CARD=NEGATIVE_RETURN_CARD,
        BUTTON_TEXT=BUTTON_TEXT,
        ZERO_RETURN_CELL_BG=ZERO_RETURN_CELL_BG,
        ZERO_RETURN_CELL_TEXT=ZERO_RETURN_CELL_TEXT,
        NONZERO_RETURN_CELL_TEXT=NONZERO_RETURN_CELL_TEXT,
        FONT_PRIMARY=FONT_PRIMARY,
    )
