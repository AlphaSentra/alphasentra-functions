import pandas as pd
import numpy as np
import plotly.graph_objects as go
from statsmodels.tsa.arima.model import ARIMA
from config import (
    EFFICIENCY_LABEL_FONT,
    EFFICIENCY_SHARPE_LINE, EFFICIENCY_SORTINO_LINE, EFFICIENCY_IR_LINE,
    EFFICIENCY_3D_START_MARKER, EFFICIENCY_3D_CURRENT_MARKER, EFFICIENCY_3D_ALPHA_PLANE,
    EFFICIENCY_COMPOSITE_GOOD, EFFICIENCY_COMPOSITE_BAD,
    EFFICIENCY_3D_BG, EFFICIENCY_3D_GRID, EFFICIENCY_3D_ZEROLINE,
    EFFICIENCY_3D_BUTTON_ACTIVE, EFFICIENCY_3D_BUTTON_INACTIVE,
    LIGHT_ELEMENT, CHART_TRANSPARENT, ZERO_RETURN_CELL_TEXT,
    POSITIVE_RETURN_CARD, NEGATIVE_RETURN_CARD, NEUTRAL_GRAY, TEXT_MUTED, TEXT_PRIMARY,
    EFFICIENCY_BETA_CARD, HEADING_TEXT,
    SHADOW_SUBTLE, SHADOW_MEDIUM, SHADOW_STRONG, GAUGE_ZERO_LINE, TEXT_LABEL_GAUGE,
    GAUGE_TRACK_BG, NO_PRICE_COLOR, FONT_PRIMARY,
    BORDER_THEME, BG_ROW_HEADER, BG_ROW_HIGHLIGHT, BG_ROW_HOVER, BG_ROW_ALT, BG_ROW_ALT_ALT,
    BG_BUTTON_PRIMARY, BG_BUTTON_PRIMARY_HOVER,
    BG_CHART, CHART_GRID
)


def generate_rolling_metrics_line_chart(returns_series, benchmark_returns, risk_free_rate=0.02, window=252):
    """
    Generates a line chart of 1-year rolling Sharpe, Sortino, and Information Ratios.
    """
    if returns_series is None or len(returns_series) < window + 10:
        return "<p>Insufficient data for rolling 1-year metrics chart.</p>"

    daily_rf = (1 + risk_free_rate) ** (1/252) - 1
    
    # Calculate rolling Sharpe
    rolling_mean = returns_series.rolling(window=window).mean()
    rolling_std = returns_series.rolling(window=window).std()
    rolling_sharpe = ((rolling_mean - daily_rf) / rolling_std) * np.sqrt(252)
    
    # Calculate rolling Sortino
    # We need to compute downside deviation rolling
    def sortino_rolling(window_returns):
        downside = window_returns[window_returns < 0]
        downside_std = downside.std()
        if pd.isna(downside_std) or downside_std == 0:
            return np.nan
        ann_ret = (1 + window_returns).prod() - 1
        # In a strict 252 window, this is already 1 year, so ann_ret is just the compound return
        return (ann_ret - risk_free_rate) / (downside_std * np.sqrt(252))

    rolling_sortino = returns_series.rolling(window=window).apply(sortino_rolling, raw=False)
    
    # Calculate rolling Information Ratio
    rolling_ir = pd.Series(index=returns_series.index, dtype=float)
    if benchmark_returns is not None and not benchmark_returns.empty:
        common_idx = returns_series.index.intersection(benchmark_returns.index)
        if len(common_idx) > window:
            excess = (returns_series.loc[common_idx] - benchmark_returns.loc[common_idx]).dropna()
            rolling_excess_mean = excess.rolling(window=window).mean()
            rolling_excess_std = excess.rolling(window=window).std()
            rolling_ir = (rolling_excess_mean / rolling_excess_std) * np.sqrt(252)

    fig = go.Figure()

    # Add traces
    fig.add_trace(go.Scatter(
        x=rolling_sharpe.index, y=rolling_sharpe,
        mode='lines', name='Sharpe Ratio',
        line=dict(color=EFFICIENCY_SHARPE_LINE, width=2)
    ))
    
    fig.add_trace(go.Scatter(
        x=rolling_sortino.index, y=rolling_sortino,
        mode='lines', name='Sortino Ratio',
        line=dict(color=EFFICIENCY_SORTINO_LINE, width=2)
    ))

    if not rolling_ir.isna().all():
        fig.add_trace(go.Scatter(
            x=rolling_ir.index, y=rolling_ir,
            mode='lines', name='Information Ratio',
            line=dict(color=EFFICIENCY_IR_LINE, width=2)
        ))

    # Add zero line
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="black")

    # First valid date across all series (after rolling window warmup)
    valid_starts = [
        s.first_valid_index()
        for s in [rolling_sharpe, rolling_sortino, rolling_ir]
        if s.first_valid_index() is not None
    ]
    x_start = min(valid_starts).isoformat() if valid_starts else None
    x_end   = rolling_sharpe.index[-1].isoformat() if not rolling_sharpe.empty else None

    fig.update_layout(
        title='Rolling 1-Year Efficiency Metrics',
        title_font=dict(color=TEXT_MUTED),
        xaxis_title='Date',
        yaxis_title='Ratio',
        height=500,
        margin=dict(l=40, r=40, t=50, b=40),
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        font=dict(color=TEXT_PRIMARY),
        legend_font=dict(color=TEXT_MUTED),
        legend_title_font=dict(color=TEXT_MUTED),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode='x unified',
        xaxis=dict(
            rangeslider=dict(visible=True),   # default thickness matches correlation chart
            type='date',
            showgrid=True,
            gridcolor=CHART_GRID,
            title_font=dict(color=TEXT_MUTED),
            tickfont=dict(color=TEXT_MUTED),
            range=[x_start, x_end]            # start exactly where data begins
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=CHART_GRID,
            title_font=dict(color=TEXT_MUTED),
            tickfont=dict(color=TEXT_MUTED)
        )
    )
    
    return fig.to_html(full_html=False, include_plotlyjs=False)

