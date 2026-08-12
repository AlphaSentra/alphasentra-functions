"""Batch worker to fetch trending instruments from eToro and store in MongoDB.

Calls the eToro public market-data search endpoint to retrieve the top 100
instruments by 7-day unique viewer popularity and by 7-day trader change, then
upserts them into the ``etoro_trending_instruments`` collection in the feed
MongoDB database.

Environment variables:
    ETORO_PUBLIC_KEY   - eToro public API key.
    ETORO_PRIVATE_KEY  - eToro private API key(s), comma-separated.
    MONGODB_URI_FEED   - MongoDB connection URI for the feed database.
    MONGODB_DATABASE_FEED - Feed database name (default: alphasentra-feed).
"""

import os
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError

# ---------------------------------------------------------------------------
# Project root setup so batch scripts can import Functions/* when executed
# directly from the repo root.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))

from Functions.etoro.auth import public_api_session, get_random_private_key
from Functions.etoro.client import _ETORO_ENDPOINT_MARKET_DATA_SEARCH as _INSTRUMENTS_ENDPOINT
from Functions.logging_utils import log_info, log_warning, log_error


# ---------------------------------------------------------------------------
# Feed-specific instrument search configurations
# ---------------------------------------------------------------------------
_INSTRUMENTS_QUERIES = [
    {
        "label": "popularity",
        "params": {
            "fields": "instrumentId,displayname,popularityUniques7Day",
            "sort": "-popularityUniques7Day",
            "pageSize": "100",
        },
    },
    {
        "label": "traders_change",
        "params": {
            "fields": "instrumentId,displayname,traders7DayChange",
            "sort": "-traders7DayChange",
            "pageSize": "100",
        },
    },
]

# ---------------------------------------------------------------------------
# Retry/backoff configuration
# ---------------------------------------------------------------------------
_MAX_RETRIES = 5
_BASE_DELAY_SECONDS = 2.0


def _get_feed_client() -> MongoClient:
    """Create and return a MongoDB client for the feed database.

    Returns:
        A connected ``MongoClient`` instance.

    Raises:
        EnvironmentError: If ``MONGODB_URI_FEED`` is not configured.
    """
    uri = os.getenv("MONGODB_URI_FEED", "")
    if not uri:
        raise EnvironmentError("MONGODB_URI_FEED environment variable is required")
    client = MongoClient(uri, serverSelectionTimeoutMS=30000)
    client.admin.command("ping")
    return client


def _fetch_instruments(session: requests.Session, params: dict) -> dict:
    """Fetch trending instruments from eToro with retry/backoff.

    Retries up to ``_MAX_RETRIES`` times on network errors or HTTP 429/5xx
    responses, using exponential backoff with jitter.

    Args:
        session: Authenticated ``requests.Session`` for eToro public API.
        params: Query parameters for the market-data search endpoint.

    Returns:
        Parsed JSON response from the market-data search endpoint.

    Raises:
        requests.HTTPError: If the final attempt returns a non-success status.
        RuntimeError: If all retry attempts are exhausted.
    """
    last_status = None
    last_body_preview = ""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = session.get(_INSTRUMENTS_ENDPOINT, params=params, timeout=30)
        except requests.RequestException as exc:
            log_warning(
                "eToro instruments API error on attempt %d/%d: %s"
                % (attempt + 1, _MAX_RETRIES, exc)
            )
            if attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(_BASE_DELAY_SECONDS * (1.1 ** attempt) + random.uniform(0, 1.0))
            continue

        last_status = resp.status_code
        try:
            last_body_preview = resp.text[:200]
        except Exception:
            last_body_preview = ""

        if resp.status_code == 429 or resp.status_code >= 500:
            log_warning(
                "eToro instruments API HTTP %d on attempt %d/%d body=%s"
                % (
                    resp.status_code,
                    attempt + 1,
                    _MAX_RETRIES,
                    last_body_preview,
                )
            )
            if attempt == _MAX_RETRIES - 1:
                resp.raise_for_status()
            time.sleep(_BASE_DELAY_SECONDS * (1.1 ** attempt) + random.uniform(0, 1.0))
            continue

        resp.raise_for_status()
        return resp.json()

    raise RuntimeError(
        f"GET {_INSTRUMENTS_ENDPOINT} failed after {_MAX_RETRIES} attempts: "
        f"last_status={last_status}, body={last_body_preview!r}"
    )


