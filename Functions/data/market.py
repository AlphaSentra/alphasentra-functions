"""
Market data utilities: downloading prices, detecting anomalies, and fetching sector/industry info.

This module provides backward-compatible access to market data through the provider
abstraction layer. To swap the data source, set MARKET_DATA_PROVIDER environment variable
(e.g. "yfinance", "alphavantage", "polygon") or pass a MarketDataProvider instance
directly to PortfolioAnalyzer.
"""

import pandas as pd
import numpy as np
from .provider_factory import get_market_data_provider


def _get_provider():
    return get_market_data_provider()


def detect_relisted_stocks(prices, drop_threshold=0.5, constant_days_threshold=20):
    relisted_tickers = []

    for ticker in prices.columns:
        if ticker.startswith('^'):
            continue

        try:
            ticker_prices = prices[ticker].dropna()
            if len(ticker_prices) < constant_days_threshold + 5:
                continue

            values = ticker_prices.values
            dates = ticker_prices.index

            for i in range(constant_days_threshold, len(values) - 1):
                prev_prices = values[i - constant_days_threshold:i]
                if len(prev_prices) > 0 and prev_prices.std() / prev_prices.mean() < 0.001:
                    current_price = values[i]
                    next_price = values[i + 1]

                    if current_price > 0 and next_price > 0:
                        drop_pct = (current_price - next_price) / current_price

                        if drop_pct >= drop_threshold:
                            relisted_tickers.append(ticker)
                            print(f"Warning: Detected potential re-listing for {ticker}. "
                                  f"Price dropped {drop_pct*100:.1f}% on {dates[i+1].strftime('%Y-%m-%d')} "
                                  f"({current_price:.4f} -> {next_price:.4f}). Excluding from analysis.")
                            break

                        jump_pct = (next_price - current_price) / current_price
                        if jump_pct >= 0.95:
                            relisted_tickers.append(ticker)
                            print(f"Warning: Detected potential re-listing for {ticker}. "
                                  f"Price jumped {jump_pct*100:.1f}% on {dates[i+1].strftime('%Y-%m-%d')} "
                                  f"({current_price:.4f} -> {next_price:.4f}). Excluding from analysis.")
                            break
        except Exception as e:
            continue

    return relisted_tickers
