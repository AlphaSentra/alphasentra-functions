"""
Lightweight file-backed cache with TTL support for portfolio report generation.

Cache keys are hashed tuples. Value serialization:
- HTML strings  -> .html (raw text)
- DataFrames    -> .pkl (pickle)
- Simple objects -> .pkl (pickle)
"""

import hashlib
import logging
import pickle
import time
from pathlib import Path
from threading import Lock
from typing import Any, Optional

import pandas as pd

_logger = logging.getLogger(__name__)

_logger.info("Filesystem cache disabled; use Functions.db.cache for MongoDB-backed caching.")

_CACHE_DIR = Path("/tmp/disabled_portfolio_cache")

_lock = Lock()


def get(key: tuple, ttl: int, ext: str = ".pkl", filename: Optional[str] = None) -> Optional[Any]:
    return None


def exists(key: tuple, ttl: int, ext: str = ".pkl", filename: Optional[str] = None) -> bool:
    return False


def set(key: tuple, value: Any, ext: str = ".pkl", filename: Optional[str] = None) -> None:
    return None


def invalidate(key: tuple, filename: Optional[str] = None) -> None:
    return None


def clear() -> None:
    return None


_arima_cache: dict[str, float] = {}


def _series_key(series: pd.Series) -> str:
    values = series.dropna()
    if values.empty:
        return ""
    name = str(values.name or "")
    length = len(values)
    try:
        digest = hashlib.md5(values.values.tobytes()).hexdigest()
    except Exception:
        digest = hashlib.md5(str(values.values).encode("utf-8")).hexdigest()
    return f"{name}:{length}:{digest}"


def arima_get(series: pd.Series) -> Optional[float]:
    key = _series_key(series)
    if not key:
        return None
    return _arima_cache.get(key)


def arima_set(series: pd.Series, value: float) -> None:
    key = _series_key(series)
    if key:
        _arima_cache[key] = value


def arima_clear() -> None:
    _arima_cache.clear()

