"""Batch worker to fetch trending Popular Investors from eToro and store in MongoDB.

Fetches the current-year top-copier Popular Investor rankings from the eToro
public API and upserts them into the ``etoro_trending_pi`` collection in the
feed MongoDB database.

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
from Functions.etoro.client import (
    _ETORO_ENDPOINT_PORTFOLIO_RANKINGS_GLOBAL as _RANKINGS_ENDPOINT,
)
from Functions.logging_utils import log_info, log_warning, log_error


# ---------------------------------------------------------------------------
# Feed-specific eToro rankings configuration
# ---------------------------------------------------------------------------
_RANKINGS_PARAMS = {
    "period": "CurrYear",
    "sort": "-copiers",
    "pageSize": "100",
    "popularInvestor": "true",
}

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


def _fetch_rankings(session: requests.Session) -> dict:
    """Fetch Popular Investor rankings from eToro with retry/backoff.

    Retries up to ``_MAX_RETRIES`` times on network errors or HTTP 429/5xx
    responses, using exponential backoff with jitter.

    Args:
        session: Authenticated ``requests.Session`` for eToro public API.

    Returns:
        Parsed JSON response from the rankings endpoint.

    Raises:
        requests.HTTPError: If the final attempt returns a non-success status.
        RuntimeError: If all retry attempts are exhausted.
    """
    last_status = None
    last_body_preview = ""
    for attempt in range(_MAX_RETRIES):
        try:
            resp = session.get(_RANKINGS_ENDPOINT, params=_RANKINGS_PARAMS, timeout=30)
        except requests.RequestException as exc:
            log_warning(
                "eToro rankings API error on attempt %d/%d: %s",
                attempt + 1,
                _MAX_RETRIES,
                exc,
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
                "eToro rankings API HTTP %d on attempt %d/%d body=%s",
                resp.status_code,
                attempt + 1,
                _MAX_RETRIES,
                last_body_preview,
            )
            if attempt == _MAX_RETRIES - 1:
                resp.raise_for_status()
            time.sleep(_BASE_DELAY_SECONDS * (1.1 ** attempt) + random.uniform(0, 1.0))
            continue

        resp.raise_for_status()
        return resp.json()

    raise RuntimeError(
        f"GET {_RANKINGS_ENDPOINT} failed after {_MAX_RETRIES} attempts: "
        f"last_status={last_status}, body={last_body_preview!r}"
    )


def _write_to_feed(items: list) -> int:
    """Upsert ranking items into the feed MongoDB collection.

    Each item is keyed by ``username`` (falling back to ``userName`` or
    ``displayName``). A UTC ``fetched_at`` timestamp is injected into every
    document. Retries up to ``_MAX_RETRIES`` times on MongoDB write errors.

    Args:
        items: Raw ranking items from the eToro API response.

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
        collection = db["etoro_trending_pi"]

        fetched_at = datetime.now(timezone.utc)
        bulk_ops = []
        skipped = 0
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            doc = {**item, "fetched_at": fetched_at}
            username = item.get("username") or item.get("userName") or item.get("displayName")
            if not username:
                skipped += 1
                continue
            bulk_ops.append(
                UpdateOne(
                    {"username": username},
                    {"$set": doc},
                    upsert=True,
                )
            )

        if skipped:
            log_warning(f"Skipped {skipped} items due to missing username or invalid format.")

        if not bulk_ops:
            log_warning("No valid ranking items to store.")
            return 0

        last_exception = None
        for attempt in range(_MAX_RETRIES):
            try:
                collection.bulk_write(bulk_ops, ordered=False)
                return len(bulk_ops)
            except PyMongoError as exc:
                last_exception = exc
                log_warning(
                    "MongoDB bulk_write failed on attempt %d/%d: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
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
    """Fetch eToro Popular Investor rankings and persist them to MongoDB."""
    api_key = os.getenv("ETORO_PUBLIC_KEY", "")
    if not api_key:
        raise EnvironmentError("ETORO_PUBLIC_KEY environment variable is required")

    log_info("Fetching trending Popular Investors from eToro rankings API...")

    session = public_api_session(api_key, get_random_private_key(), timeout=30)
    data = _fetch_rankings(session)

    if not isinstance(data, dict):
        log_warning("Unexpected rankings response type; expected dict.")
        return

    keys = sorted(data.keys())
    log_info(f"Rankings response keys: {keys}")

    items = data.get("items")
    if items is None:
        items = data.get("rankings")
    if items is None:
        items = data.get("data")
    if items is None and isinstance(data, dict):
        for key in keys:
            candidate = data[key]
            if isinstance(candidate, list):
                items = candidate
                log_info(f"Using list response key: {key}")
                break

    if not isinstance(items, list) or not items:
        log_warning(
            "Rankings response contained no usable list. "
            "Raw preview: %s",
            str(data)[:500],
        )
        return

    log_info(f"Received {len(items)} ranking items from eToro.")

    upserted = _write_to_feed(items)
    log_info(f"Upserted {upserted} documents into feed.etoro_trending_pi.")


if __name__ == "__main__":
    main()
