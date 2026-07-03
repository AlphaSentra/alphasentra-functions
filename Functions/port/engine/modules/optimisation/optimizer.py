"""
Portfolio Optimization Engine using Scipy SLSQP.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import logging

logger = logging.getLogger(__name__)

def optimize_portfolio(prices_df, portfolio_df, benchmark_series, sector_industry_df, config, current_weights_dict=None, actual_portfolio_metrics=None, portfolio_total_ts=None):
    """
    Optimizes the portfolio to find 5 distinct solutions:
    1. Max Sharpe Ratio
    2. Max Sortino Ratio
    3. Max Information Ratio
    4. Minimum Max Drawdown
    5. Balanced Multi-Objective Solution

    Supports long/short portfolios when portfolio_df contains a 'type' column
    with values 'L' (long), 'S' (short), or 'MIXED'.

    Constraints:
    - Maximum position size per asset
    - Maximum sector size per sector
    - Weights sum to 1.0 for optimized strategies; current portfolio may use
      signed weights reflecting long/short exposures.
    """
    # 1. Align tickers and data
    portfolio_tickers = [
        t for t in portfolio_df['ticker'].tolist()
        if t in prices_df.columns
    ]
    if not portfolio_tickers:
        logger.error("No portfolio tickers found in price data. Optimization cannot run.")
        return None

    # Calculate returns
    daily_returns = prices_df[portfolio_tickers].pct_change()
    if "USD=X" in daily_returns.columns:
        daily_returns["USD=X"] = daily_returns["USD=X"].fillna(0.0)
    daily_returns = daily_returns.dropna()
    daily_benchmark = benchmark_series.pct_change().dropna()
    
    # Align dates
    common_dates = daily_returns.index.intersection(daily_benchmark.index)
    
    # Slice to trailing 1-year window if requested (default)
    if config.get('opt_lookback', '1y') == '1y':
        anchor = common_dates.max()
        if anchor is not None and not pd.isnull(anchor):
            start_date = anchor - pd.DateOffset(years=1)
            one_year_dates = common_dates[common_dates >= start_date]
            common_dates = one_year_dates[-252:]
            
    daily_returns = daily_returns.loc[common_dates]
    daily_benchmark = daily_benchmark.loc[common_dates]
    
    num_assets = len(portfolio_tickers)
    
    # Get sector grouping
    sector_series = sector_industry_df.loc[portfolio_tickers, 'sector'].copy()
    name_series = sector_industry_df.loc[portfolio_tickers, 'name'].copy()
    if "USD=X" in sector_series.index and sector_series["USD=X"] is None or pd.isna(sector_series.loc["USD=X"]):
        sector_series.loc["USD=X"] = "Cash"
    if "USD=X" in name_series.index and (name_series["USD=X"] is None or pd.isna(name_series.loc["USD=X"])):
        name_series.loc["USD=X"] = "USD=X"
    sector_series = sector_series.fillna('Others')
    name_series = name_series.fillna('')
    unique_sectors = sector_series.unique()
    sector_groups = {sector: np.array([sector_series.iloc[i] == sector for i in range(num_assets)]) for sector in unique_sectors}

    # Precompute signed current weights for long/short-aware constraints
    current_weights = np.zeros(num_assets)
    signed = False
    if not portfolio_df.empty and 'type' in portfolio_df.columns:
        pf_map = {row['ticker']: row for _, row in portfolio_df.iterrows()}
        for i, t in enumerate(portfolio_tickers):
            if t in pf_map:
                row = pf_map[t]
                raw = float(row.get('weight', row.get('quantity', 0.0)) or 0.0)
                direction = str(row.get('type', 'L')).upper()
                if direction == 'S':
                    current_weights[i] = -abs(raw)
                    signed = True
                else:
                    current_weights[i] = abs(raw)
                    signed = True
    if not signed:
        w_dict = {}
        if current_weights_dict:
            w_dict = current_weights_dict
        elif 'weight' in portfolio_df.columns:
            w_dict = {row['ticker']: row['weight'] for _, row in portfolio_df.iterrows()}
        elif 'quantity' in portfolio_df.columns and not portfolio_df.empty:
            tot = portfolio_df['quantity'].sum()
            if tot > 0:
                w_dict = {row['ticker']: row['quantity'] / tot for _, row in portfolio_df.iterrows()}
        for i, t in enumerate(portfolio_tickers):
            current_weights[i] = float(w_dict.get(t, 0.0) or 0.0)
    c_sum = float(np.sum(current_weights))
    if c_sum > 1.05:
        current_weights = current_weights / 100.0
        c_sum = float(np.sum(current_weights))
    c_max = float(np.max(current_weights)) if len(current_weights) > 0 else 0.0
    c_min = float(np.min(current_weights)) if len(current_weights) > 0 else 0.0
    if c_sum >= 0.95 and c_max <= 1.0 and c_max > 0 and c_min >= 0:
        current_weights = current_weights / c_sum
    elif c_sum <= -0.95 and c_min >= -1.0 and c_min < 0 and c_max <= 0:
        current_weights = current_weights / abs(c_sum)
    else:
        gross = float(np.sum(np.abs(current_weights)))
        if gross > 1e-8:
            current_weights = current_weights / gross

    # Extract target values & parameters
    max_position_size = config.get('max_position_size', 5.0) / 100.0
    max_sector_size = config.get('max_sector_size', 30.0) / 100.0

    risk_free_rate = 0.02
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1

    _compute_cum_wealth_and_metrics = None
    use_actual_current_ts = False
    actual_current_daily_rets = None

    bench_rets = daily_benchmark.values
    asset_rets_matrix = daily_returns.values

    if portfolio_total_ts is not None and not portfolio_total_ts.empty:
        aligned_actual_ts = portfolio_total_ts.reindex(common_dates).dropna()
        if len(aligned_actual_ts) > 1:
            use_actual_current_ts = True
            actual_current_daily_rets = aligned_actual_ts.pct_change().dropna()
            aligned_actual_returns = actual_current_daily_rets
            n_days_actual = len(aligned_actual_returns)
            _cum_ret_actual = np.prod(1 + aligned_actual_returns.values) - 1
            _p_ret_actual = (1 + _cum_ret_actual) ** (252 / n_days_actual) - 1 if n_days_actual > 0 and _cum_ret_actual > -1 else 0.0
            _p_std_ann_actual = np.nanstd(aligned_actual_returns.values, ddof=1) * np.sqrt(252)
            _downside_rets_actual = aligned_actual_returns.values[aligned_actual_returns.values < 0]
            _downside_std_ann_actual = np.nanstd(_downside_rets_actual, ddof=1) * np.sqrt(252) if len(_downside_rets_actual) > 1 else 0.0
            _excess_actual = aligned_actual_returns.values - bench_rets[:len(aligned_actual_returns)]
            _excess_std_actual = np.nanstd(_excess_actual, ddof=1) if len(_excess_actual) > 1 else np.nanstd(_excess_actual)
            _ir_actual = np.nanmean(_excess_actual) / (_excess_std_actual + 1e-8) * np.sqrt(252)
            _sharpe_actual = (np.nanmean(aligned_actual_returns.values) - daily_rf) / (_p_std_ann_actual / np.sqrt(252) + 1e-8) * np.sqrt(252)
            _sortino_actual = (_p_ret_actual - risk_free_rate) / (_downside_std_ann_actual + 1e-8) if _downside_std_ann_actual > 0 else 0.0
            _cum_ret_series_actual = np.cumprod(1 + aligned_actual_returns.values)
            _running_max_actual = np.maximum.accumulate(_cum_ret_series_actual)
            _drawdowns_actual = (_running_max_actual - _cum_ret_series_actual) / _running_max_actual
            _max_dd_actual = np.max(_drawdowns_actual) if len(_drawdowns_actual) > 0 else 0.0
            _cum_wealth_actual = (np.cumprod(1 + aligned_actual_returns.values) * 100.0).tolist()

            def _compute_actual_current_metrics(c_rets):
                aligned = c_rets.reindex(common_dates).dropna()
                if len(aligned) < 2:
                    return None, None
                ac_rets = aligned.pct_change().dropna()
                if len(ac_rets) < 2:
                    return None, None
                n_days = len(ac_rets)
                cum = np.cumprod(1 + ac_rets.values)
                running_max = np.maximum.accumulate(cum)
                drawdowns = (running_max - cum) / running_max
                max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
                cum_ret = np.prod(1 + ac_rets.values) - 1
                p_ret = (1 + cum_ret) ** (252 / n_days) - 1 if n_days > 0 and cum_ret > -1 else 0.0
                p_std = np.nanstd(ac_rets.values, ddof=1) if len(ac_rets) > 1 else 0.0
                p_std_ann = p_std * np.sqrt(252)
                downside = ac_rets.values[ac_rets.values < 0]
                downside_std = np.nanstd(downside, ddof=1) * np.sqrt(252) if len(downside) > 1 else 0.0
                sharpe = (np.nanmean(ac_rets.values) - daily_rf) / (p_std + 1e-8) * np.sqrt(252)
                sortino = (p_ret - risk_free_rate) / (downside_std + 1e-8) if downside_std > 0 else 0.0
                excess = ac_rets.values - bench_rets[:len(ac_rets)]
                excess_std = np.nanstd(excess, ddof=1) if len(excess) > 1 else np.nanstd(excess)
                ir = np.nanmean(excess) / (excess_std + 1e-8) * np.sqrt(252)
                return {
                    'Sharpe Ratio': 0.0 if abs(sharpe) < 1e-9 else sharpe,
                    'Sortino Ratio': 0.0 if abs(sortino) < 1e-9 else sortino,
                    'Information Ratio': 0.0 if abs(ir) < 1e-9 else ir,
                    'Max Drawdown': max_dd,
                    'Annualized Return': p_ret,
                    'Annualized Volatility': p_std_ann,
                }, (np.cumprod(1 + ac_rets.values) * 100.0).tolist()

            _compute_cum_wealth_and_metrics = _compute_actual_current_metrics

    # 2. Feasibility Checks and Relaxation
    # Position limit relaxation
    pos_limit = max_position_size
    min_needed = 1.0 / num_assets
    if max_position_size <= min_needed + 0.02:
        relaxed_limit = min(1.0, max(max_position_size, min_needed + 0.05))
        pos_limit = relaxed_limit
        logger.warning(f"Relaxed max position size from {max_position_size:.2%} to {relaxed_limit:.2%} to allow optimization degrees of freedom.")

    min_position_size = config['min_position_size'] / 100.0
    max_feasible = 0.95 / num_assets
    if min_position_size > max_feasible:
        min_position_size = max(0.0, max_feasible)
        logger.warning(f"Asset count too large. Reduced minimum position size constraint to {min_position_size:.4%} to ensure mathematical feasibility.")

    bounds = []
    for i, t in enumerate(portfolio_tickers):
        # Allow both long and short within position limit
        bounds.append((-pos_limit, pos_limit))

    relaxed_sector_limits = {}
    for sector, mask in sector_groups.items():
        min_required_for_sector = 1.0 if np.sum(mask) == num_assets else 0.0
        relaxed_sector_limits[sector] = min(1.0, max(max_sector_size, min_required_for_sector + 0.05))
        if relaxed_sector_limits[sector] > max_sector_size:
            logger.warning(f"Relaxed sector limit for '{sector}' from {max_sector_size:.2%} to {relaxed_sector_limits[sector]:.2%} to allow optimization degrees of freedom.")

    sector_sum = sum(relaxed_sector_limits.values())
    if sector_sum < 1.20:
        scale_factor = 1.20 / max(1e-8, sector_sum)
        for sector in list(relaxed_sector_limits.keys()):
            old_lim = relaxed_sector_limits[sector]
            new_lim = min(1.0, old_lim * scale_factor)
            relaxed_sector_limits[sector] = new_lim
            if new_lim > old_lim:
                logger.warning(f"Proportionally relaxed sector limit for '{sector}' from {old_lim:.2%} to {new_lim:.2%} to ensure feasibility.")

    constraints = []
    constraints.append({
        'type': 'eq',
        'fun': lambda w: np.sum(w) - 1.0
    })

    for sector, mask in sector_groups.items():
        pos_mask = mask & (current_weights >= 0)
        neg_mask = mask & (current_weights < 0)
        if np.any(pos_mask):
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, m=pos_mask, lim=relaxed_sector_limits[sector]: lim - np.sum(w[m])
            })
        if np.any(neg_mask):
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, m=neg_mask, lim=relaxed_sector_limits[sector]: lim + np.sum(w[m])
            })

    # 4. Define performance metrics calculation
    mean_rets = daily_returns.mean().values
    cov_matrix = daily_returns.cov().values

    def get_portfolio_metrics(w):
        # Daily portfolio returns series
        daily_p_rets = asset_rets_matrix @ w
        p_mean = np.mean(daily_p_rets)
        p_std = np.std(daily_p_rets, ddof=1) if len(daily_p_rets) > 1 else np.std(daily_p_rets)
        
        # Annualized return and volatility (matching metrics.py geometric formulation)
        n_days = len(daily_p_rets)
        cum_ret = np.prod(1 + daily_p_rets) - 1
        p_ret = (1 + cum_ret) ** (252 / n_days) - 1 if n_days > 0 and cum_ret > -1 else 0.0
        p_std_ann = p_std * np.sqrt(252)
        
        # Sharpe ratio
        sharpe = (p_mean - daily_rf) / (p_std + 1e-8) * np.sqrt(252)
        
        # Sortino Ratio
        downside_rets = daily_p_rets[daily_p_rets < 0]
        if len(downside_rets) > 1:
            downside_std_ann = np.std(downside_rets, ddof=1) * np.sqrt(252)
        else:
            downside_std_ann = 0.0
            
        sortino = (p_ret - risk_free_rate) / (downside_std_ann + 1e-8) if downside_std_ann > 0 else 0.0
        
        # Information Ratio
        excess = daily_p_rets - bench_rets
        excess_std = np.std(excess, ddof=1) if len(excess) > 1 else np.std(excess)
        ir = np.mean(excess) / (excess_std + 1e-8) * np.sqrt(252)
        
        # Max Drawdown
        cum_ret_series = np.cumprod(1 + daily_p_rets)
        running_max = np.maximum.accumulate(cum_ret_series)
        drawdowns = (running_max - cum_ret_series) / running_max
        max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0.0
        
        # Normalise sub-sorting noise so -0.00 never leaks
        sharpe = 0.0 if abs(sharpe) < 1e-9 else sharpe
        sortino = 0.0 if abs(sortino) < 1e-9 else sortino
        ir = 0.0 if abs(ir) < 1e-9 else ir
        
        return sharpe, sortino, ir, max_dd, p_ret, p_std_ann

    # 5. Objective functions for optimization
    # SciPy minimizes, so we negate functions we want to maximize
    def obj_max_sharpe(w):
        sharpe, _, _, _, _, _ = get_portfolio_metrics(w)
        return -sharpe

    def obj_max_sortino(w):
        _, sortino, _, _, _, _ = get_portfolio_metrics(w)
        return -sortino

    def obj_max_ir(w):
        _, _, ir, _, _, _ = get_portfolio_metrics(w)
        return -ir

    def obj_min_drawdown(w):
        _, _, _, max_dd, _, _ = get_portfolio_metrics(w)
        # Minimize max drawdown, with a tiny penalty on negative return to avoid static portfolios
        sharpe, _, _, _, _, _ = get_portfolio_metrics(w)
        return max_dd - 0.01 * sharpe

    def obj_best_match(w):
        sharpe, sortino, ir, _, _, _ = get_portfolio_metrics(w)
        # Simultaneously maximize Sharpe, Sortino, and Information ratios (ignoring drawdown)
        return -(sharpe + sortino + ir)

    # Initial guess: signed current weights if available, otherwise equal weighting
    if np.any(current_weights != 0):
        w0 = np.array(current_weights, dtype=float)
        gross = float(np.sum(np.abs(w0)))
        if gross > 1e-8:
            w0 = w0 / gross
    else:
        w0 = np.ones(num_assets) / num_assets

    # 6. Run Optimizations
    objectives = {
        'Max Sharpe': obj_max_sharpe,
        'Max Sortino': obj_max_sortino,
        'Max IR': obj_max_ir,
        'Min Drawdown': obj_min_drawdown,
        'Best Match': obj_best_match
    }
    
    optimized_solutions = {}
    
    for name, obj_fun in objectives.items():
        sol_bounds = bounds
        sol_constraints = constraints
        sol_w0 = w0

        res = minimize(
            obj_fun,
            sol_w0,
            method='SLSQP',
            bounds=sol_bounds,
            constraints=sol_constraints,
            options={'maxiter': 500, 'ftol': 1e-6}
        )
        
        # If optimization failed, SLSQP might have got stuck, try fallback to SLSQP with equal weights
        if not res.success:
            logger.warning(f"Optimization '{name}' did not converge successfully: {res.message}. Using best found.")
            
        w_opt = res.x
        w_opt_sum = float(np.sum(w_opt))
        if w_opt_sum > 1e-8:
            w_opt = w_opt / w_opt_sum
        elif w_opt_sum < -1e-8:
            w_opt = w_opt / abs(w_opt_sum)

        # Calculate final metrics for the optimized weights
        sharpe, sortino, ir, max_dd, p_ret, p_std = get_portfolio_metrics(w_opt)
        
        # Calculate daily portfolio returns for this optimized weight
        daily_p_rets = asset_rets_matrix @ w_opt
        cum_wealth = (np.cumprod(1 + daily_p_rets) * 100.0).tolist()
        
        optimized_solutions[name] = {
            'weights': w_opt,
            'cum_wealth': cum_wealth,
            'metrics': {
                'Sharpe Ratio': sharpe,
                'Sortino Ratio': sortino,
                'Information Ratio': ir,
                'Max Drawdown': max_dd,
                'Annualized Return': p_ret,
                'Annualized Volatility': p_std
            }
        }

    # Current weights were precomputed earlier for long/short-aware constraints

    if use_actual_current_ts:
        c_cum_wealth = _cum_wealth_actual
        c_metrics = {
            'Sharpe Ratio': 0.0 if abs(_sharpe_actual) < 1e-9 else _sharpe_actual,
            'Sortino Ratio': 0.0 if abs(_sortino_actual) < 1e-9 else _sortino_actual,
            'Information Ratio': 0.0 if abs(_ir_actual) < 1e-9 else _ir_actual,
            'Max Drawdown': _max_dd_actual,
            'Annualized Return': _p_ret_actual,
            'Annualized Volatility': _p_std_ann_actual
        }
    else:
        c_sharpe, c_sortino, c_ir, c_max_dd, c_ret, c_std = get_portfolio_metrics(current_weights)
        c_daily_p_rets = asset_rets_matrix @ current_weights
        c_cum_wealth = (np.cumprod(1 + c_daily_p_rets) * 100.0).tolist()
        c_metrics = {
            'Sharpe Ratio': c_sharpe,
            'Sortino Ratio': c_sortino,
            'Information Ratio': c_ir,
            'Max Drawdown': c_max_dd,
            'Annualized Return': c_ret,
            'Annualized Volatility': c_std
        }
    
    optimized_solutions['Current'] = {
        'weights': current_weights,
        'cum_wealth': c_cum_wealth,
        'metrics': c_metrics
    }

    if actual_portfolio_metrics:
        # Override with exact metrics from the Overview tab
        optimized_solutions['Current']['metrics'] = {
            'Sharpe Ratio': actual_portfolio_metrics.get('Sharpe Ratio', c_metrics['Sharpe Ratio']),
            'Sortino Ratio': actual_portfolio_metrics.get('Sortino Ratio', c_metrics['Sortino Ratio']),
            'Information Ratio': actual_portfolio_metrics.get('Information Ratio', c_metrics['Information Ratio']),
            'Max Drawdown': abs(actual_portfolio_metrics.get('Max Drawdown', c_metrics['Max Drawdown'])) if actual_portfolio_metrics.get('Max Drawdown') is not None else c_metrics['Max Drawdown'],
            'Annualized Return': actual_portfolio_metrics.get('Annualized Return', c_metrics['Annualized Return']),
            'Annualized Volatility': actual_portfolio_metrics.get('Volatility', c_metrics['Annualized Volatility'])
        }

    dates_str = [d.strftime('%Y-%m-%d') for d in common_dates]
    bench_cum_wealth = (np.cumprod(1 + bench_rets) * 100.0).tolist()

    return {
        'tickers': portfolio_tickers,
        'solutions': optimized_solutions,
        'sectors': sector_series.tolist(),
        'names': name_series.tolist(),
        'dates': dates_str,
        'benchmark_cum_wealth': bench_cum_wealth
    }
