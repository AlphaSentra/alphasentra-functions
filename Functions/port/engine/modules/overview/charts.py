"""
Chart generation module: All Plotly visualizations for portfolio functions.
"""

import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go


from config import (
    UNDEFINED_METRIC_CARD, POSITIVE_RETURN_CARD, NEGATIVE_RETURN_CARD,
    METRIC_CARD_LABEL_TEXT, DIV_YIELD_CARD_BG, DIV_YIELD_CARD_BORDER, DIV_YIELD_CARD_TEXT,
    PERF_BAR_POSITIVE, PERF_BAR_NEGATIVE, BAR_VALUE_LABEL_TEXT, BAR_OUTLINE,
    PERF_ACTIVE_BUTTON_BG, PERF_INACTIVE_BUTTON_BG, BUTTON_TEXT, TABLE_PERIOD_LABEL_TEXT,
    CHART_TRANSPARENT, CHART_GRID, BG_CHART, TEXT_MUTED,
    CHART_CARD_SHADOW, BG_BUTTON_PRIMARY, BG_BUTTON_SECONDARY, BUTTON_TEXT,
    CHART_LINE_CAPITAL_GAIN, CHART_LINE_SINCE_INCEPTION,
    CHART_BENCHMARK_FILL, FONT_PRIMARY,
    get_benchmark_name,
)



def calculate_period_returns(total_ts):
    """
    Calculates returns for various periods: YTD, 1W, 1M, 3M, 1Y, 5Y, and Since Inception.
    """
    if total_ts is None or total_ts.empty or len(total_ts) < 2:
        return {}

    total_ts = total_ts.sort_index()
    current_date = total_ts.index[-1]
    
    # Calendar-based periods
    periods = {
        'YTD': pd.DateOffset(year=current_date.year, month=1, day=1),
        '1W': pd.DateOffset(weeks=1),
        '1M': pd.DateOffset(months=1),
        '3M': pd.DateOffset(months=3),
        '1Y': pd.DateOffset(years=1),
        '5Y': pd.DateOffset(years=5)
    }

    results = {}
    
    # YTD logic
    year_start = pd.Timestamp(year=current_date.year, month=1, day=1)
    if year_start in total_ts.index:
        start_val = total_ts.loc[year_start]
        end_val = total_ts.iloc[-1]
        if start_val > 0:
            results['YTD'] = (end_val / start_val) - 1

    # Others
    for label, offset in periods.items():
        if label == 'YTD': continue
        start_date = current_date - offset
        # Find closest date >= start_date
        valid_indices = total_ts.index[total_ts.index >= start_date]
        if len(valid_indices) > 0:
            start_val = total_ts.loc[valid_indices[0]]
            end_val = total_ts.iloc[-1]
            if start_val > 0:
                results[label] = (end_val / start_val) - 1
    
    # Since Inception
    start_val_inception = total_ts.iloc[0]
    if start_val_inception > 0:
        results['SinceInception'] = (total_ts.iloc[-1] / start_val_inception) - 1
    
    return results

