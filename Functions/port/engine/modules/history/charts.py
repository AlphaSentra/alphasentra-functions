"""
Chart generation module: All Plotly visualizations for portfolio functions.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from config import (
    EMPTY_PLACEHOLDER_TEXT, CHART_TRANSPARENT,
    TRADE_WINRATE_GOOD, TRADE_WINRATE_MODERATE, TRADE_WINRATE_BAD, TRADE_PF_NEUTRAL,
    LOSS_TRADE_PIE, WIN_PCT_ANNOTATION,
    TRADE_LOSS_BAR, TRADE_BAR_OUTLINE, BAR_VALUE_LABEL_TEXT, DANGER_INDICATOR
    
)


def _safe_to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0



def generate_trades_metrics_strip(transactions_df):
    """
    Generates header strip with key trade performance metrics for the Trades tab.

    Args:
        transactions_df (pd.DataFrame): DataFrame with transaction data containing
                                        columns: 'Date', 'Ticker', 'Side', 'EntryPrice', 'ExitPrice'.
        prices (pd.DataFrame, optional): Price data for calculating P&L over time.

    Returns:
        str: HTML string with 5 metric cards display.
    """
    if transactions_df.empty:
        return f"<div style='text-align: center; padding: 20px; color: {EMPTY_PLACEHOLDER_TEXT}'>No trade data available.</div>"

    df = transactions_df.copy()

    # Drop rows with missing essential data
    df = df.dropna(subset=['Side', 'EntryPrice', 'ExitPrice'])
    if df.empty:
        return f"<div style='text-align: center; padding: 20px; color: {EMPTY_PLACEHOLDER_TEXT}'>No valid trades found.</div>"

    df['EntryPrice'] = pd.to_numeric(df['EntryPrice'], errors='coerce').fillna(0)

    # Filter to only BUY/SELL trades
    df = df[df['Side'].str.upper().isin(['BUY', 'SELL'])]

    if df.empty:
        return f"<div style='text-align: center; padding: 20px; color: {EMPTY_PLACEHOLDER_TEXT}'>No valid trades found.</div>"

    # Ensure Date is datetime for proper sorting
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])

    # Sort by date ascending to process trades chronologically
    df = df.sort_values('Date').reset_index(drop=True)

    # Track holdings and cost basis using FIFO
    holdings = {}  # ticker -> list of {'qty': float, 'price': float, 'buy_date': Timestamp} (FIFO queue)
    completed_trades = []  # list of {'pnl_pct': float, 'date': Timestamp, 'duration_days': float}

    for _, row in df.iterrows():
        ticker = row['Ticker']
        side = row['Side'].upper()
        trade_date = row['Date']  # Capture the transaction date
        entry_price = _safe_to_float(row.get("EntryPrice"))
        exit_price = _safe_to_float(row.get("ExitPrice"))

        if ticker not in holdings:
            holdings[ticker] = []

        if side == 'BUY':
            price = entry_price
            # Add to holdings queue with buy date
            holdings[ticker].append({'qty': 1.0, 'price': price, 'buy_date': trade_date})
        elif side == 'SELL':
            price = exit_price
            # Match sells against earliest buys (FIFO)
            remaining_qty = qty
            while remaining_qty > 0 and holdings[ticker]:
                buy_lot = holdings[ticker][0]
                matched_qty = min(remaining_qty, buy_lot['qty'])

                # Calculate P&L percentage for this matched lot
                if buy_lot['price'] > 0:
                    pnl_pct = (price - buy_lot['price']) / buy_lot['price'] * 100
                else:
                    pnl_pct = 0.0

                # Calculate trade duration in days
                buy_date = buy_lot['buy_date']
                if isinstance(buy_date, pd.Timestamp) and isinstance(trade_date, pd.Timestamp):
                    duration_days = (trade_date - buy_date).days
                    # Ensure non-negative (in case of same-day trades)
                    duration_days = max(0, duration_days)
                else:
                    duration_days = 0

                # Store as a completed trade with the sell date and duration
                if buy_lot['qty'] <= matched_qty + 1e-10:
                    # Complete lot used up
                    holdings[ticker].pop(0)
                else:
                    # Partial use, reduce lot quantity
                    buy_lot['qty'] -= matched_qty

                completed_trades.append({'pnl_pct': pnl_pct, 'date': trade_date, 'duration_days': duration_days})
                remaining_qty -= matched_qty

            # If remaining_qty > 0, it means we sold more than we bought (short sale or data issue) — skip

    if not completed_trades:
        return f"<div style='text-align: center; padding: 20px; color: {EMPTY_PLACEHOLDER_TEXT}'>No completed trades found.</div>"

    # Extract P&L percentages from completed trades
    pnl_pcts = [t['pnl_pct'] for t in completed_trades]

    # Metric 1: Percentage of winning trades
    wins = [p for p in pnl_pcts if p > 0]
    losses = [p for p in pnl_pcts if p <= 0]
    total_trades = len(pnl_pcts)
    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0.0

    # Metric 2: Risk-Reward Ratio (Average Win / Average Loss magnitude)
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean([abs(p) for p in losses]) if losses else 0.0  # magnitude
    risk_reward_ratio = avg_win / avg_loss if avg_loss > 0 else np.nan

    # Metric 3: Expectancy per trade (in percentage)
    # Expectancy = (Win Rate * Avg Win) - ((1 - Win Rate) * Avg Loss)
    # Note: Avg Loss should be negative for expectancy calc (loss is negative P&L)
    avg_loss_neg = np.mean(losses) if losses else 0.0  # negative number
    expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss_neg)

    # Metric 5: Profit Factor (Gross Profit / Gross Loss in % terms)
    gross_profit = sum([p for p in pnl_pcts if p > 0])
    gross_loss = sum([abs(p) for p in pnl_pcts if p <= 0])  # absolute value
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = float('inf') if gross_profit > 0 else 0.0

    # Metric 6: Average Trade Duration (separate for wins and losses)
    win_durations = [t['duration_days'] for t in completed_trades if t['pnl_pct'] > 0]
    loss_durations = [t['duration_days'] for t in completed_trades if t['pnl_pct'] <= 0]
    avg_win_duration = np.mean(win_durations) if win_durations else np.nan
    avg_loss_duration = np.mean(loss_durations) if loss_durations else np.nan
    avg_duration_all = np.mean([t['duration_days'] for t in completed_trades]) if completed_trades else np.nan

    # Build cumulative P&L series for sparkline chart (sorted by date)
    trades_df = pd.DataFrame(completed_trades)
    cumulative_pnl = None
    if not trades_df.empty and 'date' in trades_df.columns:
        trades_df = trades_df.sort_values('date')
        trades_df['cumulative_pnl'] = trades_df['pnl_pct'].cumsum()
        cumulative_pnl = trades_df[['date', 'cumulative_pnl']]

    # Formatting
    win_rate_display = f"{win_rate:.1f}%"
    rr_display = f"{risk_reward_ratio:.2f}" if not np.isnan(risk_reward_ratio) else "N/A"
    expectancy_display = f"{expectancy:.2f}%"
    pf_display = f"{profit_factor:.2f}" if np.isfinite(profit_factor) else ("∞" if profit_factor > 0 else "0.00")

    # Colors
    def get_winrate_color(wr):
        return TRADE_WINRATE_GOOD if wr >= 55 else TRADE_WINRATE_MODERATE if wr >= 45 else TRADE_WINRATE_BAD

    def get_rr_color(rr):
        if np.isnan(rr):
            return TRADE_PF_NEUTRAL
        return TRADE_WINRATE_GOOD if rr >= 2.0 else TRADE_WINRATE_MODERATE if rr >= 1.0 else TRADE_WINRATE_BAD

    def get_expectancy_color(exp):
        return TRADE_WINRATE_GOOD if exp > 0.5 else TRADE_WINRATE_BAD if exp < -0.5 else TRADE_WINRATE_MODERATE

    def get_pf_color(pf):
        if np.isnan(pf) or not np.isfinite(pf):
            return TRADE_PF_NEUTRAL
        return TRADE_WINRATE_GOOD if pf >= 1.5 else TRADE_WINRATE_MODERATE if pf >= 1.0 else TRADE_WINRATE_BAD

    def get_duration_color(win_dur, loss_dur):
        """Color based on whether winning trades are held longer than losing trades."""
        if np.isnan(win_dur) or np.isnan(loss_dur):
            return TRADE_PF_NEUTRAL
        # If win duration is meaningfully longer than loss duration, that's generally good (green)
        # If loss duration is longer than win duration, that's generally bad (red)
        ratio = win_dur / loss_dur if loss_dur > 0 else np.inf
        if ratio >= 1.2:
            return TRADE_WINRATE_GOOD  # Green: winners held significantly longer
        elif ratio <= 0.8:
            return TRADE_WINRATE_BAD  # Red: losers held longer or winners not held long enough
        else:
            return TRADE_WINRATE_MODERATE  # Orange: roughly equal

    duration_color = get_duration_color(avg_win_duration, avg_loss_duration)

    # Formatting for duration
    def fmt_days(val):
        if np.isnan(val) or val is None:
            return "N/A"
        if val < 1:
            return "<1 day"
        elif val < 7:
            return f"{val:.0f} days"
        elif val < 30:
            return f"{val/7:.1f} weeks"
        elif val < 365:
            return f"{val/30:.1f} mo"
        else:
            return f"{val/365:.1f} yr"

    avg_win_duration_display = fmt_days(avg_win_duration)
    avg_loss_duration_display = fmt_days(avg_loss_duration)
    avg_duration_all_display = fmt_days(avg_duration_all)

    winrate_color = get_winrate_color(win_rate)
    rr_color = get_rr_color(risk_reward_ratio)
    expectancy_color = get_expectancy_color(expectancy)
    pf_color = get_pf_color(profit_factor)

    # ========================================
    # Chart helper functions (similar to breakdown tab)
    # ========================================

    def generate_win_loss_pie_chart(wins_count, total_trades, pie_color):
        """Pie chart with winning slice exploded, losses in grey."""
        if total_trades == 0:
            return ""
        losses_count = total_trades - wins_count
        labels = ['Winning Trades', 'Losing Trades']
        values = [wins_count, losses_count]
        pull = [0.15, 0]  # Explode wins slice
        colors = [pie_color, LOSS_TRADE_PIE]

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
            marker=dict(line=dict(color='white', width=2))
        )])

        win_pct = (wins_count / total_trades * 100) if total_trades > 0 else 0
        fig.add_annotation(
            x=0.5, y=0.5,
            text=f"<span style='font-size:14px;font-weight:600;color:{WIN_PCT_ANNOTATION}'>{win_pct:.0f}%</span>",
            showarrow=False, font=dict(size=14, color=WIN_PCT_ANNOTATION),
            xanchor='center', yanchor='middle'
        )

        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=140, width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    def generate_risk_reward_bar_chart(avg_win, avg_loss, rr_color):
        """Horizontal bar chart comparing average win vs average loss magnitude."""
        if np.isnan(avg_win) and np.isnan(avg_loss):
            return ""
        # Use absolute values for loss to show magnitude
        win_val = avg_win if not np.isnan(avg_win) else 0.0
        loss_val = abs(avg_loss) if not np.isnan(avg_loss) else 0.0
        max_val = max(win_val, loss_val, 0.1)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=['Avg Win', 'Avg Loss'],
            x=[win_val, loss_val],
            orientation='h',
            marker_color=[rr_color, TRADE_LOSS_BAR],
            marker_line_color=TRADE_BAR_OUTLINE,
            marker_line_width=1,
            text=[f"{win_val:.1f}%", f"{loss_val:.1f}%"],
            textposition='outside',
            textfont=dict(size=10, color=BAR_VALUE_LABEL_TEXT, weight=500),
            constraintext='none',
            hovertemplate='%{y}: %{x:.1f}%<extra></extra>',
            cliponaxis=False
        ))

        x_max = max_val * 1.4 if max_val > 0 else 1.0
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=140,
            width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False,
            xaxis=dict(showgrid=False, showticklabels=False, range=[0, x_max], zeroline=False),
            yaxis=dict(showgrid=False, showticklabels=False)
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    def generate_cumulative_pnl_chart(cumulative_pnl_df, exp_color):
        """Sparkline line chart of cumulative P&L over time."""
        if cumulative_pnl_df is None or cumulative_pnl_df.empty or len(cumulative_pnl_df) < 2:
            return ""
        dates = cumulative_pnl_df['date']
        cum_pnl = cumulative_pnl_df['cumulative_pnl']

        # Convert hex color to rgba for fillcolor with 30% opacity
        hex_color = exp_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        fillcolor = f'rgba({r},{g},{b},0.3)'

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=cum_pnl,
            mode='lines',
            line=dict(color=exp_color, width=2),
            fill='tozeroy',
            fillcolor=fillcolor,
            hoverinfo='none',
            showlegend=False
        ))

        # Add final value marker as a dot
        fig.add_trace(go.Scatter(
            x=[dates.iloc[-1]],
            y=[cum_pnl.iloc[-1]],
            mode='markers',
            marker=dict(color=exp_color, size=6),
            showlegend=False,
            hoverinfo='none'
        ))

        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=140, width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False,
            xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
            yaxis=dict(showgrid=False, showticklabels=False)
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    def generate_profit_factor_bar_chart(gross_profit, gross_loss, pf_color):
        """Side-by-side bar chart comparing gross profit vs gross loss."""
        if gross_profit == 0 and gross_loss == 0:
            return ""
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=['Gross Profit', 'Gross Loss'],
            y=[gross_profit, gross_loss],
            marker_color=[pf_color, DANGER_INDICATOR],
            marker_line_color=TRADE_BAR_OUTLINE,
            marker_line_width=1,
            hovertemplate='%{x}: %{y:.1f}%<extra></extra>',
            cliponaxis=False
        ))



        max_val = max(gross_profit, gross_loss, 0.1)
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=140,
            width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False,
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False, range=[0, max_val * 1.3])
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    def generate_duration_bar_chart(avg_win_dur, avg_loss_dur, dur_color):
        """Horizontal bar chart comparing average win vs loss trade duration in days."""
        if np.isnan(avg_win_dur) and np.isnan(avg_loss_dur):
            return ""
        win_val = avg_win_dur if not np.isnan(avg_win_dur) else 0.0
        loss_val = avg_loss_dur if not np.isnan(avg_loss_dur) else 0.0
        max_val = max(win_val, loss_val, 1.0)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=['Winning Trades', 'Losing Trades'],
            x=[win_val, loss_val],
            orientation='h',
            marker_color=[dur_color, DANGER_INDICATOR],
            marker_line_color=TRADE_BAR_OUTLINE,
            marker_line_width=1,
            text=[f"{win_val:.0f}d", f"{loss_val:.0f}d"],
            textposition='outside',
            textfont=dict(size=10, color=BAR_VALUE_LABEL_TEXT, weight=500),
            constraintext='none',
            hovertemplate='%{y}: %{x:.0f} days<extra></extra>',
            cliponaxis=False
        ))



        x_max = max_val * 1.4 if max_val > 0 else 30
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            height=140,
            width=200,
            paper_bgcolor=CHART_TRANSPARENT,
            plot_bgcolor=CHART_TRANSPARENT,
            autosize=False,
            xaxis=dict(showgrid=False, showticklabels=False, range=[0, x_max], zeroline=False),
            yaxis=dict(showgrid=False, showticklabels=False)
        )
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'staticPlot': True, 'displayModeBar': False})

    # Generate charts
    win_pie = generate_win_loss_pie_chart(len(wins), total_trades, winrate_color)
    rr_bar = generate_risk_reward_bar_chart(avg_win, avg_loss, rr_color)
    cum_pnl_chart = generate_cumulative_pnl_chart(cumulative_pnl, expectancy_color)
    pf_bar = generate_profit_factor_bar_chart(gross_profit, gross_loss, pf_color)
    dur_bar = generate_duration_bar_chart(avg_win_duration, avg_loss_duration, duration_color)

    html = f"""
    <div class="metric-strip-row">
        <!-- Win Rate Card -->
        <div class="metric-card" style="background-color: {winrate_color}20; border-color: {winrate_color};">
            <div class="metric-label">Win Rate</div>
            <div class="metric-value" style="color: {winrate_color};">{win_rate_display}</div>
            <div class="metric-sublabel">of trades profitable</div>
            <div class="metric-chart-container">{win_pie}</div>
        </div>

        <!-- Risk-Reward Ratio Card -->
        <div class="metric-card" style="background-color: {rr_color}20; border-color: {rr_color};">
            <div class="metric-label">Risk-Reward Ratio</div>
            <div class="metric-value" style="color: {rr_color};">{rr_display}</div>
            <div class="metric-sublabel">Avg Win ÷ Avg Loss</div>
            <div class="metric-chart-container">{rr_bar}</div>
        </div>

        <!-- Expectancy per Trade Card -->
        <div class="metric-card" style="background-color: {expectancy_color}20; border-color: {expectancy_color};">
            <div class="metric-label">Expected Profit/Trade</div>
            <div class="metric-value" style="color: {expectancy_color};">{expectancy_display}</div>
            <div class="metric-sublabel">expected return %</div>
            <div class="metric-chart-container">{cum_pnl_chart}</div>
        </div>

        <!-- Average Trade Duration Card (replacing Payoff Ratio) -->
        <div class="metric-card" style="background-color: {duration_color}20; border-color: {duration_color};">
            <div class="metric-label">Avg. Trade Duration</div>
            <div class="metric-value" style="color: {duration_color};">{avg_duration_all_display}</div>
            <div class="metric-sublabel">held period</div>
            <div class="metric-chart-container">{dur_bar}</div>
        </div>

        <!-- Profit Factor Card -->
        <div class="metric-card" style="background-color: {pf_color}20; border-color: {pf_color};">
            <div class="metric-label">Profit Factor</div>
            <div class="metric-value" style="color: {pf_color};">{pf_display}</div>
            <div class="metric-sublabel">Gross Profit ÷ Gross Loss</div>
            <div class="metric-chart-container">{pf_bar}</div>
        </div>
    </div>
    """
    return html


