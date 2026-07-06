from statsmodels.tsa.arima.model import ARIMA
import os
import pandas as pd
import numpy as np
import json
from jinja2 import Template

from config import (
    HOLDINGS_CAUTION_ALERT_BG, HOLDINGS_ATTENTION_ALERT_BG, HOLDINGS_MONITOR_ALERT_BG,
    HOLDINGS_BULL_MOMENTUM_BG, HOLDINGS_BEAR_MOMENTUM_BG, HOLDINGS_NEUTRAL_MOMENTUM_BG,
    ZSCORE_OVERSOLD, ZSCORE_OVERBOUGHT, ZSCORE_NEUTRAL, NO_PRICE_COLOR,
    UPSIDE_PRICE_TEXT, DOWNSIDE_PRICE_TEXT, NEUTRAL_PRICE_TEXT,
    TREND_ACCEL_BAR, TREND_DECEL_BAR, TREND_NEUTRAL_BAR, TREND_ACCEL_TEXT, TREND_DECEL_TEXT, TREND_NEUTRAL_TEXT,
    RSI_OVERSOLD_BG, RSI_OVERBOUGHT_BG,
    HOLDINGS_EXPORT_BG, BUTTON_TEXT, HOLDINGS_TOOLTIP_BG, HOLDINGS_HEADER_BG, HOLDINGS_HEADER_TEXT, HOLDINGS_CELL_BORDER, HOLDINGS_HEADER_HOVER, HOLDINGS_ROW_ALT, HOLDINGS_ROW_HOVER, HOLDINGS_SORT_ARROW, HOLDINGS_SORT_ARROW_TEXT, HOLDINGS_STDEV_LABEL, HOLDINGS_TOOLTIP_BOX_SHADOW,
    TEXT_PRIMARY, NEUTRAL_SURFACE, ANALYSIS_PAGE_URL, BG_BUTTON_PRIMARY,
)


