"""Batch worker to clear transient eToro feed collections from MongoDB.

Drops all documents from ``etoro_trending_instruments`` and
``etoro_trending_pi``, then removes stale documents from ``etoro_posts``
where ``created`` is older than 10 days.

Environment variables:
    MONGODB_URI_FEED        - MongoDB connection URI for the feed database.
    MONGODB_DATABASE_FEED   - Feed database name (default: alphasentra-feed).
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Load environment variables from .env file so batch scripts can be run directly.
load_dotenv()

# ---------------------------------------------------------------------------
# Project root setup so batch scripts can import Functions/* when executed
# directly from the repo root.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))

from Functions.logging_utils import log_info, log_error  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_FEED_URI_ENV = "MONGODB_URI_FEED"
_FEED_DB_ENV = "MONGODB_DATABASE_FEED"
_DEFAULT_FEED_DB = "alphasentra-feed"
_CLIENT_TIMEOUT_MS = 30000

# Collections cleared entirely on each run.
_FULL_CLEAR_COLLECTIONS = [
    "etoro_trending_instruments",
    "etoro_trending_pi",
]

# Age threshold (in days) for pruning etoro_posts documents.
_POSTS_STALE_DAYS = 10


# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------
def _get_feed_client() -> MongoClient:
    """Create and return a MongoDB client for the feed database.

    Returns:
        A connected ``MongoClient`` instance.

    Raises:
        EnvironmentError: If ``MONGODB_URI_FEED`` is not configured.
    """
    uri = os.getenv(_FEED_URI_ENV, "")
    if not uri:
        raise EnvironmentError(f"{_FEED_URI_ENV} environment variable is required")
    client = MongoClient(uri, serverSelectionTimeoutMS=_CLIENT_TIMEOUT_MS)
    client.admin.command("ping")
    return client


def _get_feed_db(client: MongoClient):
    """Resolve the feed database from environment or default."""
    db_name = os.getenv(_FEED_DB_ENV, _DEFAULT_FEED_DB)
    return client[db_name]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def clear_feed() -> None:
    """Clear transient eToro feed collections from MongoDB.

    In order:
    1. Drops all documents from ``etoro_trending_instruments``.
    2. Drops all documents from ``etoro_trending_pi``.
    3. Removes documents from ``etoro_posts`` where ``created`` is older
       than ``_POSTS_STALE_DAYS`` days.

    Logs the deleted document count for each operation so Render cron
    runs and local batch jobs can distinguish success from silent failure.
    """
    client = _get_feed_client()
    try:
        db = _get_feed_db(client)

        for collection_name in _FULL_CLEAR_COLLECTIONS:
            try:
                collection = db[collection_name]
                result = collection.delete_many({})
                log_info(
                    "Cleared feed collection %s (deleted %d documents)."
                    % (collection_name, result.deleted_count)
                )
            except PyMongoError as exc:
                log_error("Failed to clear feed collection %s" % collection_name, "FEED", exc)
                raise

        cutoff = datetime.now(timezone.utc) - timedelta(days=_POSTS_STALE_DAYS)
        posts_collection = db["etoro_posts"]
        result = posts_collection.delete_many({"created": {"$lt": cutoff}})
        log_info(
            "Cleared etoro_posts documents older than %d days (deleted %d documents)."
            % (_POSTS_STALE_DAYS, result.deleted_count)
        )
    finally:
        client.close()


if __name__ == "__main__":
    clear_feed()
