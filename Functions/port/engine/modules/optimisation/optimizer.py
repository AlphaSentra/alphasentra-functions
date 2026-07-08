"""
Portfolio Optimization Engine using Scipy SLSQP.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import logging

logger = logging.getLogger(__name__)

def optimize_portfolio(prices_df, portfolio_df, benchmark_series, sector_industry_df, config, current_weights_dict=None, actual_portfolio_metrics=None):
    """
    Optimizes the portfolio to find 5 distinct solutions:
    1. Max Sharpe Ratio
    2. Max Sortino Ratio
    3. Max Information Ratio
    4. Minimum Max Drawdown
    5. Balanced Multi-Objective Solution

    Supports long-only and long-short modes based on config flags.
    """
    # 1. Align tickers and data
    # Exclude cash positions (e.g. USD=X) — they have no returns to optimize against.
    portfolio_tickers = [
        t for t in portfolio_df['ticker'].tolist()
        if t in prices_df.columns and t != "USD=X"
    ]
    if not portfolio_tickers:
        logger.error("No portfolio tickers found in price data. Optimization cannot run.")
        return None

    # Calculate returns
    daily_returns = prices_df[portfolio_tickers].pct_change()
    daily_returns = daily_returns.replace([np.inf, -np.inf], np.nan)
    daily_returns = daily_returns.dropna(axis=1, how='all')
    daily_returns = daily_returns.dropna(how='any')
    portfolio_tickers = daily_returns.columns.tolist()
    if not portfolio_tickers:
        logger.error("No portfolio tickers with valid return data. Optimization cannot run.")
        return None
    
    daily_benchmark = pd.Series(dtype=float)
    if benchmark_series is not None:
        daily_benchmark = benchmark_series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    
    # Align dates
    common_dates = daily_returns.index.intersection(daily_benchmark.index)
    
    # Slice to trailing 1-year window if requested (default)
    if config.get('opt_lookback', '1y') == '1y':
        anchor = common_dates.max()
        if anchor is not None and not pd.isnull(anchor):
            start_date = anchor - pd.DateOffset(years=1)
            one_year_dates = common_dates[common_dates >= start_date]
            sliced_dates = one_year_dates[-252:]
            if len(sliced_dates) > 0:
                common_dates = sliced_dates
                
    if len(common_dates) < 2:
        logger.error(f"Insufficient aligned data points ({len(common_dates)}) for optimization. Need at least 2.")
        return None
                
    daily_returns = daily_returns.loc[common_dates]
    daily_benchmark = daily_benchmark.loc[common_dates]
    
    num_assets = len(portfolio_tickers)
    
    # Get sector grouping; use safe lookup so missing tickers fall back to 'Others'
    available_tickers = [t for t in portfolio_tickers if t in sector_industry_df.index]
    sector_series = pd.Series('Others', index=portfolio_tickers, dtype=str)
    name_series = pd.Series('', index=portfolio_tickers, dtype=str)
    if available_tickers:
        sector_series.loc[available_tickers] = sector_industry_df.loc[available_tickers, 'sector'].fillna('Others')
        name_series.loc[available_tickers] = sector_industry_df.loc[available_tickers, 'name'].fillna('')
    unique_sectors = sector_series.unique()
    sector_groups = {sector: np.array([sector_series.iloc[i] == sector for i in range(num_assets)]) for sector in unique_sectors}

    # Extract target values & parameters
    max_position_size = config.get('max_position_size', 5.0) / 100.0
    max_sector_size = config.get('max_sector_size', 30.0) / 100.0

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

    long_short = config.get('opt_long_short', False)
    max_short = config.get('max_short_size', 30.0) / 100.0
    gross_target = config.get('opt_gross_exposure', 2.0)

    bounds = []
    if long_short:
        for _ in range(num_assets):
            bounds.append((-max_short, pos_limit))
    else:
        for _ in range(num_assets):
            bounds.append((min_position_size, pos_limit))

    constraints = []
    if long_short:
        constraints.append({
            'type': 'eq',
            'fun': lambda w, gt=gross_target: np.sum(np.abs(w)) - gt
        })
    else:
        constraints.append({
            'type': 'eq',
            'fun': lambda w: np.sum(w) - 1.0
        })

    # 4. Define performance metrics calculation
    mean_rets = daily_returns.mean().values
    cov_matrix = daily_returns.cov().values
    bench_rets = daily_benchmark.values
    asset_rets_matrix = daily_returns.values

    risk_free_rate = 0.02
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1

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

    # Initial guess
    if long_short:
        half = num_assets // 2
        w0 = np.ones(num_assets) * (gross_target / num_assets)
        if half > 0:
            w0[half:] = -w0[half:]
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
        if long_short:
            w_opt = np.clip(w_opt, -max_short, pos_limit)
            gross = np.sum(np.abs(w_opt))
            if gross > 1e-8:
                w_opt = w_opt * (gross_target / gross)
        else:
            w_opt = np.maximum(w_opt, 0)
            w_sum = np.sum(w_opt)
            if w_sum > 0:
                w_opt = w_opt / w_sum
            else:
                w_opt = np.ones(num_assets) / num_assets

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

    # Include Current weights for reference
    # Let's align current weights to our optimizer assets
    current_weights = np.zeros(num_assets)
    # Check if we can extract current weights from current_weights_dict, portfolio_df, etc.
    if current_weights_dict:
        w_dict = current_weights_dict
    elif 'weight' in portfolio_df.columns:
        w_dict = {row['ticker']: row['weight'] for _, row in portfolio_df.iterrows()}
    elif 'quantity' in portfolio_df.columns and not portfolio_df.empty:
        # Standardize quantity
        tot = portfolio_df['quantity'].sum()
        if tot > 0:
            w_dict = {row['ticker']: row['quantity'] / tot for _, row in portfolio_df.iterrows()}
        else:
            w_dict = {}
    else:
        w_dict = {}

    for i, t in enumerate(portfolio_tickers):
        current_weights[i] = w_dict.get(t, 0.0)
        
    c_sum = np.sum(current_weights)
    if not long_short:
        if c_sum > 0:
            current_weights = current_weights / c_sum
        else:
            current_weights = np.ones(num_assets) / num_assets
    else:
        gross = np.sum(np.abs(current_weights))
        if gross > 1e-8:
            current_weights = current_weights * (gross_target / gross)
        else:
            current_weights = np.ones(num_assets) * (gross_target / num_assets)
            half = num_assets // 2
            if half > 0:
                current_weights[half:] = -current_weights[half:]
        
    c_sharpe, c_sortino, c_ir, c_max_dd, c_ret, c_std = get_portfolio_metrics(current_weights)
    c_daily_p_rets = asset_rets_matrix @ current_weights
    c_cum_wealth = (np.cumprod(1 + c_daily_p_rets) * 100.0).tolist()
    
    optimized_solutions['Current'] = {
        'weights': current_weights,
        'cum_wealth': c_cum_wealth,
        'metrics': {
            'Sharpe Ratio': c_sharpe,
            'Sortino Ratio': c_sortino,
            'Information Ratio': c_ir,
            'Max Drawdown': c_max_dd,
            'Annualized Return': c_ret,
            'Annualized Volatility': c_std
        }
    }

    if actual_portfolio_metrics:
        # Override with exact metrics from the Overview tab
        optimized_solutions['Current']['metrics'] = {
            'Sharpe Ratio': actual_portfolio_metrics.get('Sharpe Ratio', c_sharpe),
            'Sortino Ratio': actual_portfolio_metrics.get('Sortino Ratio', c_sortino),
            'Information Ratio': actual_portfolio_metrics.get('Information Ratio', c_ir),
            'Max Drawdown': abs(actual_portfolio_metrics.get('Max Drawdown', c_max_dd)) if actual_portfolio_metrics.get('Max Drawdown') is not None else c_max_dd,
            'Annualized Return': actual_portfolio_metrics.get('Annualized Return', c_ret),
            'Annualized Volatility': actual_portfolio_metrics.get('Volatility', c_std)
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