def _extract_items(data: dict, label: str) -> list:
    """Extract the instrument list from an API response.

    Args:
        data: Parsed JSON response from the market-data search endpoint.
        label: Query label for logging purposes.

    Returns:
        List of instrument item dicts, or an empty list if none found.
    """
    if not isinstance(data, dict):
        log_warning(f"Unexpected {label} response type; expected dict.")
        return []

    keys = sorted(data.keys())
    log_info(f"{label} response keys: {keys}")

    items = data.get("items")
    if items is None:
        items = data.get("instruments")
    if items is None:
        items = data.get("data")
    if items is None and isinstance(data, dict):
        for key in keys:
            candidate = data[key]
            if isinstance(candidate, list):
                items = candidate
                log_info(f"{label}: using list response key: {key}")
                break

    if not isinstance(items, list) or not items:
        log_warning(
            f"{label} response contained no usable list. Raw preview: %s",
            str(data)[:500],
        )
        return []

    log_info(f"{label}: received {len(items)} instrument items from eToro.")
    return items


def _write_to_feed(items: list) -> int:
    """Upsert instrument items into the feed MongoDB collection.

    Each item is keyed by ``instrumentId``. A UTC ``fetched_at`` timestamp is
    injected into every document. Retries up to ``_MAX_RETRIES`` times on
    MongoDB write errors.

    Args:
        items: Raw instrument items from the eToro API response.

    Returns:
        Number of documents successfully upserted.

    Raises:
        PyMongoError: If all MongoDB write attempts fail.
    """
    uri = os.getenv("MONGODB_URI_FEED", "")
    db_name = os.getenv("MONGODB_DATABASE_FEED", "alphasentra-feed")
    client = MongoClient(uri, serverSelectionTimeoutMS=30000)
    try:
        db = client[db_name]
        collection = db["etoro_trending_instruments"]

        fetched_at = datetime.now(timezone.utc)
        bulk_ops = []
        skipped = 0
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            doc = {**item, "fetched_at": fetched_at}
            instrument_id = item.get("instrumentId")
            if instrument_id is None:
                skipped += 1
                continue
            bulk_ops.append(
                UpdateOne(
                    {"instrumentId": instrument_id},
                    {"$set": doc},
                    upsert=True,
                )
            )

        if skipped:
            log_warning(f"Skipped {skipped} items due to missing instrumentId or invalid format.")

        if not bulk_ops:
            log_warning("No valid instrument items to store.")
            return 0

        last_exception = None
        for attempt in range(_MAX_RETRIES):
            try:
                collection.bulk_write(bulk_ops, ordered=False)
                return len(bulk_ops)
            except PyMongoError as exc:
                last_exception = exc
                log_warning(
                    "MongoDB bulk_write failed on attempt %d/%d: %s"
                    % (attempt + 1, _MAX_RETRIES, exc)
                )
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(_BASE_DELAY_SECONDS * (1.1 ** attempt) + random.uniform(0, 1.0))
    finally:
        client.close()

    if last_exception is not None:
        raise last_exception
    return 0


def main() -> None:
    """Fetch trending eToro instruments and persist them to MongoDB."""
    api_key = os.getenv("ETORO_PUBLIC_KEY", "")
    if not api_key:
        raise EnvironmentError("ETORO_PUBLIC_KEY environment variable is required")

    log_info("Fetching trending instruments from eToro market-data search API...")

    session = public_api_session(api_key, get_random_private_key(), timeout=30)

    merged_items = []
    seen_ids = set()
    for query in _INSTRUMENTS_QUERIES:
        label = query["label"]
        params = query["params"]
        log_info(f"Running {label} instruments query...")

        data = _fetch_instruments(session, params)
        items = _extract_items(data, label)

        for item in items:
            instrument_id = item.get("instrumentId") if isinstance(item, dict) else None
            if instrument_id is not None and instrument_id not in seen_ids:
                seen_ids.add(instrument_id)
                merged_items.append(item)

    if not merged_items:
        log_warning("No instrument items collected from any query.")
        return

    log_info(f"Collected {len(merged_items)} unique instrument items across all queries.")

    upserted = _write_to_feed(merged_items)
    log_info(f"Upserted {upserted} documents into feed.etoro_trending_instruments.")


if __name__ == "__main__":
    main()