def generate_overview_metrics_strip(total_ts, annual_yield=0.0):
    """
    Generates header strip with key overview metrics including mini sparkline charts.
    """
    returns = calculate_period_returns(total_ts)
    
    # Format
    def fmt(val): return f"{val*100:+.2f}%" if not np.isnan(val) else "N/A"
    
    # Define colors
    def get_color(val):
        if np.isnan(val): return UNDEFINED_METRIC_CARD
        return POSITIVE_RETURN_CARD if val >= 0 else NEGATIVE_RETURN_CARD

    # Helper to generate a mini sparkline chart for a given period
    def generate_sparkline(period_key, color):
        try:
            if total_ts is None or total_ts.empty or len(total_ts) < 2:
                return ""
            
            period_data = None
            end_date = total_ts.index[-1]
            
            if period_key == 'YTD':
                year_start = pd.Timestamp(year=end_date.year, month=1, day=1)
                period_data = total_ts[total_ts.index >= year_start]
            elif period_key == '1W':
                start_date = end_date - pd.DateOffset(weeks=1)
                period_data = total_ts[total_ts.index >= start_date]
            elif period_key == '1M':
                start_date = end_date - pd.DateOffset(months=1)
                period_data = total_ts[total_ts.index >= start_date]
            elif period_key == '1Y':
                start_date = end_date - pd.DateOffset(years=1)
                period_data = total_ts[total_ts.index >= start_date]
            elif period_key == '5Y':
                start_date = end_date - pd.DateOffset(years=5)
                period_data = total_ts[total_ts.index >= start_date]
            elif period_key == 'SinceInception':
                period_data = total_ts
            else:
                return ""
            
            if period_data is None or len(period_data) < 2:
                return ""
            
            # Normalize to percentage change from start
            start_val = period_data.iloc[0]
            if pd.isna(start_val) or start_val <= 0:
                return ""
            
            normalized = (period_data / start_val - 1) * 100
            
            # Create sparkline figure with larger dimensions
            fig = go.Figure()
            # Convert hex color to rgba for fillcolor with 30% opacity
            hex_color = color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            fillcolor = f'rgba({r},{g},{b},0.3)'
            fig.add_trace(go.Scatter(
                x=normalized.index,
                y=normalized.values,
                mode='lines',
                line=dict(width=2, color=color),
                fill='tozeroy',
                fillcolor=fillcolor,
                showlegend=False,
                hoverinfo='skip'
            ))
            
            # Add endpoint marker
            fig.add_trace(go.Scatter(
                x=[normalized.index[-1]],
                y=[normalized.values[-1]],
                mode='markers',
                marker=dict(size=6, color=color),
                showlegend=False,
                hoverinfo='skip'
            ))
            
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=80,
                width=200,
                paper_bgcolor=CHART_TRANSPARENT,
                plot_bgcolor=CHART_TRANSPARENT,
                xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False, fixedrange=True, automargin=False),
                yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False, fixedrange=True, automargin=False),
                dragmode=False
            )
            
            return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})
        except Exception:
            return ""

    # Helper to generate a metric card with mini chart
    def card(label, period_key, style_extra=""):
        val = returns.get(period_key, np.nan)
        display_label = label
        
        # If 1Y not available but since-inception is, use that with different label
        if period_key == '1Y' and (np.isnan(val) or period_key not in returns):
            if 'SinceInception' in returns:
                val = returns['SinceInception']
                display_label = 'Since Inception'
                period_key = 'SinceInception'
        # If 5Y not available but since-inception is, use that with different label
        if period_key == '5Y' and (np.isnan(val) or period_key not in returns):
            if 'SinceInception' in returns:
                val = returns['SinceInception']
                display_label = 'Since Inception'
                period_key = 'SinceInception'
        
        color = get_color(val)
        chart_html = generate_sparkline(period_key, color)
        
        return f'''
        <div class="metric-card" style="flex: 1; background-color: {color}20; border-color: {color}; border-radius: 8px; padding: 10px 8px; text-align: center; box-shadow: 0 2px 4px {CHART_CARD_SHADOW}; min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 6px;{style_extra}">
            <div style="font-size: 0.75em; color: {METRIC_CARD_LABEL_TEXT}; text-transform: uppercase; margin: 0; font-weight: bold;">{display_label}</div>
            <div style="font-size: 2.0em; font-weight: 900; color: {color}; margin: 0; line-height: 1;">{fmt(val)}</div>
            {'<div style="height:80px; display:flex; align-items:center; justify-content:center;">' + chart_html + '</div>' if chart_html else '<div style="height:80px;"></div>'}
        </div>
        '''

    html = f'''
    <div style="display: flex; gap: 10px; margin: 12px 0; font-family: {FONT_PRIMARY};">
        {card('YTD', 'YTD')}
        {card('1M', '1M')}
        {card('1Y', '1Y')}
        {card('5Y', '5Y')}
        <div class="metric-card" style="flex: 1; background-color: {DIV_YIELD_CARD_BG}; border-color: {DIV_YIELD_CARD_BORDER}; border-radius: 8px; padding: 10px 8px; text-align: center; box-shadow: 0 2px 4px {CHART_CARD_SHADOW}; min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 6px;">
            <div style="font-size: 0.75em; color: {METRIC_CARD_LABEL_TEXT}; text-transform: uppercase; margin: 0; font-weight: bold;">Div Yield</div>
            <div style="font-size: 2.0em; font-weight: 900; color: {DIV_YIELD_CARD_TEXT}; margin: 0; line-height: 1;">{fmt(annual_yield)}</div>
            <div style="height: 80px;"></div>
        </div>
    </div>
    '''
    return html



