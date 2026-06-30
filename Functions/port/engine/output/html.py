"""
HTML report generation: assembles per-tab content into the base template.
"""

from datetime import datetime
import html
import os
import re
from jinja2 import Template

from config import (
    DEFAULT_CAPITAL,
    ENABLED_MODULES,
    PORT_INTEL_REPORT_PROMPT,
    PORT_INTEL_SUMMARY_PROMPT,
    REPORT_LOGO_SRC,
    PRIMARY_TEXT,
    HEADING_TEXT,
    HEADING_TEXT_H2,
    HEADING_TEXT_H3,
    ACCENT_THEME,
    TEXT_PRIMARY,
    TEXT_MUTED,
    SUCCESS_INDICATOR,
    DANGER_INDICATOR,
    SUCCESS_BG,
    SUCCESS_TEXT,
    DANGER_BG,
    DANGER_TEXT,
    POSITIVE_RETURN_CARD,
    NEGATIVE_RETURN_CARD,
    NEUTRAL_BG,
    NEUTRAL_TEXT,
    NEUTRAL_GRAY,
    BG_MAIN,
    BORDER_THEME,
    FONT_PRIMARY,
    FONT_SECONDARY,
    LIGHT_ELEMENT,
    TEXT_ON_DARK,
    WHITE_ELEMENT,
    TEXT_ON_YELLOW,
    TEXT_TAB_HOVER,
    TEXT_ERROR,
    TEXT_MARKER_DARK,
    TEXT_LABEL_GAUGE,
    EFFICIENCY_LABEL_FONT,
    BG_ROW_HEADER,
    BG_ROW_HEADER_ALT,
    BG_ROW_ALT,
    BG_ROW_ALT_ALT,
    BG_ROW_HOVER,
    BG_ROW_HIGHLIGHT,
    BG_CODE,
    BG_PANEL,
    BG_CHART_HEADER,
    BG_TICKER_PILL,
    BG_CHART,
    BG_TAB_INACTIVE,
    BG_TAB_HOVER,
    TAB_ACTIVE,
    BG_ACTIVE_YELLOW,
    BG_OPT_CARD,
    BG_INFO_BOX,
    BG_SHOCK_KNOWLEDGE,
    BG_BUTTON_PRIMARY,
    BG_BUTTON_PRIMARY_HOVER,
    BG_BUTTON_SECONDARY,
    BG_BUTTON_SECONDARY_HOVER,
    BG_BUTTON_DANGER,
    BG_BUTTON_DANGER_HOVER,
    BG_BUTTON_NEUTRAL,
    BG_BUTTON_NEUTRAL_HOVER,
    BORDER_LIGHT,
    BORDER_MEDIUM,
    BORDER_DIVIDER,
    BORDER_PANEL,
    BORDER_CHART_HEADER,
    BORDER_INFO,
    SHADOW_SUBTLE,
    SHADOW_MEDIUM,
    SHADOW_STRONG,
    ACCENT_THEME_HOVER,
    SUCCESS_DARK,
    SUCCESS_SUBTLE,
    DANGER_DARK,
    DANGER_SUBTLE,
    WARNING_ACCENT,
    BEST_MATCH_ACCENT,
    ERR_DARK,
    GAUGE_TRACK_BG,
    GAUGE_ZERO_LINE,
    GAUGE_MARKER_SHADOW,
    GAUGE_TRACK_SHADOW,
    GAUGE_TRACK_WIDE_SHADOW,
    CHART_TEXT,
    CHART_AREA_TOP,
    CHART_AREA_BOTTOM,
    CHART_AREA_LINE,
    CHART_GRID,
    DD_RISK_BAR_LOW,
    DD_RISK_BAR_MEDIUM,
    DD_RISK_BAR_HIGH,
    DD_RISK_BAR_BORDER,
    DD_RISK_MARKER,
    DD_RISK_LABEL,
    CORR_PERCENTILE_20,
    CORR_PERCENTILE_40,
    CORR_PERCENTILE_60,
    CORR_PERCENTILE_80,
    CORR_PERCENTILE_100,
    CORR_PERCENTILE_MARKER,
    CORR_PERCENTILE_BORDER,
    TERM_CARD_BORDER,
    TERM_CARD_BAR,
    MC_CARD_GREEN_BG,
    MC_CARD_GREEN_BORDER,
    MC_CARD_RED_BG,
    MC_CARD_RED_BORDER,
    MC_CARD_ORANGE_BG,
    MC_CARD_ORANGE_BORDER,
    MC_CARD_GRAY_BG,
    MC_CARD_GRAY_BORDER,
    STABILITY_MEDIUM,
    ALERT_CAUTION_BG,
    PILL_POSITIVE_TEXT,
    PILL_NEGATIVE_BG,
    PILL_NEGATIVE_TEXT,
    PILL_NEUTRAL_BG,
    PILL_NEUTRAL_TEXT,
)

