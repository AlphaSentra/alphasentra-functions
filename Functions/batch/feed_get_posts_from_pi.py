"""Batch worker to fetch posts from trending Popular Investors and store in MongoDB.

Reads the ``etoro_trending_pi`` collection from the feed database, then for each
PI fetches their public feed posts over the last 30 days via the eToro public
API. Each post is stored as a raw payload with its eToro post URL in the
``etoro_posts`` collection.

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
from datetime import datetime, timezone, timedelta
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
    _ETORO_PUBLIC_API_BASE,
    _ETORO_ENDPOINT_USER_FEED as _FEED_ENDPOINT,
)
from Functions.logging_utils import log_info, log_warning, log_error

try:
    from Functions.port.config import ETORO_POST_URL
except Exception:
    ETORO_POST_URL = "https://www.etoro.com/posts/[post_id]"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_FEED_PARAMS = {
    "take": "100",
    "offset": "0",
}
_LOOKBACK_DAYS = 30
_RATE_LIMIT_DELAY_SECONDS = 1.0
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


def _get_pi_user_ids(client: MongoClient) -> list:
    """Load PI user IDs from the ``etoro_trending_pi`` collection.

    Returns:
        List of unique user ID strings.
    """
    db_name = os.getenv("MONGODB_DATABASE_FEED", "alphasentra-feed")
    db = client[db_name]
    collection = db["etoro_trending_pi"]

    sample_doc = collection.find_one()
    if sample_doc:
        log_info("Sample etoro_trending_pi doc keys: %s" % sorted(sample_doc.keys()))
        log_info(
            "Sample etoro_trending_pi doc preview: %s"
            % str(sample_doc)[:500]
        )
    else:
        log_warning("etoro_trending_pi collection is empty.")

    id_fields = [
        "cid",
        "userId",
        "user_id",
        "userIdNumber",
        "id",
        "userIdStr",
        "userIdString",
        "realCID",
        "gcid",
        "username",
    ]
    projection = {field: 1 for field in id_fields}
    projection["_id"] = 0

    cursor = collection.find({}, projection)
    user_ids = set()
    for doc in cursor:
        for field in id_fields:
            value = doc.get(field)
            if value is not None:
                user_ids.add(str(value))
                break

    log_info(f"Found {len(user_ids)} user IDs from etoro_trending_pi.")
    return list(user_ids)


def _parse_iso_datetime(value) -> datetime | None:
    """Parse an ISO datetime string or return None on failure."""
    if value is None:
        return None
    text = str(value)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_post_metrics(discussion: dict) -> dict | None:
    """Extract the post ID and preserve the full raw discussion payload.

    Args:
        discussion: Raw discussion dict from the feed API.

    Returns:
        Dict with post_id, created_at, likes, comments, owner_username,
        message_text, and raw discussion, or None if invalid.
    """
    post = discussion.get("post") or {}
    post_id = post.get("id")
    created_raw = post.get("created")
    created_at = _parse_iso_datetime(created_raw)
    if post_id is None or created_at is None:
        return None

    emotions_data = discussion.get("emotionsData") or {}
    like_data = emotions_data.get("like") or {}
    like_paging = like_data.get("paging") or {}
    likes = int((like_paging.get("totalCount") or 0))

    comments_data = discussion.get("commentsData") or {}
    reaction_paging = comments_data.get("reactionPaging") or {}
    comments = int((reaction_paging.get("totalCount") or 0))

    owner = post.get("owner") or {}
    owner_username = owner.get("username")

    message = post.get("message") or {}
    message_text = message.get("text")

    return {
        "post_id": str(post_id),
        "created_at": created_at,
        "likes": likes,
        "comments": comments,
        "owner_username": owner_username,
        "message_text": message_text,
        "raw": discussion,
    }


def _prepare_documents(posts: list) -> list:
    """Build documents with raw payload and post URL only.

    Args:
        posts: List of normalized post dicts with post_id and raw payload.

    Returns:
        List of documents ready for MongoDB upsert.
    """
    documents = []
    for post in posts:
        post_url = (
            ETORO_POST_URL.replace("[post_id]", post["post_id"])
            if "[post_id]" in ETORO_POST_URL
            else f"{ETORO_POST_URL.rstrip('/')}/{post['post_id']}"
        )
        documents.append(
            {
                "post_id": post["post_id"],
                "post_url": post_url,
                "created": post.get("created_at"),
                "owner_username": post.get("owner_username"),
                "message_text": post.get("message_text"),
                "likes": post.get("likes", 0),
                "comments": post.get("comments", 0),
                "raw": post.get("raw"),
            }
        )
    return documents


def _fetch_user_feed(session: requests.Session, user_id: str) -> list:
    """Fetch all posts for a user within the lookback window.

    Paginates using ``paging.next`` until posts are older than the lookback
    window or no more pages are available.

    Args:
        session: Authenticated ``requests.Session`` for eToro public API.
        user_id: eToro user ID to fetch feed for.

    Returns:
        List of normalized post metric dicts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
    url = _FEED_ENDPOINT.format(user_id=user_id)
    params = dict(_FEED_PARAMS)

    posts = []
    seen_post_ids = set()
    last_status = None
    last_body_preview = ""

    for attempt in range(_MAX_RETRIES):
        current_url = url
        current_params = dict(params)
        should_retry = False

        while current_url:
            try:
                resp = session.get(current_url, params=current_params, timeout=30)
            except requests.RequestException as exc:
                log_warning(
                    "Feed API error for user %s on attempt %d/%d: %s"
                    % (user_id, attempt + 1, _MAX_RETRIES, exc)
                )
                should_retry = True
                break

            last_status = resp.status_code
            try:
                last_body_preview = resp.text[:200]
            except Exception:
                last_body_preview = ""

            if resp.status_code == 429 or resp.status_code == 417 or resp.status_code >= 500:
                log_warning(
                    "Feed API HTTP %d for user %s on attempt %d/%d body=%s"
                    % (
                        resp.status_code,
                        user_id,
                        attempt + 1,
                        _MAX_RETRIES,
                        last_body_preview,
                    )
                )
                if attempt == _MAX_RETRIES - 1:
                    resp.raise_for_status()
                should_retry = True
                break

            resp.raise_for_status()
            data = resp.json()

            discussions = data.get("discussions") or []
            for discussion in discussions:
                metrics = _extract_post_metrics(discussion)
                if metrics is None:
                    continue
                if metrics["created_at"] < cutoff:
                    return posts
                if metrics["post_id"] in seen_post_ids:
                    continue
                seen_post_ids.add(metrics["post_id"])
                posts.append(metrics)

            paging = data.get("paging") or {}
            current_url = paging.get("next")
            current_params = {}
            if not current_url:
                break

            time.sleep(_RATE_LIMIT_DELAY_SECONDS)

        if not should_retry:
            return posts

        if attempt == _MAX_RETRIES - 1:
            break
        time.sleep(_BASE_DELAY_SECONDS * (1.1 ** attempt) + random.uniform(0, 1.0))

    raise RuntimeError(
        f"GET {url} failed after {_MAX_RETRIES} attempts for user {user_id}: "
        f"last_status={last_status}, body={last_body_preview!r}"
    )


