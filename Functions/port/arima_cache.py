"""
In-memory cache for ARIMA 1-step forecasts.

Used by holdings/renderer.py, efficiency/charts.py, and intel/commentary.py
so the same ticker series is not fit repeatedly within a single report run.
"""

from typing import Optional
import hashlib

import pandas as pd


_cache: dict[str, float] = {}


def _series_key(series: pd.Series) -> str:
    values = series.dropna()
    if values.empty:
        return ""
    # Include the ticker/name, length, and a stable hash of the values so identical
    # price series map to the same cached forecast.
    name = str(values.name or "")
    length = len(values)
    # pd.util.hash_pandas_object(values).sum() is deterministic but can be slow
    # for very long series, so we hash the raw bytes directly.
    try:
        digest = hashlib.md5(values.values.tobytes()).hexdigest()
    except Exception:
        digest = hashlib.md5(str(values.values).encode("utf-8")).hexdigest()
    return f"{name}:{length}:{digest}"


def get(series: pd.Series) -> Optional[float]:
    key = _series_key(series)
    if not key:
        return None
    return _cache.get(key)


def set(series: pd.Series, value: float) -> None:
    key = _series_key(series)
    if key:
        _cache[key] = value


def clear() -> None:
    _cache.clear()
