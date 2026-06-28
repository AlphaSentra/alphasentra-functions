import os
import pandas as pd
import numpy as np
import json
from jinja2 import Template
from config import (
    CHART_TRANSPARENT, CLUSTER_PALETTE, PIE_SLICE_BORDER,
    TEXT_PRIMARY, TEXT_HEADING_H2, FONT_PRIMARY,
)


def generate_sector_industry_analysis(risk_contrib, sector_industry_df, include_yield=True):
    """
    Analyzes portfolio weighting per sector and industry.
    Returns dict with 'table_html' and 'pie_chart_html'.
    """
    analysis_df = risk_contrib[['Weight']].merge(sector_industry_df, left_index=True, right_index=True, how='left')
    analysis_df['sector'] = analysis_df['sector'].fillna('Others')
    analysis_df['industry'] = analysis_df['industry'].fillna('Others')

    sector_weights = analysis_df.groupby('sector')['Weight'].sum().sort_values(ascending=False)
    industry_weights = analysis_df.groupby(['sector', 'industry'])['Weight'].sum().reset_index()
    industry_weights = industry_weights.sort_values(['sector', 'Weight'], ascending=[True, False])

    yield_header = '<th class="table-col-yield">Avg. Div Yield (%)</th>' if include_yield else ""
    table_html = f"""
    <table class="sector-weight-table">
        <thead>
            <tr>
                <th class="table-col-sector">Sector / Industry</th>
                <th class="table-col-weight">Weight</th>
                {yield_header}
            </tr>
        </thead>
        <tbody>
    """
    for sector, s_weight in sector_weights.items():
        # Calculate weighted average dividend yield for the sector
        sector_data = analysis_df[analysis_df['sector'] == sector]

        table_html += f"""
            <tr class="sector-row">
                <td>{sector if sector != "Unknown" else "Others"}</td>
                <td class="u-align-right">{s_weight*100:.2f}%</td>
        """
        if include_yield:
            # Re-normalize weights within the sector for yield calculation
            sector_yield = (sector_data['dividendYield'] * sector_data['Weight']).sum() / s_weight if s_weight > 0 else 0
            table_html += f"<td class='u-align-right'>{sector_yield*100:.2f}%</td>"

        table_html += "</tr>"

        s_industries = industry_weights[industry_weights['sector'] == sector]
        for _, row in s_industries.iterrows():
            table_html += f"""
                <tr class="industry-row">
                    <td>&bull; {row['industry'] if row['industry'] != "Unknown" else "Others"}</td>
                    <td class="u-align-right">{row['Weight']*100:.2f}%</td>
            """
            if include_yield:
                # Calculate weighted average dividend yield for the industry
                industry_data = analysis_df[(analysis_df['sector'] == sector) & (analysis_df['industry'] == row['industry'])]
                industry_yield = (industry_data['dividendYield'] * industry_data['Weight']).sum() / row['Weight'] if row['Weight'] > 0 else 0
                table_html += f"<td class='u-align-right'>{industry_yield*100:.2f}%</td>"

            table_html += "</tr>"
    table_html += "</tbody></table>"

    labels = sector_weights.index.tolist()
    values = sector_weights.values.tolist()

    import plotly.graph_objects as go

    # ============================================================
    # Sector & Industry Allocation pie chart
    # ============================================================
    pie = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.4,
        sort=False,
        direction='clockwise',
        textinfo='label+percent',
        textposition='outside',
        textfont=dict(size=10, color=TEXT_PRIMARY),
        insidetextorientation='horizontal',
        marker=dict(
            colors=CLUSTER_PALETTE,
            line=dict(color=PIE_SLICE_BORDER, width=2)
        ),
        pull=[0.02] * len(labels),
        hovertemplate='%{label}<br>%{percent:.1%}<extra></extra>'
    )])

    pie.update_layout(
        showlegend=False,
        margin=dict(l=30, r=30, t=50, b=30),
        uniformtext_minsize=9,
        uniformtext_mode='hide',
        title=None,
        title_font=dict(size=14, color=TEXT_HEADING_H2, family=FONT_PRIMARY),
        plot_bgcolor=CHART_TRANSPARENT,
        paper_bgcolor=CHART_TRANSPARENT,
    )

    pie.update_traces(
        textfont=dict(size=10),
        rotation=90
    )

    pie_chart_html = pie.to_html(full_html=False, include_plotlyjs=False)

    return {'table_html': table_html, 'pie_chart_html': pie_chart_html}