def _write_to_feed(documents: list) -> int:
    """Upsert post documents into the feed MongoDB collection.

    Documents are keyed by ``post_id``.

    Args:
        documents: Post documents to store.

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
        collection = db["etoro_posts"]

        if not documents:
            log_warning("No post documents to store.")
            return 0

        bulk_ops = []
        for doc in documents:
            bulk_ops.append(
                UpdateOne(
                    {"post_id": doc["post_id"]},
                    {"$set": doc},
                    upsert=True,
                )
            )

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
    """Fetch posts from trending PIs and persist raw posts to MongoDB."""
    api_key = os.getenv("ETORO_PUBLIC_KEY", "")
    if not api_key:
        raise EnvironmentError("ETORO_PUBLIC_KEY environment variable is required")

    log_info("Fetching trending PI user IDs from feed.etoro_trending_pi...")

    client = _get_feed_client()
    try:
        user_ids = _get_pi_user_ids(client)
    finally:
        client.close()

    if not user_ids:
        log_warning("No user IDs found in etoro_trending_pi.")
        return

    log_info(f"Found {len(user_ids)} PI user IDs to process.")

    session = public_api_session(api_key, get_random_private_key(), timeout=30)

    all_posts = []
    for idx, user_id in enumerate(user_ids, start=1):
        log_info(f"Fetching feed for user {user_id} ({idx}/{len(user_ids)})...")
        try:
            posts = _fetch_user_feed(session, user_id)
            all_posts.extend(posts)
            log_info(f"Collected {len(posts)} posts for user {user_id}.")
        except Exception as exc:
            log_warning(f"Failed to fetch feed for user {user_id}: {exc}")
            continue

        if idx < len(user_ids):
            time.sleep(_RATE_LIMIT_DELAY_SECONDS)

    if not all_posts:
        log_warning("No posts collected from any PI feed.")
        return

    seen_ids = set()
    unique_posts = []
    for post in all_posts:
        post_id = post.get("post_id")
        if post_id and post_id not in seen_ids:
            seen_ids.add(post_id)
            unique_posts.append(post)

    log_info(f"Collected {len(unique_posts)} unique posts across all PIs.")

    documents = _prepare_documents(unique_posts)
    log_info(f"Prepared {len(documents)} post documents.")

    upserted = _write_to_feed(documents)
    log_info(f"Upserted {upserted} documents into feed.etoro_posts.")


if __name__ == "__main__":
    main()