def generate_performance_barchart(ts_data, benchmark_ticker=None, annual_yield=0.0, include_yield_toggle=False):
    """
    Generates a grouped bar chart showing portfolio vs benchmark performance over various time periods."""
    total_ts = ts_data.get("total")
    benchmark_ts = ts_data.get("benchmark")

    if total_ts is None or total_ts.empty or len(total_ts) < 2:
        return "<p>Insufficient data for performance chart.</p>"

    # Ensure index is sorted
    total_ts = total_ts.sort_index()
    if benchmark_ts is not None and not benchmark_ts.empty:
        benchmark_ts = benchmark_ts.sort_index()

    current_date = total_ts.index[-1]
    current_year = current_date.year

    # Helper to calculate period performances for a given daily yield factor
    def calculate_performances(daily_yield_factor):
        period_days = {
            'YTD': None,
            '6M': 126,
            '1Y': 252,
            '3Y': 756,
            '5Y': 1260
        }
        period_order = ['YTD', '6M', '1Y', '3Y', '5Y']
        port_perf = {}
        bench_perf = {}

        # YTD
        try:
            ytd_indices = total_ts.index[total_ts.index.year == current_year]
            if len(ytd_indices) > 0:
                start_val = total_ts.loc[ytd_indices[0]]
                end_val = total_ts.iloc[-1]
                if start_val > 0 and not pd.isna(start_val) and not pd.isna(end_val):
                    n_days = len(ytd_indices)
                    yield_factor = daily_yield_factor ** n_days if annual_yield > 0 else 1.0
                    port_perf['YTD'] = ((end_val / start_val) * yield_factor) - 1

                if benchmark_ts is not None and not benchmark_ts.empty:
                    bench_start = benchmark_ts.loc[ytd_indices[0]]
                    bench_end = benchmark_ts.iloc[-1]
                    if not pd.isna(bench_start) and not pd.isna(bench_end) and bench_start > 0:
                        bench_perf['YTD'] = (bench_end / bench_start) - 1
        except Exception:
            pass

        # Other periods
        for label in period_order:
            if label == 'YTD':
                continue
            days = period_days[label]
            if len(total_ts) >= days:
                start_idx = len(total_ts) - days
                start_val = total_ts.iloc[start_idx]
                end_val = total_ts.iloc[-1]
                if start_val > 0 and not pd.isna(start_val) and not pd.isna(end_val):
                    yield_factor = daily_yield_factor ** days if annual_yield > 0 else 1.0
                    port_perf[label] = ((end_val / start_val) * yield_factor) - 1

                if benchmark_ts is not None and not benchmark_ts.empty and len(benchmark_ts) >= days:
                    bench_start_val = benchmark_ts.iloc[start_idx]
                    bench_end_val = benchmark_ts.iloc[-1]
                    if not pd.isna(bench_start_val) and not pd.isna(bench_end_val) and bench_start_val > 0:
                        bench_perf[label] = (bench_end_val / bench_start_val) - 1

        return port_perf, bench_perf

    # Calculate for capital gain (yield=0)
    port_cap_gain, bench_perf = calculate_performances(1.0)

    if not port_cap_gain:
        return "<p>No performance data available for any period.</p>"

    # Prepare data for grouped bar chart in order
    period_order = ['YTD', '6M', '1Y', '3Y', '5Y']
    labels = []
    bench_values = []

    for p in period_order:
        if p in port_cap_gain:  # Use portfolio data as the source of truth for available periods
            labels.append(p)
            bench_values.append(bench_perf.get(p, None))

    # Create grouped bar chart
    fig = go.Figure()

    # Portfolio bars - Capital Gain (green/red based on performance)
    if port_cap_gain:
        cap_gain_values = [port_cap_gain.get(p, None) for p in period_order if p in port_cap_gain]
        cap_gain_colors = [PERF_BAR_POSITIVE if v >= 0 else PERF_BAR_NEGATIVE for v in cap_gain_values]
        fig.add_trace(go.Bar(
            x=labels,
            y=cap_gain_values,
            name='Portfolio',
            marker_color=cap_gain_colors,
            marker_line_color=BAR_OUTLINE,
            marker_line_width=1,
            text=[f"{v:.1%}" for v in cap_gain_values],
            textposition='outside'
        ))

    # Benchmark bars (gray with black outline)
    valid_bench_values = [v for v in bench_values if v is not None]
    if valid_bench_values:
        fig.add_trace(go.Bar(
            x=labels,
            y=bench_values,
            name=f'Benchmark ({get_benchmark_name(benchmark_ticker)})' if benchmark_ticker else 'Benchmark',
            marker_color=CHART_BENCHMARK_FILL,
            marker_line_color=BAR_OUTLINE,
            marker_line_width=1,
            text=[f"{v:.1%}" if v is not None else "" for v in bench_values],
            textposition='outside'
        ))

    chart_title = "Portfolio vs Benchmark Performance"
    fig.update_layout(
        title=chart_title,
        font=dict(color=TEXT_MUTED),
        xaxis_title="Period",
        yaxis_title="Return (%)",
        yaxis_tickformat=".0%",
        barmode='group',
        height=450,
        margin=dict(l=60, r=60, t=60, b=80),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        yaxis=dict(rangemode='tozero'),
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        xaxis_showgrid=True,
        yaxis_showgrid=True,
        xaxis_gridcolor=CHART_GRID,
        yaxis_gridcolor=CHART_GRID,
    )
    fig.add_hline(y=0, line_width=2, line_color=CHART_GRID)

    # Expand y-axis range to accommodate outside text labels
    all_values = []
    for trace in fig.data:
        if hasattr(trace, 'y') and trace.y is not None:
            all_values.extend([v for v in trace.y if v is not None])

    if all_values:
        max_val = max(all_values)
        min_val = min(all_values)
        max_abs = max(abs(max_val), abs(min_val))
        # Add 15% padding to the maximum absolute value to make room for outside labels
        y_max_padding = max_abs * 0.15
        y_min_padding = max_abs * 0.15
        fig.update_yaxes(range=[min_val - y_min_padding, max_val + y_max_padding])

    # Generate chart HTML
    chart_html = fig.to_html(full_html=False, include_plotlyjs=False)
    return chart_html



