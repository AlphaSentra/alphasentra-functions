"""
Lightweight file-backed cache with TTL support for portfolio report generation.

Cache keys are hashed tuples. Value serialization:
- HTML strings  -> .html (raw text)
- DataFrames    -> .pkl (pickle)
- Simple objects -> .pkl (pickle)
"""

import hashlib
import pickle
import time
from pathlib import Path
from threading import Lock
from typing import Any, Optional

_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
try:
    _CACHE_DIR.mkdir(exist_ok=True)
except Exception:
    _CACHE_DIR = Path("/tmp") / "portfolio_cache"
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
    except Exception:
        _CACHE_DIR = Path("/tmp")

_REPORT_TTL = 30 * 60    # 30 minutes
_PRICE_TTL = 6 * 60 * 60  # 6 hours
_SECTOR_TTL = 24 * 60 * 60  # 24 hours
_ETORO_TTL = 5 * 60      # 5 minutes

_lock = Lock()


def _key_str(key: tuple) -> str:
    return hashlib.md5(str(key).encode()).hexdigest()


def _path(key_str: str, ext: str = ".pkl") -> Path:
    return _CACHE_DIR / f"{key_str}{ext}"


def get(key: tuple, ttl: int, ext: str = ".pkl") -> Optional[Any]:
    key_str = _key_str(key)
    p = _path(key_str, ext)
    if not p.exists():
        return None
    try:
        mtime = p.stat().st_mtime
        if time.time() - mtime > ttl:
            p.unlink(missing_ok=True)
            return None
        if ext == ".pkl":
            with open(p, "rb") as f:
                return pickle.load(f)
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


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
        except Exception:
            pass


def invalidate(key: tuple) -> None:
    key_str = _key_str(key)
    with _lock:
        for ext in [".pkl", ".html", ".json"]:
            p = _path(key_str, ext)
            p.unlink(missing_ok=True)


def clear() -> None:
    with _lock:
        for f in _CACHE_DIR.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
