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

_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
try:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception as exc:
    _logger.warning("Portfolio cache dir %s unusable (%s); falling back to /tmp/portfolio_cache", _CACHE_DIR, exc)
    _CACHE_DIR = Path("/tmp") / "portfolio_cache"
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _logger.warning("Fallback portfolio cache dir %s unusable (%s); using system tmp", _CACHE_DIR, exc)
        _CACHE_DIR = Path("/tmp")
_logger.info("Portfolio cache directory: %s", _CACHE_DIR)

_lock = Lock()


def _key_str(key: tuple) -> str:
    return hashlib.md5(str(key).encode()).hexdigest()


def _path(key_str: str, ext: str = ".pkl") -> Path:
    return _CACHE_DIR / f"{key_str}{ext}"


def get(key: tuple, ttl: int, ext: str = ".pkl") -> Optional[Any]:
    key_str = _key_str(key)
    p = _path(key_str, ext)
    if not p.exists():
        _logger.debug("Cache miss key=%s path=%s", key_str, p)
        return None
    try:
        mtime = p.stat().st_mtime
        if time.time() - mtime > ttl:
            _logger.debug("Cache expired key=%s path=%s age=%ss ttl=%s", key_str, p, int(time.time() - mtime), ttl)
            p.unlink(missing_ok=True)
            return None
        if ext == ".pkl":
            with open(p, "rb") as f:
                value = pickle.load(f)
        else:
            with open(p, "r", encoding="utf-8") as f:
                value = f.read()
        _logger.debug("Cache hit key=%s path=%s", key_str, p)
        return value
    except Exception as exc:
        _logger.warning("Cache read error key=%s path=%s error=%s", key_str, p, exc)
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def exists(key: tuple, ttl: int, ext: str = ".pkl") -> bool:
    key_str = _key_str(key)
    p = _path(key_str, ext)
    if not p.exists():
        _logger.debug("Cache exists miss key=%s path=%s", key_str, p)
        return False
    try:
        if time.time() - p.stat().st_mtime > ttl:
            _logger.debug("Cache exists expired key=%s path=%s", key_str, p)
            p.unlink(missing_ok=True)
            return False
        _logger.debug("Cache exists hit key=%s path=%s", key_str, p)
        return True
    except Exception as exc:
        _logger.warning("Cache exists error key=%s path=%s error=%s", key_str, p, exc)
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def set(key: tuple, value: Any, ext: str = ".pkl") -> None:
    key_str = _key_str(key)
    p = _path(key_str, ext)
    with _lock:
        try:
            if ext == ".pkl":
                with open(p, "wb") as f:
                    pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
            elif ext == ".html":
                with open(p, "w", encoding="utf-8") as f:
                    f.write(value)
            else:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(str(value))
            _logger.debug("Cache write key=%s path=%s", key_str, p)
        except Exception as exc:
            _logger.warning("Cache write error key=%s path=%s error=%s", key_str, p, exc)


def invalidate(key: tuple) -> None:
    key_str = _key_str(key)
    with _lock:
        for ext in [".pkl", ".html", ".json"]:
            p = _path(key_str, ext)
            p.unlink(missing_ok=True)
        _logger.debug("Cache invalidated key=%s", key_str)


def clear() -> None:
    with _lock:
        for f in list(_CACHE_DIR.glob("*")):
            try:
                f.unlink()
            except Exception as exc:
                _logger.warning("Cache clear error path=%s error=%s", f, exc)
    _logger.info("Portfolio cache cleared directory=%s", _CACHE_DIR)


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