def generate_3d_risk_trajectory(returns_series, benchmark_returns, risk_free_rate=0.02, window=252):
    """
    Generates a 3D scatter/line chart showing the 1-year rolling trajectory of:
      X = Rolling Beta  (market sensitivity)
      Y = Rolling Correlation (with benchmark)
      Z = Rolling Alpha (annualised excess return vs CAPM, expressed as %)
    Points are coloured from cool-purple (earliest) to warm-pink (latest) to convey time progression.
    """
    import json
    if returns_series is None or benchmark_returns is None:
        return "<p>Insufficient data for 3D Risk Trajectory chart.</p>"

    # Align on common dates
    common_idx = returns_series.index.intersection(benchmark_returns.index)
    if len(common_idx) < window + 10:
        return "<p>Insufficient overlapping data for 3D Risk Trajectory chart (need at least 1 year + benchmark).</p>"

    port  = returns_series.loc[common_idx]
    bench = benchmark_returns.loc[common_idx]

    dates  = []
    betas  = []
    corrs  = []
    alphas = []

    for i in range(window, len(common_idx) + 1):
        p_win = port.iloc[i - window: i]
        b_win = bench.iloc[i - window: i]

        b_var = b_win.var()
        if b_var == 0 or pd.isna(b_var):
            continue

        beta = p_win.cov(b_win) / b_var
        corr = p_win.corr(b_win)

        # Annualised alpha: compound portfolio return minus CAPM expectation
        port_ann  = (1 + p_win).prod() - 1
        bench_ann = (1 + b_win).prod() - 1
        alpha = port_ann - (risk_free_rate + beta * (bench_ann - risk_free_rate))

        if pd.isna(beta) or pd.isna(corr) or pd.isna(alpha):
            continue

        dates.append(common_idx[i - 1])
        betas.append(float(beta))
        corrs.append(float(corr))
        alphas.append(float(alpha) * 100)   # express as %

    if not dates:
        return "<p>Could not calculate rolling metrics for 3D trajectory.</p>"

    n           = len(dates)
    t_norm      = list(range(n))
    date_labels = [d.strftime("%Y-%m-%d") for d in dates]

    # Pre-calculate periods for the interactive time horizon selector
    period_days = {
        '1W': 5,
        '1M': 22,
        '3M': 63,
        '1Y': 252,
        '5Y': 1260
    }

    precalculated_trajectory = {}
    for period, days in period_days.items():
        if days is not None and len(dates) > days:
            slice_betas = betas[-days:]
            slice_corrs = corrs[-days:]
            slice_alphas = alphas[-days:]
            slice_date_labels = date_labels[-days:]
        else:
            slice_betas = betas
            slice_corrs = corrs
            slice_alphas = alphas
            slice_date_labels = date_labels

        k = len(slice_betas)
        if k == 0:
            continue

        bx = [min(slice_betas), max(slice_betas)]
        cy = [min(slice_corrs), max(slice_corrs)]

        precalculated_trajectory[period] = {
            't0': {
                'x': slice_betas,
                'y': slice_corrs,
                'z': slice_alphas,
                'text': slice_date_labels,
                'marker_color': list(range(k)),
                'tickvals': [0, k - 1],
                'ticktext': [slice_date_labels[0], slice_date_labels[-1]]
            },
            't1': {
                'x': [slice_betas[0]],
                'y': [slice_corrs[0]],
                'z': [slice_alphas[0]],
                'text': [f"Start<br>{slice_date_labels[0]}"]
            },
            't2': {
                'x': [slice_betas[-1]],
                'y': [slice_corrs[-1]],
                'z': [slice_alphas[-1]],
                'text': [f"Current<br>{slice_date_labels[-1]}"]
            },
            't3': {
                'x': [[bx[0], bx[1]], [bx[0], bx[1]]],
                'y': [[cy[0], cy[0]], [cy[1], cy[1]]],
                'z': [[0, 0], [0, 0]]
            }
        }

    fig = go.Figure()

    # ── Trajectory points (big markers colored by time) ──
    fig.add_trace(go.Scatter3d(
        x=betas,
        y=corrs,
        z=alphas,
        mode='markers',
        marker=dict(
            size=8,
            color=t_norm,
            colorscale='Plasma',
            opacity=0.9,
            colorbar=dict(
                title=dict(text='Time →', side='right'),
                tickvals=[0, n - 1],
                ticktext=[date_labels[0], date_labels[-1]],
                len=0.55,
                thickness=14,
                x=1.01,
                outlinewidth=0
            )
        ),
        text=date_labels,
        hovertemplate=(
            "<b>%{text}</b><br>Beta: %{x:.3f}<br>Correlation: %{y:.3f}<br>Alpha: %{z:.2f}%"
        ),
        name='Trajectory',
        showlegend=True
    )) 


    # ── Start marker ──
    fig.add_trace(go.Scatter3d(
        x=[betas[0]],
        y=[corrs[0]],
        z=[alphas[0]],
        mode='markers+text',
        marker=dict(size=9, color=EFFICIENCY_3D_START_MARKER, symbol='circle',
                    line=dict(color=LIGHT_ELEMENT, width=1.5)),
        text=[f"Start<br>{date_labels[0]}"] ,
        textposition='top center',
        textfont=dict(size=10, color=EFFICIENCY_3D_START_MARKER),
        hovertemplate=f"<b>Start</b><br>Beta: %{{x:.3f}}<br>Correlation: %{{y:.3f}}<br>Alpha: %{{z:.2f}}%",
        showlegend=True,
        name='Start'
    ))

    # ── Current point (more visible) ──
    fig.add_trace(go.Scatter3d(
        x=[betas[-1]],
        y=[corrs[-1]],
        z=[alphas[-1]],
        mode='markers+text',
        marker=dict(size=15, color=EFFICIENCY_3D_CURRENT_MARKER, symbol='diamond',
                    line=dict(color=LIGHT_ELEMENT, width=3)),
        text=[f"Current<br>{date_labels[-1]}"] ,
        textposition='top center',
        textfont=dict(size=12, color=EFFICIENCY_3D_CURRENT_MARKER),
        hovertemplate=f"<b>Current</b><br>Beta: %{{x:.3f}}<br>Correlation: %{{y:.3f}}<br>Alpha: %{{z:.2f}}%",
        showlegend=True,
        name='Current'
    ))

    # ── Alpha = 0 reference plane ──
    bx = [min(betas),  max(betas)]
    cy = [min(corrs),  max(corrs)]
    fig.add_trace(go.Surface(
        x=[[bx[0], bx[1]], [bx[0], bx[1]]],
        y=[[cy[0], cy[0]], [cy[1], cy[1]]],
        z=[[0, 0], [0, 0]],
        opacity=0.12,
        colorscale=[[0, EFFICIENCY_3D_ALPHA_PLANE], [1, EFFICIENCY_3D_ALPHA_PLANE]],
        showscale=False,
        hoverinfo='skip',
        name='Alpha = 0',
        showlegend=True
    ))

    fig.update_layout(
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        font=dict(color=TEXT_PRIMARY),
        title=dict(
            text='3D Rolling Portfolio Dynamics  ·  Beta / Correlation / Alpha  (1Y Rolling)',
            font=dict(size=15, color=TEXT_MUTED)
        ),
        scene=dict(
            xaxis=dict(title='Rolling Beta',
                       showbackground=True,
                       backgroundcolor=EFFICIENCY_3D_BG,
                       gridcolor=EFFICIENCY_3D_GRID,
                       zeroline=True,
                       zerolinecolor=EFFICIENCY_3D_ZEROLINE,
                       zerolinewidth=2,
                       title_font=dict(color=TEXT_MUTED),
                       tickfont=dict(color=TEXT_MUTED)),
            yaxis=dict(title='Rolling Correlation',
                       showbackground=True,
                       backgroundcolor=EFFICIENCY_3D_BG,
                       gridcolor=EFFICIENCY_3D_GRID,
                       zeroline=True,
                       zerolinecolor=EFFICIENCY_3D_ZEROLINE,
                       zerolinewidth=2,
                       title_font=dict(color=TEXT_MUTED),
                       tickfont=dict(color=TEXT_MUTED)),
            zaxis=dict(title='Rolling Alpha (%)',
                       showbackground=True,
                       backgroundcolor=EFFICIENCY_3D_BG,
                       gridcolor=EFFICIENCY_3D_GRID,
                       zeroline=True,
                       zerolinecolor=EFFICIENCY_3D_ZEROLINE,
                       zerolinewidth=2,
                       title_font=dict(color=TEXT_MUTED),
                       tickfont=dict(color=TEXT_MUTED)),
            bgcolor=BG_CHART,
            camera=dict(eye=dict(x=1.4, y=1.4, z=1.2)),
            aspectmode='manual',
            aspectratio=dict(x=1, y=1, z=1)
        ),
        margin=dict(l=10, r=10, t=60, b=80, pad=0),
        showlegend=True,
        legend_font=dict(color=TEXT_MUTED),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=-0.12,
            xanchor='center',
            x=0.5,
            font=dict(size=11, color=TEXT_MUTED)
        ),
        height=650
    )

    chart_div_id = "risk-trajectory-3d-chart"
    chart_html = fig.to_html(full_html=False, include_plotlyjs=False, div_id=chart_div_id, config={'responsive': True, 'auto_margin': False, 'scrollZoom': False})

    # Generate horizon selector if we have multiple periods available
    selector_html = ""
    js_code = ""
    if len(precalculated_trajectory) > 1:
        json_trajectory_data = json.dumps(precalculated_trajectory)
        btn_order = ['1W', '1M', '3M', '1Y', '5Y']
        buttons = []
        for p in btn_order:
            if p in precalculated_trajectory:
                default_period = next((pp for pp in reversed(btn_order) if pp in precalculated_trajectory), btn_order[-1])
                active = (p == default_period)
                style = f'background-color: {EFFICIENCY_3D_BUTTON_ACTIVE};' if active else f'background-color: {EFFICIENCY_3D_BUTTON_INACTIVE};'
                btn = f'<button type="button" class="traj-horizon-btn" data-period="{p}" onclick="set3DHorizon(\'{p}\')" style="{style}">{p}</button>'
                buttons.append(btn)

        buttons_html = '<div id="trajectory-horizon-buttons" class="traj-horizon-buttons">' + ''.join(buttons) + '</div>'
        selector_html = f'<div class="traj-horizon-wrapper"><span class="traj-horizon-label">Time Horizon:</span>{buttons_html}</div>'

        js_code = f'''
<script>
    var trajectoryData = {json_trajectory_data};
    function set3DHorizon(period) {{
        var gd = document.getElementById('{chart_div_id}');
        if (!gd || !trajectoryData[period]) return;

        var pData = trajectoryData[period];

        // Restyle coordinates of traces (0: Trajectory, 1: Start, 2: Current, 3: Alpha = 0 plane)
        Plotly.restyle(gd, {{
            'x': [pData.t0.x, pData.t1.x, pData.t2.x, pData.t3.x],
            'y': [pData.t0.y, pData.t1.y, pData.t2.y, pData.t3.y],
            'z': [pData.t0.z, pData.t1.z, pData.t2.z, pData.t3.z],
            'text': [pData.t0.text, pData.t1.text, pData.t2.text, null]
        }}, [0, 1, 2, 3]);

        // Restyle marker and colorbar tick properties on Trace 0 (Trajectory points)
        Plotly.restyle(gd, {{
            'marker.color': [pData.t0.marker_color],
            'marker.colorbar.tickvals': [pData.t0.tickvals],
            'marker.colorbar.ticktext': [pData.t0.ticktext]
        }}, [0]);

        // Update button active state colors
        var buttons = document.querySelectorAll('#trajectory-horizon-buttons .traj-horizon-btn');
        buttons.forEach(function(btn) {{
        btn.style.backgroundColor = btn.dataset.period === period ? 'var(--color-bg-button-primary)' : 'var(--color-bg-button-secondary)';
        }});
    }}
</script>
'''
    return selector_html + chart_html + js_code