def generate_sector_performance_table(risk_contrib, sector_industry_df, price_data):
    """
    Generates a table showing securities per sector with 3M and 1M performance.

    Args:
        risk_contrib (pd.DataFrame): DataFrame with "Weight" for each ticker.
        sector_industry_df (pd.DataFrame): DataFrame with 'sector' and 'industry' for each ticker.
        price_data (pd.DataFrame): DataFrame with historical prices.

    Returns:
        str: HTML string for the performance table.
    """
    # Merge weights with sector data
    analysis_df = risk_contrib[['Weight']].merge(sector_industry_df, left_index=True, right_index=True, how='left')
    analysis_df['sector'] = analysis_df['sector'].fillna('Others')
    if 'name' not in analysis_df.columns:
        analysis_df['name'] = analysis_df.index
    else:
        analysis_df['name'] = analysis_df['name'].fillna(analysis_df.index.to_series())

    # Calculate 3M, 1M, and 1Y returns for each ticker
    end_date = price_data.index[-1]
    start_3m = end_date - pd.DateOffset(months=3)
    start_1m = end_date - pd.DateOffset(months=1)
    start_1y = end_date - pd.DateOffset(years=1)

    returns_3m = {}
    returns_1m = {}
    returns_1y = {}

    for ticker in analysis_df.index:
        if ticker in price_data.columns:
            prices = price_data[ticker].dropna()
            if len(prices) > 1:
                # 3M
                prices_3m = prices[prices.index <= end_date]
                prices_3m = prices_3m[prices_3m.index >= start_3m]
                if len(prices_3m) > 1:
                    ret_3m = (prices_3m.iloc[-1] / prices_3m.iloc[0] - 1) * 100
                    returns_3m[ticker] = ret_3m
                else:
                    returns_3m[ticker] = np.nan

                # 1M
                prices_1m = prices[prices.index <= end_date]
                prices_1m = prices_1m[prices_1m.index >= start_1m]
                if len(prices_1m) > 1:
                    ret_1m = (prices_1m.iloc[-1] / prices_1m.iloc[0] - 1) * 100
                    returns_1m[ticker] = ret_1m
                else:
                    returns_1m[ticker] = np.nan

                # 1Y
                prices_1y = prices[prices.index <= end_date]
                prices_1y = prices_1y[prices_1y.index >= start_1y]
                if len(prices_1y) > 1:
                    ret_1y = (prices_1y.iloc[-1] / prices_1y.iloc[0] - 1) * 100
                    returns_1y[ticker] = ret_1y
                else:
                    returns_1y[ticker] = np.nan
            else:
                returns_3m[ticker] = np.nan
                returns_1m[ticker] = np.nan
                returns_1y[ticker] = np.nan
        else:
            returns_3m[ticker] = np.nan
            returns_1m[ticker] = np.nan
            returns_1y[ticker] = np.nan

    analysis_df['3M Perf (%)'] = analysis_df.index.map(returns_3m)
    analysis_df['1M Perf (%)'] = analysis_df.index.map(returns_1m)
    analysis_df['1Y Perf (%)'] = analysis_df.index.map(returns_1y)

    # Group by sector and sort sectors by total weight
    sector_weights = analysis_df.groupby('sector')['Weight'].sum().sort_values(ascending=False)

    # Generate HTML table with collapsible sectors
    table_html = """
    <script>
    function toggleSector(sectorId) {
        var tbody = document.getElementById(sectorId + '-securities');
        var arrow = document.getElementById('arrow-' + sectorId);
        var isHidden = getComputedStyle(tbody).display === 'none';
        tbody.style.display = isHidden ? 'table-row-group' : 'none';
        arrow.innerHTML = isHidden ? '▼' : '▶';
    }
    function toggleAll(expand) {
        var bodies = document.querySelectorAll('.sector-securities');
        var arrows = document.querySelectorAll('[id^="arrow-"]');
        bodies.forEach(function(tbody) {
            tbody.style.display = expand ? 'table-row-group' : 'none';
        });
        arrows.forEach(function(arrow) {
            arrow.innerHTML = expand ? '▼' : '▶';
        });
    }
    </script>
    <div class="m-b-5">
        <button onclick="toggleAll(true)" class="action-button m-r-10">Expand All</button>
        <button onclick="toggleAll(false)" class="action-button">Collapse All</button>
    </div>
    <table class="bloomberg-table">
        <thead>
            <tr>
                <th>Sector</th>
                <th>Ticker</th>
                <th>Name</th>
                <th class="number-cell">Weight (%)</th>
                <th class="number-cell perf-cell">1Y Perf (%)</th>
                <th class="number-cell perf-cell">3M Perf (%)</th>
                <th class="number-cell perf-cell">1M Perf (%)</th>
            </tr>
        </thead>
    """

    for sector in sector_weights.index:
        sector_data = analysis_df[analysis_df['sector'] == sector].sort_values('Weight', ascending=False)
        total_weight = sector_data['Weight'].sum()
        sector_id = sector.replace(' ', '').replace('/', '').replace('&', '')

        # Calculate weighted averages for sector
        def weighted_avg(perf_col):
            valid_data = sector_data[pd.notna(sector_data[perf_col])]
            if valid_data.empty or total_weight == 0:
                return np.nan
            return (valid_data[perf_col] * valid_data['Weight']).sum() / total_weight

        sector_3m = weighted_avg('3M Perf (%)')
        sector_1m = weighted_avg('1M Perf (%)')
        sector_1y = weighted_avg('1Y Perf (%)')

        # Format performance with color
        def format_perf(value):
            if pd.isna(value):
                return '<span class="perf-pill perf-pill-na">N/A</span>'
            is_pos = value > 0
            css_class = 'perf-pill-pos' if is_pos else 'perf-pill-neg' if value < 0 else 'perf-pill-na'
            arrow = '▲' if is_pos else '▼' if value < 0 else ''
            return f'<span class="perf-pill {css_class}">{arrow} {value:.2f}%</span>'

        table_html += f"""
        <tbody>
            <tr onclick="toggleSector('{sector_id}')" class="sector-row">
                <td><span id="arrow-{sector_id}" class="sector-arrow">▶</span>{sector}</td>
                <td></td>
                <td></td>
                <td class="number-cell">{total_weight*100:.2f}%</td>
                <td class="number-cell perf-cell">{format_perf(sector_1y)}</td>
                <td class="number-cell perf-cell">{format_perf(sector_3m)}</td>
                <td class="number-cell perf-cell">{format_perf(sector_1m)}</td>
            </tr>
        </tbody>
        <tbody id="{sector_id}-securities" class="sector-securities display-none">
"""
        # Individual securities
        for idx, row in sector_data.iterrows():
            table_html += f"""
            <tr>
                <td></td>
                <td>{idx}</td>
                <td>{row['name'] if pd.notna(row['name']) else ''}</td>
                <td class="number-cell">{row['Weight']*100:.2f}%</td>
                <td class="number-cell perf-cell">{format_perf(row['1Y Perf (%)'])}</td>
                <td class="number-cell perf-cell">{format_perf(row['3M Perf (%)'])}</td>
                <td class="number-cell perf-cell">{format_perf(row['1M Perf (%)'])}</td>
            </tr>
"""
        table_html += "</tbody>"
    table_html += "</table>"

    return table_html


def render_breakdown_tab(risk_contrib, sector_industry_df, price_data, holdings_df, position_values, include_yield=True, charts=None) -> str:
    """
    Renders the Breakdown tab HTML block.
    """
    sector_analysis = generate_sector_industry_analysis(risk_contrib, sector_industry_df, include_yield)
    sector_perf_table = generate_sector_performance_table(risk_contrib, sector_industry_df, price_data)

    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    template = Template(template_src)
    return template.render(
        sector_analysis=sector_analysis,
        sector_perf_table=sector_perf_table,
        charts=charts or {}
    )