from Functions.crypt import decrypt_string
from Functions.genAI.ai_prompt import get_gen_ai_response


def _get_neutral_gradients():
    try:
        from config import NEUTRAL_GRADIENT_1, NEUTRAL_GRADIENT_2, NEUTRAL_GRADIENT_3
        return NEUTRAL_GRADIENT_1, NEUTRAL_GRADIENT_2, NEUTRAL_GRADIENT_3
    except ImportError:
        return NEUTRAL_GRAY, NEUTRAL_GRAY, NEUTRAL_GRAY


def _md_to_html(text):
    if not text:
        return ""
    text = html.escape(text)
    text = re.sub(r'^### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    lines = text.split('\n')
    in_list = False
    new_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith('- ') or stripped.startswith('* '):
            content = stripped[2:]
            if not in_list:
                new_lines.append('<ul>')
                in_list = True
            new_lines.append(f'<li>{content}</li>')
        else:
            if in_list and line.strip():
                new_lines.append('</ul>')
                in_list = False
            new_lines.append(line)
    if in_list:
        new_lines.append('</ul>')
    text = '\n'.join(new_lines)
    parts = text.split('\n\n')
    result = ""
    for part in parts:
        part = part.strip()
        if part:
            part = part.replace('\n', '<br>')
            result += f'<p style="margin:0 0 0.8em 0;line-height:1.6;">{part}</p>'
    return result


def _strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def generate_portfolio_ai_commentary(metrics, charts, title, start, **kwargs):
    holdings_df = kwargs.get('holdings_df')
    returns_series = kwargs.get('returns_series')
    benchmark_ticker = kwargs.get('benchmark_ticker')
    price_data = kwargs.get('price_data')

    parts = []

    if ENABLED_MODULES.get("overview", True):
        from engine.modules.intel.commentary import generate_overview_commentary
        overview_html = generate_overview_commentary(metrics, holdings_df)
        parts.append(_strip_html(overview_html))

    if ENABLED_MODULES.get("holdings", True) and holdings_df is not None and not holdings_df.empty:
        from engine.modules.intel.commentary import generate_holdings_commentary
        holdings_html = generate_holdings_commentary(holdings_df)
        parts.append(_strip_html(holdings_html))

    if ENABLED_MODULES.get("efficiency", True) and returns_series is not None:
        benchmark_returns = None
        if price_data is not None and benchmark_ticker:
            benchmark_returns = price_data[benchmark_ticker].pct_change().dropna()
        from engine.modules.intel.commentary import generate_efficiency_commentary
        efficiency_html = generate_efficiency_commentary(
            returns_series, benchmark_returns, holdings_df, price_data
        )
        parts.append(_strip_html(efficiency_html))

    return "\n\n".join(parts) if parts else "No commentary available."


def generate_html_report(metrics, charts, title, start, **kwargs):
    transactions_df = kwargs.get('transactions_df')
    include_yield = kwargs.get('include_yield', True)
    trades_table = kwargs.get('trades_table', '')
    holdings_df = kwargs.get('holdings_df')
    position_values = kwargs.get('position_values')
    price_data = kwargs.get('price_data')
    risk_df = kwargs.get('risk_df')
    sector_industry_df = kwargs.get('sector_industry_df')
    portfolio_df = kwargs.get('portfolio_df')
    returns_series = kwargs.get('returns_series')
    benchmark_ticker = kwargs.get('benchmark_ticker')
    config = kwargs.get('config', {})

    # Generate intel commentary first (used by both intel tab and overview summary)
    current_commentary = ""
    intel_commentary_text = ""
    if ENABLED_MODULES.get("intel", True):
        current_commentary = generate_portfolio_ai_commentary(
            metrics,
            charts,
            title,
            start,
            holdings_df=holdings_df,
            returns_series=returns_series,
            benchmark_ticker=benchmark_ticker,
            price_data=price_data,
        )
        decrypted_prompt = decrypt_string(PORT_INTEL_REPORT_PROMPT)
        current_date = datetime.now().strftime("%b %d, %Y")
        decrypted_prompt = decrypted_prompt.replace("{current_date}", current_date)
        combined_prompt = f"{decrypted_prompt}\n\n{current_commentary}" if decrypted_prompt else current_commentary
        intel_commentary_text = get_gen_ai_response(prompt=combined_prompt)
        if not intel_commentary_text or intel_commentary_text.startswith("Error generating content") or intel_commentary_text.startswith("Daily AI prompt limit"):
            intel_commentary_text = ""

    # Generate overview AI interpretation from intel commentary text
    overview_ai_interpretation = ""
    if intel_commentary_text:
        try:
            decrypted_summary_prompt = decrypt_string(PORT_INTEL_SUMMARY_PROMPT)
            current_date = datetime.now().strftime("%b %d, %Y")
            decrypted_summary_prompt = decrypted_summary_prompt.replace("{current_date}", current_date)
            combined_summary = f"{decrypted_summary_prompt}\n\n{intel_commentary_text}" if decrypted_summary_prompt else intel_commentary_text
            overview_ai_interpretation = get_gen_ai_response(prompt=combined_summary)
            if not overview_ai_interpretation or overview_ai_interpretation.startswith("Error generating content") or overview_ai_interpretation.startswith("Daily AI prompt limit"):
                overview_ai_interpretation = ""
        except Exception:
            overview_ai_interpretation = ""

    tabs_content = ""

    # Overview
    if ENABLED_MODULES.get("overview", True):
        from engine.modules.overview.renderer import render_overview_tab
        tabs_content += render_overview_tab(
            metrics=metrics,
            charts=charts,
            holdings_df=holdings_df,
            inception_date=start,
            include_yield=include_yield,
            overview_ai_interpretation=overview_ai_interpretation,
        )
    else:
        tabs_content += '<div id="Overview" class="tab-content"></div>'


    # Portfolio (with sub-tabs)
    sub_tab_names = []
    if ENABLED_MODULES.get("holdings", True):
        sub_tab_names.append("holdings")
    if ENABLED_MODULES.get("breakdown", True):
        sub_tab_names.append("breakdown")
    if ENABLED_MODULES.get("optimisation", True):
        sub_tab_names.append("optimisation")

    if ENABLED_MODULES.get("portfolio", True) and sub_tab_names:
        from engine.modules.holdings.renderer import render_holdings_tab
        from engine.modules.breakdown.renderer import render_breakdown_tab
        from engine.modules.optimisation.renderer import render_optimisation_tab
        tabs_content += '<div id="Portfolio" class="tab-content">'
        tabs_content += '<div class="sub-tab-nav">'
        for sub in sub_tab_names:
            active_class = ' active' if sub == 'holdings' else ''
            tabs_content += f'<button class="sub-tab-button{active_class}" onclick="openSubTab(event, \'{sub.capitalize()}\')">{sub.capitalize()}</button>'
        tabs_content += '</div>'

        for sub in sub_tab_names:
            active_class = ' active' if sub == 'holdings' else ''
            tabs_content += f'<div id="{sub.capitalize()}" class="sub-tab-content{active_class}">'
            if sub == "holdings":
                if risk_df is not None and not risk_df.empty:
                    tabs_content += render_holdings_tab(
                        risk_contrib=risk_df,
                        sector_industry_df=sector_industry_df,
                        price_data=price_data,
                        portfolio_df=portfolio_df,
                        metrics=metrics,
                        charts=charts,
                    )
                else:
                    tabs_content += '<p>No holdings data available.</p>'
            elif sub == "breakdown":
                if risk_df is not None and not risk_df.empty:
                    tabs_content += render_breakdown_tab(
                        risk_contrib=risk_df,
                        sector_industry_df=sector_industry_df,
                        price_data=price_data,
                        holdings_df=holdings_df,
                        position_values=position_values,
                        include_yield=include_yield,
                        charts=charts,
                    )
                else:
                    tabs_content += '<p>No breakdown data available.</p>'
            elif sub == "optimisation":
                benchmark_series = None
                if price_data is not None and benchmark_ticker:
                    benchmark_series = price_data[benchmark_ticker]
                current_weights_dict = None
                if holdings_df is not None and 'Weight' in holdings_df.columns:
                    current_weights_dict = holdings_df['Weight'].to_dict()
                tabs_content += render_optimisation_tab(
                    prices_df=price_data,
                    portfolio_df=portfolio_df,
                    benchmark_series=benchmark_series,
                    sector_industry_df=sector_industry_df,
                    config=config,
                    current_weights_dict=current_weights_dict,
                    actual_portfolio_metrics=metrics.get('total'),
                    total_portfolio_value=config.get('DEFAULT_CAPITAL', DEFAULT_CAPITAL),
                )
            tabs_content += '</div>'

        tabs_content += '</div>'
    elif ENABLED_MODULES.get("portfolio", True):
        tabs_content += '<div id="Portfolio" class="tab-content"></div>'

    # Stats (with sub-tabs)
    stats_sub_tab_names = []
    if ENABLED_MODULES.get("correlation", True):
        stats_sub_tab_names.append("correlation")
    if ENABLED_MODULES.get("monte_carlo", True):
        stats_sub_tab_names.append("monte_carlo")
    if ENABLED_MODULES.get("risks", True):
        stats_sub_tab_names.append("risks")
    if ENABLED_MODULES.get("efficiency", True):
        stats_sub_tab_names.append("efficiency")

    if ENABLED_MODULES.get("stats", True) and stats_sub_tab_names:
        from engine.modules.correlation.renderer import render_correlation_tab
        from engine.modules.monte_carlo.renderer import render_monte_carlo_tab
        from engine.modules.risks.renderer import render_risks_tab
        from engine.modules.efficiency.renderer import render_efficiency_tab
        
        tabs_content += '<div id="Stats" class="tab-content">'
        tabs_content += '<div class="sub-tab-nav">'
        for sub in stats_sub_tab_names:
            active_class = ' active' if sub == 'correlation' else ''
            display_name = "Monte Carlo" if sub == "monte_carlo" else sub.capitalize()
            tabs_content += f'<button class="sub-tab-button{active_class}" onclick="openSubTab(event, \'{sub.capitalize()}\')">{display_name}</button>'
        tabs_content += '</div>'

        for sub in stats_sub_tab_names:
            active_class = ' active' if sub == 'correlation' else ''
            tabs_content += f'<div id="{sub.capitalize()}" class="sub-tab-content{active_class}">'
            if sub == "correlation":
                if ENABLED_MODULES.get("correlation", True):
                    tabs_content += render_correlation_tab(charts=charts)
                else:
                    tabs_content += '<p>No correlation data available.</p>'
                tabs_content += '</div>'
            elif sub == "monte_carlo":
                if ENABLED_MODULES.get("monte_carlo", True):
                    tabs_content += render_monte_carlo_tab(charts=charts, metrics=metrics, holdings_df=holdings_df)
                else:
                    tabs_content += '<p>No Monte Carlo data available.</p>'
                tabs_content += '</div>'
            elif sub == "risks":
                if ENABLED_MODULES.get("risks", True):
                    tabs_content += render_risks_tab(
                        charts=charts,
                        metrics=metrics,
                        holdings_df=holdings_df,
                        position_values=position_values,
                        shock_level=0.20,
                    )
                else:
                    tabs_content += '<p>No risks data available.</p>'
                tabs_content += '</div>'
            elif sub == "efficiency":
                if ENABLED_MODULES.get("efficiency", True) and returns_series is not None:
                    benchmark_returns = None
                    if price_data is not None and benchmark_ticker:
                        benchmark_returns = price_data[benchmark_ticker].pct_change().dropna()
                    tabs_content += render_efficiency_tab(
                        returns_series=returns_series,
                        benchmark_returns=benchmark_returns,
                        holdings_df=holdings_df,
                        prices=price_data,
                    )
                else:
                    tabs_content += '<p>No efficiency data available.</p>'
                tabs_content += '</div>'

        tabs_content += '</div>'
    elif ENABLED_MODULES.get("stats", True):
        tabs_content += '<div id="Stats" class="tab-content"></div>'

    # History
    if ENABLED_MODULES.get("history", True) and trades_table and transactions_df is not None and not transactions_df.empty:
        from engine.modules.history.renderer import render_trades_tab
        tabs_content += render_trades_tab(
            transactions_df=transactions_df,
            sector_industry_df=sector_industry_df,
            price_data=price_data,
            holdings_df=holdings_df,
            charts=charts,
        )

    # Intel
    if ENABLED_MODULES.get("intel", True):
        from engine.modules.intel.renderer import render_intel_tab
        from engine.modules.intel.commentary import _build_overview_underperforming_table

        formatted_commentary = _md_to_html(intel_commentary_text)

        attention_table = ""
        if ENABLED_MODULES.get("overview", True) and holdings_df is not None:
            attention_table = _build_overview_underperforming_table(holdings_df)

        action_alerts_table = ""
        if ENABLED_MODULES.get("holdings", True) and holdings_df is not None:
            from engine.modules.intel.commentary import _build_alert_table
            action_alerts_table = _build_alert_table(holdings_df)

        securities_attention_table = ""
        if ENABLED_MODULES.get("efficiency", True):
            from engine.modules.intel.commentary import _build_securities_attention_table
            securities_attention_table = _build_securities_attention_table(
                holdings_df, price_data, returns_series, risk_free_rate=0.02
            )

        top_performers_table = ""
        lagging_positions_table = ""
        if ENABLED_MODULES.get("holdings", True) and holdings_df is not None:
            from engine.modules.intel.commentary import _build_top_performers_table, _build_holdings_underperforming_table
            top_performers_table = _build_top_performers_table(holdings_df)
            lagging_positions_table = _build_holdings_underperforming_table(holdings_df)

        tabs_content += render_intel_tab(
            metrics=metrics,
            charts=charts,
            holdings_df=holdings_df,
            intel_commentary=formatted_commentary,
            attention_table=attention_table,
            action_alerts_table=action_alerts_table,
            securities_attention_table=securities_attention_table,
            top_performers_table=top_performers_table,
            lagging_positions_table=lagging_positions_table,
            overview_ai_interpretation=overview_ai_interpretation,
        )
    else:
        tabs_content += '<div id="Intel" class="tab-content"></div>'

    # Base template
    template_path = os.path.join(os.path.dirname(__file__), "templates", "base.html")
    with open(template_path, "r", encoding="utf-8") as f:
        base_template = f.read()

    NEUTRAL_GRADIENT_1, NEUTRAL_GRADIENT_2, NEUTRAL_GRADIENT_3 = _get_neutral_gradients()

    template = Template(base_template)
    rendered = template.render(
        report_title=title,
        REPORT_LOGO_SRC=REPORT_LOGO_SRC,
        trades_table=trades_table,
        PRIMARY_TEXT=PRIMARY_TEXT,
        HEADING_TEXT=HEADING_TEXT,
        HEADING_TEXT_H2=HEADING_TEXT_H2,
        HEADING_TEXT_H3=HEADING_TEXT_H3,
        ACCENT_THEME=ACCENT_THEME,
        TEXT_PRIMARY=TEXT_PRIMARY,
        TEXT_MUTED=TEXT_MUTED,
        POSITIVE_RETURN_CARD=POSITIVE_RETURN_CARD,
        NEGATIVE_RETURN_CARD=NEGATIVE_RETURN_CARD,
        NEUTRAL_BG=NEUTRAL_BG,
        NEUTRAL_TEXT=NEUTRAL_TEXT,
        NEUTRAL_GRAY=NEUTRAL_GRAY,
        BG_MAIN=BG_MAIN,
        BORDER_THEME=BORDER_THEME,
        FONT_PRIMARY=FONT_PRIMARY,
        FONT_SECONDARY=FONT_SECONDARY,
        LIGHT_ELEMENT=LIGHT_ELEMENT,
        TEXT_ON_DARK=TEXT_ON_DARK,
        WHITE_ELEMENT=WHITE_ELEMENT,
        TEXT_ON_YELLOW=TEXT_ON_YELLOW,
        TEXT_TAB_HOVER=TEXT_TAB_HOVER,
        TEXT_ERROR=TEXT_ERROR,
        TEXT_MARKER_DARK=TEXT_MARKER_DARK,
        TEXT_LABEL_GAUGE=TEXT_LABEL_GAUGE,
        EFFICIENCY_LABEL_FONT=EFFICIENCY_LABEL_FONT,
        BG_ROW_HEADER=BG_ROW_HEADER,
        BG_ROW_HEADER_ALT=BG_ROW_HEADER_ALT,
        BG_ROW_ALT=BG_ROW_ALT,
        BG_ROW_ALT_ALT=BG_ROW_ALT_ALT,
        BG_ROW_HOVER=BG_ROW_HOVER,
        BG_ROW_HIGHLIGHT=BG_ROW_HIGHLIGHT,
        BG_CODE=BG_CODE,
        BG_PANEL=BG_PANEL,
        BG_CHART_HEADER=BG_CHART_HEADER,
        BG_TICKER_PILL=BG_TICKER_PILL,
        BG_CHART=BG_CHART,
        BG_TAB_INACTIVE=BG_TAB_INACTIVE,
        BG_TAB_HOVER=BG_TAB_HOVER,
        TAB_ACTIVE=TAB_ACTIVE,
        BG_ACTIVE_YELLOW=BG_ACTIVE_YELLOW,
        BG_OPT_CARD=BG_OPT_CARD,
        BG_INFO_BOX=BG_INFO_BOX,
        BG_SHOCK_KNOWLEDGE=BG_SHOCK_KNOWLEDGE,
        BG_BUTTON_PRIMARY=BG_BUTTON_PRIMARY,
        BG_BUTTON_PRIMARY_HOVER=BG_BUTTON_PRIMARY_HOVER,
        BG_BUTTON_SECONDARY=BG_BUTTON_SECONDARY,
        BG_BUTTON_SECONDARY_HOVER=BG_BUTTON_SECONDARY_HOVER,
        BG_BUTTON_DANGER=BG_BUTTON_DANGER,
        BG_BUTTON_DANGER_HOVER=BG_BUTTON_DANGER_HOVER,
        BG_BUTTON_NEUTRAL=BG_BUTTON_NEUTRAL,
        BG_BUTTON_NEUTRAL_HOVER=BG_BUTTON_NEUTRAL_HOVER,
        BORDER_LIGHT=BORDER_LIGHT,
        BORDER_MEDIUM=BORDER_MEDIUM,
        BORDER_DIVIDER=BORDER_DIVIDER,
        BORDER_PANEL=BORDER_PANEL,
        BORDER_CHART_HEADER=BORDER_CHART_HEADER,
        BORDER_INFO=BORDER_INFO,
        SHADOW_SUBTLE=SHADOW_SUBTLE,
        SHADOW_MEDIUM=SHADOW_MEDIUM,
        SHADOW_STRONG=SHADOW_STRONG,
        ACCENT_THEME_HOVER=ACCENT_THEME_HOVER,
        SUCCESS_DARK=SUCCESS_DARK,
        SUCCESS_SUBTLE=SUCCESS_SUBTLE,
        DANGER_DARK=DANGER_DARK,
        DANGER_SUBTLE=DANGER_SUBTLE,
        SUCCESS_BG=SUCCESS_BG,
        SUCCESS_TEXT=SUCCESS_TEXT,
        DANGER_BG=DANGER_BG,
        DANGER_TEXT=DANGER_TEXT,
        WARNING_ACCENT=WARNING_ACCENT,
        BEST_MATCH_ACCENT=BEST_MATCH_ACCENT,
        ERR_DARK=ERR_DARK,
        GAUGE_TRACK_BG=GAUGE_TRACK_BG,
        GAUGE_ZERO_LINE=GAUGE_ZERO_LINE,
        GAUGE_MARKER_SHADOW=GAUGE_MARKER_SHADOW,
        GAUGE_TRACK_SHADOW=GAUGE_TRACK_SHADOW,
        GAUGE_TRACK_WIDE_SHADOW=GAUGE_TRACK_WIDE_SHADOW,
        CHART_TEXT=CHART_TEXT,
        CHART_AREA_TOP=CHART_AREA_TOP,
        CHART_AREA_BOTTOM=CHART_AREA_BOTTOM,
        CHART_AREA_LINE=CHART_AREA_LINE,
        CHART_GRID=CHART_GRID,
        DD_RISK_BAR_LOW=DD_RISK_BAR_LOW,
        DD_RISK_BAR_MEDIUM=DD_RISK_BAR_MEDIUM,
        DD_RISK_BAR_HIGH=DD_RISK_BAR_HIGH,
        DD_RISK_BAR_BORDER=DD_RISK_BAR_BORDER,
        DD_RISK_MARKER=DD_RISK_MARKER,
        DD_RISK_LABEL=DD_RISK_LABEL,
        CORR_PERCENTILE_20=CORR_PERCENTILE_20,
        CORR_PERCENTILE_40=CORR_PERCENTILE_40,
        CORR_PERCENTILE_60=CORR_PERCENTILE_60,
        CORR_PERCENTILE_80=CORR_PERCENTILE_80,
        CORR_PERCENTILE_100=CORR_PERCENTILE_100,
        CORR_PERCENTILE_MARKER=CORR_PERCENTILE_MARKER,
        CORR_PERCENTILE_BORDER=CORR_PERCENTILE_BORDER,
        TERM_CARD_BORDER=TERM_CARD_BORDER,
        TERM_CARD_BAR=TERM_CARD_BAR,
        MC_CARD_GREEN_BG=MC_CARD_GREEN_BG,
        MC_CARD_GREEN_BORDER=MC_CARD_GREEN_BORDER,
        MC_CARD_RED_BG=MC_CARD_RED_BG,
        MC_CARD_RED_BORDER=MC_CARD_RED_BORDER,
        MC_CARD_ORANGE_BG=MC_CARD_ORANGE_BG,
        MC_CARD_ORANGE_BORDER=MC_CARD_ORANGE_BORDER,
        MC_CARD_GRAY_BG=MC_CARD_GRAY_BG,
        MC_CARD_GRAY_BORDER=MC_CARD_GRAY_BORDER,
        SUCCESS_INDICATOR=SUCCESS_INDICATOR,
        DANGER_INDICATOR=DANGER_INDICATOR,
        STABILITY_MEDIUM=STABILITY_MEDIUM,
        ALERT_CAUTION_BG=ALERT_CAUTION_BG,
        PILL_POSITIVE_TEXT=PILL_POSITIVE_TEXT,
        PILL_NEGATIVE_BG=PILL_NEGATIVE_BG,
        PILL_NEGATIVE_TEXT=PILL_NEGATIVE_TEXT,
        PILL_NEUTRAL_BG=PILL_NEUTRAL_BG,
        PILL_NEUTRAL_TEXT=PILL_NEUTRAL_TEXT,
        NEUTRAL_GRADIENT_1=NEUTRAL_GRADIENT_1,
        NEUTRAL_GRADIENT_2=NEUTRAL_GRADIENT_2,
        NEUTRAL_GRADIENT_3=NEUTRAL_GRADIENT_3,
        ENABLED_MODULES=ENABLED_MODULES,
    )

    html = rendered.replace("<!-- TABS_CONTENT_PLACEHOLDER -->", tabs_content)

    from engine.modules.history.renderer import minify_html
    minified_html = minify_html(html)

    return minified_html
