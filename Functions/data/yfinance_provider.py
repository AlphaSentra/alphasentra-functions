import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from .protocols import MarketDataProvider
from .models import AssetMetadata
from Functions.port.cache import get as cache_get, set as cache_set
from Functions.port.config import CACHE_TTL_PRICE as _PRICE_TTL, CACHE_TTL_SECTOR as _SECTOR_TTL


def _normalize_dividend_yield(div_yield) -> float:
    if div_yield is None:
        return 0.0
    if div_yield > 0.0:
        return div_yield / 100.0
    return float(div_yield)


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_camel_case(meta: AssetMetadata) -> dict:
    return {
        'ticker': meta.ticker,
        'name': meta.name,
        'sector': meta.sector,
        'industry': meta.industry,
        'dividendYield': meta.dividend_yield,
        'marketCap': meta.market_cap,
        'eps': meta.eps,
        'ev_ebitda': meta.ev_ebitda,
        'eps_growth': meta.eps_growth,
        'forward_pe': meta.forward_pe,
        'roe': meta.roe,
        'current_ratio': meta.current_ratio,
    }


class YFinanceProvider(MarketDataProvider):
    def download_price_data(self, tickers, start_date, end_date) -> pd.DataFrame:
        cache_key = (tuple(sorted(tickers)), str(start_date))
        cached = cache_get(cache_key, _PRICE_TTL, ext=".pkl")
        if cached is not None:
            return cached
        data = yf.download(
            tickers,
            start=start_date,
            end=end_date,
            auto_adjust=False,
            progress=False,
        )
        if data.empty:
            raise ValueError("No data downloaded for the specified tickers and date range.")
        cache_set(cache_key, data, ext=".pkl")
        return data

    def get_sector_industry_data(self, tickers) -> pd.DataFrame:
        cache_key = ("sector", tuple(sorted(tickers)))
        cached = cache_get(cache_key, _SECTOR_TTL, ext=".pkl")
        if cached is not None:
            return cached

        _MAX_WORKERS = min(10, len(tickers) or 1)
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_map = {
                executor.submit(self._fetch_info_with_retries, ticker): ticker
                for ticker in tickers
            }
            results = {}
            for future in as_completed(future_map):
                ticker = future_map[future]
                try:
                    results[ticker] = future.result()
                except Exception as exc:
                    logging.getLogger(__name__).warning("Failed to fetch info for %s: %s", ticker, exc)
                    results[ticker] = None

        records = []
        for ticker in tickers:
            info = results.get(ticker)
            if info is None:
                records.append(AssetMetadata.failed(ticker))
                continue
            keys_found = [k for k in ['longName','sector','industry','enterpriseToEbitda','returnOnEquity','currentRatio','forwardPE'] if info.get(k) is not None]
            meta = AssetMetadata(
                ticker=ticker,
                name=info.get("longName") or ticker,
                sector=info.get("sector") or "Others",
                industry=info.get("industry") or "Others",
                dividend_yield=_normalize_dividend_yield(info.get("dividendYield")),
                market_cap=_safe_float(info.get("marketCap")),
                eps=_safe_float(info.get("trailingEps")),
                ev_ebitda=_safe_float(info.get("enterpriseToEbitda")),
                eps_growth=_safe_float(info.get("earningsGrowth")),
                forward_pe=_safe_float(info.get("forwardPE")),
                roe=_safe_float(info.get("returnOnEquity")) or _safe_float(info.get("roe")),
                current_ratio=_safe_float(info.get("currentRatio")),
            )
            records.append(meta)

        df = pd.DataFrame([_to_camel_case(r) for r in records])
        result = df.set_index("ticker")
        cache_set(cache_key, result, ext=".pkl")
        return result

    @staticmethod
    def _fetch_info_with_retries(ticker: str, max_retries: int = 3, delay: float = 2.0):
        for attempt in range(1, max_retries + 1):
            try:
                info = yf.Ticker(ticker).info
                if info and isinstance(info, dict):
                    return info
            except Exception as exc:
                if attempt == max_retries:
                    print(f"Warning: Could not fetch info for {ticker} after {max_retries} attempts: {exc}")
                else:
                    time.sleep(delay * attempt)
        return None