def generate_rolling_metrics_table(returns_series, benchmark_returns, risk_free_rate=0.02, window=252):
    """
    Generates a Bloomberg-style HTML table of 1-year rolling metrics ordered by date DESC.
    """
    if returns_series is None or benchmark_returns is None:
        return "<p>Insufficient data for metrics table.</p>"

    common_idx = returns_series.index.intersection(benchmark_returns.index)
    if len(common_idx) < window + 10:
        return "<p>Insufficient overlapping data for metrics table.</p>"

    port  = returns_series.loc[common_idx]
    bench = benchmark_returns.loc[common_idx]

    daily_rf = (1 + risk_free_rate) ** (1/252) - 1

    # Rolling calculations
    port_rolling_mean = port.rolling(window=window).mean()
    port_rolling_std = port.rolling(window=window).std()
    
    sharpe = ((port_rolling_mean - daily_rf) / port_rolling_std) * np.sqrt(252)

    def sortino_rolling(w):
        downside = w[w < 0]
        downside_std = downside.std()
        if pd.isna(downside_std) or downside_std == 0:
            return np.nan
        ann_ret = (1 + w).prod() - 1
        return (ann_ret - risk_free_rate) / (downside_std * np.sqrt(252))
    
    sortino = port.rolling(window=window).apply(sortino_rolling, raw=False)

    excess = port - bench
    rolling_excess_mean = excess.rolling(window=window).mean()
    rolling_excess_std = excess.rolling(window=window).std()
    ir = (rolling_excess_mean / rolling_excess_std) * np.sqrt(252)

    cov_pb = port.rolling(window=window).cov(bench)
    var_b = bench.rolling(window=window).var()
    beta = cov_pb / var_b

    corr = port.rolling(window=window).corr(bench)

    def ann_ret_rolling(w):
        return (1+w).prod() - 1

    port_ann = port.rolling(window=window).apply(ann_ret_rolling, raw=False)
    bench_ann = bench.rolling(window=window).apply(ann_ret_rolling, raw=False)
    
    alpha = port_ann - (risk_free_rate + beta * (bench_ann - risk_free_rate))
    alpha = alpha * 100

    df = pd.DataFrame({
        'Date': port.index,
        'Sharpe Ratio': sharpe,
        'Sortino Ratio': sortino,
        'Information Ratio': ir,
        'Alpha (%)': alpha,
        'Beta': beta,
        'Correlation': corr
    })

    # Drop NaNs and group by month to make the table clean and manageable
    # (otherwise thousands of daily rows might freeze the browser when sorting)
    df = df.dropna()
    df = df.set_index('Date').groupby(pd.Grouper(freq='ME')).last().reset_index()
    # In case pd.Grouper(freq='ME') fails in older pandas versions, fallback to 'M':
    # Actually 'ME' is newer, let's use 'M' or just resample
    # Try using 'ME' for newer pandas, fallback to 'M' for older
    try:
        df = df.set_index('Date').groupby(pd.Grouper(freq='ME')).last().reset_index()
    except ValueError:
        df = df.set_index('Date').groupby(pd.Grouper(freq='M')).last().reset_index()

    df['Alpha_diff'] = df['Alpha (%)'].diff()
    df['Beta_diff'] = df['Beta'].diff()

    df = df.sort_values(by='Date', ascending=False)
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    
    html = ['<table id="efficiency-metrics-table">']
    html.append('<thead><tr>')
    cols = ['Date', 'Sharpe Ratio', 'Sortino Ratio', 'Information Ratio', 'Alpha (%)', 'Beta', 'Correlation']
    for col in cols:
        align_style = 'text-align: center;' if col != 'Date' else 'text-align: left;'
        html.append(f'<th onclick="sortEfficiencyTable(\'efficiency-metrics-table\', this)" style="cursor:pointer; {align_style}" title="Sort by {col}">{col} <span class="sort-icon"></span></th>')
    html.append('</tr></thead>')
    html.append('<tbody>')

    def get_gauge_params(series):
        v_min, v_max = series.min(), series.max()
        v_range = v_max - v_min
        if v_range == 0: v_range = 1
        pad = v_range * 0.05
        return v_min - pad, v_max + pad

    sr_min, sr_max = get_gauge_params(df['Sharpe Ratio'])
    srt_min, srt_max = get_gauge_params(df['Sortino Ratio'])
    info_min, info_max = get_gauge_params(df['Information Ratio'])

    def render_gauge(val, v_min, v_max, color):
        if pd.isna(val): return "-"
        v_range = v_max - v_min if v_max > v_min else 1
        val_pct = max(0, min(100, (val - v_min) / v_range * 100))
        zero_pct = max(0, min(100, (0 - v_min) / v_range * 100))
        
        return f"""<div class="gauge-container">
            <span class="gauge-value" style="color: {color};">{val:.3f}</span>
            <div class="gauge-track">
                <div class="gauge-zero-line" style="left: {zero_pct}%;"></div>
                <div class="gauge-marker" style="left: {val_pct}%; background: {color};"></div>
            </div>
        </div>"""

    def render_pill(val, is_pct=False, invert_colors=False):
        if pd.isna(val):
            return ""

        # Arrow always follows the actual direction of change
        if val > 0:
            arrow = "▲"
            display_val = val
        elif val < 0:
            arrow = "▼"
            display_val = abs(val)
        else:
            arrow = "–"
            display_val = abs(val)

        # Color logic: optionally invert (e.g. rising Beta is bad = red)
        if val > 0:
            good = not invert_colors
        elif val < 0:
            good = invert_colors
        else:
            good = None

        if good is True:
            pill_class = "diff-pill positive"
        elif good is False:
            pill_class = "diff-pill negative"
        else:
            pill_class = "diff-pill"

        fmt_val = f"{display_val:.2f}%" if is_pct else f"{display_val:.3f}"
        return f'<div class="diff-pill-wrapper"><div class="{pill_class}">{arrow} {fmt_val}</div></div>'

    for _, row in df.iterrows():
        date_str = row['Date']
        sr = row['Sharpe Ratio']
        srt = row['Sortino Ratio']
        info = row['Information Ratio']
        alp = row['Alpha (%)']
        b = row['Beta']
        c = row['Correlation']
        alp_diff = row.get('Alpha_diff', np.nan)
        b_diff = row.get('Beta_diff', np.nan)

        html.append('<tr>')
        html.append(f'<td>{date_str}</td>')
        
        # Color formatting
        sr_color = POSITIVE_RETURN_CARD if sr > 0 else NEGATIVE_RETURN_CARD if sr < 0 else "inherit"
        srt_color = POSITIVE_RETURN_CARD if srt > 0 else NEGATIVE_RETURN_CARD if srt < 0 else "inherit"
        info_color = POSITIVE_RETURN_CARD if info > 0 else NEGATIVE_RETURN_CARD if info < 0 else "inherit"
        alp_color = POSITIVE_RETURN_CARD if alp > 0 else NEGATIVE_RETURN_CARD if alp < 0 else "inherit"

        html.append(f'<td class="metrics-td-center">{render_gauge(sr, sr_min, sr_max, sr_color)}</td>')
        html.append(f'<td class="metrics-td-center">{render_gauge(srt, srt_min, srt_max, srt_color)}</td>')
        html.append(f'<td class="metrics-td-center">{render_gauge(info, info_min, info_max, info_color)}</td>')
        html.append(f'<td class="metrics-td-center" style="color: {alp_color}; font-weight: bold; font-family: var(--font-mono); font-size: 1.05em;">{alp:.2f}%{render_pill(alp_diff, is_pct=True)}</td>')
        html.append(f'<td class="metrics-td-center"><div style="font-family: var(--font-mono); font-size: 1.05em;">{b:.3f}</div>{render_pill(b_diff, is_pct=False, invert_colors=True)}</td>')
        html.append(f'<td class="metrics-td-center">{c:.3f}</td>')
        html.append('</tr>')

    html.append('</tbody></table>')
    
    script = """
    <script>
    function sortEfficiencyTable(tableId, thElement) {
        const table = document.getElementById(tableId);
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const headers = Array.from(table.querySelectorAll('th'));
        const colIndex = headers.indexOf(thElement);
        
        let isAsc = thElement.classList.contains('asc');
        
        headers.forEach(th => th.classList.remove('asc', 'desc'));
        
        isAsc = !isAsc;
        thElement.classList.add(isAsc ? 'asc' : 'desc');
        
        rows.sort((a, b) => {
            const aText = a.children[colIndex].textContent.trim();
            const bText = b.children[colIndex].textContent.trim();
            
            if (colIndex === 0) {
                return isAsc ? aText.localeCompare(bText) : bText.localeCompare(aText);
            }
            
            const aNum = parseFloat(aText);
            const bNum = parseFloat(bText);
            
            if (!isNaN(aNum) && !isNaN(bNum)) {
                return isAsc ? aNum - bNum : bNum - aNum;
            }
            
            return isAsc ? aText.localeCompare(bText) : bText.localeCompare(aText);
        });
        
        rows.forEach(row => tbody.appendChild(row));
    }
    </script>
    """
    
    return f'<div id="efficiency-metrics-wrapper">\n{script}\n' + "".join(html) + '\n</div>'


