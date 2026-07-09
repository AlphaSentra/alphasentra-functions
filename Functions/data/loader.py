"""
Data loading utilities for portfolio and transaction data.
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import requests

from Functions.etoro.client import EToroClientError, ETPublicClient
from Functions.etoro.auth import public_api_session

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parent / ".etoro_instrument_cache.json"
_CACHE_TTL_SECONDS = 24 * 60 * 60
_MAX_WORKERS = 10


def _load_cache() -> Dict[str, Dict[str, str]]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            cache: Dict[str, Any] = json.load(f)
        now = time.time()
        return {k: v for k, v in cache.items() if now - v.get("_ts", 0) < _CACHE_TTL_SECONDS}
    except Exception:
        return {}


def _save_cache(metadata: Dict[str, Dict[str, str]]) -> None:
    try:
        cache = _load_cache()
        for k, v in metadata.items():
            cache[k] = {"_ts": time.time(), **v}
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as exc:
        logger.debug("Failed to save instrument metadata cache: %s", exc)


def _fetch_one(session: requests.Session, search_url: str, iid: str) -> Optional[Dict[str, str]]:
    try:
        resp = session.get(search_url, params={"instrumentId": iid}, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return None
        item = items[0]
        symbol = item.get("internalSymbolFull") or item.get("internalSymbol") or item.get("symbol")
        name = (
            item.get("internalInstrumentDisplayName")
            or item.get("displayname")
            or item.get("displayName")
            or item.get("instrumentDisplayName")
            or item.get("name")
            or item.get("instrumentName")
            or item.get("title")
            or ""
        )
        if symbol:
            return {"symbol": str(symbol), "name": str(name)}
    except Exception as exc:
        logger.debug("Failed to resolve instrument %s: %s", iid, exc)
    return None


def _resolve_instrument_metadata(instrument_ids: list, api_key: str, user_key: str, timeout: int = 30) -> Dict[str, Dict[str, str]]:
    """
    Resolve eToro InstrumentIDs to full symbol and display name via the search API.
    
    Returns a dict keyed by InstrumentID with values like:
        {"symbol": "AAPL", "name": "Apple Inc."}
    """
    result: Dict[str, Dict[str, str]] = {}
    if not instrument_ids:
        return result

    cache = _load_cache()
    remaining = [iid for iid in instrument_ids if str(iid) not in cache]
    for iid in instrument_ids:
        iid_str = str(iid)
        if iid_str in cache:
            result[iid_str] = {k: v for k, v in cache[iid_str].items() if k != "_ts"}

    if not remaining:
        return result

    session = public_api_session(api_key, user_key, timeout=timeout)
    search_url = "https://public-api.etoro.com/api/v1/market-data/search"

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_one, session, search_url, iid): iid for iid in remaining}
        for future in as_completed(futures):
            iid = futures[future]
            try:
                meta = future.result()
                if meta:
                    result[str(iid)] = meta
            except Exception as exc:
                logger.debug("Instrument resolution future failed for %s: %s", iid, exc)

    if result:
        _save_cache(result)

    return result


def _safe_to_float(value) -> Optional[float]:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_to_str(value) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_side(direction) -> str:
    text = str(direction).strip().upper()
    if text in {"BUY", "B", "LONG", "1"}:
        return "BUY"
    if text in {"SELL", "S", "SHORT", "-1", "0"}:
        return "SELL"
    return text


def _parse_date(value) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    try:
        ts = pd.to_datetime(value, utc=True)
        return ts.tz_localize(None) if ts.tzinfo else ts
    except Exception:
        return None


def _map_record_to_row(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    close_date_val = raw.get("CloseDateTime")
    open_date_val = raw.get("OpenDateTime")
    symbol = raw.get("InstrumentID")
    is_buy = raw.get("IsBuy")
    close_rate = raw.get("CloseRate")
    open_rate = raw.get("OpenRate")
    net_profit = raw.get("NetProfit")

    if not close_date_val or not close_rate or not symbol:
        return None

    parsed_close_date = _parse_date(close_date_val)
    parsed_open_date = _parse_date(open_date_val)
    if parsed_close_date is None:
        return None

    side = "BUY" if bool(is_buy) else "SELL"

    return {
        "Exit Date": parsed_close_date,
        "OpenDate": parsed_open_date,
        "Ticker": str(symbol),
        "Name": "",
        "Side": side,
        "EntryPrice": _safe_to_float(open_rate),
        "ExitPrice": _safe_to_float(close_rate),
        "PnL": _safe_to_float(net_profit),
        "_instrument_id": str(symbol),
    }


def load_transactions_from_etoro(
    username: str,
    cid: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    user_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Loads transaction data from the eToro public trade history API.

    If `cid` is provided, it is used directly as the customer ID parameter.
    Otherwise, the client attempts to resolve `username` automatically
    via multiple strategies (public API, profile scraping).

    Args:
        username: eToro username.
        cid: Optional explicit CID to skip automatic resolution.
        api_key: Optional explicit eToro public API key.
        user_key: Optional explicit eToro user key.

    Returns:
        pd.DataFrame: A DataFrame with columns Date, Ticker, Name, Side,
            EntryPrice, ExitPrice, PnL. Returns empty DataFrame on failure.
    """
    try:
        resolved_api_key = api_key if api_key is not None else os.getenv("ETORO_PUBLIC_KEY", "")
        resolved_user_key = user_key if user_key is not None else os.getenv("ETORO_PRIVATE_KEY", "")
        client = ETPublicClient(api_key=resolved_api_key, user_key=resolved_user_key)
        resolved_cid = cid or client.resolve_cid(username)
        history = client.get_trade_history(username=username, explicit_cid=resolved_cid)

        if not history.records:
            logger.warning("eToro trade history returned no records for %s.", username)
            return pd.DataFrame()

        records = []
        instrument_ids = []
        for record in history.records:
            raw = record.raw if isinstance(record.raw, dict) else {}
            row = _map_record_to_row(raw)
            if row is not None:
                records.append(row)
                iid = row.get("_instrument_id")
                if iid:
                    instrument_ids.append(iid)

        df = pd.DataFrame(records)

        metadata = {}
        if not df.empty:
            unique_ids = sorted({str(i) for i in instrument_ids})
            metadata = _resolve_instrument_metadata(
                unique_ids,
                api_key=client._api_key,
                user_key=client._user_key,
                timeout=client._timeout,
            )

        if metadata:
            df["Ticker"] = df["_instrument_id"].map(lambda iid: metadata.get(str(iid), {}).get("symbol", str(iid)))
            df["Name"] = df["_instrument_id"].map(lambda iid: metadata.get(str(iid), {}).get("name", ""))
            df = df.drop(columns=["_instrument_id"])

            drop_cols = [c for c in df.columns if c.startswith("_")]
            if drop_cols:
                df = df.drop(columns=drop_cols)

            required_cols = {"Exit Date", "OpenDate", "Ticker", "Name", "Side", "EntryPrice", "ExitPrice", "PnL"}
            missing = required_cols - set(df.columns)
            if missing:
                logger.warning("eToro trade history missing expected columns: %s", sorted(missing))

            df["Exit Date"] = pd.to_datetime(df["Exit Date"], utc=True).dt.tz_localize(None)
            df = df.sort_values("Exit Date").reset_index(drop=True)

        logger.info("Loaded %d eToro trade history records for %s.", len(df), username)
        return df

    except EToroClientError as exc:
        logger.warning("Failed to load eToro trade history for %s: %s", username, exc)
        return pd.DataFrame()
    except Exception as exc:
        logger.warning("Unexpected error loading eToro trade history for %s: %s", username, exc)
        return pd.DataFrame()