def generate_advances_declines_charts(holdings_df):
    """
    Generates two horizontal bar charts showing top 10 advances and declines
    with a time horizon selector (1W, 1M, 3M).

    Args:
        holdings_df (pd.DataFrame): DataFrame with ticker index, 'name', 'ret_1w', 'ret_1m', 'ret_3m' columns.

    Returns:
        str: HTML string with time horizon selector and interactive Plotly bar charts.
    """
    if holdings_df.empty:
        return "<p>No performance data available.</p>"

    df = holdings_df.copy()
    df['label'] = df.get('name', df.index.to_series()).fillna(df.index.to_series())

    if 'type' in df.columns:
        mask_short = df['type'] == 'S'
        for perf_col in ['ret_1w', 'ret_1m', 'ret_3m', 'ret_1y', 'ret_5y', 'ret_all']:
            if perf_col in df.columns:
                df.loc[mask_short, perf_col] = -df.loc[mask_short, perf_col]

    period_map = {'1W': 'ret_1w', '1M': 'ret_1m', '3M': 'ret_3m', '1Y': 'ret_1y', '5Y': 'ret_5y', 'All': 'ret_all'}
    available = {k: v for k, v in period_map.items() if v in df.columns}
    if not available:
        return "<p>No performance data available.</p>"

    def build_fig(data, col, is_advances, suffix):
        if data.empty:
            return None, None
        values = data[col].values * 100
        tickers = list(data.index)
        names = [row['label'] if pd.notna(row['label']) else idx for idx, row in data.iterrows()]
        hover_texts = [f"{name} ({ticker}): {v:+.2f}%" for ticker, name, v in zip(tickers, names, values)]
        color = PERF_BAR_POSITIVE if is_advances else PERF_BAR_NEGATIVE
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=tickers,
            x=values,
            orientation='h',
            marker_color=color,
            marker_line_color=BAR_VALUE_LABEL_TEXT,
            marker_line_width=1,
            hovertext=hover_texts,
            hoverinfo='text',
            cliponaxis=False
        ))
        max_abs = max(abs(v) for v in values) if len(values) > 0 else 10
        padding = max_abs * 0.35
        div_id = f"adv-dec-{suffix}"
        if is_advances:
            x_range = [0, max_abs + padding]
            margin = dict(l=10, r=100, t=20, b=10)
            fig.update_traces(text=[f"+{v:.2f}%" for v in values], textposition='outside')
        else:
            x_range = [-(max_abs + padding), 0]
            margin = dict(l=100, r=10, t=20, b=10)
            fig.update_traces(text=[f"{v:.2f}%" for v in values], textposition='outside')
        fig.update_layout(
            height=380,
            margin=margin,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            font=dict(color=TEXT_MUTED),
            xaxis=dict(
                showgrid=True, gridcolor=CHART_GRID,
                tickformat='.1f',
                range=x_range,
                title=dict(text='Return (%)', font=dict(size=11)),
                side='top'
            ),
            yaxis=dict(
                showgrid=False, autorange='reversed',
                side='right' if not is_advances else 'left'
            ),
            bargap=0.3,
        )
        return fig, div_id

    periods_html = {}
    for label, col in available.items():
        col_df = df[df[col].notna()]
        if col_df.empty:
            continue
        advances = col_df[col_df[col] > 0].sort_values(col, ascending=False).head(10)
        declines = col_df[col_df[col] < 0].sort_values(col, ascending=True).head(10)

        adv_fig, adv_id = build_fig(advances, col, True, f"adv-{label}")
        dec_fig, dec_id = build_fig(declines, col, False, f"dec-{label}")

        adv_html = adv_fig.to_html(full_html=False, include_plotlyjs=False, div_id=adv_id) if adv_fig else ""
        dec_html = dec_fig.to_html(full_html=False, include_plotlyjs=False, div_id=dec_id) if dec_fig else ""

        periods_html[label] = f'''
        <div class="adv-dec-period" data-period="{label}" style="display: {"flex" if label == list(available.keys())[0] else "none"}; gap: 20px; width: 100%;">
            <div style="width: 50%; min-width: 0; box-sizing: border-box;">{dec_html}</div>
            <div style="width: 50%; min-width: 0; box-sizing: border-box;">{adv_html}</div>
        </div>
        '''

    buttons_html = ''.join(
        f'<button type="button" class="adv-horizon-btn" data-period="{k}" onclick="switchAdvHorizon(\'{k}\')" '
        f'style="background-color: {PERF_ACTIVE_BUTTON_BG if i == 0 else PERF_INACTIVE_BUTTON_BG}; color: {BUTTON_TEXT}; border: none; padding: 6px 12px; cursor: pointer; border-radius: 4px; font-weight: bold; font-size: 0.85em;">{k}</button>'
        for i, k in enumerate(available.keys())
    )
    selector_html = f'<div id="adv-horizon-buttons" style="margin-bottom: 10px;"><span style="font-weight: bold; color: {TABLE_PERIOD_LABEL_TEXT}; font-size: 0.85em; margin-right: 5px;">Time Horizon:</span><div style="display: inline-flex; gap: 5px;">{buttons_html}</div></div>'

    js = f'''
<script>
function switchAdvHorizon(period) {{
    var containers = document.querySelectorAll('.adv-dec-period');
    containers.forEach(function(el) {{
        el.style.display = el.dataset.period === period ? 'flex' : 'none';
    }});
    var buttons = document.querySelectorAll('#adv-horizon-buttons .adv-horizon-btn');
    buttons.forEach(function(btn) {{
            btn.style.backgroundColor = btn.dataset.period === period ? '{BG_BUTTON_PRIMARY}' : '{BG_BUTTON_SECONDARY}';
    }});
}}
</script>
'''

    body = ''.join(periods_html.values())
    return selector_html + js + f'<div style="font-family: {FONT_PRIMARY}; width: 100%;">{body}</div>'


