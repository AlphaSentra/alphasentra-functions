# Data Provider Architecture

Market data is abstracted behind a provider interface to support pluggable data sources. The default provider is **Yahoo Finance**, selected via the `DATA_PROVIDER` config key or the `MARKET_DATA_PROVIDER` environment variable.

## Components

| File | Purpose |
|------|---------|
| `protocols.py` | Abstract base class `MarketDataProvider` defining the provider interface |
| `models.py` | `AssetMetadata` dataclass for sector/industry/fundamental data |
| `yfinance_provider.py` | Default `YFinanceProvider` implementation using `yfinance` |
| `provider_factory.py` | Factory function `get_market_data_provider()` returning the configured provider |
| `market.py` | Facade module preserving existing function signatures while delegating to the provider |
| `loader.py` | Additional data loading utilities |

## Provider Interface

`protocols.py` defines the contract:

```python
class MarketDataProvider(ABC):
    @abstractmethod
    def download_price_data(self, tickers, start_date, end_date) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_sector_industry_data(self, tickers) -> pd.DataFrame:
        pass
```

## Factory Selection

`provider_factory.py` selects the provider at runtime:

```python
def get_market_data_provider() -> MarketDataProvider:
    provider_name = os.getenv("MARKET_DATA_PROVIDER", "yfinance").lower()
    if provider_name == "yfinance":
        return YFinanceProvider()
    raise ValueError(f"Unsupported market data provider: {provider_name}")
```

The `DATA_PROVIDER` constant in `config.py` documents the default but the actual runtime selection uses the `MARKET_DATA_PROVIDER` environment variable.

## Default Provider: Yahoo Finance

`YFinanceProvider` implements both interface methods:

- **`download_price_data`** — Calls `yf.download()` with `auto_adjust=False`. Results are cached via `Functions/port/cache.py` with `_PRICE_TTL` (6 hours). Handles `.ASX` → `.AX` ticker normalization.
- **`get_sector_industry_data`** — Fetches `yf.Ticker(ticker).info` concurrently with up to 10 workers. Retries failed tickers up to 3 times. Returns an `AssetMetadata` DataFrame cached with `_SECTOR_TTL` (12 hours).

## Facade Layer

`market.py` wraps the provider with utility functions such as `detect_relisted_stocks()`, providing a backward-compatible interface for the rest of the portfolio engine.

## Usage

```python
from data.provider_factory import get_market_data_provider

provider = get_market_data_provider()
prices = provider.download_price_data(tickers, start_date, end_date)
sector_data = provider.get_sector_industry_data(tickers)
```

To add a new provider, implement `MarketDataProvider` and register it in `provider_factory.py`.