def generate_efficiency_metrics_strip(returns_series, benchmark_returns, risk_free_rate=0.02, window=252):
    """
    Generates header strip with key efficiency metrics including mini sparkline charts.
    """
    if returns_series is None or benchmark_returns is None:
        return ""
    common_idx = returns_series.index.intersection(benchmark_returns.index)
    if len(common_idx) < window + 10:
        return ""
    
    port = returns_series.loc[common_idx]
    bench = benchmark_returns.loc[common_idx]
    daily_rf = (1 + risk_free_rate) ** (1/252) - 1

    port_rolling_mean = port.rolling(window=window).mean()
    port_rolling_std = port.rolling(window=window).std()
    sharpe = ((port_rolling_mean - daily_rf) / port_rolling_std) * np.sqrt(252)

    def sortino_rolling(w):
        downside = w[w < 0]
        downside_std = downside.std()
        if pd.isna(downside_std) or downside_std == 0:
            return np.nan
        ann_ret = (1 + w).prod() - 1
        return (ann_ret - risk_free_rate) / (downside_std * np.sqrt(252))
    
    sortino = port.rolling(window=window).apply(sortino_rolling, raw=False)

    excess = port - bench
    rolling_excess_mean = excess.rolling(window=window).mean()
    rolling_excess_std = excess.rolling(window=window).std()
    ir = (rolling_excess_mean / rolling_excess_std) * np.sqrt(252)

    cov_pb = port.rolling(window=window).cov(bench)
    var_b = bench.rolling(window=window).var()
    beta = cov_pb / var_b

    def ann_ret_rolling(w):
        return (1+w).prod() - 1
    
    port_ann = port.rolling(window=window).apply(ann_ret_rolling, raw=False)
    bench_ann = bench.rolling(window=window).apply(ann_ret_rolling, raw=False)
    alpha = (port_ann - (risk_free_rate + beta * (bench_ann - risk_free_rate))) * 100

    metrics = {
        'Sharpe Ratio': sharpe,
        'Sortino Ratio': sortino,
        'Information Ratio': ir,
        'Alpha (%)': alpha,
        'Beta (1Y Rolling)': beta
    }
    
    anchor = port.index.max()
    start_1y = anchor - pd.DateOffset(years=1)
    port_1y = port.loc[port.index >= start_1y]
    bench_1y = bench.loc[bench.index >= start_1y]
    common_1y = port_1y.index.intersection(bench_1y.index)
    port_1y = port_1y.loc[common_1y]
    bench_1y = bench_1y.loc[common_1y]

    def _fixed_sharpe(p, b):
        if len(p) < 2 or p.std() == 0:
            return np.nan
        return ((p.mean() - daily_rf) / p.std()) * np.sqrt(252)

    def _fixed_sortino(p):
        if len(p) < 2:
            return np.nan
        downside = p[p < 0]
        if downside.empty or downside.std() == 0:
            return np.nan
        ann_ret = (1 + p).prod() - 1
        n = len(p)
        ann_ret = (1 + ann_ret) ** (252 / n) - 1
        return (ann_ret - risk_free_rate) / (downside.std() * np.sqrt(252))

    def _fixed_ir(p, b):
        if len(p) < 2:
            return np.nan
        excess = p - b
        if excess.std() == 0:
            return np.nan
        return (excess.mean() / excess.std()) * np.sqrt(252)

    fixed_1y = {
        'Sharpe Ratio': _fixed_sharpe(port_1y, bench_1y),
        'Sortino Ratio': _fixed_sortino(port_1y),
        'Information Ratio': _fixed_ir(port_1y, bench_1y),
    }
    
    def generate_gauge(series, val, color):
        """Render a Bloomberg-style linear gauge: track bar + zero tick + round marker."""
        try:
            clean = series.dropna()
            if clean.empty or pd.isna(val):
                return ""
            v_min, v_max = clean.min(), clean.max()
            v_range = v_max - v_min
            if v_range == 0:
                v_range = 1
            # Add 5% padding on each side so the marker never clips the edge
            pad = v_range * 0.05
            g_min = v_min - pad
            g_max = v_max + pad
            g_range = g_max - g_min

            val_pct  = max(0.0, min(100.0, (val  - g_min) / g_range * 100))
            zero_pct = max(0.0, min(100.0, (0.0  - g_min) / g_range * 100))

            # Min / Max labels
            if "Alpha" in series.name if hasattr(series, 'name') and series.name else False:
                lbl_min = f"{v_min:+.1f}%"
                lbl_max = f"{v_max:+.1f}%"
            else:
                lbl_min = f"{v_min:.2f}"
                lbl_max = f"{v_max:.2f}"

            return f"""
            <div style="width: 100%; padding: 4px 0 2px 0; box-sizing: border-box;">
                <!-- Track -->
                <div style="position: relative; width: 90%; margin: 0 auto; height: 6px;
                            background: {SHADOW_SUBTLE}; border-radius: 3px;
                            box-shadow: inset 0 1px 3px {SHADOW_MEDIUM};">
                    <!-- Zero line -->
                    <div style="position: absolute; left: {zero_pct:.2f}%; top: -3px;
                                height: 12px; width: 2px;
                                background: {GAUGE_ZERO_LINE}; border-radius: 1px;
                                transform: translateX(-50%);"></div>
                    <!-- Round marker -->
                    <div style="position: absolute; left: {val_pct:.2f}%;
                                top: 50%; transform: translate(-50%, -50%);
                                width: 14px; height: 14px; border-radius: 50%;
                                background: {color};
                                box-shadow: 0 0 0 2px {LIGHT_ELEMENT}, 0 0 0 3.5px {color}, 0 2px 6px {SHADOW_STRONG};
                                z-index: 2;"></div>
                </div>
                <!-- Min / Max labels -->
                <div style="display: flex; justify-content: space-between; width: 90%; margin: 4px auto 0 auto;">
                    <span style="font-size: 0.68em; color: {TEXT_LABEL_GAUGE};">{lbl_min}</span>
                    <span style="font-size: 0.68em; color: {TEXT_LABEL_GAUGE};">{lbl_max}</span>
                </div>
                <!-- Min / Max labels -->
                <div style="display: flex; justify-content: space-between; width: 90%; margin: 4px auto 0 auto;">
                    <span style="font-size: 0.68em; color: {TEXT_LABEL_GAUGE};">{lbl_min}</span>
                    <span style="font-size: 0.68em; color: {TEXT_LABEL_GAUGE};">{lbl_max}</span>
                </div>
            </div>"""
        except Exception:
            return ""

    def card(label, series_name, fixed_1y_val=None):
        if fixed_1y_val is not None and not pd.isna(fixed_1y_val):
            val = fixed_1y_val
            series = metrics[series_name]
        else:
            series = metrics[series_name]
            clean = series.dropna()
            val = clean.iloc[-1] if not clean.empty else np.nan

        if np.isnan(val):
            color = NEUTRAL_GRAY
        elif series_name == 'Beta (1Y Rolling)':
            color = EFFICIENCY_BETA_CARD
        else:
            color = POSITIVE_RETURN_CARD if val >= 0 else NEGATIVE_RETURN_CARD

        gauge_series = metrics[series_name] if fixed_1y_val is None else series
        gauge_html = generate_gauge(gauge_series, val, color)

        if np.isnan(val):
            val_str = "N/A"
        elif "Alpha" in series_name:
            val_str = f"{val:+.2f}%"
        else:
            val_str = f"{val:.2f}"

        return f'''
        <div class="metric-card" style="flex: 1; background-color: {color}20; border-color: {color}; border-radius: 8px;
                    padding: 10px 8px; text-align: center; box-shadow: 0 2px 4px {SHADOW_SUBTLE};
                    min-height: 110px; display: flex; flex-direction: column;
                    align-items: center; justify-content: flex-start; gap: 6px;">
            <div style="font-size: 0.75em; color: {TEXT_PRIMARY}; text-transform: uppercase; margin: 0; font-weight: bold;">{label}</div>
            <div style="font-size: 2.0em; font-weight: 900; color: {color}; margin: 0; line-height: 1;">{val_str}</div>
            {gauge_html if gauge_html else '<div style="height:30px;"></div>'}
        </div>
        '''

    html = f'''
    <div style="display: flex; gap: 10px; margin: 12px 0; font-family: {FONT_PRIMARY};">
        {card('Sharpe Ratio (1-Yr)', 'Sharpe Ratio', fixed_1y_val=fixed_1y.get('Sharpe Ratio'))}
        {card('Sortino Ratio (1-Yr)', 'Sortino Ratio', fixed_1y_val=fixed_1y.get('Sortino Ratio'))}
        {card('Info Ratio (1-Yr)', 'Information Ratio', fixed_1y_val=fixed_1y.get('Information Ratio'))}
        {card('Alpha (1-Yr)', 'Alpha (%)')}
        {card('Beta (1-Yr)', 'Beta (1Y Rolling)')}
    </div>
    '''
    return html

