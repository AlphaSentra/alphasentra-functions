"""
Chart generation module: All Plotly visualizations for portfolio functions.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from config import (
    SUCCESS_INDICATOR, DANGER_INDICATOR, NEUTRAL_GRAY,
    DIV_YIELD_CARD_BG, ACCENT_THEME, TEXT_MUTED, CHART_TRANSPARENT, SHADOW_SUBTLE,
    PRIMARY_TEXT, METRIC_CARD_LABEL_TEXT,
    POSITIVE_RETURN_CARD, NEGATIVE_RETURN_CARD, FONT_PRIMARY,
)



def generate_holdings_metrics_strip(holdings_df):
    """
    Generates header strip with key holdings summary metrics for the Holdings tab.

    Args:
        holdings_df (pd.DataFrame): DataFrame with holdings data including 'Weight', 'ret_1m' (or 'ret_1w'), 'z_score', 'name'.

    Returns:
        str: HTML string with metrics display
    """
    if holdings_df is None or holdings_df.empty:
        return f"<div style='text-align: center; padding: 20px; color: {TEXT_MUTED};'>No holdings data available.</div>"

    df = holdings_df.copy()
    df['Weight'] = pd.to_numeric(df['Weight'], errors='coerce').fillna(0)

    # Card 1: Total number of holdings
    total_holdings = len(df)

    # Card 2: Pie chart - count of positive-return vs negative-return positions
    # Use pnl_pct column, fallback to 1M or 1W returns
    ret_col = 'pnl_pct' if 'pnl_pct' in df.columns else ('ret_1m' if 'ret_1m' in df.columns else ('ret_1w' if 'ret_1w' in df.columns else None))
    pos_count = 0
    neg_count = 0
    if ret_col is not None:
        for idx, row in df.iterrows():
            ret = row[ret_col]
            if pd.notna(ret):
                if ret > 0:
                    pos_count += 1
                else:
                    neg_count += 1
    total_trades = pos_count + neg_count
    pos_pct = (pos_count / total_trades * 100) if total_trades > 0 else 0.0
    neg_pct = (neg_count / total_trades * 100) if total_trades > 0 else 0.0

    def generate_ret_pie(pos_c, neg_c, pos_pct_val, neg_pct_val):
        if pos_c == 0 and neg_c == 0:
            return ""
        fig = go.Figure()
        values = [pos_c, neg_c] if neg_c > 0 else [pos_c]
        labels = ['Positive', 'Negative']
        colors = [POSITIVE_RETURN_CARD, NEGATIVE_RETURN_CARD] if neg_c > 0 else [POSITIVE_RETURN_CARD]
        fig.add_trace(go.Pie(
            labels=labels,
            values=values,
            hole=0.6,
            marker_colors=colors,
            textinfo='label',
            textposition='outside',
            textfont=dict(color=PRIMARY_TEXT),
            hoverinfo='label+percent',
            showlegend=False,
            sort=False,
            marker=dict(line=dict(color='white', width=2))
        ))
        fig.update_layout(
            margin=dict(l=40, r=40, t=10, b=10),
            height=160, width=220,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    # Card 3: Bar chart - weighted avg performance of winners vs losers
    win_vals = []   # list of (weight, return)
    loss_vals = []
    # Use pnl_pct if available, otherwise fall back to 1M/1W returns
    pnl_col = 'pnl_pct' if 'pnl_pct' in df.columns else (ret_col if ret_col is not None else None)
    
    if pnl_col is not None:
        for idx, row in df.iterrows():
            pnl = row[pnl_col]
            w = row['Weight']
            if pd.notna(pnl):
                if pnl > 0:
                    win_vals.append((w, pnl))
                elif pnl < 0:
                    loss_vals.append((w, pnl))
    avg_win = np.nan
    avg_loss = np.nan
    if win_vals:
        tw = sum(w for w, r in win_vals)
        if tw > 0:
            avg_win = sum(r * w for w, r in win_vals) / tw
    if loss_vals:
        tw = sum(w for w, r in loss_vals)
        if tw > 0:
            avg_loss = sum(r * w for w, r in loss_vals) / tw

    def generate_win_loss_bar(avg_win_val, avg_loss_val):
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=['Win', 'Loss'],
            y=[avg_win_val if not np.isnan(avg_win_val) else 0,
               abs(avg_loss_val) if not np.isnan(avg_loss_val) else 0],
            marker_color=[POSITIVE_RETURN_CARD, NEGATIVE_RETURN_CARD],
            marker_line_color=PRIMARY_TEXT,
            marker_line_width=1,
            text=[f"{avg_win_val:.1f}%" if not np.isnan(avg_win_val) else "N/A",
                  f"{abs(avg_loss_val):.1f}%" if not np.isnan(avg_loss_val) else "N/A"],
            textposition='outside',
            textfont=dict(size=11, color=PRIMARY_TEXT),
            hovertemplate='%{x}: %{y:.1f}%<extra></extra>',
            cliponaxis=False
        ))
        
        # Determine range for clean visualization
        max_abs = max(abs(avg_win_val) if not np.isnan(avg_win_val) else 0,
                      abs(avg_loss_val) if not np.isnan(avg_loss_val) else 0)
        
        fig.update_layout(
            margin=dict(l=10, r=10, t=30, b=10),
            height=140,
            width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            xaxis=dict(showgrid=False, showticklabels=False, title=None),
            yaxis=dict(showgrid=False, showticklabels=False, range=[0, max_abs * 1.5]),
            bargap=0.3
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    win_loss_bar = generate_win_loss_bar(avg_win, avg_loss)

    # Card 4: Average Z-Score (weighted)
    if 'z_score' in df.columns:
        valid = df['z_score'].notna() & df['Weight'].notna()
        if valid.any():
            total_weight = df.loc[valid, 'Weight'].sum()
            if total_weight > 0:
                avg_z_score = (df.loc[valid, 'z_score'] * df.loc[valid, 'Weight']).sum() / total_weight
            else:
                avg_z_score = np.nan
        else:
            avg_z_score = np.nan
    else:
        avg_z_score = np.nan
    z_score_display = f"{avg_z_score:+.2f}" if not np.isnan(avg_z_score) else "N/A"
    def get_zscore_color(val):
        if np.isnan(val):
            return NEUTRAL_GRAY
        return POSITIVE_RETURN_CARD if val > 0 else NEGATIVE_RETURN_CARD if val < 0 else NEUTRAL_GRAY
    z_color = get_zscore_color(avg_z_score)

    # Card 5: Momentum Distribution (exclude N/A)
    momentum_data = df.groupby('momentum_signal').size()
    # Only show BULL, BEAR, NEUT in the pie; N/A holdings excluded from chart
    labels = ['BULL', 'BEAR', 'NEUT']
    colors = [SUCCESS_INDICATOR, DANGER_INDICATOR, NEUTRAL_GRAY]
    
    def generate_momentum_pie(data):
        fig = go.Figure()
        values = [data.get(l, 0) for l in labels]
        
        fig.add_trace(go.Pie(
            labels=labels,
            values=values,
            hole=0.6,
            marker_colors=colors,
            textinfo='label+percent',
            textposition='outside',
            textfont=dict(color=PRIMARY_TEXT),
            hoverinfo='label+value',
            showlegend=False,
            sort=False,
            marker=dict(line=dict(color='white', width=2))
        ))
        
        fig.update_layout(
            margin=dict(l=40, r=40, t=10, b=10),
            height=160, width=220,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    momentum_pie = generate_momentum_pie(momentum_data)

    # Generate chart pieces
    ret_pie = generate_ret_pie(pos_count, neg_count, pos_pct, neg_pct)

    # Compose final HTML with 5 cards
    html = f'''
    <div style="display: flex; gap: 10px; margin: 10px 0; font-family: {FONT_PRIMARY}; align-items: stretch; flex-wrap: wrap;">
        <!-- Card 1: Holdings -->
        <div class="metric-card" style="flex: 1; min-width: 200px; background-color: {DIV_YIELD_CARD_BG}; border-color: {ACCENT_THEME}; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 2px 4px {SHADOW_SUBTLE}; display: flex; flex-direction: column;">
            <div style="font-size: 0.8em; color: {METRIC_CARD_LABEL_TEXT}; text-transform: uppercase; margin-bottom: 2px; font-weight: bold;">Holdings</div>
            <div style="font-size: 2.2em; font-weight: 900; color: {ACCENT_THEME}; margin-bottom: 0px;">{total_holdings}</div>
            <div class="metric-sublabel">securities</div>
            <div style="flex-grow: 1;"></div>
        </div>

        <!-- Card 2: Return Distribution Pie -->
        <div class="metric-card" style="flex: 1; min-width: 200px; background-color: {DIV_YIELD_CARD_BG}; border-color: {ACCENT_THEME}; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 2px 4px {SHADOW_SUBTLE}; display: flex; flex-direction: column;">
            <div style="font-size: 0.8em; color: {METRIC_CARD_LABEL_TEXT}; text-transform: uppercase; margin-bottom: 2px; font-weight: bold;">Return Distribution</div>
            <div style="font-size: 1em; color: {METRIC_CARD_LABEL_TEXT}; margin-bottom: 6px; font-weight: 500;">
                <span style="color: {POSITIVE_RETURN_CARD}; font-weight: 600;">{pos_pct:.0f}% pos</span>
                <span style="color: {METRIC_CARD_LABEL_TEXT}; margin: 0 6px;">•</span>
                <span style="color: {NEGATIVE_RETURN_CARD}; font-weight: 600;">{neg_pct:.0f}% neg</span>
            </div>
            <div style="display: flex; justify-content: center; align-items: center; min-height: 140px; flex-grow: 1;">{ret_pie}</div>
        </div>

        <!-- Card 3: Avg Weighted Performance -->
        <div class="metric-card" style="flex: 1; min-width: 200px; background-color: {ACCENT_THEME}20; border-color: {ACCENT_THEME}; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 2px 4px {SHADOW_SUBTLE}; display: flex; flex-direction: column;">
            <div style="font-size: 0.8em; color: {METRIC_CARD_LABEL_TEXT}; text-transform: uppercase; margin-bottom: 2px; font-weight: bold;">Avg Position PnL</div>
            <div style="display: flex; justify-content: center; align-items: center; min-height: 140px; flex-grow: 1;">{win_loss_bar}</div>
        </div>

        <!-- Card 5: Momentum Spread -->
        <div class="metric-card" style="flex: 1; min-width: 200px; background-color: {ACCENT_THEME}20; border-color: {ACCENT_THEME}; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 2px 4px {SHADOW_SUBTLE}; display: flex; flex-direction: column;">
            <div style="font-size: 0.8em; color: {METRIC_CARD_LABEL_TEXT}; text-transform: uppercase; margin-bottom: 2px; font-weight: bold;">Momentum Spread</div>
            <div style="display: flex; justify-content: center; align-items: center; min-height: 140px; flex-grow: 1;">{momentum_pie}</div>
        </div>

        <!-- Card 4: Average Z-Score -->
        <div class="metric-card" style="flex: 1; min-width: 200px; background-color: {z_color}20; border-color: {z_color}; border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 2px 4px {SHADOW_SUBTLE}; display: flex; flex-direction: column;">
            <div style="font-size: 0.8em; color: {METRIC_CARD_LABEL_TEXT}; text-transform: uppercase; margin-bottom: 2px; font-weight: bold;">Avg Z-Score</div>
            <div style="font-size: 2.2em; font-weight: 900; color: {z_color}; margin-bottom: 0px;">{z_score_display}</div>
            <div style="flex-grow: 1;"></div>
        </div>
    </div>
    '''
    return html


