"""
Chart generation module: All Plotly visualizations for portfolio functions.
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from config import (
    BREAKDOWN_GRID_COLOR, BREAKDOWN_LINE_COLOR,
    BREAKDOWN_NEUTRAL_ORANGE, BREAKDOWN_POSITIVE_GREEN, BREAKDOWN_NEGATIVE_RED, BREAKDOWN_NEUTRAL_BLUE,
    NEUTRAL_GRAY, ZERO_RETURN_CELL_TEXT, POSITIVE_RETURN_CARD, NEGATIVE_RETURN_CARD, TEXT_MUTED, BORDER_MEDIUM,
    BG_ROW_HEADER_ALT, BORDER_THEME, BG_ROW_ALT_ALT, NEUTRAL_TEXT,
    BG_BUTTON_PRIMARY, BG_BUTTON_SECONDARY, TEXT_PRIMARY, BG_TAB_HOVER, BAR_VALUE_LABEL_TEXT,
    CHART_BENCHMARK_MARKER, CHART_TRANSPARENT, PRIMARY_TEXT, LIGHT_ELEMENT, EFFICIENCY_LABEL_FONT,
    TEXT_SECONDARY, BORDER_CHART_HEADER, FONT_PRIMARY, BG_CHART, CHART_GRID, METRIC_CARD_LABEL_TEXT,
    PIE_SLICE_BORDER,
)



def generate_zscore_scatter_plot(holdings_df, risk_contrib):
    """
    Generates a scatter plot of Z-Score vs Weight, with bubble size representing risk contribution.

    Args:
        holdings_df (pd.DataFrame): DataFrame with 'z_score' and 'Weight'.
        risk_contrib (pd.DataFrame): DataFrame with '% Risk Contribution'.

    Returns:
        str: HTML string representing the generated Plotly chart.
    """
    # Merge holdings with risk contribution to get the % Risk Contribution
    plot_df = holdings_df.merge(risk_contrib[['% Risk Contribution']], left_index=True, right_index=True, how='left')

    # Ensure % Risk Contribution is positive for bubble size (risk can't be negative in this context usually)
    plot_df['Abs Risk Contrib'] = plot_df['% Risk Contribution'].fillna(0).abs() * 100

    # Define color column based on Z-Score
    plot_df['Z-Score Sentiment'] = plot_df['z_score'].apply(lambda x: 'Positive Z-Score' if x > 0 else 'Negative Z-Score')

    fig = px.scatter(
        plot_df,
        x="z_score",
        y="Weight",
        size="Abs Risk Contrib",
        size_max=60,
        color="Z-Score Sentiment",
        color_discrete_map={
            'Positive Z-Score': POSITIVE_RETURN_CARD,
            'Negative Z-Score': NEGATIVE_RETURN_CARD
        },
        hover_name=plot_df.index,
        hover_data={
            "z_score": ":.2f",
            "Weight": ":.2%",
            "% Risk Contribution": ":.2%",
            "name": True
        },
        title="Portfolio Z-Score Analysis (Weight vs. Z-Score)",
        labels={
            "z_score": "Z-Score (1Y Historical)",
            "Weight": "Portfolio Weight",
            "type": "Component Type"
        },
        height=450
    )

    # Format Y axis as percentage
    fig.update_layout(yaxis_tickformat=".1%")

    fig.update_layout(
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        title_font=dict(color=TEXT_MUTED),
        font=dict(color=TEXT_PRIMARY),
        legend_font=dict(color=TEXT_MUTED),
        legend_title_font=dict(color=TEXT_MUTED),
        margin=dict(l=60, r=50, t=60, b=50),
        xaxis=dict(
            autorange=True,
            zeroline=True,
            showgrid=True,
            gridcolor=CHART_GRID,
            automargin=False,
            title_font=dict(color=TEXT_MUTED),
            tickfont=dict(color=TEXT_MUTED)
        ),
        yaxis=dict(
            autorange=True,
            showgrid=True,
            gridcolor=CHART_GRID,
            automargin=False,
            title_font=dict(color=TEXT_MUTED),
            tickfont=dict(color=TEXT_MUTED)
        )
    )

    # Add vertical lines at Z-Score = -2, 0, 2 for reference
    fig.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.add_vline(x=2, line_dash="dot", line_color=BREAKDOWN_NEGATIVE_RED, opacity=0.3)
    fig.add_vline(x=-2, line_dash="dot", line_color=BREAKDOWN_POSITIVE_GREEN, opacity=0.3)

    return fig.to_html(full_html=False, include_plotlyjs=False, config={'responsive': True, 'auto_margin': False})



def generate_breakdown_metrics_strip(holdings_df, price_data=None):
    """
    Generates header strip with key breakdown metrics.

    Args:
        holdings_df (pd.DataFrame): DataFrame with holdings data including 'Weight', 'sector', and ticker index.
        price_data (pd.DataFrame, optional): Price data for calculating sector returns.

    Returns:
        str: HTML string with metrics display
    """
    if holdings_df is None or holdings_df.empty:
        return "<div class='no-data-message'>No breakdown metrics available.</div>"

    sector_col = 'sector' if 'sector' in holdings_df.columns else ('Sector' if 'Sector' in holdings_df.columns else None)
    if sector_col is None:
        return "<div class='no-data-message'>Sector data not available.</div>"

    df = holdings_df.copy()
    df[sector_col] = df[sector_col].fillna('Others')
    df['Weight'] = pd.to_numeric(df['Weight'], errors='coerce').fillna(0)

    # Metric 1: Number of sectors
    num_sectors = df[sector_col].nunique()

    # Metric 2: Top sector by weight
    sector_weights = df.groupby(sector_col)['Weight'].sum()
    top_sector_name = sector_weights.idxmax()
    top_sector_weight = sector_weights.max()

    # Metric 3: HHI (Herfindahl-Hirschman Index) * 10000
    hhi = (df['Weight']**2).sum() * 10000

    # Metric 4 & 5: Top positive and negative sector contributors (3M)
    pos_name, pos_return = "N/A", 0.0
    neg_name, neg_return = "N/A", 0.0
    sector_returns = {}  # Store 3M returns for all sectors
    direction_map = holdings_df['type'].to_dict() if 'type' in holdings_df.columns else {}
    
    if price_data is not None and not price_data.empty:
        try:
            end_date = price_data.index[-1]
            start_3m = end_date - pd.DateOffset(months=3)

            sector_returns = {}
            for sector in df[sector_col].unique():
                sector_tickers = df[df[sector_col] == sector].index
                sector_weight_total = df[df[sector_col] == sector]['Weight'].sum()
                if sector_weight_total <= 0:
                    continue

                weighted_return = 0.0
                for ticker in sector_tickers:
                    if ticker in price_data.columns:
                        prices = price_data[ticker].dropna()
                        prices_3m = prices[(prices.index >= start_3m) & (prices.index <= end_date)]
                        if len(prices_3m) > 1:
                                ret = (prices_3m.iloc[-1] / prices_3m.iloc[0]) - 1
                                if direction_map.get(ticker) == 'S':
                                    ret = -ret
                                weight = df.loc[ticker, 'Weight'] if ticker in df.index else 0
                                weighted_return += ret * weight

                if sector_weight_total > 0:
                    sector_returns[sector] = weighted_return / sector_weight_total

            if sector_returns:
                sorted_sectors = sorted(sector_returns.items(), key=lambda x: x[1], reverse=True)
                pos_name, pos_return = sorted_sectors[0]
                neg_name, neg_return = sorted_sectors[-1]

                if pos_return <= 0 and neg_return < 0:
                    pos_name, pos_return = "None", 0.0
                elif neg_return >= 0 and pos_return > 0:
                    neg_name, neg_return = "None", 0.0
        except Exception:
            pass  # Keep defaults

    # Formatting
    num_sectors_display = str(num_sectors)
    top_sector_name_display = top_sector_name
    top_sector_weight_display = f"{top_sector_weight*100:.1f}%"
    hhi_display = f"{hhi:.0f}"
    pos_display = f"{pos_return*100:.1f}%" if pos_name != "N/A" else "N/A"
    neg_display = f"{neg_return*100:.1f}%" if neg_name != "N/A" else "N/A"

    # Use full sector names (no shortening)
    pos_name_short = pos_name
    neg_name_short = neg_name

    # Color helpers
    def get_sector_color(n):
        return BREAKDOWN_POSITIVE_GREEN if n >= 8 else BREAKDOWN_NEUTRAL_ORANGE if n >= 5 else BREAKDOWN_NEGATIVE_RED

    def get_top_sector_color(w):
        return BREAKDOWN_NEGATIVE_RED if w > 0.25 else BREAKDOWN_NEUTRAL_ORANGE if w > 0.15 else BREAKDOWN_POSITIVE_GREEN

    def get_hhi_color(h):
        return BREAKDOWN_NEGATIVE_RED if h > 2500 else BREAKDOWN_NEUTRAL_ORANGE if h > 1000 else BREAKDOWN_POSITIVE_GREEN

    def get_hhi_concentration_label(h):
        return "High" if h > 2500 else "Medium" if h > 1000 else "Low"

    sector_color = get_sector_color(num_sectors)
    top_sector_color = get_top_sector_color(top_sector_weight)
    hhi_color = get_hhi_color(hhi)
    hhi_concentration = get_hhi_concentration_label(hhi)
    pos_color = BREAKDOWN_POSITIVE_GREEN if pos_return > 0 else NEUTRAL_GRAY
    neg_color = BREAKDOWN_NEGATIVE_RED if neg_return < 0 else NEUTRAL_GRAY
    neutral_color = BREAKDOWN_NEUTRAL_BLUE

    # Helper to generate a small pie chart with exploded slice - highlighted sector in card color, others in single dimmed grey
    def generate_sector_pie_chart(sector_weights_dict, highlight_sector, highlight_color):
        """
        Creates a small pie chart with one sector exploded and colored,
        other sectors in a single dimmed grey color.

        Args:
            sector_weights_dict: dict of {sector: weight}
            highlight_sector: sector to explode (or None)
            highlight_color: color for the highlighted sector (matches card)

        Returns:
            HTML string with the pie chart
        """
        if not sector_weights_dict or highlight_sector not in sector_weights_dict:
            return ""
        
        labels = list(sector_weights_dict.keys())
        values = list(sector_weights_dict.values())
        
        # Create pull array: explode the highlighted sector
        pull = [0.15 if label == highlight_sector else 0 for label in labels]
        
        # Colors: highlighted sector gets card color, all others same dimmed grey
        colors = [highlight_color if label == highlight_sector else BG_TAB_HOVER for label in labels]
        
        fig = go.Figure(data=[go.Pie(
             labels=labels,
             values=values,
             hole=0.6,
             pull=pull,
             marker_colors=colors,
             textinfo='none',
             hoverinfo='label+percent',
             showlegend=False,
             sort=False,
             marker=dict(
                 line=dict(color=PIE_SLICE_BORDER, width=2)
             )
         )])
        
        # Add percentage in the center
        highlight_weight = sector_weights_dict[highlight_sector]
        fig.add_annotation(
            x=0.5,
            y=0.5,
            text=f"<span style='font-size:14px;font-weight:600;color:{ZERO_RETURN_CELL_TEXT}'>{highlight_weight*100:.1f}%</span>",
            showarrow=False,
            font=dict(size=14, color=ZERO_RETURN_CELL_TEXT),
            xanchor='center',
            yanchor='middle'
        )
        
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=140,
            width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False
        )
        
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    # Helper to generate a horizontal bar chart showing 3M sector performance for the Number of Sectors card
    # Shows all sectors with green/red coloring based on performance (no labels - clean view)
    def generate_sector_performance_chart_all(sector_weights_dict, sector_returns):
        """
        Creates a horizontal bar chart of 3M sector performance for all sectors.
        Positive returns shown in green, negative in red, with percentage labels.

        Args:
            sector_weights_dict: dict of {sector: weight}
            sector_returns: dict of {sector: 3M return as decimal}

        Returns:
            HTML string with the bar chart
        """
        if not sector_weights_dict or not sector_returns:
            return ""
        
        # Sort sectors by weight (descending) for display
        sorted_sectors = sorted(sector_weights_dict.items(), key=lambda x: x[1], reverse=True)
        sectors = [s[0] for s in sorted_sectors]
        returns_pct = [sector_returns.get(s, 0) * 100 for s in sectors]  # Convert to percentage
        
        # Colors: green for positive, red for negative
        colors = [POSITIVE_RETURN_CARD if r >= 0 else NEGATIVE_RETURN_CARD for r in returns_pct]
        
        # Create text array: show percentage only for best and worst performing sectors
        if returns_pct:
            max_return = max(returns_pct)
            min_return = min(returns_pct)
            # Use tolerance for floating-point comparison
            tolerance = 1e-6
            text_values = []
            for r in returns_pct:
                if abs(r - max_return) < tolerance or abs(r - min_return) < tolerance:
                    text_values.append(f"{r:.1f}%")
                else:
                    text_values.append("")
        else:
            text_values = []
        
        # Create horizontal bar chart
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
             y=sectors,
             x=returns_pct,
             orientation='h',
             marker_color=colors,
             marker_line_color=CHART_BENCHMARK_MARKER,
             marker_line_width=1,
             text=text_values,
             textposition='outside',
             textfont=dict(size=10, color=BAR_VALUE_LABEL_TEXT, weight=500),
             constraintext='none',  # Allow text to be placed without constraint
             hovertemplate='%{y}: %{x:.1f}%<extra></extra>',
             cliponaxis=False  # Allow labels to extend beyond axis range
         ))
        
        # Calculate axis range to center around 0 and accommodate all values plus label space
        if returns_pct:
            max_abs = max(abs(min(returns_pct)), abs(max(returns_pct)))
            # Add padding for bar length plus space for labels
            x_min = -max_abs * 1.3 if min(returns_pct) < 0 else min(returns_pct) * 1.3
            x_max = max_abs * 1.3 if max(returns_pct) > 0 else max(returns_pct) * 1.3
            # Ensure 0 is included and add extra space for labels
            x_min = min(x_min, -0.5)
            x_max = max(x_max, 0.5)
            # Add extra padding on right side for labels (if positive values exist)
            if max(returns_pct) > 0:
                x_max += 1.0  # Add 1% width on right for labels
            # Add extra padding on left side for negative labels
            if min(returns_pct) < 0:
                x_min -= 1.0  # Add 1% width on left for labels
        else:
            x_min, x_max = -1, 1
        
        # Add vertical line at 0
        fig.add_vline(x=0, line_width=1.5, line_color=ZERO_RETURN_CELL_TEXT)
        
        fig.update_layout(
            margin=dict(l=40, r=40, t=5, b=5),
            height=max(100, len(sectors) * 22),
            width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False,
            xaxis=dict(
                showgrid=True,
                gridcolor=BREAKDOWN_GRID_COLOR,
                showline=True,
                linecolor=BREAKDOWN_LINE_COLOR,
                linewidth=1,
                showticklabels=False,
                ticks='',
                range=[x_min, x_max]
            ),
            yaxis=dict(
                showgrid=False,
                showticklabels=False,
                automargin=False
            ),
            bargap=0.2
        )
        
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    # Helper to generate a horizontal bar chart showing 3M sector performance (for Largest Sector Allocation)
    def generate_sector_performance_bar_chart(sector_weights_dict, highlight_sector, highlight_color, sector_returns):
        """
        Creates a horizontal bar chart of 3M sector performance.
        The largest allocation sector bar is highlighted in card color, others dimmed grey.

        Args:
            sector_weights_dict: dict of {sector: weight}
            highlight_sector: the largest allocation sector (shown in highlight color)
            highlight_color: card color for the largest sector
            sector_returns: dict of {sector: 3M return as decimal}

        Returns:
            HTML string with the bar chart
        """
        if not sector_weights_dict or not sector_returns:
            return ""
        
        # Sort sectors by weight (descending) for display
        sorted_sectors = sorted(sector_weights_dict.items(), key=lambda x: x[1], reverse=True)
        sectors = [s[0] for s in sorted_sectors]
        returns_pct = [sector_returns.get(s, 0) * 100 for s in sectors]  # Convert to percentage
        
        # Calculate axis range with safe fallbacks and padding for labels
        if returns_pct:
            max_abs = max(abs(min(returns_pct)), abs(max(returns_pct)))
            # Add padding for bar length plus space for labels
            x_min = -max_abs * 1.3 if min(returns_pct) < 0 else min(returns_pct) * 1.3
            x_max = max_abs * 1.3 if max(returns_pct) > 0 else max(returns_pct) * 1.3
            # Ensure 0 is included
            x_min = min(x_min, -0.5)
            x_max = max(x_max, 0.5)
            # Add extra padding on right side for labels (if positive values exist)
            if max(returns_pct) > 0:
                x_max += 1.0  # Add 1% width on right for labels
            # Add extra padding on left side for negative labels
            if min(returns_pct) < 0:
                x_min -= 1.0  # Add 1% width on left for labels
        else:
            x_min, x_max = -1, 1
        x_range = [x_min, x_max]
        
        # Create horizontal bar chart
        fig = go.Figure()
        
        # Colors: largest sector gets highlight color, others dimmed grey
        colors = [highlight_color if s == highlight_sector else BG_TAB_HOVER for s in sectors]
        
        # Create text array: only show percentage for highlighted sector
        text_values = [f"{r:.1f}%" if s == highlight_sector else "" for s, r in zip(sectors, returns_pct)]
        
        fig.add_trace(go.Bar(
             y=sectors,
             x=returns_pct,
             orientation='h',
             marker_color=colors,
             marker_line_color=CHART_BENCHMARK_MARKER,
             marker_line_width=1,
             text=text_values,
             textposition='outside',
             textfont=dict(size=10, color=highlight_color, weight=500),
             constraintext='none',
             cliponaxis=False,
             hovertemplate='%{y}: %{x:.1f}%<extra></extra>'
         ))
        
        fig.update_layout(
            margin=dict(l=40, r=40, t=5, b=5),
            height=max(90, len(sectors) * 18),
            width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False,
            xaxis=dict(
                showgrid=True,
                gridcolor=BREAKDOWN_GRID_COLOR,
                showline=True,
                linecolor=BREAKDOWN_LINE_COLOR,
                linewidth=1,
                showticklabels=False,
                ticks='',
                range=x_range
            ),
            yaxis=dict(
                showgrid=False,
                showticklabels=False
            )
        )
        
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    # Generate charts
    sector_weights_dict = sector_weights.to_dict()
    pos_pie = generate_sector_pie_chart(sector_weights_dict, pos_name if pos_name != "N/A" else None, pos_color)
    neg_pie = generate_sector_pie_chart(sector_weights_dict, neg_name if neg_name != "N/A" else None, neg_color)
    top_bar = generate_sector_performance_bar_chart(sector_weights_dict, top_sector_name, neutral_color, sector_returns)
    all_sectors_bar = generate_sector_performance_chart_all(sector_weights_dict, sector_returns) if sector_returns else ""

    html = f"""
    <div class="metric-strip-row">
        <!-- Best Performing Sector (3M) -->
        <div class="metric-card" style="background-color: {pos_color}20; border-color: {pos_color};">
            <div class="metric-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Best 3M Sector</div>
            <div class="metric-value" style="color: {pos_color};">{pos_display}</div>
            <div class="metric-sublabel">{pos_name_short}</div>
            <div class="metric-chart-container">{pos_pie}</div>
        </div>

        <!-- Worst Performing Sector (3M) -->
        <div class="metric-card" style="background-color: {neg_color}20; border-color: {neg_color};">
            <div class="metric-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Worst 3M Sector</div>
            <div class="metric-value" style="color: {neg_color};">{neg_display}</div>
            <div class="metric-sublabel">{neg_name_short}</div>
            <div class="metric-chart-container">{neg_pie}</div>
        </div>

        <!-- Largest Sector Allocation -->
        <div class="metric-card" style="background-color: {neutral_color}20; border-color: {neutral_color};">
            <div class="metric-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Largest Sector Allocation</div>
            <div class="metric-value" style="color: {neutral_color};">{top_sector_weight_display}</div>
            <div class="metric-sublabel">{top_sector_name_display}</div>
            <div class="metric-chart-container">{top_bar}</div>
        </div>

        <!-- Number of Sectors -->
        <div class="metric-card" style="background-color: {sector_color}20; border-color: {sector_color};">
            <div class="metric-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Number of Sectors</div>
            <div class="metric-value" style="color: {sector_color};">{num_sectors_display}</div>
            <div class="metric-chart-container">{all_sectors_bar}</div>
        </div>

        <!-- Portfolio Concentration (HHI) -->
        <div class="metric-card" style="background-color: {hhi_color}20; border-color: {hhi_color};">
            <div class="metric-label" style="color: {METRIC_CARD_LABEL_TEXT}; font-weight: bold; text-transform: uppercase;">Portfolio Concentration (HHI)</div>
            <div class="metric-value" style="color: {hhi_color};">{hhi_display}</div>
            <div class="metric-sublabel" style="color: {hhi_color}; margin-top: 5px;">{hhi_concentration}</div>
        </div>
    </div>
    """
    return html


def generate_sector_sunburst_chart(holdings_df):
    """
    Generates an interactive sector/industry sunburst chart with hierarchical breakdown.
    Includes a side table with collapsible hierarchy for better drill-down.
    """
    if holdings_df.empty:
        return "<p>No sector performance data available.</p>"

    import plotly.graph_objects as go

    df = holdings_df.copy()
    df['sector'] = df.get('sector', pd.Series(index=df.index)).fillna('Others').astype(str)
    df['industry'] = df.get('industry', pd.Series(index=df.index)).fillna('Others').astype(str)

    if 'type' in df.columns:
        mask_short = df['type'] == 'S'
        for perf_col in ['ret_1w', 'ret_1m', 'ret_3m', 'ret_1y', 'ret_5y', 'ret_all']:
            if perf_col in df.columns:
                df.loc[mask_short, perf_col] = -df.loc[mask_short, perf_col]

    period_map = {'1W': 'ret_1w', '1M': 'ret_1m', '3M': 'ret_3m', '1Y': 'ret_1y', '5Y': 'ret_5y', 'All': 'ret_all'}
    available = {k: v for k, v in period_map.items() if v in df.columns}
    if not available:
        return "<p>No performance data available.</p>"

    sector_weights = df.groupby('sector')['Weight'].sum().sort_values(ascending=False)

    def weighted_perf(group, col):
        valid = group[pd.notna(group[col])]
        if valid.empty:
            return None
        return (valid[col] * valid['Weight']).sum() / valid['Weight'].sum()

    sector_perf_all = {}
    for label, col in available.items():
        sector_perf_all[label] = df.groupby('sector').apply(lambda g, c=col: weighted_perf(g, c))

    periods_html = {}
    for period_label, perf_col in available.items():

        labels = []
        parents = []
        values = []
        perf_colors = []

        industry_weights = df.groupby(['sector', 'industry'])['Weight'].sum()
        industry_perf = df.groupby(['sector', 'industry']).apply(lambda g, c=perf_col: weighted_perf(g, c))

        for sector in sector_weights.index:
            labels.append(sector)
            parents.append("")
            values.append(sector_weights[sector] * 100)
            p = sector_perf_all[period_label].get(sector)
            perf_colors.append(p * 100 if pd.notna(p) else None)

        for (sector, industry), weight in industry_weights.items():
            label = f"{industry} ({sector})"
            labels.append(label)
            parents.append(sector)
            values.append(weight * 100)
            p = industry_perf.get((sector, industry))
            perf_colors.append(p * 100 if pd.notna(p) else None)

        for idx, row in df.iterrows():
            label = f"{row.get('name', idx)} ({idx})" if pd.notna(row.get('name', idx)) else str(idx)
            industry_key = f"{row['industry']} ({row['sector']})"
            labels.append(label)
            parents.append(industry_key)
            values.append(row['Weight'] * 100)
            p = row[perf_col]
            perf_colors.append(p * 100 if pd.notna(p) else None)

        fig = go.Figure(go.Sunburst(
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(
                colors=perf_colors,
                colorscale=[
                    [0.0, NEGATIVE_RETURN_CARD],
                    [0.5, BORDER_MEDIUM],
                    [1.0, POSITIVE_RETURN_CARD]
                ],
                cmid=0,
                line=dict(color=LIGHT_ELEMENT, width=1.5)
            ),
            hovertemplate='<b>%{label}</b><br>Weight: %{value:.2f}%<br>Perf: %{color:.2f}%<extra></extra>',
            textfont=dict(size=11, color=PRIMARY_TEXT)
        ))

        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            width=650,
            height=650,
            paper_bgcolor=LIGHT_ELEMENT,
        )

        div_id = f"sector-sunburst-{period_label}"
        chart_html = fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id)

        sector_ids = {}
        for s in sector_weights.index:
            sector_ids[s] = s.replace(' ', '').replace('/', '').replace('&', '').replace('(', '').replace(')', '')

        industry_data = {}
        for sector in sector_weights.index:
            sector_df = df[df['sector'] == sector]
            ind_groups = sector_df.groupby('industry')
            industry_data[sector] = {}
            for industry, group in ind_groups:
                industry_data[sector][industry] = group.sort_values('Weight', ascending=False)

        def perf_badge(pval):
            if pval is None or pd.isna(pval):
                return f'<span style="background-color: {TEXT_MUTED}; color: {LIGHT_ELEMENT}; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 0.85em;">N/A</span>'
            val = pval * 100
            color = POSITIVE_RETURN_CARD if val > 0 else NEGATIVE_RETURN_CARD if val < 0 else TEXT_MUTED
            arrow = '▲' if val > 0 else '▼' if val < 0 else ''
            return f'<span style="background-color: {color}; color: {LIGHT_ELEMENT}; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 0.85em; white-space: nowrap;">{arrow} {val:.2f}%</span>'

        table_rows = ""
        for sector in sector_weights.index:
            sid = sector_ids[sector]
            s_w = sector_weights[sector] * 100
            s_p = sector_perf_all[period_label].get(sector)

            sector_block = (
                f'<tr onclick="toggleSunburstSector(\'{period_label}\', \'{sid}\')" '
                f'style="cursor: pointer; background-color: var(--color-bg-row-header); '
                f'color: {TEXT_SECONDARY}; border-bottom: 1px solid {BORDER_CHART_HEADER};">'
                f'<td><span id="sunburst-arrow-{period_label}-{sid}" '
                                f'style="display:inline-block; width:14px; color: {EFFICIENCY_LABEL_FONT}">&#9654;</span>{sector}</td>'
                f'<td style="text-align: right;">{s_w:.2f}%</td>'
                f'<td style="text-align: right;">{perf_badge(s_p)}</td>'
                f'</tr>'
            )

            ind_idx = 0
            for industry, group in industry_data[sector].items():
                iid = f"{sid}-ind{ind_idx}"
                i_w = group['Weight'].sum() * 100
                i_p = industry_perf.get((sector, industry))
                ind_idx += 1

                industry_row = (
                    f'<tr onclick="toggleSunburstIndustry(\'{period_label}\', \'{iid}\')" '
                    f'data-sector-id="{sid}" data-industry-id="{iid}" '
                    f'style="cursor: pointer; background-color: {BG_ROW_HEADER_ALT};">'
                    f'<td style="padding-left: 20px;">'
                    f'<span id="sunburst-arrow-{period_label}-{iid}" '
                    f'style="display:inline-block; width:14px; color: {EFFICIENCY_LABEL_FONT}">&#9654;</span>{industry}'
                    f'</td>'
                    f'<td style="text-align: right;">{i_w:.2f}%</td>'
                    f'<td style="text-align: right;">{perf_badge(i_p)}</td>'
                    f'</tr>'
                )

                sector_block += industry_row

                for idx, row in group.iterrows():
                    label = row.get('name', idx) if pd.notna(row.get('name', idx)) else str(idx)
                    label = f"{label} ({idx})"
                    p = row[perf_col]
                    weight_pct = "{:.2f}".format(row['Weight'] * 100)
                    badge = perf_badge(p)
                    sec_row = (
                        f'<tr data-parent-id="{iid}" style="display: none;">'
                        f'<td style="padding-left: 35px; font-size: 0.9em;">{label}</td>'
                        f'<td style="text-align: right;">{weight_pct}%</td>'
                        f'<td style="text-align: right;">{badge}</td>'
                        f'</tr>'
                    )
                    sector_block += sec_row

            table_rows += f"<tbody>{sector_block}</tbody>"

        summary_table = f"""
        <style>
        .sunburst-table {{
            font-size: 0.82em;
            font-family: {FONT_PRIMARY};
            border-collapse: collapse;
            width: 100%;
        }}
        .sunburst-table th {{
            padding: 6px 8px;
            border: 1px solid {BORDER_THEME};
            background-color: {BG_ROW_ALT_ALT};
            color: {NEUTRAL_TEXT};
        }}
        .sunburst-table td {{
            padding: 4px 8px;
            border: 1px solid {BORDER_THEME};
        }}
        </style>
        <table class="sunburst-table">
            <thead>
                <tr>
                    <th style="width: 55%;">Name</th>
                    <th style="width: 20%; text-align: right;">Weight (%)</th>
                    <th style="width: 25%; text-align: right;">{period_label} (%)</th>
                </tr>
            </thead>
            {table_rows}
        </table>"""

        toggle_js = f"""
        <script>
        function toggleSunburstSector(period, sid) {{
            var industries = document.querySelectorAll('tr[data-sector-id="' + sid + '"]');
            var arrow = document.getElementById('sunburst-arrow-' + period + '-' + sid);
            var anyVisible = Array.from(industries).some(function(el) {{
                return el.style.display !== 'none';
            }});
            if (anyVisible) {{
                industries.forEach(function(el) {{
                    el.style.display = 'none';
                    var iid = el.getAttribute('data-industry-id');
                    var indArrow = document.getElementById('sunburst-arrow-' + period + '-' + iid);
                    if (indArrow) indArrow.innerHTML = '&#9654;';
                    var securities = document.querySelectorAll('tr[data-parent-id="' + iid + '"]');
                    securities.forEach(function(sec) {{
                        sec.style.display = 'none';
                    }});
                }});
            }} else {{
                industries.forEach(function(el) {{
                    el.style.display = '';
                }});
            }}
            arrow.innerHTML = anyVisible ? '&#9654;' : '&#9660;';
        }}
        function toggleSunburstIndustry(period, iid) {{
            var sel = 'tr[data-parent-id="' + iid + '"]';
            var els = document.querySelectorAll(sel);
            var arrow = document.getElementById('sunburst-arrow-' + period + '-' + iid);
            var anyVisible = els.length > 0 && els[0].style.display !== 'none';
            els.forEach(function(el) {{
                el.style.display = anyVisible ? 'none' : 'table-row';
            }});
            arrow.innerHTML = anyVisible ? '&#9654;' : '&#9660;';
        }}
        </script>
        """

        periods_html[period_label] = f'''
        <div class="sector-sunburst-period" data-period="{period_label}" style="display: {"flex" if period_label == list(available.keys())[0] else "none"}; gap: 20px; align-items: flex-start;">
            <div style="flex: 0 0 380px; min-width: 380px;">
                {toggle_js}
                {summary_table}
            </div>
            <div style="flex: 1; min-width: 0;">
                {chart_html}
            </div>
        </div>
        '''

    buttons_html = ''.join(
        f'<button type="button" class="sector-sunburst-btn" data-period="{k}" onclick="switchSectorPeriod(\'{k}\')" '
        f'style="background-color: {BG_BUTTON_PRIMARY if i == 0 else BG_BUTTON_SECONDARY}; color: {LIGHT_ELEMENT}; border: none; padding: 6px 12px; cursor: pointer; border-radius: 4px; font-weight: bold; font-size: 0.85em;">{k}</button>'
        for i, k in enumerate(available.keys())
    )
    selector_html = f'<div id="sector-sunburst-buttons" style="margin-bottom: 10px;"><span style="font-weight: bold; color: {TEXT_PRIMARY}; font-size: 0.85em; margin-right: 5px;">Time Horizon:</span><div style="display: inline-flex; gap: 5px;">{buttons_html}</div></div>'

    js = '''
<script>
function switchSectorPeriod(period) {
    var containers = document.querySelectorAll('.sector-sunburst-period');
    containers.forEach(function(el) {
        el.style.display = el.dataset.period === period ? 'flex' : 'none';
    });
    var buttons = document.querySelectorAll('#sector-sunburst-buttons .sector-sunburst-btn');
    buttons.forEach(function(btn) {
        btn.style.backgroundColor = btn.dataset.period === period ? 'var(--color-bg-button-primary)' : 'var(--color-bg-button-secondary)';
    });
}
</script>
'''

    body = ''.join(periods_html.values())
    return selector_html + js + f'<div style="font-family: {FONT_PRIMARY}; width: 100%;">{body}</div>'