def generate_portfolio_holdings_analysis(risk_contrib, sector_industry_df, price_data, portfolio_df):
    """
    Generates a table of portfolio holdings sorted by weight from largest to lowest.
    Returns tuple (html_table, holdings_df).
    """
    # Merge all data
    holdings = risk_contrib[['Weight']].merge(sector_industry_df, left_index=True, right_index=True, how='left')
    cols = ['ticker', 'type']
    if 'quantity' in portfolio_df.columns:
        cols.append('quantity')
    if 'avg_price' in portfolio_df.columns:
        cols.append('avg_price')
    elif 'average_cost' in portfolio_df.columns:
        cols.append('average_cost')
    
    # Safety check: if columns are missing (e.g. empty portfolio_df), skip the merge
    if all(col in portfolio_df.columns for col in ['ticker', 'type']):
        holdings = holdings.merge(portfolio_df[cols].drop_duplicates().set_index('ticker'), left_index=True, right_index=True, how='left')
    else:
        # If missing, initialize with defaults
        if 'quantity' not in holdings.columns:
            holdings['quantity'] = 1.0
        if 'type' not in holdings.columns:
            holdings['type'] = 'active'
    holdings['type'] = holdings['type'].fillna('active').astype(str)
    if 'quantity' not in holdings.columns:
        holdings['quantity'] = 1.0 # Default to Long if unknown
    
    # Calculate percentage growth and momentum spread
    # price_data columns are tickers, index are dates
    growth_pct = {}
    momentum_spreads = {}
    momentum_signals = {}
    reversal_risks = {}
    rsis = {}
    alerts = {}
    perf_metrics = {}
    z_scores = {}
    pnl_pcts = {}
    dist_to_highs = {}
    z_score_max_5y = {}
    z_score_min_5y = {}
    est_dips = {}
    est_peaks = {}
    # Statistics for historical oversold outcomes
    expected_downsides = {}
    worst_downsides = {}
    reversal_probs = {}
    oversold_threshold_used = {}
    expected_upsides = {}
    worst_upsides = {}
    overbought_threshold_used = {}
    biases = {}  # asymmetry: (upside - |downside|)
    expected_returns = {}  # efficiency metric ER (1Y)
    
    for ticker in holdings.index:
        # Get price series for ticker
        ticker_prices = None
        if isinstance(price_data.columns, pd.MultiIndex):
            if ticker in price_data['Close'].columns:
                ticker_prices = price_data['Close'][ticker].dropna()
        elif 'Close' in price_data.columns:
            # Assuming single ticker structure or similar
            ticker_prices = price_data['Close'].dropna()
        else:
             # Fallback if price_data is already a Series
             ticker_prices = price_data[ticker].dropna() if ticker in price_data.columns else None

        if ticker_prices is not None and not ticker_prices.empty:
            end_price = ticker_prices.iloc[-1]
            
            # PnL Calculation
            avg_price = holdings.loc[ticker].get("avg_price", holdings.loc[ticker].get("average_cost", 0))
            
            if pd.notna(avg_price) and avg_price > 0:
                direction = holdings.loc[ticker].get("type", "active")
                if direction == "S":
                    pnl = (avg_price - end_price) / avg_price * 100
                else:
                    pnl = (end_price - avg_price) / avg_price * 100
            else:
                pnl = 0.0
            pnl_pcts[ticker] = pnl
            
            # Momentum Spread calculation (Price vs 200d SMA)
            if len(ticker_prices) >= 200:
                sma200 = ticker_prices.rolling(window=200).mean().iloc[-1]
                spread = (end_price / sma200) - 1
            elif len(ticker_prices) >= 20:
                # Fallback to shorter SMA if 200d not available
                sma_alt = ticker_prices.rolling(window=len(ticker_prices)).mean().iloc[-1]
                spread = (end_price / sma_alt) - 1
            else:
                spread = 0.0
            
            momentum_spreads[ticker] = spread
            
            if spread > 0.02:
                momentum_signals[ticker] = "BULL"
            elif spread < -0.02:
                momentum_signals[ticker] = "BEAR"
            else:
                momentum_signals[ticker] = "NEUT"
            
            if len(ticker_prices) < 20:
                momentum_signals[ticker] = "N/A"
            
            # Performance metrics
            p_current = ticker_prices.iloc[-1]
            p_1w = ticker_prices.iloc[-min(len(ticker_prices), 6)] # 5 sessions ago
            p_1m = ticker_prices.iloc[-min(len(ticker_prices), 22)] # 21 sessions ago
            p_3m = ticker_prices.iloc[-min(len(ticker_prices), 64)] # 63 sessions ago
            p_1y = ticker_prices.iloc[-min(len(ticker_prices), 252)] # ~1Y
            p_5y = ticker_prices.iloc[-min(len(ticker_prices), 1260)] # ~5Y
            p_all = ticker_prices.iloc[0] # inception
            
            ret_1w = (p_current / p_1w - 1)
            ret_1m = (p_current / p_1m - 1)
            ret_3m = (p_current / p_3m - 1)
            ret_1y = (p_current / p_1y - 1)
            ret_5y = (p_current / p_5y - 1)
            ret_all = (p_current / p_all - 1)
            perf_metrics[ticker] = {'1w': ret_1w, '1m': ret_1m, '3m': ret_3m, '1y': ret_1y, '5y': ret_5y, 'all': ret_all}
            
            # Expected Return ER (1Y) — price action model: 12M trend + 3M momentum + mean reversion + ARIMA
            w1, w2, w3, w4 = 0.5, 0.3, 0.2, 0.2
            days_252 = min(len(ticker_prices) - 1, 252)
            days_63 = min(len(ticker_prices) - 1, 63)
            days_200 = min(len(ticker_prices), 200)
            ret_12m = ticker_prices.iloc[-1] / ticker_prices.iloc[-days_252] - 1 if days_252 >= 1 else np.nan
            ret_3m = ticker_prices.iloc[-1] / ticker_prices.iloc[-days_63] - 1 if days_63 >= 1 else np.nan
            ma_200 = ticker_prices.rolling(days_200).mean().iloc[-1] if days_200 >= 1 else np.nan
            mean_reversion = -(end_price / ma_200 - 1) if pd.notna(ma_200) and ma_200 != 0 else np.nan
            arima_contrib = np.nan
            if len(ticker_prices.dropna()) >= 10:
                try:
                    model = ARIMA(ticker_prices.dropna(), order=(1, 1, 1))
                    fitted = model.fit()
                    forecast = fitted.forecast(steps=1).iloc[0]
                    arima_contrib = (forecast / end_price - 1)
                except Exception:
                    arima_contrib = np.nan
            er_vals = [v for v in [ret_12m, ret_3m, mean_reversion] if pd.notna(v)]
            if er_vals:
                expected_return = (w1 * ret_12m if pd.notna(ret_12m) else 0.0) + \
                                  (w2 * ret_3m if pd.notna(ret_3m) else 0.0) + \
                                  (w3 * mean_reversion if pd.notna(mean_reversion) else 0.0) + \
                                  (w4 * arima_contrib if pd.notna(arima_contrib) else 0.0)
                direction = holdings.loc[ticker].get("type", "active")
                if direction == "S":
                    expected_return = -expected_return
                expected_returns[ticker] = expected_return
            else:
                expected_returns[ticker] = np.nan

            # Z-Score and Est. dip/peak Calculation using return-space framework
            # Core: operate in log-return space, convert back via exponentiation
            if len(ticker_prices) >= 20:
                lookback = min(len(ticker_prices), 252)
                recent_prices = ticker_prices.iloc[-lookback:]
                
                # --- Compute log returns ---
                log_returns = np.log(recent_prices / recent_prices.shift(1)).dropna()
                
                if len(log_returns) >= 10:
                    mu_r = log_returns.mean()
                    sigma_r = log_returns.std()
                    
                    if sigma_r > 0:
                        # Current price
                        P0 = end_price
                        
                        # Current Z-score in return space: Z0 = (r_current - μ_r) / σ_r
                        # where r_current is the latest log return
                        r_current = log_returns.iloc[-1]
                        Z0 = (r_current - mu_r) / sigma_r
                        z_scores[ticker] = Z0
                        
                        # 5-year rolling Z-score extremes (for target Z selection)
                        if len(ticker_prices) >= 252:
                            price_returns = np.log(ticker_prices / ticker_prices.shift(1)).dropna()
                            if len(price_returns) >= 252:
                                rolling_window = 252
                                rolling_mean = price_returns.rolling(window=rolling_window).mean()
                                rolling_std = price_returns.rolling(window=rolling_window).std()
                                rolling_z = (price_returns - rolling_mean) / rolling_std
                                rolling_z = rolling_z.replace([np.inf, -np.inf], np.nan)
                                rolling_z_valid = rolling_z.dropna()
                                if not rolling_z_valid.empty:
                                    z_score_max_5y[ticker] = rolling_z_valid.max()
                                    z_score_min_5y[ticker] = rolling_z_valid.min()
                                else:
                                    z_score_max_5y[ticker] = np.nan
                                    z_score_min_5y[ticker] = np.nan
                            else:
                                # Not enough returns to compute a full rolling window
                                z_score_max_5y[ticker] = np.nan
                                z_score_min_5y[ticker] = np.nan
                        else:
                            z_score_max_5y[ticker] = np.nan
                            z_score_min_5y[ticker] = np.nan
                        
                        # --- Target Z-scores ---
                        Z_os = z_score_min_5y.get(ticker, Z0 - 2.0)
                        Z_ob = z_score_max_5y.get(ticker, Z0 + 2.0)
                        
                        # Fallback if still NaN
                        if pd.isna(Z_os):
                            Z_os = Z0 - 2.0
                        if pd.isna(Z_ob):
                            Z_ob = Z0 + 2.0
                        
                        # Save thresholds used
                        oversold_threshold_used[ticker] = Z_os
                        overbought_threshold_used[ticker] = Z_ob
                        
                        # --- Regime Adjustment (optional) ---
                        # Increase volatility during stress (extreme |Z0|)
                        # σ_adj = σ_r * (1 + k * |Z0|) with k = 0.1
                        sigma_adj = sigma_r * (1 + 0.1 * abs(Z0))
                        
                        # --- Est. dip (oversold target) ---
                        # P_os = P0 * exp((Z_os - Z0) * σ_adj)
                        est_dip_val = P0 * np.exp((Z_os - Z0) * sigma_adj)
                        # Est. dip should not exceed current price (floor at current if target is less oversold)
                        if est_dip_val > P0:
                            est_dip_val = P0
                        est_dips[ticker] = max(est_dip_val, 0.0)  # floor at $0.00
                        
                        # --- Est. peak (overbought target) ---
                        # P_ob = P0 * exp((Z_ob - Z0) * σ_adj)
                        est_peak_val = P0 * np.exp((Z_ob - Z0) * sigma_adj)
                        # Est. peak should not be below current price (ceiling at current if target is less overbought)
                        if est_peak_val < P0:
                            est_peak_val = P0
                        est_peaks[ticker] = est_peak_val
                        
                        # --- Implied return ranges ---
                        # expected_downside/upside as returns from current to target
                        expected_downsides[ticker] = (est_dips[ticker] - P0) / P0
                        expected_upsides[ticker] = (est_peaks[ticker] - P0) / P0
                        # Bias: positive = more upside expected, negative = more downside expected
                        biases[ticker] = expected_upsides[ticker] - abs(expected_downsides[ticker])
                        # worst-case: use a more extreme Z (e.g., Z0 ± 2σ beyond target)
                        Z_os_worst = min(Z_os, Z0) - 2.0
                        Z_ob_worst = max(Z_ob, Z0) + 2.0
                        worst_downsides[ticker] = (P0 * np.exp((Z_os_worst - Z0) * sigma_adj) - P0) / P0
                        worst_upsides[ticker] = (P0 * np.exp((Z_ob_worst - Z0) * sigma_adj) - P0) / P0
                        reversal_probs[ticker] = np.nan  # not estimated in this framework
                    else:
                        z_scores[ticker] = 0.0
                        z_score_max_5y[ticker] = np.nan
                        z_score_min_5y[ticker] = np.nan
                        est_dips[ticker] = np.nan
                        est_peaks[ticker] = np.nan
                        expected_downsides[ticker] = np.nan
                        worst_downsides[ticker] = np.nan
                        expected_upsides[ticker] = np.nan
                        worst_upsides[ticker] = np.nan
                        oversold_threshold_used[ticker] = np.nan
                        overbought_threshold_used[ticker] = np.nan
                        reversal_probs[ticker] = np.nan
                else:
                    z_scores[ticker] = 0.0
                    z_score_max_5y[ticker] = np.nan
                    z_score_min_5y[ticker] = np.nan
                    est_dips[ticker] = np.nan
                    est_peaks[ticker] = np.nan
                    expected_downsides[ticker] = np.nan
                    worst_downsides[ticker] = np.nan
                    expected_upsides[ticker] = np.nan
                    worst_upsides[ticker] = np.nan
                    oversold_threshold_used[ticker] = np.nan
                    overbought_threshold_used[ticker] = np.nan
                    reversal_probs[ticker] = np.nan
            else:
                z_scores[ticker] = 0.0
                z_score_max_5y[ticker] = np.nan
                z_score_min_5y[ticker] = np.nan
                est_dips[ticker] = np.nan
                est_peaks[ticker] = np.nan
                expected_downsides[ticker] = np.nan
                worst_downsides[ticker] = np.nan
                expected_upsides[ticker] = np.nan
                worst_upsides[ticker] = np.nan
                oversold_threshold_used[ticker] = np.nan
                overbought_threshold_used[ticker] = np.nan
                reversal_probs[ticker] = np.nan

            # Distance to 52W High calculation
            if len(ticker_prices) >= 252:
                high_52w = ticker_prices.iloc[-252:].max()
            elif len(ticker_prices) >= 20:
                high_52w = ticker_prices.max()
            else:
                high_52w = end_price if len(ticker_prices) > 0 else 0
            if high_52w > 0:
                dist_to_high = (high_52w - end_price) / high_52w * 100
            else:
                dist_to_high = 0.0
            dist_to_highs[ticker] = dist_to_high

            # Short-term Reversal Risk calculation (RSI 14)
            if len(ticker_prices) >= 15:
                delta = ticker_prices.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                # Avoid division by zero
                rs = gain / loss.replace(0, np.nan)
                rsi_series = 100 - (100 / (1 + rs))
                rsi = rsi_series.iloc[-1]
                rsis[ticker] = rsi
                
                if rsi > 70:
                    reversal_risks[ticker] = "OVERBOUGHT"
                elif rsi < 30:
                    reversal_risks[ticker] = "OVERSOLD"
                else:
                    reversal_risks[ticker] = "STABLE"
            else:
                rsis[ticker] = 50.0
                reversal_risks[ticker] = "N/A"
        else:
            momentum_spreads[ticker] = 0.0
            momentum_signals[ticker] = "N/A"
            rsis[ticker] = 50.0
            reversal_risks[ticker] = "N/A"
            perf_metrics[ticker] = {'1w': 0, '1m': 0, '3m': 0, '1y': 0, '5y': 0, 'all': 0}
            expected_returns[ticker] = np.nan
            z_scores[ticker] = 0.0
            z_score_max_5y[ticker] = np.nan
            z_score_min_5y[ticker] = np.nan
            dist_to_highs[ticker] = 0.0

    
    holdings['momentum_spread'] = pd.Series(momentum_spreads)
    holdings['momentum_signal'] = pd.Series(momentum_signals)
    holdings['reversal_risk'] = pd.Series(reversal_risks)
    holdings['rsi'] = pd.Series(rsis)
    holdings['z_score'] = pd.Series(z_scores)
    holdings['z_score_max_5y'] = pd.Series(z_score_max_5y)
    holdings['z_score_min_5y'] = pd.Series(z_score_min_5y)
    holdings['est_dip'] = pd.Series(est_dips)
    holdings['est_peak'] = pd.Series(est_peaks)
    holdings['expected_downside'] = pd.Series(expected_downsides)
    holdings['worst_downside'] = pd.Series(worst_downsides)
    holdings['reversal_prob'] = pd.Series(reversal_probs)
    holdings['oversold_threshold_used'] = pd.Series(oversold_threshold_used)
    holdings['expected_upside'] = pd.Series(expected_upsides)
    holdings['worst_upside'] = pd.Series(worst_upsides)
    holdings['overbought_threshold_used'] = pd.Series(overbought_threshold_used)
    holdings['bias'] = pd.Series(biases)
    holdings['expected_return'] = pd.Series(expected_returns)
    holdings['dist_to_52w_high'] = pd.Series(dist_to_highs)
    holdings['ret_1w'] = pd.Series({k: v['1w'] for k, v in perf_metrics.items()})
    holdings['ret_1m'] = pd.Series({k: v['1m'] for k, v in perf_metrics.items()})
    holdings['ret_3m'] = pd.Series({k: v['3m'] for k, v in perf_metrics.items()})
    holdings['ret_1y'] = pd.Series({k: v['1y'] for k, v in perf_metrics.items()})
    holdings['ret_5y'] = pd.Series({k: v['5y'] for k, v in perf_metrics.items()})
    holdings['ret_all'] = pd.Series({k: v['all'] for k, v in perf_metrics.items()})
    holdings['pnl_pct'] = pd.Series(pnl_pcts)
    
    # Calculate Trend Acceleration (1W vs 1M trend)
    accel_list = []
    accel_scores = []
    for ticker, row in holdings.iterrows():
        # Average weekly return based on 1M performance
        avg_w_1m = row['ret_1m'] / 4.2
        diff = row['ret_1w'] - avg_w_1m
        score = diff * 100 # In percentage points
        
        if diff > 0.02:
            accel_list.append("ACCEL")
        elif diff < -0.02:
            accel_list.append("DECEL")
        else:
            accel_list.append("FLAT")
        accel_scores.append(score)
    holdings['trend_accel'] = accel_list
    holdings['accel_score'] = accel_scores
    
    # Calculate industry average Forward P/E for comparison
    # Ensure forward_pe, eps_growth, ev_ebitda are numeric before comparison
    holdings['forward_pe'] = pd.to_numeric(holdings['forward_pe'], errors='coerce').fillna(0.0)
    holdings['eps_growth'] = pd.to_numeric(holdings['eps_growth'], errors='coerce').fillna(0.0)
    holdings['ev_ebitda'] = pd.to_numeric(holdings['ev_ebitda'], errors='coerce').fillna(0.0)
    
    valid_pes = holdings[holdings['forward_pe'] > 0]
    if not valid_pes.empty:
        industry_avg_pes = valid_pes.groupby('industry')['forward_pe'].mean()
        holdings['industry_avg_pe'] = holdings['industry'].map(industry_avg_pes)
    else:
        holdings['industry_avg_pe'] = 0.0

    valid_eps = holdings[holdings['eps_growth'] != 0]
    if not valid_eps.empty:
        industry_avg_eps = valid_eps.groupby('industry')['eps_growth'].mean()
        holdings['industry_avg_eps'] = holdings['industry'].map(industry_avg_eps)
    else:
        holdings['industry_avg_eps'] = 0.0
        
    valid_ev = holdings[holdings['ev_ebitda'] > 0]
    if not valid_ev.empty:
        industry_avg_ev = valid_ev.groupby('industry')['ev_ebitda'].mean()
        holdings['industry_avg_ev'] = holdings['industry'].map(industry_avg_ev)
    else:
        holdings['industry_avg_ev'] = 0.0

    # Calculate Alerts with Multi-Factor Scoring
    alert_list = []
    alert_colors = []
    for ticker, row in holdings.iterrows():
        # 1. Valuation Score (vs Industry)
        pe_diff = (row['forward_pe'] / row['industry_avg_pe'] - 1) if row['industry_avg_pe'] > 0 else 0
        v_score = 2 if pe_diff < -0.15 else 1 if pe_diff < -0.05 else -2 if pe_diff > 0.25 else -1 if pe_diff > 0.10 else 0
        
        # 2. Momentum Score (Long-term)
        m_score = 2 if row['momentum_signal'] == "BULL" else -2
        
        # 3. Reversal Score (Short-term Exhaustion)
        rsi = row['rsi']
        r_score = 1 if rsi < 35 else -2 if rsi > 75 else 0
        
        # 4. Velocity Score (Trend Accel)
        vel = row['accel_score']
        vel_score = 1 if vel > 8 else -1 if vel < -8 else 0
        
        # 5. Performance Profile (multi-month consistency)
        r1w, r1m, r3m = row['ret_1w'], row['ret_1m'], row['ret_3m']
        p_score = 1 if (r1w > 0 and r1m > 0 and r3m > 0) else -1 if r1w < -0.07 else 0
        
        # 5b. 1M Performance Score (standalone momentum)
        m1m_score = 0
        if r1m > 0.05:
            m1m_score = 2   # strong 1M positive momentum
        elif r1m > 0.01:
            m1m_score = 1   # mild 1M positive momentum
        elif r1m < -0.05:
            m1m_score = -2  # strong 1M negative momentum
        elif r1m < -0.01:
            m1m_score = -1  # mild 1M negative momentum
        # else → 0 (flat)
        
        # 6. Urgent Penalty — severe short-term distress (direction-dependent)
        # For longs: large drop (r1w < -10%) or extreme overbought (RSI > 85) = distress
        # For shorts: large rally (r1w > +10%) or extreme oversold (RSI < 15) = distress
        # These are always negative contributions.
        urgent_penalty = 0
        if row['quantity'] < 0:  # SHORT position
            if r1w > 0.10:
                urgent_penalty -= 4
            if rsi < 15:
                urgent_penalty -= 4
        else:  # LONG position (default)
            if r1w < -0.10:
                urgent_penalty -= 4
            if rsi > 85:
                urgent_penalty -= 4
        
        # 7. Bias Score (Expected upside vs downside asymmetry)
        bias_val = row.get('bias', np.nan)
        bias_score = 0
        if pd.notna(bias_val):
            if bias_val > 0.08:
                bias_score = 3  # strong bullish asymmetry
            elif bias_val > 0.04:
                bias_score = 2  # moderate bullish asymmetry
            elif bias_val > 0.01:
                bias_score = 1  # mild bullish asymmetry
            elif bias_val < -0.08:
                bias_score = -3  # strong bearish asymmetry
            elif bias_val < -0.04:
                bias_score = -2  # moderate bearish asymmetry
            elif bias_val < -0.01:
                bias_score = -1  # mild bearish asymmetry
            # else near-zero → 0
        
        # Base score (direction-sensitive: invert for shorts)
        base_total = v_score + m_score + r_score + vel_score + p_score + m1m_score + bias_score
        if row['quantity'] < 0:  # SHORT → flip base signal polarity
            base_total = -base_total
        
        total_score = base_total + urgent_penalty
        
        # Determine Final Alert — ordered by severity: Caution > Attention > Neutral > Monitor
        if total_score <= -5:
            alert, color = "Caution", HOLDINGS_CAUTION_ALERT_BG
        elif total_score <= -2:
            alert, color = "Attention", HOLDINGS_ATTENTION_ALERT_BG
        elif total_score >= 4:
            alert, color = "Monitor", HOLDINGS_MONITOR_ALERT_BG
        else:
            alert, color = "Neutral", "transparent"
        
        alert_list.append(alert)
        alert_colors.append(color)
    
    holdings['alert'] = alert_list
    holdings['alert_color'] = alert_colors


    # Prepare latest prices for display
    latest_prices = {}
    for ticker in holdings.index:
        ticker_prices = None
        if isinstance(price_data.columns, pd.MultiIndex):
            if ticker in price_data['Close'].columns:
                ticker_prices = price_data['Close'][ticker].dropna()
        elif 'Close' in price_data.columns:
            ticker_prices = price_data['Close'].dropna()
        else:
            ticker_prices = price_data[ticker].dropna() if ticker in price_data.columns else None
        
        if ticker_prices is not None and not ticker_prices.empty:
            latest_prices[ticker] = ticker_prices.iloc[-1]
    holdings['latest_price'] = pd.Series(latest_prices)

    # Prepare chart data for JavaScript
    chart_data_dict = {}
    cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=1)
    for ticker in holdings.index:
        # Determine ticker Close series (mirrors the latest_prices loop above)
        ticker_prices = None
        if isinstance(price_data.columns, pd.MultiIndex):
            if ticker in price_data['Close'].columns:
                ticker_prices = price_data['Close'][ticker].dropna()
        elif 'Close' in price_data.columns:
            ticker_prices = price_data['Close'].dropna()
        else:
            ticker_prices = price_data[ticker].dropna() if ticker in price_data.columns else None

        if ticker_prices is not None and not ticker_prices.empty:
            # Filter for last 1 year
            ticker_prices = ticker_prices[ticker_prices.index >= cutoff_date]
            data = []
            for date, val in ticker_prices.items():
                if hasattr(date, 'strftime'):
                    data.append({
                        'time': date.strftime('%Y-%m-%d'),
                        'value': float(val)
                    })
            chart_data_dict[ticker] = data
    chart_data_json = json.dumps(chart_data_dict)

    # Define Column Configurations for each view
    VIEW_CONFIGS = {
        'components': {
             'columns': ['Analysis', 'Direction', 'Avg Entry', 'Latest Price', 'Ticker', 'Name', 'Sector', 'Weight (%)', 'Performance', 'Div Yield (%)', 'PnL (%)', 'Action Alert'],
            'widths': [70, 60, 60, 70, 70, 200, 150, 70, 70, 70, 70, 70],
            'tooltips': {
                'Analysis': "Ticker Analysis:\nClick to open the detailed analysis page for this ticker.",
                'Direction': "Position Direction:\nShows if the position is long (buy) or short (sell).",
                'Avg Entry': "Average Entry Price:\nThe average price at which shares, assets or instruments were acquired.",
                'Latest Price': "Latest Market Price:\nThe most recent closing price of the security.",
                'Analysis': "Ticker Analysis:\nClick to open the detailed analysis page for this ticker.",
                'Name': "Asset Name:\nThe full name of the security.",
                'Sector': "Sector:\nThe industry sector classification of the security.",
                'Weight (%)': "Portfolio Weight:\nThe percentage of the total portfolio value represented by this holding.",
                'Perf (3M, 1M, 1W)': "Performance Metrics (3M, 1M, 1W):\nPercentage returns over the last 3 months, 1 month, and 1 week.",
                'Div Yield (%)': "Dividend Yield (%):\nAnnual dividend yield percentage based on the latest dividend payout.",
                'PnL (%)': "Profit and Loss:\nThe unrealized gain or loss of the position.",
                'Action Alert': "Action Alert:\nRecommended action based on a multi-factor scoring system that aggregates 8 indicators. For short positions, the signal polarity is inverted (bullish signals are negative, bearish signals are positive).\n\nScoring factors:\n\n1. Valuation (vs industry): PE, EPS growth, EV/EBITDA\n   • Undervalued (−15%% to −5%%) → +1/+2 | Overvalued (+10%% to +25%%) → −1/−2\n\n2. Momentum (long-term trend): SMA200 spread\n   • Bull (spread > 2%%) → +2 | Bear (spread < −2%%) → −2\n\n3. Reversal (short-term exhaustion): RSI 14\n   • Oversold RSI < 35 → +1 | Overbought RSI > 75 → −2\n\n4. Velocity (trend acceleration): (ret_1w − ret_1m/4.2) × 100\n   • Accel > +8 pts → +1 | Decel < −8 pts → −1\n\n5. Consistency (multi-month performance)\n   • All 1W/1M/3M positive → +1 | 1W < −7%% → −1\n\n6. 1M Momentum (standalone monthly return)\n   • r1m > +5%% → +2 | +1%% < r1m ≤ +5%% → +1\n   • −5%% ≤ r1m < −1%% → −1 | r1m < −5%% → −2\n\n7. Bias (expected upside vs downside asymmetry)\n   • bias > +8%% → +3 | bias > +4%% → +2 | bias > +1%% → +1\n   • bias < −1%% → −1 | bias < −4%% → −2 | bias < −8%% → −3\n\n8. Urgency (severe short-term distress)\n   • 1W return < −10%% → −4 | RSI > 85 → −4\n\nPosition direction inversion:\n  • Long positions: bullish signals (+) are favorable, bearish (−) are unfavorable\n  • Short positions: polarity inverted; bullish signals are unfavorable, bearish signals are favorable\n\nScore thresholds (after direction adjustment):\n  • score ≥ +4  → Monitor  (green)   — favorable outlook\n  • −2 < score < +4 → Neutral   (transparent) — hold\n  • −5 < score ≤ −2 → Attention (orange) — moderate risk\n  • score ≤ −5  → Caution   (red)    — high risk"
            }
        },
        'fundamentals': {
            'columns': ['Direction', 'Avg Entry', 'Ticker', 'Name', 'Weight (%)', 'Forward P/E', 'EPS Growth (%)', 'EV/EBITDA', 'ROE (%)', 'Current Ratio', 'Performance', 'PnL (%)', 'Action Alert'],
            'widths': [60, 60, 60, 200, 70, 70, 70, 70, 70, 80, 70, 70, 70],
            'tooltips': {
                'Direction': "Position Direction:\nL = Long (positive weight), S = Short (negative weight/position).",
                'Avg Entry': "Average Entry Price:\nAverage acquisition price of the position.",
                'Ticker': "Ticker Symbol",
                'Name': "Asset Name:\nFull name of the security.",
                'Weight (%)': "Portfolio Weight:\nPercentage of total portfolio value.",
                'Forward P/E': "Forward Price-to-Earnings:\nCompany's forward P/E ratio vs industry average. Up arrow = cheaper than industry avg.",
                'EPS Growth (%)': "EPS Growth (%):\nYear-over-year earnings per share growth rate.",
                'EV/EBITDA': "EV/EBITDA:\nEnterprise Value to EBITDA ratio – valuation multiple.",
                'ROE (%)': "ROE (%):\nReturn on Equity – profitability percentage.",
                'Current Ratio': "Current Ratio:\nLiquidity ratio (current assets / current liabilities).",
                'Perf (3M, 1M, 1W)': "Performance Metrics (3M, 1M, 1W):\nPercentage returns over the last 3 months, 1 month, and 1 week.",
                'PnL (%)': "Profit and Loss:\nThe unrealized gain or loss of the position.",
                'Action Alert': "Action Alert:\nRecommended action based on a multi-factor scoring system that aggregates 8 indicators. For short positions, the signal polarity is inverted (bullish signals are negative, bearish signals are positive).\n\nScoring factors:\n\n1. Valuation (vs industry): PE, EPS growth, EV/EBITDA\n   • Undervalued (−15%% to −5%%) → +1/+2 | Overvalued (+10%% to +25%%) → −1/−2\n\n2. Momentum (long-term trend): SMA200 spread\n   • Bull (spread > 2%%) → +2 | Bear (spread < −2%%) → −2\n\n3. Reversal (short-term exhaustion): RSI 14\n   • Oversold RSI < 35 → +1 | Overbought RSI > 75 → −2\n\n4. Velocity (trend acceleration): (ret_1w − ret_1m/4.2) × 100\n   • Accel > +8 pts → +1 | Decel < −8 pts → −1\n\n5. Consistency (multi-month performance)\n   • All 1W/1M/3M positive → +1 | 1W < −7%% → −1\n\n6. 1M Momentum (standalone monthly return)\n   • r1m > +5%% → +2 | +1%% < r1m ≤ +5%% → +1\n   • −5%% ≤ r1m < −1%% → −1 | r1m < −5%% → −2\n\n7. Bias (expected upside vs downside asymmetry)\n   • bias > +8%% → +3 | bias > +4%% → +2 | bias > +1%% → +1\n   • bias < −1%% → −1 | bias < −4%% → −2 | bias < −8%% → −3\n\n8. Urgency (severe short-term distress)\n   • 1W return < −10%% → −4 | RSI > 85 → −4\n\nPosition direction inversion:\n  • Long positions: bullish signals (+) are favorable, bearish (−) are unfavorable\n  • Short positions: polarity inverted; bullish signals are unfavorable, bearish signals are favorable\n\nScore thresholds (after direction adjustment):\n  • score ≥ +4  → Monitor  (green)   — favorable outlook\n  • −2 < score < +4 → Neutral   (transparent) — hold\n  • −5 < score ≤ −2 → Attention (orange) — moderate risk\n  • score ≤ −5  → Caution   (red)    — high risk"
            }
        },
        'technicals': {
            'columns': ['Direction', 'Avg Entry', 'Ticker', 'Name', 'Weight (%)', 'Momentum Spread', 'Trend Velocity', 'RSI', 'Distance to 52W High', 'Performance', 'PnL (%)', 'Action Alert'],
            'widths': [60, 60, 60, 200, 70, 90, 90, 70, 70, 70, 70, 70],
            'tooltips': {
                'Direction': "Position Direction:\nL = Long (positive weight), S = Short (negative weight/position).",
                'Avg Entry': "Average Entry Price:\nThe average price at which the position was acquired.",
                'Ticker': "Ticker Symbol",
                'Name': "Asset Name:\nThe full name of the security.",
                'Weight (%)': "Portfolio Weight:\nThe percentage of the total portfolio value represented by this holding.",
                'Momentum Spread': "Momentum Spread:\nThe percentage difference between the current price and its 200-day moving average. Positive indicates price above SMA200 (bullish), negative indicates below (bearish).",
                'Trend Velocity': "Trend Velocity:\nMeasures trend acceleration by comparing 1-week return vs average weekly return over last month (ret_1m/4.2). Formula: (ret_1w - ret_1m/4.2) × 100. Positive = ACCEL (speeding up), Negative = DECEL (slowing down), Near zero = FLAT. Threshold: >+2 pts = ACCEL, <-2 pts = DECEL. Bar count shows magnitude; green=positive, red=negative, gray=neutral.",
                'RSI': "RSI (14):\nRelative Strength Index measuring momentum and overbought/oversold conditions. Above 70 = overbought, below 30 = oversold.",
                'Distance to 52W High': "Distance to 52W High:\nPercentage difference between current price and the 52-week high. Positive means below the high, negative means above it.",
                'Perf (3M, 1M, 1W)': "Performance Metrics (3M, 1M, 1W):\nPercentage returns over the last 3 months, 1 month, and 1 week.",
                'PnL (%)': "Profit and Loss:\nThe unrealized gain or loss of the position.",
                 'Action Alert': "Action Alert:\nRecommended action based on a multi-factor scoring system that aggregates 8 indicators. For short positions, the signal polarity is inverted (bullish signals are negative, bearish signals are positive).\n\nScoring factors:\n\n1. Valuation (vs industry): PE, EPS growth, EV/EBITDA\n   • Undervalued (−15%% to −5%%) → +1/+2 | Overvalued (+10%% to +25%%) → −1/−2\n\n2. Momentum (long-term trend): SMA200 spread\n   • Bull (spread > 2%%) → +2 | Bear (spread < −2%%) → −2\n\n3. Reversal (short-term exhaustion): RSI 14\n   • Oversold RSI < 35 → +1 | Overbought RSI > 75 → −2\n\n4. Velocity (trend acceleration): (ret_1w − ret_1m/4.2) × 100\n   • Accel > +8 pts → +1 | Decel < −8 pts → −1\n\n5. Consistency (multi-month performance)\n   • All 1W/1M/3M positive → +1 | 1W < −7%% → −1\n\n6. 1M Momentum (standalone monthly return)\n   • r1m > +5%% → +2 | +1%% < r1m ≤ +5%% → +1\n   • −5%% ≤ r1m < −1%% → −1 | r1m < −5%% → −2\n\n7. Bias (expected upside vs downside asymmetry)\n   • bias > +8%% → +3 | bias > +4%% → +2 | bias > +1%% → +1\n   • bias < −1%% → −1 | bias < −4%% → −2 | bias < −8%% → −3\n\n8. Urgency (severe short-term distress)\n   • 1W return < −10%% → −4 | RSI > 85 → −4\n\nPosition direction inversion:\n  • Long positions: bullish signals (+) are favorable, bearish (−) are unfavorable\n  • Short positions: polarity inverted; bullish signals are unfavorable, bearish signals are favorable\n\nScore thresholds (after direction adjustment):\n  • score ≥ +4  → Monitor  (green)   — favorable outlook\n  • −2 < score < +4 → Neutral   (transparent) — hold\n  • −5 < score ≤ −2 → Attention (orange) — moderate risk\n  • score ≤ −5  → Caution   (red)    — high risk"
            }
        },
           'insights': {
                 'columns': ['Direction', 'Avg Entry', 'Ticker', 'Name', 'Est. OS Z-Score', 'Current Z-Score', 'Est. OB Z-Score', 'Est. dip', 'Est. Peak', 'ER (1Y)', 'PnL (%)', 'Action Alert'],
                'widths': [60, 60, 60, 200, 80, 80, 80, 70, 70, 60, 70, 70],
                'tooltips': {
                    'Direction': "Position Direction:\nL = Long (positive weight), S = Short (negative weight/position).",
                    'Avg Entry': "Average Entry Price:\nThe average price at which the position was acquired.",
                    'Ticker': "Ticker Symbol",
                    'Name': "Asset Name:\nThe full name of the security.",
                    'Est. OS Z-Score': "Estimated Oversold Z-Score (5Y):\nMost negative rolling 1-year Z-score (in log-return space) observed over the past 5 years. Indicates the deepest historical oversold condition.",
                    'Current Z-Score': "Current Z-Score:\nCurrent log-return deviation from 1-year historical mean, measured in standard deviations. Z = (r_t - μ_r) / σ_r where r_t is the latest log return.",
                    'Est. OB Z-Score': "Estimated Overbought Z-Score (5Y):\nMost positive rolling 1-year Z-score (in log-return space) observed over the past 5 years. Indicates the deepest historical overbought condition.",
                    'Est. dip': "Est. dip:\nEstimated price target under oversold conditions using a return-based Z-score model: P_os = P0 * exp((Z_os - Z0) * σ_adj). Z_os is the 5Y minimum Z-score; σ_adj = σ_r * (1 + k|Z0|) adjusts volatility for regime stress. Represents the theoretical price when the stock reaches its deepest historical oversold level.",
                    'Est. Peak': "Est. Peak:\nEstimated price target under overbought conditions using a return-based Z-score model: P_ob = P0 * exp((Z_ob - Z0) * σ_adj). Z_ob is the 5Y maximum Z-score; σ_adj = σ_r * (1 + k|Z0|) adjusts volatility for regime stress. Represents the theoretical price when the stock reaches its deepest historical overbought level.",
                    'ER (1Y)': "Expected Return (1Y):\nEstimated 1-year return based on price action model combining 12-month trend, 3-month momentum, 200-day mean reversion, and ARIMA forecast. Positive = bullish outlook, Negative = bearish outlook.",
                    'PnL (%)': "Profit and Loss:\nThe unrealized gain or loss of the position.",
                    'Action Alert': "Action Alert:\nRecommended action based on a multi-factor scoring system that aggregates 8 indicators. For short positions, the signal polarity is inverted (bullish signals are negative, bearish signals are positive).\n\nScoring factors:\n\n1. Valuation (vs industry): PE, EPS growth, EV/EBITDA\n   • Undervalued (−15%% to −5%%) → +1/+2 | Overvalued (+10%% to +25%%) → −1/−2\n\n2. Momentum (long-term trend): SMA200 spread\n   • Bull (spread > 2%%) → +2 | Bear (spread < −2%%) → −2\n\n3. Reversal (short-term exhaustion): RSI 14\n   • Oversold RSI < 35 → +1 | Overbought RSI > 75 → −2\n\n4. Velocity (trend acceleration): (ret_1w − ret_1m/4.2) × 100\n   • Accel > +8 pts → +1 | Decel < −8 pts → −1\n\n5. Consistency (multi-month performance)\n   • All 1W/1M/3M positive → +1 | 1W < −7%% → −1\n\n6. 1M Momentum (standalone monthly return)\n   • r1m > +5%% → +2 | +1%% < r1m ≤ +5%% → +1\n   • −5%% ≤ r1m < −1%% → −1 | r1m < −5%% → −2\n\n7. Bias (expected upside vs downside asymmetry)\n   • bias > +8%% → +3 | bias > +4%% → +2 | bias > +1%% → +1\n   • bias < −1%% → −1 | bias < −4%% → −2 | bias < −8%% → −3\n\n8. Urgency (severe short-term distress)\n   • 1W return < −10%% → −4 | RSI > 85 → −4\n\nPosition direction inversion:\n  • Long positions: bullish signals (+) are favorable, bearish (−) are unfavorable\n  • Short positions: polarity inverted; bullish signals are unfavorable, bearish signals are favorable\n\nScore thresholds (after direction adjustment):\n  • score ≥ +4  → Monitor  (green)   — favorable outlook\n  • −2 < score < +4 → Neutral   (transparent) — hold\n  • −5 < score ≤ −2 → Attention (orange) — moderate risk\n  • score ≤ −5  → Caution   (red)    — high risk"
                }
            }
    }

    # Helper function to generate a specific view table
    def render_view_table(view_name, config):
        cols = config['columns']
        widths = config['widths']
        tooltips = config['tooltips']
        
        html = f"""
        <div id="holdings-view-{view_name}" class="holdings-view{' hidden' if view_name != 'components' else ''}">
            <table class="holdings-table" id="holdings-table-{view_name}">
                <colgroup>
                    {"".join([f'<col style="width: {w}px;">' for w in widths])}
                </colgroup>
                <thead>
                    <tr>
                        {"".join([f'<th class="{"desc" if c == "Weight (%)" else ""}" data-tooltip="{tooltips.get(c, c)}" onclick="sortHoldingsTable(\'{view_name}\', this)">{c} <span class="sort-icon"></span></th>' for c in cols])}
                    </tr>
                </thead>
                <tbody>
        """
        
        for ticker, row in holdings.iterrows():
            # Common calculations
            mc = row['marketCap']
            if mc >= 1e12: mc_str = f"{mc/1e12:.2f}T"
            elif mc >= 1e9: mc_str = f"{mc/1e9:.2f}B"
            elif mc >= 1e6: mc_str = f"{mc/1e6:.2f}M"
            elif mc > 0: mc_str = f"{mc:,.0f}"
            else: mc_str = "-"
            
            sector = row['sector'] if row['sector'] != "Unknown" else "Others"
            ms = row['momentum_signal']
            bg_color = HOLDINGS_BULL_MOMENTUM_BG if ms == "BULL" else HOLDINGS_BEAR_MOMENTUM_BG if ms == "BEAR" else HOLDINGS_NEUTRAL_MOMENTUM_BG if ms == "NEUT" else "transparent"
            text_color = "white" if ms in ["BULL", "BEAR", "NEUT"] else "black"
            
            html += f'<tr onclick="showTickerChart(\'{ticker}\', this)" class="cursor-pointer">'
            
            for col in cols:
                if col == 'Analysis':
                    analysis_url = ANALYSIS_PAGE_URL.replace('[ticker]', ticker)
                    html += f'''<td class="u-align-center u-valign-middle">
                        <a href="{analysis_url}" target="_blank" rel="noopener noreferrer"
                           style="display:inline-flex; align-items:center; justify-content:center; background-color: {BG_BUTTON_PRIMARY}; color: {BUTTON_TEXT}; padding: 4px; border-radius: 4px; text-decoration: none; font-size: 0.85em; white-space: nowrap;"
                           title="Open analysis for {ticker}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                                <polyline points="15 3 21 3 21 9"></polyline>
                                <line x1="10" y1="14" x2="21" y2="3"></line>
                            </svg>
                        </a>
                    </td>'''
                elif col == 'Direction':
                    direction = row.get('type', '')
                    if direction == 'L':
                        badge_class, display = 'badge-long', 'L'
                    elif direction == 'S':
                        badge_class, display = 'badge-short', 'S'
                    else:
                        is_long = row.get('quantity', 0) >= 0
                        badge_class = 'badge-long' if is_long else 'badge-short'
                        display = 'L' if is_long else 'S'
                    html += f"""
                    <td class="u-align-center u-valign-middle">
                        <div class="badge {badge_class}">{display}</div>
                    </td>"""
                elif col == 'Avg Entry':
                    avg_val = row.get('avg_price', row.get('average_cost', 0))
                    val_str = f"${avg_val:.2f}" if pd.notna(avg_val) else "-"
                    html += f'<td class="u-sm">{val_str}</td>'
                elif col == 'Latest Price':
                    latest_val = row.get('latest_price')
                    val_str = f"${latest_val:.2f}" if pd.notna(latest_val) else "-"
                    html += f'<td class="u-sm">{val_str}</td>'
                elif col == 'Ticker':
                    html += f'<td class="u-sm u-nowrap overflow-visible">{ticker}</td>'
                elif col == 'Name':
                    html += f'<td class="u-sm">{row["name"]}</td>'
                elif col == 'Weight (%)':
                    html += f'<td class="weight-cell">{row["Weight"]*100:.2f}%</td>'
                elif col == 'PnL (%)':
                    pnl_val = row['pnl_pct']
                    pnl_display = "0%" if pd.isna(pnl_val) else f"{pnl_val:+.2f}%"
                    pnl_class = 'pnl-positive' if pd.notna(pnl_val) and pnl_val > 0 else 'pnl-negative' if pd.notna(pnl_val) and pnl_val < 0 else 'pnl-neutral'
                    html += f'<td class="u-align-center u-valign-middle"><div class="metric-chip {pnl_class}">{pnl_display}</div></td>'
                elif col == 'Action Alert':
                    alert_map = {"Monitor": "watch", "Attention": "caution", "Caution": "critical", "Neutral": "neutral"}
                    alert_class = alert_map.get(row["alert"], "neutral")
                    alert_content = f'<div class="alert-chip {alert_class}">{row["alert"]}</div>' if row["alert"] != 'Neutral' else '<div class="alert-spacer"></div>'
                    html += f"""
                    <td class="u-align-center u-valign-middle">
                        <div class="alert-wrap">
                            {alert_content}
                            <div class="alert-meta">1W: {row['ret_1w']*100:+.1f}%<br/>1M: {row['ret_1m']*100:+.1f}%</div>
                        </div>
                    </td>"""
                elif col == 'Sector':
                    html += f'<td class="u-sm">{sector}</td>'
                elif col == 'Market Cap':
                    html += f'<td class="u-sm">{mc_str}</td>'
                elif col == 'Forward P/E':
                    if row['forward_pe'] > 0:
                        diff = (row["forward_pe"] / row["industry_avg_pe"] - 1) if row['industry_avg_pe'] > 0 else 0
                        diff_class = 'pe-diff-high' if diff > 0.05 else 'pe-diff-low' if diff < -0.05 else 'pe-diff-neutral'
                        symbol = "&#9650;" if diff > 0.05 else "&#9660;" if diff < -0.05 else "&#8226;"
                        
                        html += f"""
                        <td>
                            <div class="pe-value">{row["forward_pe"]:.2f}</div>
                            {f'<div class="pe-diff {diff_class}">{symbol} {abs(diff) * 100:.1f}% vs Ind.</div>' if row['industry_avg_pe'] > 0 else ""}
                        </td>"""
                    else:
                        html += '<td>-</td>'
                elif col == 'EPS Growth (%)':
                    eps_val = row.get('eps_growth', 0)
                    eps_pct = eps_val * 100 if pd.notna(eps_val) else 0
                    eps_class = 'eps-high' if eps_pct > 10 else 'eps-low' if eps_pct < 0 else ''
                    html += f'<td class="u-align-center u-valign-middle"><div class="eps-growth-chip {eps_class}">{eps_pct:+.1f}%</div></td>'
                elif col == 'EV/EBITDA':
                    ev_val = row.get('ev_ebitda', np.nan)
                    if pd.notna(ev_val) and ev_val > 0:
                        ev_class = 'val-low' if ev_val < 10 else 'val-high' if ev_val > 20 else ''
                        html += f'<td class="u-align-center u-valign-middle"><div class="val-chip {ev_class}">{ev_val:.2f}x</div></td>'
                    else:
                        html += '<td>-</td>'
                elif col == 'ROE (%)':
                    roe_val = row.get('roe', np.nan)
                    roe_pct = roe_val * 100 if pd.notna(roe_val) else np.nan
                    if pd.notna(roe_pct) and roe_pct != 0:
                        roe_class = 'val-low' if roe_pct > 15 else 'val-high' if roe_pct < 0 else ''
                        html += f'<td class="u-align-center u-valign-middle"><div class="val-chip {roe_class}">{roe_pct:.1f}%</div></td>'
                    else:
                        html += '<td>-</td>'
                elif col == 'Current Ratio':
                    cr_val = row.get('current_ratio', np.nan)
                    if pd.notna(cr_val) and cr_val != 0:
                        cr_class = 'val-low' if cr_val > 1.5 else 'val-high' if cr_val < 1.0 else ''
                        html += f'<td class="u-align-center u-valign-middle"><div class="val-chip {cr_class}">{cr_val:.2f}</div></td>'
                    else:
                        html += '<td>-</td>'
                elif col == 'Performance':
                    html += f"""
                    <td class="u-align-center u-valign-middle">
                        <div class="performance-strip">
                            {"".join([f'''
                            <div class="mini-bar-wrap" title="{period} Performance: {row['ret_'+period.lower()]*100:+.1f}%">
                                <div class="mini-bar-column">
                                    {f'<div class="spark-pos" style="height: {min(14, max(1, int(row["ret_"+period.lower()]*100)))}px;"></div>' if row['ret_'+period.lower()] > 0 else ""}
                                </div>
                                <div class="spark-axis"></div>
                                <div class="mini-bar-column">
                                    {f'<div class="spark-neg" style="height: {min(14, max(1, int(abs(row["ret_"+period.lower()])*100)))}px;"></div>' if row['ret_'+period.lower()] < 0 else ""}
                                </div>
                                <div class="spark-label">{period}</div>
                            </div>''' for period in ['3M', '1M', '1W']])}
                         </div>
                      </td>"""
                elif col == 'Div Yield (%)':
                    dy_val = row.get('dividendYield', np.nan)
                    if pd.notna(dy_val) and dy_val > 0:
                        dy_pct = dy_val * 100
                        dy_class = 'div-yield-high' if dy_pct > 5 else 'div-yield-moderate' if dy_pct > 2 else 'div-yield-low'
                        html += f'<td class="u-align-center u-valign-middle"><div class="val-chip {dy_class}">{dy_pct:.2f}%</div></td>'
                    else:
                        html += '<td class="u-sm">-</td>'
                elif col == 'Momentum Spread':
                    ms = row['momentum_signal']
                    ms_class = 'momentum-badge-bull' if ms == 'BULL' else 'momentum-badge-bear' if ms == 'BEAR' else 'momentum-badge-neut' if ms == 'NEUT' else 'momentum-badge-empty'
                    html += f'''
                    <td class="u-align-center u-valign-middle">
                        <div class="momentum-badge {ms_class}">
                            {ms}
                        </div>
                        <div class="momentum-value {'positive' if row['momentum_spread'] > 0 else 'negative' if row['momentum_spread'] < 0 else ''}">
                            {row['momentum_spread']*100:+.2f}%
                        </div>
                    </td>
                    '''
                elif col == 'Perf (3M, 1M, 1W)':
                    html += f"""
                    <td class="u-align-center u-valign-middle">
                        <div class="performance-strip">
                            {"".join([f'''
                            <div class="mini-bar-wrap" title="{period} Performance: {row['ret_'+period.lower()]*100:+.1f}%">
                                <div class="mini-bar-column">
                                    {f'<div class="spark-pos" style="height: {min(14, max(1, int(row["ret_"+period.lower()]*100)))}px;"></div>' if row['ret_'+period.lower()] > 0 else ""}
                                </div>
                                <div class="spark-axis"></div>
                                <div class="mini-bar-column">
                                    {f'<div class="spark-neg" style="height: {min(14, max(1, int(abs(row["ret_"+period.lower()])*100)))}px;"></div>' if row['ret_'+period.lower()] < 0 else ""}
                                </div>
                                <div class="spark-label">{period}</div>
                            </div>''' for period in ['3M', '1M', '1W']])}
                        </div>
                    </td>"""
                elif col == 'Est. OS Z-Score':
                    val = row.get('z_score_min_5y', np.nan)
                    if pd.notna(val):
                        color = ZSCORE_OVERSOLD if val < -1.5 else ZSCORE_OVERBOUGHT if val > 1.5 else ZSCORE_NEUTRAL
                        html += f'''
                        <td class="u-align-center u-valign-middle">
                            <div class="stdev-wrap">
                                <div class="stdev-value {'negative' if val < -1.5 else 'positive' if val > 1.5 else ''}" style="color: {color};">
                                    {val:+.2f}
                                </div>
                                <div class="stdev-label">STDEV</div>
                            </div>
                        </td>'''
                    else:
                        html += '<td>-</td>'
                elif col == 'Current Z-Score':
                    val = row.get('z_score', np.nan)
                    if pd.notna(val):
                        color = ZSCORE_OVERSOLD if val < -1.5 else ZSCORE_OVERBOUGHT if val > 1.5 else ZSCORE_NEUTRAL
                        html += f'''
                        <td class="u-align-center u-valign-middle">
                            <div class="stdev-wrap">
                                <div class="stdev-value {'negative' if val < -1.5 else 'positive' if val > 1.5 else ''}" style="color: {color};">
                                    {val:+.2f}
                                </div>
                                <div class="stdev-label">STDEV</div>
                            </div>
                        </td>'''
                    else:
                        html += '<td>-</td>'
                elif col == 'Est. OB Z-Score':
                    val = row.get('z_score_max_5y', np.nan)
                    if pd.notna(val):
                        color = ZSCORE_OVERSOLD if val < -1.5 else ZSCORE_OVERBOUGHT if val > 1.5 else ZSCORE_NEUTRAL
                        html += f'''
                        <td class="u-align-center u-valign-middle">
                            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 50px;">
                                <div style="font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.2em; color: {color};">
                                    {val:+.2f}
                                </div>
                                <div style="font-size: 0.8em; color: {HOLDINGS_STDEV_LABEL}; font-weight: bold;">
                                    STDEV
                                </div>
                            </div>
                        </td>'''
                    else:
                        html += '<td>-</td>'
                elif col == 'Est. dip':
                    val = row.get('est_dip', np.nan)
                    if pd.notna(val):
                        current_price_val = row.get('latest_price', np.nan)
                        exp_down = row.get('expected_downside', np.nan)
                        worst_down = row.get('worst_downside', np.nan)
                        threshold = row.get('oversold_threshold_used', np.nan)
                        if pd.notna(current_price_val):
                            pct_change = (val - current_price_val) / current_price_val * 100
                            arrow = "▲" if pct_change > 0 else "▼" if pct_change < 0 else "–"
                            color = UPSIDE_PRICE_TEXT if pct_change > 0 else DOWNSIDE_PRICE_TEXT if pct_change < 0 else NEUTRAL_PRICE_TEXT
                            pct_str = f"{arrow} {pct_change:+.1f}%"
                        else:
                            pct_str = ""
                            color = NO_PRICE_COLOR
                        tooltip_parts = []
                        if pd.notna(exp_down):
                            tooltip_parts.append(f"Est. return: {exp_down*100:+.1f}%")
                        if pd.notna(worst_down):
                            tooltip_parts.append(f"Stress return: {worst_down*100:+.1f}%")
                        if pd.notna(threshold):
                            tooltip_parts.append(f"Target Z: {threshold:.2f}")
                        tooltip = " | ".join(tooltip_parts) if tooltip_parts else ""
                        html += f'''
                        <td class="u-align-center u-valign-middle">
                            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 50px;">
                                <div style="font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.1em; color: {color}; line-height: 1.1;">
                                    ${val:.2f}
                                </div>
                                <div style="font-family: 'Courier New', monospace; font-size: 0.8em; font-weight: bold; color: {color};">
                                    {pct_str}
                                </div>
                            </div>
                        </td>'''
                    else:
                        html += '<td>-</td>'
                elif col == 'Est. Peak':
                    val = row.get('est_peak', np.nan)
                    if pd.notna(val):
                        current_price_val = row.get('latest_price', np.nan)
                        exp_up = row.get('expected_upside', np.nan)
                        worst_up = row.get('worst_upside', np.nan)
                        threshold = row.get('overbought_threshold_used', np.nan)
                        if pd.notna(current_price_val):
                            pct_change = (val - current_price_val) / current_price_val * 100
                            arrow = "▲" if pct_change > 0 else "▼" if pct_change < 0 else "–"
                            color = UPSIDE_PRICE_TEXT if pct_change > 0 else DOWNSIDE_PRICE_TEXT if pct_change < 0 else NEUTRAL_PRICE_TEXT
                            pct_str = f"{arrow} {pct_change:+.1f}%"
                        else:
                            pct_str = ""
                            color = NO_PRICE_COLOR
                        tooltip_parts = []
                        if pd.notna(exp_up):
                            tooltip_parts.append(f"Est. return: {exp_up*100:+.1f}%")
                        if pd.notna(worst_up):
                            tooltip_parts.append(f"Stress return: {worst_up*100:+.1f}%")
                        if pd.notna(threshold):
                            tooltip_parts.append(f"Target Z: {threshold:.2f}")
                        tooltip = " | ".join(tooltip_parts) if tooltip_parts else ""
                        html += f'''
                        <td class="u-align-center u-valign-middle">
                            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 50px;">
                                <div style="font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.1em; color: {color}; line-height: 1.1;">
                                    ${val:.2f}
                                </div>
                                <div style="font-family: 'Courier New', monospace; font-size: 0.8em; font-weight: bold; color: {color};">
                                    {pct_str}
                                </div>
                            </div>
                        </td>'''
                    else:
                        html += '<td>-</td>'
                elif col == 'ER (1Y)':
                     val = row.get('expected_return', np.nan)
                     if pd.notna(val):
                         if val > 0.02:
                             bg_class = "bias-chip bullish"
                         elif val < -0.02:
                             bg_class = "bias-chip bearish"
                         else:
                             bg_class = "bias-chip neutral"
                         html += f'''
                         <td class="u-align-center u-valign-middle">
                             <div class="{bg_class}">
                                 {val*100:+.1f}%
                             </div>
                         </td>'''
                     else:
                         html += '<td>-</td>'
                elif col == 'Trend Velocity':
                    accel_score = row['accel_score']
                    bar_color = TREND_ACCEL_BAR if accel_score > 0 else TREND_DECEL_BAR if accel_score < 0 else TREND_NEUTRAL_BAR
                    text_color = TREND_ACCEL_TEXT if accel_score > 0 else TREND_DECEL_TEXT if accel_score < 0 else TREND_NEUTRAL_TEXT
                    abs_score = abs(accel_score)
                    if abs_score > 10:
                        full_bars = 5
                    elif abs_score > 7:
                        full_bars = 4
                    elif abs_score > 4:
                        full_bars = 3
                    elif abs_score > 1:
                        full_bars = 2
                    else:
                        full_bars = 1
                    bars_html = "".join([
                        f'<div style="width: 4px; height: 13px; border-radius: 1px; background-color: {bar_color}; opacity: {"1.0" if i < full_bars else "0.2"};"></div>'
                        for i in range(5)
                    ])
                    html += f"""
                    <td style="text-align: center; vertical-align: middle;" title="Trend Velocity (points): Measures trend acceleration by comparing the most recent 1-week return against the average weekly return over the last month (ret_1m / 4.2).&#10;&#10;Calculation: (ret_1w - ret_1m/4.2) × 100 = percentage points deviation&#10;&#10;Interpretation:&#10;  • Positive values → Trend is ACCELERATING (speeding up)&#10;  • Negative values → Trend is DECELERATING (slowing down)&#10;  • Near zero → Trend is FLAT&#10;&#10;Thresholds: &gt;+2 pts = ACCEL, &lt;-2 pts = DECEL&#10;&#10;Bar visualization: 5 bars where bar count (full opacity) reflects acceleration magnitude; green = positive, red = negative, gray = neutral">
                        <div style="display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <div style="display: flex; gap: 2px;">
                                {bars_html}
                            </div>
                            <div style="min-width: 30px; text-align: left;">
                                <span style="color: {text_color}; font-weight: bold; font-family: 'Courier New', monospace; font-size: 1.1em;">
                                    {('+' if accel_score > 0 else '-' if accel_score < 0 else '')}{abs(accel_score):.0f}<span style="font-size: 0.75em; font-weight: normal;">pts</span>
                                </span>
                            </div>
                        </div>
                    </td>"""
                elif col == 'RSI':
                    rsi_val = row['rsi']
                    if rsi_val < 30:
                        rsi_color = RSI_OVERSOLD_BG
                        status = 'Oversold'
                    elif rsi_val > 70:
                        rsi_color = RSI_OVERBOUGHT_BG
                        status = 'Overbought'
                    else:
                        rsi_color = HOLDINGS_NEUTRAL_MOMENTUM_BG
                        status = 'Neutral'
                    # Fill width represents the RSI value (0-100 scale)
                    fill_pct = min(max(rsi_val, 0), 100)
                    html += f'''
                    <td class="u-align-center u-valign-middle">
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 2px;">
                            <div style="font-size: 0.75em; color: {TEXT_PRIMARY}; font-weight: bold;">{status}</div>
                            <div style="width: 60px; height: 8px; background-color: {NEUTRAL_SURFACE}; border-radius: 4px; position: relative; overflow: hidden;">
                                <div style="position: absolute; left: 0; top: 0; height: 100%; width: {fill_pct}%; background-color: {rsi_color};"></div>
                            </div>
                            <div style="font-family: 'Courier New', monospace; font-size: 1.0em; font-weight: bold; color: {rsi_color};">{rsi_val:.1f}</div>
                        </div>
                    </td>'''
                elif col == 'Distance to 52W High':
                    dist = row['dist_to_52w_high']
                    if dist < -5:
                        dist_color = ZSCORE_OVERBOUGHT
                        status = 'Above High'
                    elif dist > 5:
                        dist_color = ZSCORE_OVERSOLD
                        status = 'Below High'
                    else:
                        dist_color = ZSCORE_NEUTRAL
                        status = 'Near High'
                    fill_pct = min(max((dist + 50) / 100 * 100, 0), 100)
                    html += f'''
                    <td class="u-align-center u-valign-middle">
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 3px;">
                            <div style="font-size: 0.75em; color: {TEXT_PRIMARY}; font-weight: bold;">{status}</div>
                            <div style="width: 70px; height: 6px; background-color: {NEUTRAL_SURFACE}; border-radius: 3px; overflow: hidden; position: relative;">
                                <div style="position: absolute; left: 0; top: 0; height: 100%; width: {fill_pct}%; background-color: {dist_color}; transition: none;"></div>
                            </div>
                            <div style="font-family: 'Courier New', monospace; font-size: 1.0em; font-weight: bold; color: {dist_color};">{dist:+.1f}%</div>
                        </div>
                    </td>'''
                elif col == 'Momentum Signal':
                    html += f"""
                    <td class="u-align-center u-valign-middle">
                        <div style="background-color: {bg_color}; color: {text_color}; padding: 3px 7px; border-radius: 2px; font-weight: bold; font-family: 'Courier New', monospace; font-size: 0.95em; display: inline-block; min-width: 45px;">
                            {ms}
                        </div>
                    </td>"""
                else:
                    html += '<td>-</td>'
            
            html += '</tr>'
            
        html += "</tbody></table></div>"
        return html

    # Generate HTML Table
    
    table_html = f"""
    <div class="holdings-table-container">

    <button onclick="exportVisibleHoldingsTable(this)" style="position: absolute; top: 20px; right: 20px; background-color: {HOLDINGS_EXPORT_BG}; color: {BUTTON_TEXT}; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-weight: bold; display: flex; align-items: center; gap: 8px; z-index: 10; font-size: 0.85em;">
        <span style="font-size: 1.1em;">&#128196;</span> Export Excel
    </button>
    <div class="header-tooltip" style="position: fixed; background: {HOLDINGS_TOOLTIP_BG}; color: {BUTTON_TEXT}; padding: 8px 12px; border-radius: 4px; font-size: 0.8em; white-space: pre-wrap; z-index: 10000; display: none; max-width: 300px; box-shadow: 0 2px 4px {HOLDINGS_TOOLTIP_BOX_SHADOW};"></div>
    <div style="overflow-x: auto; overflow-y: scroll; max-height: calc(100vh - 100px); font-size: 0.9em; max-width: 100%;">
        <style>
        .holdings-table {{
            font-size: 0.9em;
            min-width: 100%;
            table-layout: fixed;
            width: 100%;
        }}
        .holdings-table thead th {{
            position: sticky;
            top: 0;
            z-index: 1;
            background-color: {HOLDINGS_HEADER_BG};
            color: {HOLDINGS_HEADER_TEXT};
            font-size: 0.8em;
            padding: 5px 8px;
            border: 1px solid {HOLDINGS_CELL_BORDER};
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: pointer;
        }}
        .holdings-table thead th:hover {{
            background-color: {HOLDINGS_HEADER_HOVER};
        }}
        .holdings-table tbody td {{
            padding: 10px 8px;
            border: 1px solid {HOLDINGS_CELL_BORDER};
            vertical-align: middle;
            line-height: 1.2;
        }}
        .holdings-table tbody tr:nth-child(even) {{
            background-color: {HOLDINGS_ROW_ALT};
        }}
        .holdings-table tbody tr:hover {{
            background-color: {HOLDINGS_ROW_HOVER};
        }}
        .compact-num {{
            font-family: 'Courier New', monospace;
            font-size: 1.0em;
            white-space: nowrap;
        }}
        .sort-arrow {{
            margin-left: 5px;
            font-size: 0.8em;
            color: {HOLDINGS_SORT_ARROW};
            font-weight: bold;
        }}
        .holdings-table th .sort-icon::after {{
            content: '';
            opacity: 0;
        }}
        .holdings-table th.asc .sort-icon::after {{
            content: '▲';
            opacity: 1;
            color: {HOLDINGS_SORT_ARROW_TEXT};
            font-weight: bold;
            font-size: 0.8em;
            margin-left: 5px;
        }}
        .holdings-table th.desc .sort-icon::after {{
            content: '▼';
            opacity: 1;
            color: {HOLDINGS_SORT_ARROW_TEXT};
            font-weight: bold;
            font-size: 0.8em;
            margin-left: 5px;
        }}
    </style>
    """
    
    # Generate all four tables
    holdings = holdings.sort_values('Weight', ascending=False)
    for view_name, config in VIEW_CONFIGS.items():
        table_html += render_view_table(view_name, config)
        
    table_html += "</div></div>"
    return table_html, holdings, chart_data_json


def render_holdings_tab(risk_contrib, sector_industry_df, price_data, portfolio_df, metrics=None, charts=None) -> str:
    """
    Renders the Holdings tab HTML block.
    """
    html_table, holdings_df, chart_data_json = generate_portfolio_holdings_analysis(risk_contrib, sector_industry_df, price_data, portfolio_df)
    
    # Prepare charts dictionary for the template
    if charts is None:
        charts = {}
    charts['holdings_table'] = html_table
    charts['chart_data'] = chart_data_json

    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        template_src = f.read()

    template = Template(template_src)
    return template.render(
        charts=charts,
    )