def generate_main_performance_chart(ts_data, benchmark_ticker, annual_yield):
    """
    Generates the main portfolio performance chart with time horizon selection.
    """
    # Portfolio Performance Chart
    fig = go.Figure()
    fig.update_layout(
        title="Portfolio Performance Over Time",
        font=dict(color=TEXT_MUTED),
        height=700,
    )

    # Calculate base series
    base_returns = ts_data["total"].pct_change().fillna(0)
    
    series_map = {
        "Portfolio % Capital Gain": (1 + base_returns).cumprod() - 1,
    }
    if not ts_data["benchmark"].empty:
        series_map[f"Benchmark ({get_benchmark_name(benchmark_ticker)}) % Performance"] = (ts_data["benchmark"] / ts_data["benchmark"].iloc[0]) - 1

    # Pre-calculate data for each period
    periods = {
        '1W': pd.DateOffset(weeks=1),
        '1M': pd.DateOffset(months=1),
        '3M': pd.DateOffset(months=3),
        '1Y': pd.DateOffset(years=1),
        '5Y': pd.DateOffset(years=5),
        'All': None
    }
    precalculated_data = {}
    last_date = ts_data["total"].index[-1]

    for period, offset in periods.items():
        period_series = []
        for name, series in series_map.items():
            if offset:
                start_date = last_date - offset
                sliced = series[series.index >= start_date]
            else:
                sliced = series
            
            # Normalize to 0% at start
            if not sliced.empty:
                start_val = sliced.iloc[0]
                normalized = ((1 + sliced) / (1 + start_val) - 1).tolist()
                
                period_series.append({
                    "name": name,
                    "x": sliced.index.strftime('%Y-%m-%d').tolist(),
                    "y": normalized
                })
        precalculated_data[period] = period_series

    # Add default trace (5Y)
    default_data = precalculated_data.get('5Y', [])
    for trace in default_data:
        color = CHART_LINE_CAPITAL_GAIN if 'Capital Gain' in trace['name'] else CHART_LINE_SINCE_INCEPTION
        fig.add_trace(go.Scatter(x=trace['x'], y=trace['y'], name=trace['name'], mode='lines', line=dict(width=3, color=color)))

    fig.update_layout(
        yaxis_tickformat=".0%",
        xaxis_showgrid=True,
        yaxis_showgrid=True,
        xaxis_gridcolor=CHART_GRID,
        yaxis_gridcolor=CHART_GRID,
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        legend=dict(orientation="h", y=-0.2, yanchor="top"),
        hovermode="x unified",
    )
    chart_div_id = "portfolio-performance-chart"
    chart_html = fig.to_html(full_html=False, include_plotlyjs=False, div_id=chart_div_id)

    # JavaScript to switch series
    json_period_data = json.dumps(precalculated_data)
    js = f'''
<script>
    var periodData = {json_period_data};
    function setTimeHorizon(period) {{
        var gd = document.getElementById('{chart_div_id}');
        if (!gd || !periodData[period]) return;
        
        var newY = [];
        var newX = [];
        for (var i = 0; i < periodData[period].length; i++) {{
            newY.push(periodData[period][i].y);
            newX.push(periodData[period][i].x);
        }}
        
        Plotly.restyle(gd, {{y: newY, x: newX}});
        
        var buttons = document.querySelectorAll('#time-horizon-buttons .time-horizon-btn');
        buttons.forEach(function(btn) {{
        btn.style.backgroundColor = btn.dataset.period === period ? '{BG_BUTTON_PRIMARY}' : '{BG_BUTTON_SECONDARY}';
        }});
    }}
</script>
'''

    # Time Horizon Selector HTML
    periods = ['1W', '1M', '3M', '1Y', '5Y', 'All']
    buttons = []
    for p in periods:
        active = (p == '5Y')
        style = f'background-color: {BG_BUTTON_PRIMARY if active else BG_BUTTON_SECONDARY}; color: {BUTTON_TEXT};'
        btn = f'<button type="button" class="time-horizon-btn" data-period="{p}" onclick="setTimeHorizon(\'{p}\')" style="{style} border: none; padding: 6px 12px; cursor: pointer; border-radius: 4px; font-weight: bold; font-size: 0.85em;">{p}</button>'
        buttons.append(btn)
    buttons_html = '<div id="time-horizon-buttons" style="display: inline-flex; gap: 5px;">' + ''.join(buttons) + '</div>'
    selector_html = f'<div style="margin-bottom: 10px;"><span style="font-weight: bold; color: {TABLE_PERIOD_LABEL_TEXT}; font-size: 0.85em; margin-right: 5px;">Time Horizon:</span>{buttons_html}</div>'

    return selector_html + chart_html + js
    
