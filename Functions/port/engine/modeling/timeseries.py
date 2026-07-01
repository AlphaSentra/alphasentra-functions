"""
Portfolio time series construction and return calculation.
"""

import pandas as pd
import numpy as np
from config import DEFAULT_CAPITAL


def build_portfolio_timeseries(price_data, portfolio_df=None, transactions_df=None, total_investment=None, rebalance=False, force_percentage=None, percentage_format=None, start_date=None):
    """
    Constructs time series for portfolio position values. It can either process
    static portfolio holdings or dynamic transaction data.

    Args:
        price_data (pd.DataFrame): DataFrame of historical closing prices for all tickers,
                                   with dates as index and tickers as columns.
        portfolio_df (pd.DataFrame, optional): DataFrame containing static portfolio holdings
                                               with 'ticker' and 'quantity' columns.
                                               Required if transactions_df is None.
        transactions_df (pd.DataFrame, optional): DataFrame containing transaction data with
                                                  'Date', 'Ticker', 'Side', 'Quantity', 'Price', 'Fees', 'Currency'.
                                                  Required if portfolio_df is None.
        total_investment (float, optional): Total capital to invest if quantities are given as percentages.
                                            Used in static portfolio mode.
        rebalance (bool): Whether to rebalance the portfolio to maintain target weights daily.
                          Only applies to static portfolio percentage allocations.
        force_percentage (bool, optional): If True, treat quantities as percentages. If False, treat as shares.
                                           If None, auto-detect. Only applies to static portfolio mode.
        percentage_format (str, optional): 'decimal' (0.05=5%) or 'whole' (5=5%). Only used if force_percentage is True.
                                           Only applies to static portfolio mode.
        start_date (datetime, optional): The effective start date for portfolio calculation in transaction mode.

    Returns:
        dict: A dictionary containing pandas Series for:
              - 'total': Total portfolio value over time.
              - 'positions': DataFrame of individual position values over time.
              - 'holdings': DataFrame of share quantities over time (transaction mode only).
    """
    pos_values = pd.DataFrame(index=price_data.index)
    total_ts = pd.Series(0.0, index=price_data.index)

    # Detect stocks that first become available after a gap (new IPOs or re-listed stocks)
    newly_available_tickers = []
    for ticker in price_data.columns:
        if ticker.startswith('^'):
            continue
        ticker_prices = price_data[ticker]
        first_valid_idx = ticker_prices.first_valid_index()
        if first_valid_idx is not None:
            first_valid_pos = price_data.index.get_loc(first_valid_idx)
            if first_valid_pos > 30:
                newly_available_tickers.append(ticker)

    existing_tickers = [t for t in price_data.columns if t not in newly_available_tickers]
    if existing_tickers:
        price_data[existing_tickers] = price_data[existing_tickers].ffill()

    for ticker in newly_available_tickers:
        ticker_prices = price_data[ticker]
        first_valid_idx = ticker_prices.first_valid_index()
        if first_valid_idx is not None:
            price_data.loc[:first_valid_idx, ticker] = np.nan
            price_data[ticker] = price_data[ticker].ffill()

    if newly_available_tickers:
        print(f"Note: {len(newly_available_tickers)} stocks first appeared mid-way in price data. "
              f"Handling them to avoid artificial performance spikes.")

    if transactions_df is not None and not transactions_df.empty:
        # Transaction-based portfolio simulation
        transactions_df = transactions_df.dropna(subset=["Date", "Ticker", "Side", "Quantity", "Price"])
        print("Building portfolio time series from transactions...")
        transactions_df["Ticker"] = transactions_df["Ticker"].astype(str)
        cash_balance = total_investment if total_investment is not None else DEFAULT_CAPITAL

        transactions_df = transactions_df.sort_values(by="Date")

        current_holdings = {ticker: 0.0 for ticker in price_data.columns}
        holdings_over_time = pd.DataFrame(0.0, index=price_data.index, columns=price_data.columns)
        cash_over_time = pd.Series(cash_balance, index=price_data.index)

        daily_returns = pd.Series(0.0, index=price_data.index)
        prev_total_eod = cash_balance
        last_processed_idx = 0

        for i, current_date in enumerate(price_data.index):
            if start_date is not None and current_date < start_date:
                continue

            pre_trans_pos_value = 0.0
            for ticker, qty in current_holdings.items():
                if qty > 0 and ticker in price_data.columns:
                    price = price_data.loc[current_date, ticker]
                    if not pd.isna(price):
                        pre_trans_pos_value += qty * price

            pre_trans_total_value = pre_trans_pos_value + cash_balance

            if i > 0 and prev_total_eod > 0:
                daily_returns.loc[current_date] = (pre_trans_total_value / prev_total_eod) - 1

            for j in range(last_processed_idx, len(transactions_df)):
                transaction = transactions_df.iloc[j]
                transaction_date = transaction["Date"]
                ticker = transaction["Ticker"]
                side = transaction["Side"]
                quantity = transaction["Quantity"]
                price = transaction["Price"]
                fees = transaction["Fees"] if not pd.isna(transaction["Fees"]) else 0.0

                if transaction_date <= current_date:
                    if ticker in current_holdings:
                        cost = (quantity * price) + fees
                        if side == "BUY":
                            current_holdings[ticker] += quantity
                            cash_balance -= cost
                        elif side == "SELL":
                            current_holdings[ticker] -= quantity
                            cash_balance += (quantity * price) - fees
                        current_holdings[ticker] = max(0, current_holdings[ticker])
                    else:
                        if ticker not in price_data.columns:
                            print(f"Warning: Ticker {ticker} from transactions not found in price data. Skipping transaction.")
                            continue
                        cost = (quantity * price) + fees
                        if side == "BUY":
                             current_holdings[ticker] = quantity
                             cash_balance -= cost
                        elif side == "SELL":
                             current_holdings[ticker] = 0.0
                    last_processed_idx = j + 1
                else:
                    break

            for ticker, qty in current_holdings.items():
                if ticker in holdings_over_time.columns:
                    holdings_over_time.loc[current_date, ticker] = qty

            cash_over_time.loc[current_date] = cash_balance

            post_trans_pos_value = 0.0
            for ticker, qty in current_holdings.items():
                if qty > 0 and ticker in price_data.columns:
                    price = price_data.loc[current_date, ticker]
                    if not pd.isna(price):
                        post_trans_pos_value += qty * price

            prev_total_eod = post_trans_pos_value + cash_balance

        perf_adjusted_total = pd.Series(0.0, index=price_data.index)
        if start_date is not None:
            start_idx_pos = price_data.index.get_loc(price_data.index[price_data.index >= start_date][0])
        else:
            start_idx_pos = 0
        initial_val = total_investment if total_investment is not None else DEFAULT_CAPITAL
        perf_adjusted_total.iloc[start_idx_pos] = initial_val

        for i in range(start_idx_pos + 1, len(daily_returns)):
            perf_adjusted_total.iloc[i] = perf_adjusted_total.iloc[i-1] * (1 + daily_returns.iloc[i])

        pos_values = holdings_over_time.multiply(price_data).fillna(0)
        total_ts = perf_adjusted_total

        last_trans_date = transactions_df["Date"].max()
        last_pos_date = pos_values[pos_values.sum(axis=1) > 0].index.max()
        end_idx = max(last_trans_date, last_pos_date) if not pd.isna(last_pos_date) else last_trans_date

        pos_values = pos_values.loc[:end_idx]
        total_ts = total_ts.loc[:end_idx]
        cash_over_time = cash_over_time.loc[:end_idx]

    else:
        if portfolio_df is None or portfolio_df.empty:
            raise ValueError("Either portfolio_df or transactions_df must be provided and not empty.")

        total_qty = portfolio_df["quantity"].sum()
        max_qty = portfolio_df["quantity"].max()

        is_percentage = False
        scale_factor = 1.0

        if force_percentage is True:
            is_percentage = True
            if percentage_format == 'decimal':
                scale_factor = 1.0
                print("Forcing quantity as decimal percentage (e.g. 0.05 = 5%).")
            elif percentage_format == 'whole':
                scale_factor = 100.0
                print("Forcing quantity as whole-number percentage (e.g. 5 = 5%).")
            else:
                if max_qty <= 1.05:
                    scale_factor = 1.0
                    print("Forcing quantity as decimal percentage (scale 1.0).")
                else:
                    scale_factor = 100.0
                    print("Forcing quantity as whole-number percentage (e.g. 5 = 5%).")
        elif force_percentage is False:
            is_percentage = False
            print("Forcing quantity as actual share counts.")
        else:
            if max_qty <= 1.0:
                is_percentage = True
                scale_factor = 1.0
                print(f"Auto-detected quantity as decimal percentage (Max Qty: {max_qty:.4f}).")
            elif 2 <= total_qty <= 1000:
                is_percentage = True
                scale_factor = 100.0
                print(f"Auto-detected quantity as whole-number percentage (Total Qty: {total_qty:.2f}).")
            elif 0.5 <= total_qty <= 2.0:
                is_percentage = True
                scale_factor = 1.0
                print(f"Auto-detected quantity as decimal percentage (Total Qty: {total_qty:.4f}).")
            elif any(portfolio_df["quantity"].between(0.0001, 0.2)) and total_qty < 5.0:
                is_percentage = True
                scale_factor = 1.0
                print(f"Auto-detected quantity as decimal percentage based on small values (Sum: {total_qty:.4f}).")

        if is_percentage and total_investment is None:
            total_investment = DEFAULT_CAPITAL
            print(f"Quantities detected as percentages. Using default total investment of ${total_investment:,.2f}")
            if (total_qty/scale_factor) < 0.98:
                print(f"Warning: Total portfolio quantity ({total_qty/scale_factor*100:.1f}%) is less than 100%. Remaining will be treated as uninvested (Cash).")

        pos_values = pd.DataFrame(index=price_data.index)

        if is_percentage and rebalance:
            print("Rebalancing enabled. Maintaining target weights quarterly.")
            returns_df = price_data.pct_change().fillna(0)
            target_weights = {row["ticker"]: row["quantity"] / scale_factor for _, row in portfolio_df.iterrows()}
            total_target_sum = sum(target_weights.values())
            if total_target_sum > 2.0 and scale_factor == 1.0:
                 print(f"Warning: Target weights sum to {total_target_sum:.2f}, which is unusually high for decimal format. Re-scaling to whole-number percentage.")
                 scale_factor = 100.0
                 target_weights = {row["ticker"]: row["quantity"] / scale_factor for _, row in portfolio_df.iterrows()}
                 total_target_sum = sum(target_weights.values())

            total_ts = pd.Series(0.0, index=price_data.index)
            for ticker in target_weights:
                if ticker in price_data.columns:
                    pos_values[ticker] = 0.0

            current_total = total_investment
            current_weights = {}
            total_target_sum = sum(target_weights.values())
            last_rebalance_month = -1

            for i in range(len(price_data.index)):
                date = price_data.index[i]
                if i > 0:
                    daily_ret = 0
                    for t, w in current_weights.items():
                        asset_ret = returns_df.loc[date, t] if not pd.isna(returns_df.loc[date, t]) else 0
                        daily_ret += w * asset_ret
                    new_total = current_total * (1 + daily_ret)
                    if new_total > 0:
                        current_weights = {t: (w * current_total * (1 + (returns_df.loc[date, t] if not pd.isna(returns_df.loc[date, t]) else 0))) / new_total
                                          for t, w in current_weights.items()}
                    current_total = new_total
                total_ts.iloc[i] = current_total

                current_month = date.month
                is_quarter_start_month = current_month in [1, 4, 7, 10]
                should_rebalance = (i == 0) or (is_quarter_start_month and current_month != last_rebalance_month)
                if should_rebalance:
                    last_rebalance_month = current_month
                    available_tickers = [t for t in target_weights if t in price_data.columns and not pd.isna(price_data.loc[date, t])]
                    sum_available_target = sum(target_weights[t] for t in available_tickers)
                    if sum_available_target > 0:
                        scale_up = total_target_sum / sum_available_target
                        current_weights = {t: target_weights[t] * scale_up for t in available_tickers}
                    else:
                        current_weights = {}
                    for t in target_weights:
                        if t not in current_weights:
                            current_weights[t] = 0.0

                if i == len(price_data.index) - 1:
                    available_tickers = [t for t in target_weights if t in price_data.columns and not pd.isna(price_data.loc[date, t])]
                    if len(available_tickers) == len(target_weights):
                        current_weights = target_weights

                for t, w in current_weights.items():
                    pos_values.loc[date, t] = current_total * w

        else:
            for _, row in portfolio_df.iterrows():
                ticker = row["ticker"]
                qty = row["quantity"]
                if ticker in price_data.columns:
                    ticker_prices = price_data[ticker]
                    first_valid = ticker_prices.first_valid_index()
                    if first_valid is not None:
                        prices_from_inception = ticker_prices.loc[first_valid:].ffill()
                        full_ticker_prices = pd.Series(np.nan, index=price_data.index)
                        full_ticker_prices.update(prices_from_inception)
                        initial_price = full_ticker_prices.loc[first_valid]
                        full_ticker_prices[:first_valid] = initial_price
                        if is_percentage:
                            initial_price = full_ticker_prices.loc[first_valid]
                            calculated_qty = (qty / scale_factor) * total_investment / initial_price
                            pos_values[ticker] = full_ticker_prices * calculated_qty
                        else:
                            pos_values[ticker] = full_ticker_prices * qty

        pos_values = pos_values.fillna(0)
        if is_percentage and rebalance:
            total_ts = pos_values.sum(axis=1)
        else:
            total_ts = pos_values.sum(axis=1)

    return {
        "total": total_ts,
        "positions": pos_values,
        "holdings": holdings_over_time if transactions_df is not None else None
    }


def calculate_returns(timeseries_dict):
    """
    Calculates the daily percentage returns for each time series in the input dictionary.
    """
    returns = {}
    for k, ts in timeseries_dict.items():
        if isinstance(ts, pd.Series) or isinstance(ts, pd.DataFrame):
            returns[k] = ts.pct_change().dropna()
    return returns