def generate_security_efficiency_table(returns_series, holdings_df, prices, risk_free_rate=0.02, window=252):
    """
    Generates a table of individual security efficiency metrics over the last 1 year.
    Columns: Security Name (Ticker), Weight, Expected Return (1Y), Volatility (1Y), Correlation to Portfolio (1Y), Composite Score (0-100)
    """
    if holdings_df is None or holdings_df.empty or prices is None or prices.empty:
        return "<p>Insufficient data to generate security efficiency table.</p>"

    # Ensure returns_series is valid
    if returns_series is None or returns_series.empty:
        return "<p>Insufficient portfolio return data to calculate correlation.</p>"

    port_rets_1y = returns_series.tail(window)
    
    rows_data = []
    
    # Calculate metrics for each holding
    for ticker in holdings_df.index:
        if ticker not in prices.columns:
            continue
            
        series = prices[ticker].dropna()
        if len(series) < 20:
            continue
            
        rets = series.pct_change().dropna()
        rets_1y = rets.tail(window)
        
        if len(rets_1y) < 20:
            continue
            
        # Expected Return (price-action: 12M trend + 3M momentum + mean reversion) & Volatility
        w1, w2, w3, w4 = 0.5, 0.3, 0.2, 0.2
        days_252 = min(len(series) - 1, 252)
        days_63 = min(len(series) - 1, 63)
        days_200 = min(len(series), 200)

        ret_12m = series.iloc[-1] / series.iloc[-days_252] - 1 if days_252 >= 1 else np.nan
        ret_3m = series.iloc[-1] / series.iloc[-days_63] - 1 if days_63 >= 1 else np.nan

        ma_200 = series.rolling(days_200).mean().iloc[-1] if days_200 >= 1 else np.nan
        mean_reversion = -(series.iloc[-1] / ma_200 - 1) if pd.notna(ma_200) and ma_200 != 0 else np.nan

        arima_contrib = np.nan
        if len(series.dropna()) >= 10:
            try:
                model = ARIMA(series.dropna(), order=(1, 1, 1))
                fitted = model.fit()
                forecast = fitted.forecast(steps=1).iloc[0]
                arima_contrib = (forecast / series.iloc[-1] - 1)
            except Exception:
                arima_contrib = np.nan

        expected_ret = w1 * ret_12m + w2 * ret_3m + w3 * mean_reversion + w4 * arima_contrib
        direction = holdings_df.loc[ticker, 'type'] if 'type' in holdings_df.columns else 'active'
        if direction == 'S':
            expected_ret = -expected_ret
        std_ret = rets_1y.std()
        
        if std_ret > 0:
            vol = std_ret * np.sqrt(252)
        else:
            vol = np.nan
            
        # Correlation to Portfolio
        common_idx = rets_1y.index.intersection(port_rets_1y.index)
        if len(common_idx) > 20:
            corr = rets_1y.loc[common_idx].corr(port_rets_1y.loc[common_idx])
        else:
            corr = np.nan
            
        # Composite Score Calculation
        if pd.isna(expected_ret) or pd.isna(vol) or pd.isna(corr):
            composite = np.nan
        else:
            # Expected Return Score: 0 to 20% -> 0 to 1
            if expected_ret <= 0.0:
                e_score = 0.0
            elif expected_ret >= 0.20:
                e_score = 1.0
            else:
                e_score = expected_ret / 0.20

            # Volatility Score: 5% (1.0) to 40% (0.0)
            if vol >= 0.40:
                v_score = 0.0
            elif vol <= 0.05:
                v_score = 1.0
            else:
                v_score = (0.40 - vol) / (0.40 - 0.05)

            # Correlation Score: 0.0 (1.0) to 0.8 (0.0)
            if corr >= 0.8:
                c_score = 0.0
            elif corr <= 0.0:
                c_score = 1.0
            else:
                c_score = (0.8 - corr) / 0.8

            composite = (e_score * 0.4 + v_score * 0.3 + c_score * 0.3) * 100
            
        weight = holdings_df.loc[ticker, 'Weight'] if 'Weight' in holdings_df.columns else 0.0
        name = holdings_df.loc[ticker, 'name'] if 'name' in holdings_df.columns and pd.notna(holdings_df.loc[ticker, 'name']) else ticker
        
        # If name and ticker are same, just use ticker
        sec_name = f"{name} ({ticker})" if name != ticker else ticker
        
        sector_col = 'sector' if 'sector' in holdings_df.columns else ('Sector' if 'Sector' in holdings_df.columns else None)
        industry_col = 'industry' if 'industry' in holdings_df.columns else ('Industry' if 'Industry' in holdings_df.columns else None)
        sector = holdings_df.loc[ticker, sector_col] if sector_col and pd.notna(holdings_df.loc[ticker, sector_col]) else 'Others'
        industry = holdings_df.loc[ticker, industry_col] if industry_col and pd.notna(holdings_df.loc[ticker, industry_col]) else 'Others'

        rows_data.append({
            'ticker': ticker,
            'sec_name': sec_name,
            'weight': weight,
            'expected_return': expected_ret,
            'vol': vol,
            'corr': corr,
            'composite': composite,
            'sector': sector,
            'industry': industry
        })
        
    if not rows_data:
        return "<p>No security data met the criteria for inclusion.</p>"

    # Helper function for rollup weighted averages
    def weighted_avg(items, val_key, weight_key='weight'):
        valid_items = [item for item in items if pd.notna(item[val_key]) and pd.notna(item[weight_key]) and item[weight_key] > 0]
        if not valid_items:
            # Fallback to simple average of non-nan values
            non_nan_vals = [item[val_key] for item in items if pd.notna(item[val_key])]
            return np.mean(non_nan_vals) if non_nan_vals else np.nan
        total_weight = sum(item[weight_key] for item in valid_items)
        if total_weight <= 0:
            non_nan_vals = [item[val_key] for item in items if pd.notna(item[val_key])]
            return np.mean(non_nan_vals) if non_nan_vals else np.nan
        return sum(item[val_key] * item[weight_key] for item in valid_items) / total_weight

    # Group by sector and industry
    sector_data = {}
    for item in rows_data:
        sec = item['sector']
        ind = item['industry']
        if sec not in sector_data:
            sector_data[sec] = {}
        if ind not in sector_data[sec]:
            sector_data[sec][ind] = []
        sector_data[sec][ind].append(item)

    rolled_sectors = []
    for sec, industries in sector_data.items():
        rolled_industries = []
        sec_items_all = []
        for ind, items in industries.items():
            sec_items_all.extend(items)
            # Roll up industry
            ind_weight = sum(item['weight'] for item in items)
            ind_er = weighted_avg(items, 'expected_return')
            ind_vol = weighted_avg(items, 'vol')
            ind_corr = weighted_avg(items, 'corr')
            ind_comp = weighted_avg(items, 'composite')
            
            # Sort items in industry by weight descending
            sorted_items = sorted(items, key=lambda x: x['weight'], reverse=True)
            
            rolled_industries.append({
                'name': ind,
                'weight': ind_weight,
                'expected_return': ind_er,
                'vol': ind_vol,
                'corr': ind_corr,
                'composite': ind_comp,
                'securities': sorted_items
            })
            
        # Roll up sector
        sec_weight = sum(item['weight'] for item in sec_items_all)
        sec_er = weighted_avg(sec_items_all, 'expected_return')
        sec_vol = weighted_avg(sec_items_all, 'vol')
        sec_corr = weighted_avg(sec_items_all, 'corr')
        sec_comp = weighted_avg(sec_items_all, 'composite')
        
        # Sort industries by weight descending
        sorted_industries = sorted(rolled_industries, key=lambda x: x['weight'], reverse=True)
        
        rolled_sectors.append({
            'name': sec,
            'weight': sec_weight,
            'expected_return': sec_er,
            'vol': sec_vol,
            'corr': sec_corr,
            'composite': sec_comp,
            'industries': sorted_industries
        })
        
    # Sort sectors by weight descending
    rolled_sectors = sorted(rolled_sectors, key=lambda x: x['weight'], reverse=True)

    # Generate Sunburst chart data for Composite Score
    def get_comp_color(comp_val):
        if pd.isna(comp_val):
            return ZERO_RETURN_CELL_TEXT
        if comp_val >= 60:
            return EFFICIENCY_COMPOSITE_GOOD
        elif comp_val >= 40:
            t = (comp_val - 40) / 20.0
            r = int(168 - 23 * t)
            g = int(148 + 22 * t)
            b = int(148 + 7  * t)
            return f"rgb({r}, {g}, {b})"
        else:
            return EFFICIENCY_COMPOSITE_BAD

    labels = []
    parents = []
    values = []
    colors = []
    scores = []

    for sector_item in rolled_sectors:
        s_name = sector_item['name']
        labels.append(s_name)
        parents.append("")
        values.append(sector_item['weight'] * 100)
        colors.append(get_comp_color(sector_item['composite']))
        scores.append(sector_item['composite'] if pd.notna(sector_item['composite']) else 0.0)

        for ind_item in sector_item['industries']:
            i_name = ind_item['name']
            parent_key = s_name
            label_key = f"{i_name} ({s_name})"
            labels.append(label_key)
            parents.append(parent_key)
            values.append(ind_item['weight'] * 100)
            colors.append(get_comp_color(ind_item['composite']))
            scores.append(ind_item['composite'] if pd.notna(ind_item['composite']) else 0.0)

            for sec_row in ind_item['securities']:
                sec_label = sec_row['sec_name']
                labels.append(sec_label)
                parents.append(label_key)
                values.append(sec_row['weight'] * 100)
                colors.append(get_comp_color(sec_row['composite']))
                scores.append(sec_row['composite'] if pd.notna(sec_row['composite']) else 0.0)

    fig = go.Figure(go.Sunburst(
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        customdata=scores,
        marker=dict(
            colors=colors,
            line=dict(color=LIGHT_ELEMENT, width=1.5)
        ),
        hovertemplate='<b>%{label}</b><br>Weight: %{value:.2f}%<br>Composite Score: %{customdata:.1f}<extra></extra>',
        textfont=dict(size=11, color=TEXT_PRIMARY)
    ))

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        width=500,
        height=500,
        paper_bgcolor=CHART_TRANSPARENT,
    )
    
    sunburst_html = fig.to_html(full_html=False, include_plotlyjs=False, config={'responsive': True, 'auto_margin': False})

    def format_er(er_val):
        if pd.isna(er_val):
            return '<span class="er-pill neutral">N/A</span>'
        val = er_val * 100
        pill_class = "er-pill positive" if val > 0 else "er-pill negative" if val < 0 else "er-pill neutral"
        arrow = '▲' if val > 0 else '▼' if val < 0 else ''
        return f'<span class="{pill_class}">{arrow} {val:.2f}%</span>'

    def format_composite(comp_val):
        if pd.isna(comp_val):
            return '<div style="font-family: var(--font-mono);"> - </div>'
        comp_color = get_comp_color(comp_val)
        return f"""
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: bold; font-family: var(--font-mono); min-width: 25px; color: {comp_color}; font-size: 0.9em;">{comp_val:.0f}</span>
            <div style="flex-grow: 1; height: 5px; background-color: {GAUGE_TRACK_BG}; border-radius: 3px; overflow: hidden; width: 50px;">
                <div style="width: {comp_val:.0f}%; height: 100%; background-color: {comp_color}; border-radius: 3px;"></div>
            </div>
        </div>
        """

    # Build HTML table
    html = []
    # Add a flex container with Expand/Collapse buttons
    html.append('<div style="display:flex; justify-content: flex-start; align-items:center; margin-bottom: 10px; gap: 10px;">')
    html.append('    <div style="display: flex; gap: 8px;">')
    html.append('        <button onclick="toggleAllEfficiency(true)" class="action-button">Expand All</button>')
    html.append('        <button onclick="toggleAllEfficiency(false)" class="action-button">Collapse All</button>')
    html.append('    </div>')
    html.append('</div>')
    
    html.append('<table id="security-efficiency-table">')
    html.append('<thead><tr>')
    cols_config = [
        (f'Name<br><span style="font-size: 0.85em; font-weight: normal; color: {EFFICIENCY_LABEL_FONT};">(Sector / Industry / Security)</span>', 'text-align: left;'),
        ('Weight<br>(%)', 'text-align: center; width: 60px;'),
        ('ER<br>(1Y)', 'text-align: center; width: 60px;'),
        ('Vol<br>(1Y)', 'text-align: center; width: 60px;'),
        ('Correl<br>(1Y)', 'text-align: center; width: 60px;'),
        ('Composite<br>Score', 'text-align: left; width: 80px;')
    ]
    for col_name, style in cols_config:
        html.append(f'<th style="{style}">{col_name}</th>')
    html.append('</tr></thead>')
    
    sector_idx = 0
    for sector_item in rolled_sectors:
        sector_idx += 1
        sid = f"sec-{sector_idx}"
        
        # Sector row
        s_name = sector_item['name']
        s_weight = f"{sector_item['weight'] * 100:.2f}%"
        s_er_html = format_er(sector_item['expected_return'])
        s_vol = f"{sector_item['vol'] * 100:.2f}%" if pd.notna(sector_item['vol']) else "-"
        s_corr = f"{sector_item['corr']:.3f}" if pd.notna(sector_item['corr']) else "-"
        s_comp_html = format_composite(sector_item['composite'])
        
        # Sector row HTML
        html.append('<tbody>')
        html.append(f'<tr onclick="toggleEfficiencySector(\'{sid}\')" class="sector-row">')
        html.append(f'<td><span id="eff-arrow-{sid}" class="tree-arrow">▶</span><strong>{s_name}</strong></td>')
        html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace; font-weight: bold;">{s_weight}</td>')
        html.append(f'<td style="text-align: center;">{s_er_html}</td>')
        html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace; font-weight: bold;">{s_vol}</td>')
        html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace; font-weight: bold;">{s_corr}</td>')
        html.append(f'<td>{s_comp_html}</td>')
        html.append('</tr>')
        html.append('</tbody>')
        
        # Sector's industry container
        html.append(f'<tbody id="eff-industries-{sid}" class="industry-container" style="display: none;">')
        
        industry_idx = 0
        for ind_item in sector_item['industries']:
            industry_idx += 1
            iid = f"{sid}-ind-{industry_idx}"
            
            i_name = ind_item['name']
            i_weight = f"{ind_item['weight'] * 100:.2f}%"
            i_er_html = format_er(ind_item['expected_return'])
            i_vol = f"{ind_item['vol'] * 100:.2f}%" if pd.notna(ind_item['vol']) else "-"
            i_corr = f"{ind_item['corr']:.3f}" if pd.notna(ind_item['corr']) else "-"
            i_comp_html = format_composite(ind_item['composite'])
            
            # Industry row HTML
            html.append(f'<tr onclick="toggleEfficiencyIndustry(event, \'{iid}\')" class="industry-row">')
            html.append(f'<td style="padding-left: 20px;"><span id="eff-arrow-{iid}" class="tree-arrow">▶</span>{i_name}</td>')
            html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace;">{i_weight}</td>')
            html.append(f'<td style="text-align: center;">{i_er_html}</td>')
            html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace;">{i_vol}</td>')
            html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace;">{i_corr}</td>')
            html.append(f'<td>{i_comp_html}</td>')
            html.append('</tr>')
            
            for sec_row in ind_item['securities']:
                sec_name = sec_row['sec_name']
                sec_weight = f"{sec_row['weight'] * 100:.2f}%"
                sec_er_html = format_er(sec_row['expected_return'])
                sec_vol = f"{sec_row['vol'] * 100:.2f}%" if pd.notna(sec_row['vol']) else "-"
                sec_corr = f"{sec_row['corr']:.3f}" if pd.notna(sec_row['corr']) else "-"
                sec_comp_html = format_composite(sec_row['composite'])
                
                sec_er_val = sec_row['expected_return']
                sec_er_csv = f"{'+' if sec_er_val > 0 else ''}{sec_er_val * 100:.2f}" if pd.notna(sec_er_val) else "N/A"
                sec_comp_csv = f"{sec_row['composite']:.0f}" if pd.notna(sec_row['composite']) else "-"
                sec_weight_csv = f"{sec_row['weight'] * 100:.2f}"
                sec_vol_csv = f"{sec_row['vol'] * 100:.2f}" if pd.notna(sec_row['vol']) else "-"
                sec_corr_csv = f"{sec_row['corr']:.3f}" if pd.notna(sec_row['corr']) else "-"
                # Escape any double-quotes in the name for use in data attributes
                sec_name_csv = sec_name.replace('"', '&quot;')

                html.append(f'<tr class="security-row {sid}-securities {iid}-securities" style="display: none; background-color: {LIGHT_ELEMENT};"'
                            f' data-csv-name="{sec_name_csv}"'
                            f' data-csv-weight="{sec_weight_csv}"'
                            f' data-csv-er="{sec_er_csv}"'
                            f' data-csv-vol="{sec_vol_csv}"'
                            f' data-csv-corr="{sec_corr_csv}"'
                            f' data-csv-comp="{sec_comp_csv}">')
                html.append(f'<td style="padding-left: 35px; font-size: 0.9em; color: {NO_PRICE_COLOR};">{sec_name}</td>')
                html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace; color: {NO_PRICE_COLOR};">{sec_weight}</td>')
                html.append(f'<td style="text-align: center;">{sec_er_html}</td>')
                html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace; color: {NO_PRICE_COLOR};">{sec_vol}</td>')
                html.append(f'<td style="text-align: center; font-family: \'Courier New\', monospace; color: {NO_PRICE_COLOR};">{sec_corr}</td>')
                html.append(f'<td>{sec_comp_html}</td>')
                html.append('</tr>')
                
        html.append('</tbody>')
    
    html.append('</table>')
    
    style_block = (
        f"""
        <style>
        #security-efficiency-wrapper {{
            margin-top: 15px;
            overflow-x: auto;
        }}
        #security-efficiency-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.82em;
            font-family: Arial, sans-serif;
        }}
        #security-efficiency-table thead th {{
            background-color: {BG_ROW_HEADER};
            color: {NO_PRICE_COLOR};
            font-weight: bold;
            padding: 6px 8px;
            border: 1px solid {BORDER_THEME};
            white-space: normal;
            vertical-align: bottom;
        }}
        #security-efficiency-table tbody td {{
            padding: 4px 8px;
            border: 1px solid {BORDER_THEME};
            vertical-align: middle;
        }}
        .sector-row {{
            background-color: {BG_ROW_HIGHLIGHT};
            font-weight: bold;
            cursor: pointer;
        }}
        .sector-row:hover {{
            background-color: {BG_ROW_HOVER};
        }}
        .industry-row {{
            background-color: {BG_ROW_ALT};
            cursor: pointer;
        }}
        .industry-row:hover {{
            background-color: {BG_ROW_ALT_ALT};
        }}
        .security-row:hover {{
            background-color: {BG_ROW_HOVER};
        }}
        .tree-arrow {{
            display: inline-block;
            width: 14px;
            color: {EFFICIENCY_LABEL_FONT};
            font-size: 0.8em;
        }}
        .action-button {{
            padding: 6px 12px;
            background-color: {BG_BUTTON_PRIMARY};
            color: {LIGHT_ELEMENT};
            border: none;
            cursor: pointer;
            border-radius: 4px;
            font-weight: bold;
            font-size: 0.82em;
            transition: background-color 0.2s;
        }}
        .action-button:hover {{
            background-color: {BG_BUTTON_PRIMARY_HOVER};
        }}
        </style>
        """
    )

    script_block = """
    <script>
    function toggleEfficiencySector(sid) {
        var tbody = document.getElementById('eff-industries-' + sid);
        var arrow = document.getElementById('eff-arrow-' + sid);
        if (tbody.style.display === 'none') {
            tbody.style.display = 'table-row-group';
            arrow.innerHTML = '▼';
        } else {
            tbody.style.display = 'none';
            arrow.innerHTML = '▶';
            var secRows = tbody.querySelectorAll('.security-row');
            secRows.forEach(function(row) {
                row.style.display = 'none';
            });
            var indArrows = tbody.querySelectorAll('.industry-row .tree-arrow');
            indArrows.forEach(function(arr) {
                arr.innerHTML = '▶';
            });
        }
    }
    
    function toggleEfficiencyIndustry(event, iid) {
        event.stopPropagation();
        var arrow = document.getElementById('eff-arrow-' + iid);
        var secRows = document.querySelectorAll('.' + iid + '-securities');
        
        if (secRows.length === 0) return;
        
        var currentlyHidden = secRows[0].style.display === 'none';
        
        secRows.forEach(function(row) {
            row.style.display = currentlyHidden ? 'table-row' : 'none';
        });
        
        arrow.innerHTML = currentlyHidden ? '▼' : '▶';
    }

    function toggleAllEfficiency(expand) {
        var bodies = document.querySelectorAll('.industry-container');
        var arrows = document.querySelectorAll('#security-efficiency-table .tree-arrow');
        var secRows = document.querySelectorAll('#security-efficiency-table .security-row');
        
        bodies.forEach(function(tbody) {
            tbody.style.display = expand ? 'table-row-group' : 'none';
        });
        secRows.forEach(function(row) {
            row.style.display = expand ? 'table-row' : 'none';
        });
        arrows.forEach(function(arrow) {
            arrow.innerHTML = expand ? '▼' : '▶';
        });
    }
    function exportEfficiencyToCSV(btn, filename) {
        var originalText = btn.innerHTML;
        btn.innerHTML = '<span style="font-size: 1.1em;">⏳</span> Exporting...';

        var table = document.getElementById('security-efficiency-table');
        if (!table) {
            btn.innerHTML = originalText;
            return;
        }
        var securityRows = Array.from(table.querySelectorAll('.security-row'));

        var csv = [];

        var staticHeaders = ['Name','Weight','ER (1Y)','Vol (1Y)','Correl (1Y)','Composite Score'];
        csv.push(staticHeaders.join(','));

        // Security rows — read clean values from data attributes (avoids textContent spacing issues)
        securityRows.forEach(function(row) {
            var d = row.dataset;
            var fields = [
                d.csvName   || '',
                d.csvWeight || '',
                d.csvEr     || '',
                d.csvVol    || '',
                d.csvCorr   || '',
                d.csvComp   || ''
            ];
            var rowLine = fields.map(function(val) {
                return '"' + val.replace(/"/g, '""') + '"';
            });
            csv.push(rowLine.join(','));
        });

        var lineEnding = String.fromCharCode(13) + String.fromCharCode(10);
        var csvContent = String.fromCharCode(65279) + csv.join(lineEnding);
        var blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        var link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename + '.csv';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        setTimeout(function() {
            btn.innerHTML = originalText;
        }, 1000);
    }
    </script>
    """

    style_and_script = style_block + script_block
    
    table_wrapper = f'<div id="security-efficiency-wrapper">\n{style_and_script}\n' + "".join(html) + '\n</div>'
    
    combined_layout = f"""
    <div class="efficiency-container-flex" style="display: flex; gap: 20px; align-items: flex-start; width: 100%; flex-wrap: wrap;">
        <div class="efficiency-table-column" style="flex: 1 1 0; min-width: 450px; max-width: 100%;">
            {table_wrapper}
        </div>
        <div class="efficiency-sunburst-column" style="flex: 1 1 0; min-width: 450px; max-width: 100%; display: flex; flex-direction: column; align-items: center; padding: 15px;">
            <h3 style="margin-top: 0; margin-bottom: 10px; font-size: 1.05em; font-weight: bold; color: {HEADING_TEXT}; text-align: center;">Security Efficiency Structure (Composite Score)</h3>
            <p style="margin-top: 0; margin-bottom: 15px; font-size: 0.82em; color: {TEXT_MUTED}; text-align: center; max-width: 360px;">Sized by portfolio weight. Color coded by Composite Score (Red = Poor/0, Green = Good/100). Click sectors/industries to drill down.</p>
            {sunburst_html}
        </div>
    </div>
    """
    return combined_layout

