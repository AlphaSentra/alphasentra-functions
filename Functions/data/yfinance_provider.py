import pandas as pd
import yfinance as yf

from .protocols import MarketDataProvider
from .models import AssetMetadata


def _normalize_ticker(ticker: str) -> str:
    return ticker.replace(".ASX", ".AX") if isinstance(ticker, str) and ticker.endswith(".ASX") else ticker


def _normalize_tickers(tickers):
    return [_normalize_ticker(t) for t in tickers]


def _normalize_dividend_yield(div_yield) -> float:
    if div_yield is None:
        return 0.0
    if div_yield > 0.0:
        return div_yield / 100.0
    return float(div_yield)


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
        normalized = _normalize_tickers(tickers)
        data = yf.download(
            normalized,
            start=start_date,
            end=end_date,
            auto_adjust=False,
            progress=False,
        )
        if data.empty:
            raise ValueError("No data downloaded for the specified tickers and date range.")
        return data

    def get_sector_industry_data(self, tickers) -> pd.DataFrame:
        normalized = _normalize_tickers(tickers)
        records = []
        for ticker in normalized:
            try:
                info = yf.Ticker(ticker).info
                meta = AssetMetadata(
                    ticker=ticker,
                    name=info.get("longName", ticker),
                    sector=info.get("sector", "Others"),
                    industry=info.get("industry", "Others"),
                    dividend_yield=_normalize_dividend_yield(info.get("dividendYield")),
                    market_cap=info.get("marketCap", 0.0),
                    eps=info.get("trailingEps", 0.0),
                    ev_ebitda=info.get("enterpriseToEbitda", 0.0),
                    eps_growth=info.get("earningsGrowth", 0.0),
                    forward_pe=info.get("forwardPE", 0.0),
                    roe=info.get("returnOnEquity", info.get("roe", 0.0)),
                    current_ratio=info.get("currentRatio", 0.0),
                )
                records.append(meta)
            except Exception as e:
                print(f"Warning: Could not fetch info for {ticker}: {e}")
                records.append(AssetMetadata.default(ticker))

        df = pd.DataFrame([_to_camel_case(r) for r in records])
        return df.set_index("ticker")
