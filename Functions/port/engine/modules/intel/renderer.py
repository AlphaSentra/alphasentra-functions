"""
Intel tab renderer: generates the Intel tab HTML block.
"""

from jinja2 import Template
import os
from datetime import datetime, timezone


def render_intel_tab(metrics, charts, holdings_df=None, intel_commentary="", attention_table="", action_alerts_table="", securities_attention_table="", top_performers_table="", lagging_positions_table="", overview_ai_interpretation="", **kwargs) -> str:
    """
    Renders the Intel tab HTML block.
    """
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    template = Template(template_src)
    now_gmt = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M GMT")
    return template.render(
        metrics=metrics,
        charts=charts,
        holdings_df=holdings_df,
        intel_commentary=intel_commentary,
        attention_table=attention_table,
        action_alerts_table=action_alerts_table,
        securities_attention_table=securities_attention_table,
        top_performers_table=top_performers_table,
        lagging_positions_table=lagging_positions_table,
        overview_ai_interpretation=overview_ai_interpretation,
        now_gmt=now_gmt,
    )
