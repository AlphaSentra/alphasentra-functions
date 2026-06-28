import os
from .yfinance_provider import YFinanceProvider
from .protocols import MarketDataProvider


def get_market_data_provider() -> MarketDataProvider:
    provider_name = os.getenv("MARKET_DATA_PROVIDER", "yfinance").lower()
    if provider_name == "yfinance":
        return YFinanceProvider()
    raise ValueError(f"Unsupported market data provider: {provider_name}")
