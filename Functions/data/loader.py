"""
Data loading utilities for portfolio and transaction data.
"""

import logging
import os
from typing import Any, Dict, Optional

import pandas as pd

from Functions.etoro.client import EToroClientError, ETPublicClient, InvalidSymbolError
from Functions.etoro.auth import get_random_private_key

logger = logging.getLogger(__name__)
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
    client: Optional[ETPublicClient] = None,
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
        client: Optional pre-authenticated ETPublicClient to reuse.

    Returns:
        pd.DataFrame: A DataFrame with columns Date, Ticker, Name, Side,
            EntryPrice, ExitPrice, PnL. Returns empty DataFrame on failure.
    """
    try:
        resolved_api_key = api_key if api_key is not None else os.getenv("ETORO_PUBLIC_KEY", "")
        resolved_user_key = user_key if user_key is not None else get_random_private_key()
        resolved_client = client or ETPublicClient(api_key=resolved_api_key, user_key=resolved_user_key)
        resolved_cid = cid or resolved_client.resolve_cid(username)
        history = resolved_client.get_trade_history(username=username, explicit_cid=resolved_cid)

        for record in history.records:
            raw = record.raw if isinstance(record.raw, dict) else {}
            ticker = raw.get("Ticker", "")
            name = raw.get("Name", "")
            if isinstance(ticker, str) and isinstance(name, str) and (ticker.isdigit() or name.isdigit()):
                raise InvalidSymbolError(
                    f"Trade history for {username} contains numeric-only field(s) "
                    f"(Ticker={ticker!r}, Name={name!r}). Skipping portfolio."
                )

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
        unresolved_iids = set()
        if not df.empty:
            unique_ids = sorted({str(i) for i in instrument_ids})
            raw_metadata = resolved_client.resolve_instrument_metadata(unique_ids)

            resolved_ids = set(raw_metadata.keys())
            unresolved_iids = {str(iid) for iid in unique_ids if str(iid) not in resolved_ids}
            if unresolved_iids:
                logger.warning(
                    "Failed to resolve instrument metadata for %d instrument(s): %s. "
                    "These will be excluded from trade history.",
                    len(unresolved_iids), sorted(unresolved_iids)[:10],
                )

            metadata = dict(raw_metadata)

            for attempt in range(5):
                bad_iids = [
                    iid for iid, meta in metadata.items()
                    if (
                        isinstance(meta.get("symbol"), str) and meta["symbol"].isdigit()
                    ) or (
                        isinstance(meta.get("name"), str) and meta["name"].isdigit()
                    )
                ]
                if not bad_iids:
                    break
                logger.warning(
                    "Numerical field(s) in resolved metadata for instrument(s) %s "
                    "(symbol or name) — attempt %d/5. Clearing cache and retrying...",
                    bad_iids, attempt + 1,
                )
                from Functions.etoro.client import _remove_from_instrument_cache
                for iid in bad_iids:
                    _remove_from_instrument_cache(iid)
                try:
                    retry_metadata = resolved_client.resolve_instrument_metadata(bad_iids)
                    for iid in bad_iids:
                        metadata.pop(iid, None)
                    for iid, meta in retry_metadata.items():
                        if meta.get("symbol"):
                            metadata[iid] = meta
                except Exception as exc:
                    logger.warning("Retry failed to resolve trade history symbols/names: %s", exc)
                    for iid in bad_iids:
                        metadata.pop(iid, None)
            else:
                remaining_bad = [
                    iid for iid, meta in metadata.items()
                    if (
                        isinstance(meta.get("symbol"), str) and meta["symbol"].isdigit()
                    ) or (
                        isinstance(meta.get("name"), str) and meta["name"].isdigit()
                    )
                ]
                if remaining_bad:
                    raise InvalidSymbolError(
                        f"Trade history instrument(s) {remaining_bad} returned numerical "
                        f"symbol or name after 5 retries"
                    )

        if metadata:
            df = df[~df["_instrument_id"].isin(unresolved_iids)].copy()

            df["Ticker"] = df["_instrument_id"].map(
                lambda iid: metadata.get(str(iid), {}).get("symbol", str(iid))
            )
            df["Name"] = df["_instrument_id"].map(
                lambda iid: metadata.get(str(iid), {}).get("name", "")
            )
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

    except InvalidSymbolError:
        raise
    except EToroClientError as exc:
        logger.warning("Failed to load eToro trade history for %s: %s", username, exc)
        return pd.DataFrame()
    except Exception as exc:
        logger.warning("Unexpected error loading eToro trade history for %s: %s", username, exc)
        return pd.DataFrame()
