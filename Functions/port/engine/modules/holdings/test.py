"""Quick test: fetch ABBN.SW fundamentals from yfinance."""

import sys
from pathlib import Path

venv_site_packages = Path(__file__).resolve().parent / "venv" / "lib" / "python3.14" / "site-packages"
if venv_site_packages.exists():
    sys.path.insert(0, str(venv_site_packages))

import yfinance as yf


def fetch_fundamentals(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = t.info

    def _safe_float(key):
        val = info.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return {
        "ticker": ticker,
        "name": info.get("longName"),
        "sector": info.get("sector"),
        "EV/EBITDA": _safe_float("enterpriseToEbitda"),
        "ROE": _safe_float("returnOnEquity") or _safe_float("roe"),
        "Current Ratio": _safe_float("currentRatio"),
        "Forward PE": _safe_float("forwardPE"),
    }


if __name__ == "__main__":
    result = fetch_fundamentals("wise.l")
    for k, v in result.items():
        print(f"  {k}: {v}")
