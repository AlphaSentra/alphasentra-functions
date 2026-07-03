"""
Optimisation tab renderer: generates the Optimisation tab HTML block.
"""

import os
from jinja2 import Template
import pandas as pd
import plotly.graph_objects as go
from config import (
    DEFAULT_CAPITAL,
    OPTIMISATION_CURRENT_STRATEGY,
    OPTIMISATION_SHARPE_STRATEGY,
    OPTIMISATION_SORTINO_STRATEGY,
    OPTIMISATION_IR_STRATEGY,
    OPTIMISATION_DRAWDOWN_STRATEGY,
    OPTIMISATION_BEST_MATCH_STRATEGY,
    STRATEGY_DEFAULT_COLOR,
    CURRENT_PORTFOLIO_FILL,
    CURRENT_PORTFOLIO_LINE,
    BG_CHART,
    CHART_GRID,
    TEXT_MUTED,
    TEXT_PRIMARY
)
from .optimizer import optimize_portfolio

def render_optimisation_tab(prices_df, portfolio_df, benchmark_series, sector_industry_df, config, current_weights_dict=None, actual_portfolio_metrics=None, total_portfolio_value=DEFAULT_CAPITAL, portfolio_total_ts=None) -> str:
    """
    Renders the Optimisation tab HTML block.
    """
    # 1. Run optimization
    opt_results = optimize_portfolio(prices_df, portfolio_df, benchmark_series, sector_industry_df, config, current_weights_dict, actual_portfolio_metrics, portfolio_total_ts=portfolio_total_ts)
    
    if not opt_results:
        return None

    tickers = opt_results['tickers']
    solutions = opt_results['solutions']
    sectors = opt_results['sectors']
    names = opt_results['names']
    
    # 2. Generate weight comparison Plotly chart
    fig = go.Figure()
    
    strategy_colors = {
        'Current': OPTIMISATION_CURRENT_STRATEGY,
        'Max Sharpe': OPTIMISATION_SHARPE_STRATEGY,
        'Max Sortino': OPTIMISATION_SORTINO_STRATEGY,
        'Max IR': OPTIMISATION_IR_STRATEGY,
        'Min Drawdown': OPTIMISATION_DRAWDOWN_STRATEGY,
        'Best Match': OPTIMISATION_BEST_MATCH_STRATEGY
    }
    
    for name, sol in solutions.items():
        fig.add_trace(go.Bar(
            name=name,
            x=tickers,
            y=sol['weights'] * 100.0,  # convert to %
            marker_color=strategy_colors.get(name, STRATEGY_DEFAULT_COLOR),
            text=[f"{w*100:.1f}%" if w > 0.005 else "" for w in sol['weights']],
            textposition='auto'
        ))
        
    fig.update_layout(
        title="Asset Allocation Comparison across Optimization Strategies",
        xaxis_title="Security Ticker",
        yaxis_title="Allocation Weight (%)",
        barmode='group',
        template='plotly_white',
        height=500,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    chart_html = fig.to_html(full_html=False, include_plotlyjs=False)

    # 2b. Generate timeseries comparison chart
    dates = opt_results.get('dates', [])
    bench_cum = opt_results.get('benchmark_cum_wealth', [])
    
    fig_ts = go.Figure()
    
    # Trace for Current portfolio as an area chart
    if 'Current' in solutions and 'cum_wealth' in solutions['Current']:
        fig_ts.add_trace(go.Scatter(
            x=dates,
            y=solutions['Current']['cum_wealth'],
            name='Current Portfolio',
            fill='tozeroy',
            fillcolor=CURRENT_PORTFOLIO_FILL,
            line=dict(color=CURRENT_PORTFOLIO_LINE, width=2)
        ))
        
    # Traces for optimized strategies
    for name in ['Max Sharpe', 'Max Sortino', 'Max IR', 'Min Drawdown', 'Best Match']:
        if name in solutions and 'cum_wealth' in solutions[name]:
            fig_ts.add_trace(go.Scatter(
                x=dates,
                y=solutions[name]['cum_wealth'],
                name=name,
                line=dict(color=strategy_colors.get(name, STRATEGY_DEFAULT_COLOR), width=2.5)
            ))
            
    # Calculate y-axis range to prevent squashing (auto-scaling to zero due to fill='tozeroy')
    all_values = []
    for name in ['Current', 'Max Sharpe', 'Max Sortino', 'Max IR', 'Min Drawdown', 'Best Match']:
        if name in solutions and 'cum_wealth' in solutions[name]:
            all_values.extend(solutions[name]['cum_wealth'])
            
    y_range = None
    if all_values:
        y_min = min(all_values)
        y_max = max(all_values)
        span = y_max - y_min
        # Set a larger padding at the top (at least 3.0 units or 12% of span) to prevent line clipping
        padding_top = max(span * 0.12, 3.0)
        padding_bottom = max(span * 0.08, 2.0)
        y_range = [y_min - padding_bottom, y_max + padding_top]

    layout_args = dict(
        title="Historical Cumulative Performance Comparison (Trailing 1-Year lookback, base 100)",
        xaxis_title="Date",
        yaxis_title="Growth (Base 100)",
        plot_bgcolor=BG_CHART,
        paper_bgcolor=BG_CHART,
        title_font=dict(color=TEXT_MUTED),
        font=dict(color=TEXT_PRIMARY),
        legend_font=dict(color=TEXT_MUTED),
        legend_title_font=dict(color=TEXT_MUTED),
        height=450,
        margin=dict(l=40, r=40, t=50, b=40),
        hovermode="x unified",
        xaxis=dict(
            showgrid=True,
            gridcolor=CHART_GRID,
            title_font=dict(color=TEXT_MUTED),
            tickfont=dict(color=TEXT_MUTED)
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=CHART_GRID,
            tickformat=".2f",
            title_font=dict(color=TEXT_MUTED),
            tickfont=dict(color=TEXT_MUTED)
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.2,
            xanchor="center",
            x=0.5
        )
    )
    if y_range:
        layout_args['yaxis']['range'] = y_range

    fig_ts.update_layout(**layout_args)
    ts_chart_html = fig_ts.to_html(full_html=False, include_plotlyjs=False)

    def make_weight_pill(diff):
        if abs(diff) < 0.005:
            return ""  # No pill for negligible changes
        pill_class = "pill pill-positive" if diff > 0 else "pill pill-negative"
        arrow = "▲" if diff > 0 else "▼"
        sign = "+" if diff > 0 else ""
        return f'<div class="{pill_class}"><span>{arrow}</span><span>{sign}{diff:.2f}%</span></div>'

    def make_qty_pill(diff):
        if abs(diff) < 0.005:
            return ""  # No pill for negligible changes
        pill_class = "pill pill-positive" if diff > 0 else "pill pill-negative"
        arrow = "▲" if diff > 0 else "▼"
        sign = "+" if diff > 0 else ""
        formatted_diff = f"{diff:,.0f}"
        return f'<div class="{pill_class}"><span>{arrow}</span><span>{sign}{formatted_diff}</span></div>'

    # 3. Create weight comparison table rows html
    table_rows = []
    
    # Zip data together to allow sorting by Current Weight descending
    zipped_data = []
    for i, t in enumerate(tickers):
        curr_w = solutions['Current']['weights'][i] * 100.0
        sharpe_w = solutions['Max Sharpe']['weights'][i] * 100.0
        sortino_w = solutions['Max Sortino']['weights'][i] * 100.0
        ir_w = solutions['Max IR']['weights'][i] * 100.0
        drawdown_w = solutions['Min Drawdown']['weights'][i] * 100.0
        best_match_w = solutions['Best Match']['weights'][i] * 100.0
        
        zipped_data.append({
            'ticker': t,
            'name': names[i],
            'sector': sectors[i],
            'curr_w': curr_w,
            'sharpe_w': sharpe_w,
            'sortino_w': sortino_w,
            'ir_w': ir_w,
            'drawdown_w': drawdown_w,
            'best_match_w': best_match_w
        })
        
    # Get latest prices for quantity calculation
    latest_prices = {}
    for t in tickers:
        if isinstance(prices_df.columns, pd.MultiIndex):
            if t in prices_df['Close'].columns:
                s = prices_df['Close'][t].dropna()
                latest_prices[t] = s.iloc[-1] if len(s) > 0 else 0.0
            else:
                latest_prices[t] = 0.0
        elif 'Close' in prices_df.columns:
            s = prices_df['Close'].dropna()
            latest_prices[t] = s.iloc[-1] if len(s) > 0 else 0.0
        else:
            if t in prices_df.columns:
                s = prices_df[t].dropna()
                latest_prices[t] = s.iloc[-1] if len(s) > 0 else 0.0
            else:
                latest_prices[t] = 0.0

    # Sort descending by Current Weight
    zipped_data.sort(key=lambda x: x['curr_w'], reverse=True)
    
    for row in zipped_data:
        t = row['ticker']
        p = latest_prices.get(t, 0.0)
        
        # Calculate Quantities
        if p > 0:
            row['curr_q'] = (row['curr_w'] / 100.0 * total_portfolio_value) / p
            row['sharpe_q'] = (row['sharpe_w'] / 100.0 * total_portfolio_value) / p
            row['sortino_q'] = (row['sortino_w'] / 100.0 * total_portfolio_value) / p
            row['ir_q'] = (row['ir_w'] / 100.0 * total_portfolio_value) / p
            row['drawdown_q'] = (row['drawdown_w'] / 100.0 * total_portfolio_value) / p
            row['best_match_q'] = (row['best_match_w'] / 100.0 * total_portfolio_value) / p
        else:
            row['curr_q'] = 0.0
            row['sharpe_q'] = 0.0
            row['sortino_q'] = 0.0
            row['ir_q'] = 0.0
            row['drawdown_q'] = 0.0
            row['best_match_q'] = 0.0

        row_class = 'active-row'
        name = row['name']
        sector = row['sector']
        curr_w = row['curr_w']
        sharpe_w = row['sharpe_w']
        sortino_w = row['sortino_w']
        ir_w = row['ir_w']
        drawdown_w = row['drawdown_w']
        best_match_w = row['best_match_w']
        
        curr_q = row['curr_q']
        sharpe_q = row['sharpe_q']
        sortino_q = row['sortino_q']
        ir_q = row['ir_q']
        drawdown_q = row['drawdown_q']
        best_match_q = row['best_match_q']
        
        def format_qty(q):
            return f"{q:,.0f}"

        row_str = f"""
        <tr class="{row_class}" data-ticker="{t}" data-price="{p:.4f}" data-wcurr="{curr_w:.4f}" data-wsharpe="{sharpe_w:.4f}" data-wsortino="{sortino_w:.4f}" data-wir="{ir_w:.4f}" data-wdrawdown="{drawdown_w:.4f}" data-wbestmatch="{best_match_w:.4f}" data-diffsharpe="{sharpe_w - curr_w:.4f}" data-diffsortino="{sortino_w - curr_w:.4f}" data-diffir="{ir_w - curr_w:.4f}" data-diffdrawdown="{drawdown_w - curr_w:.4f}" data-diffbestmatch="{best_match_w - curr_w:.4f}">
            <td><strong>{t}</strong></td>
            <td>{name}</td>
            <td>{sector}</td>
            <td class="opt-cell">
                <div class="opt-view-percentage"><strong>{curr_w:.2f}%</strong></div>
                <div class="opt-view-quantity"><strong>{format_qty(curr_q)}</strong></div>
            </td>
            <td class="opt-cell opt-cell-sharpe">
                <div class="opt-view-percentage">
                    <div class="opt-val">{sharpe_w:.2f}%</div>
                    {make_weight_pill(sharpe_w - curr_w)}
                </div>
                <div class="opt-view-quantity">
                    <div class="opt-val">{format_qty(sharpe_q)}</div>
                    {make_qty_pill(sharpe_q - curr_q)}
                </div>
            </td>
            <td class="opt-cell opt-cell-sortino">
                <div class="opt-view-percentage">
                    <div class="opt-val">{sortino_w:.2f}%</div>
                    {make_weight_pill(sortino_w - curr_w)}
                </div>
                <div class="opt-view-quantity">
                    <div class="opt-val">{format_qty(sortino_q)}</div>
                    {make_qty_pill(sortino_q - curr_q)}
                </div>
            </td>
            <td class="opt-cell opt-cell-ir">
                <div class="opt-view-percentage">
                    <div class="opt-val">{ir_w:.2f}%</div>
                    {make_weight_pill(ir_w - curr_w)}
                </div>
                <div class="opt-view-quantity">
                    <div class="opt-val">{format_qty(ir_q)}</div>
                    {make_qty_pill(ir_q - curr_q)}
                </div>
            </td>
            <td class="opt-cell opt-cell-drawdown">
                <div class="opt-view-percentage">
                    <div class="opt-val">{drawdown_w:.2f}%</div>
                    {make_weight_pill(drawdown_w - curr_w)}
                </div>
                <div class="opt-view-quantity">
                    <div class="opt-val">{format_qty(drawdown_q)}</div>
                    {make_qty_pill(drawdown_q - curr_q)}
                </div>
            </td>
            <td class="opt-cell opt-cell-best-match">
                <div class="opt-view-percentage">
                    <div class="opt-val">{best_match_w:.2f}%</div>
                    {make_weight_pill(best_match_w - curr_w)}
                </div>
                <div class="opt-view-quantity">
                    <div class="opt-val">{format_qty(best_match_q)}</div>
                    {make_qty_pill(best_match_q - curr_q)}
                </div>
            </td>
        </tr>
        """
        table_rows.append(row_str)

    # Add totals row
    curr_w_sum = sum(solutions['Current']['weights'])*100
    sharpe_w_sum = sum(solutions['Max Sharpe']['weights'])*100
    sortino_w_sum = sum(solutions['Max Sortino']['weights'])*100
    ir_w_sum = sum(solutions['Max IR']['weights'])*100
    drawdown_w_sum = sum(solutions['Min Drawdown']['weights'])*100
    best_match_w_sum = sum(solutions['Best Match']['weights'])*100

    totals_row = f"""
    <tr class="opt-totals-row">
        <td>TOTAL</td>
        <td>-</td>
        <td>-</td>
        <td class="opt-cell">
            <div class="opt-view-percentage">{curr_w_sum:.1f}%</div>
            <div class="opt-view-quantity">-</div>
        </td>
        <td class="opt-cell">
            <div class="opt-view-percentage">{sharpe_w_sum:.1f}%</div>
            <div class="opt-view-quantity">-</div>
        </td>
        <td class="opt-cell">
            <div class="opt-view-percentage">{sortino_w_sum:.1f}%</div>
            <div class="opt-view-quantity">-</div>
        </td>
        <td class="opt-cell">
            <div class="opt-view-percentage">{ir_w_sum:.1f}%</div>
            <div class="opt-view-quantity">-</div>
        </td>
        <td class="opt-cell">
            <div class="opt-view-percentage">{drawdown_w_sum:.1f}%</div>
            <div class="opt-view-quantity">-</div>
        </td>
        <td class="opt-cell">
            <div class="opt-view-percentage">{best_match_w_sum:.1f}%</div>
            <div class="opt-view-quantity">-</div>
        </td>
    </tr>
    """
    table_rows.append(totals_row)
    
    weights_table_rows_html = "\n".join(table_rows)

    # 4. Create metrics summary table html
    metric_names = ['Sharpe Ratio', 'Sortino Ratio', 'Information Ratio', 'Max Drawdown', 'Annualized Return', 'Annualized Volatility']
    metric_rows = []
    
    for m in metric_names:
        row_str = f"<tr><td><strong>{m}</strong></td>"
        for sol_name in ['Current', 'Max Sharpe', 'Max Sortino', 'Max IR', 'Min Drawdown', 'Best Match']:
            val = solutions[sol_name]['metrics'][m]
            
            # Format display
            if 'Ratio' in m:
                formatted_val = f"{val:.3f}"
            else:  # percentage metrics
                formatted_val = f"{val*100.0:.2f}%"
                
            row_str += f"<td class='opt-metric-cell'>{formatted_val}</td>"
        row_str += "</tr>"
        metric_rows.append(row_str)
        
    metrics_table_rows_html = "\n".join(metric_rows)

    # 5. Render template
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    template = Template(template_src)
    return template.render(
        chart_html=chart_html,
        ts_chart_html=ts_chart_html,
        weights_table_rows_html=weights_table_rows_html,
        metrics_table_rows_html=metrics_table_rows_html,
        solutions=solutions,
        config=config,
        total_portfolio_value=total_portfolio_value
    )
