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
from datetime import datetime, timezone, timedelta, timedelta
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
    _ETORO_ENDPOINT_POST_COMMENTS as _POST_COMMENTS_ENDPOINT,
    _ETORO_ENDPOINT_COMMENT_REPLIES as _COMMENT_REPLIES_ENDPOINT,
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
_BATCH_WRITE_USERS = 25


def _build_comments_url(post_id: str, take: int = 100, order: str = "Desc", offset_entity_id: str | None = None) -> str:
    base = _POST_COMMENTS_ENDPOINT.format(post_id=post_id)
    params = [
        f"take={min(max(take, 1), 100)}",
        f"order={'Asc' if order == 'Asc' else 'Desc'}",
    ]
    if offset_entity_id:
        params.append(f"offsetEntityId={offset_entity_id}")
    return f"{base}?{'&'.join(params)}"


def _fetch_post_comments(
    session_factory,
    post_id: str,
    take: int = 100,
    order: str = "Desc",
) -> list:
    comments = []
    offset_entity_id = None
    last_status = None
    last_body_preview = ""

    for attempt in range(_MAX_RETRIES):
        session = session_factory()
        current_url = _build_comments_url(post_id, take=take, order=order, offset_entity_id=offset_entity_id)
        should_retry = False

        while current_url:
            try:
                resp = session.get(current_url, timeout=30)
            except requests.RequestException as exc:
                log_warning(
                    "Comments API error for post %s on attempt %d/%d: %s"
                    % (post_id, attempt + 1, _MAX_RETRIES, exc)
                )
                should_retry = True
                break

            last_status = resp.status_code
            try:
                last_body_preview = resp.text[:200]
            except Exception:
                last_body_preview = ""

            if resp.status_code == 429 or resp.status_code >= 500:
                log_warning(
                    "Comments API HTTP %d for post %s on attempt %d/%d body=%s"
                    % (
                        resp.status_code,
                        post_id,
                        attempt + 1,
                        _MAX_RETRIES,
                        last_body_preview,
                    )
                )
                if attempt == _MAX_RETRIES - 1:
                    resp.raise_for_status()
                should_retry = True
                break

            if resp.status_code == 401:
                log_warning(
                    "Comments API HTTP 401 for post %s on attempt %d/%d; rotating session"
                    % (post_id, attempt + 1, _MAX_RETRIES)
                )
                should_retry = True
                break

            resp.raise_for_status()
            data = resp.json()

            items = data.get("items") or data.get("comments") or []
            for item in items:
                entity = item.get("entity") or item if isinstance(item, dict) else item
                comment_id = None
                if isinstance(entity, dict):
                    comment_id = (
                        entity.get("id")
                        or entity.get("commentId")
                        or item.get("id")
                        or item.get("commentId")
                    )
                if comment_id:
                    comments.append(
                        {
                            "comment_id": str(comment_id),
                            "post_id": post_id,
                            "raw": item,
                        }
                    )

            paging = data.get("paging") or {}
            offset_entity_id = paging.get("offsetEntityId") or paging.get("next")
            if offset_entity_id:
                current_url = _build_comments_url(post_id, take=take, order=order, offset_entity_id=offset_entity_id)
                time.sleep(_RATE_LIMIT_DELAY_SECONDS)
            else:
                current_url = None

        if not should_retry:
            return comments

        if attempt == _MAX_RETRIES - 1:
            break
        time.sleep(_BASE_DELAY_SECONDS * (1.1 ** attempt) + random.uniform(0, 1.0))

    raise RuntimeError(
        f"GET {_POST_COMMENTS_ENDPOINT.format(post_id=post_id)} failed after {_MAX_RETRIES} attempts for post {post_id}: "
        f"last_status={last_status}, body={last_body_preview!r}"
    )


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
    if "." in text:
        parts = text.split(".", 1)
        fractional = parts[1].rstrip("Z")
        fractional = fractional[:6]
        fractional = fractional.ljust(6, "0")
        text = f"{parts[0]}.{fractional}Z"
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
    post = discussion.get("post") or discussion
    post_id = post.get("id")
    created_raw = post.get("created")
    if created_raw is None:
        created_raw = discussion.get("created")
    created_at = _parse_iso_datetime(created_raw)
    if post_id is None or created_at is None:
        if post_id is not None:
            log_warning(
                "Skipping post %s: missing created_at from created_raw=%s (type=%s)"
                % (post_id, created_raw, type(created_raw).__name__)
            )
        return None
    post_id_str = str(post_id)
    if not post_id_str:
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
        "post_id": post_id_str,
        "created_at": created_at,
        "likes": likes,
        "comments": comments,
        "owner_username": owner_username,
        "message_text": message_text,
        "raw": discussion,
    }

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


def _get_created_at(post: dict) -> datetime | None:
    """Return the best available created_at for a post dict.

    Checks ``post["created_at"]`` first, then falls back to
    ``post["raw"]["post"]["created"]`` or ``post["raw"]["created"]``.
    """
    created_at = post.get("created_at")
    if created_at is not None:
        return created_at
    raw = post.get("raw") or {}
    post_data = raw.get("post") or raw
    created_raw = post_data.get("created")
    if created_raw:
        return _parse_iso_datetime(created_raw)
    return None


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
        raw = post.get("raw") or {}
        post_data = raw.get("post") or {}
        tags = post_data.get("tags") or []
        attachments = post_data.get("attachments") or []
        badges = [
            tag.get("market", {}).get("symbolName")
            for tag in tags
            if isinstance(tag, dict)
            and isinstance(tag.get("market"), dict)
            and tag["market"].get("symbolName")
        ]
        owner = post_data.get("owner") or raw.get("owner") or {}
        avatar = owner.get("avatar") or {}
        avatar_medium = avatar.get("medium")
        created_at = _get_created_at(post)
        documents.append(
            {
                "post_id": post["post_id"],
                "post_url": post_url,
                "badges": badges,
                "attachments": attachments,
                "created": created_at,
                "owner_username": post.get("owner_username"),
                "message_text": post.get("message_text"),
                "likes": post.get("likes", 0),
                "comments": post.get("comments", 0),
                "avatar_medium": avatar_medium,
                "raw": post.get("raw"),
            }
        )
    return documents


def _build_replies_url(
    post_id: str,
    comment_id: str,
    take: int = 20,
    order: str = "Desc",
    offset_entity_id: str | None = None,
) -> str:
    base = _COMMENT_REPLIES_ENDPOINT.format(post_id=post_id, comment_id=comment_id)
    params = [
        f"take={min(max(take, 1), 100)}",
        f"order={'Asc' if order == 'Asc' else 'Desc'}",
    ]
    if offset_entity_id:
        params.append(f"offsetEntityId={offset_entity_id}")
    return f"{base}?{'&'.join(params)}"


def _fetch_comment_replies(
    session_factory,
    post_id: str,
    comment_id: str,
    take: int = 20,
    order: str = "Desc",
) -> list:
    replies = []
    offset_entity_id = None
    last_status = None
    last_body_preview = ""

    for attempt in range(_MAX_RETRIES):
        session = session_factory()
        current_url = _build_replies_url(post_id, comment_id, take=take, order=order, offset_entity_id=offset_entity_id)
        should_retry = False

        while current_url:
            try:
                resp = session.get(current_url, timeout=30)
            except requests.RequestException as exc:
                log_warning(
                    "Replies API error for post %s comment %s on attempt %d/%d: %s"
                    % (post_id, comment_id, attempt + 1, _MAX_RETRIES, exc)
                )
                should_retry = True
                break

            last_status = resp.status_code
            try:
                last_body_preview = resp.text[:200]
            except Exception:
                last_body_preview = ""

            if resp.status_code == 429 or resp.status_code >= 500:
                log_warning(
                    "Replies API HTTP %d for post %s comment %s on attempt %d/%d body=%s"
                    % (
                        resp.status_code,
                        post_id,
                        comment_id,
                        attempt + 1,
                        _MAX_RETRIES,
                        last_body_preview,
                    )
                )
                if attempt == _MAX_RETRIES - 1:
                    resp.raise_for_status()
                should_retry = True
                break

            if resp.status_code == 401:
                log_warning(
                    "Replies API HTTP 401 for post %s comment %s on attempt %d/%d; rotating session"
                    % (post_id, comment_id, attempt + 1, _MAX_RETRIES)
                )
                should_retry = True
                break

            resp.raise_for_status()
            data = resp.json()

            items = data.get("items") or data.get("comments") or []
            for item in items:
                entity = item.get("entity") or item if isinstance(item, dict) else item
                reply_id = None
                if isinstance(entity, dict):
                    reply_id = (
                        entity.get("id")
                        or entity.get("replyId")
                        or item.get("id")
                        or item.get("replyId")
                    )
                if reply_id:
                    replies.append(
                        {
                            "reply_id": str(reply_id),
                            "comment_id": comment_id,
                            "post_id": post_id,
                            "raw": item,
                        }
                    )

            paging = data.get("paging") or {}
            offset_entity_id = paging.get("offsetEntityId") or paging.get("next")
            if offset_entity_id:
                current_url = _build_replies_url(post_id, comment_id, take=take, order=order, offset_entity_id=offset_entity_id)
                time.sleep(_RATE_LIMIT_DELAY_SECONDS)
            else:
                current_url = None

        if not should_retry:
            return replies

        if attempt == _MAX_RETRIES - 1:
            break
        time.sleep(_BASE_DELAY_SECONDS * (1.1 ** attempt) + random.uniform(0, 1.0))

    raise RuntimeError(
        f"GET {_COMMENT_REPLIES_ENDPOINT.format(post_id=post_id, comment_id=comment_id)} failed after {_MAX_RETRIES} attempts for post {post_id} comment {comment_id}: "
        f"last_status={last_status}, body={last_body_preview!r}"
    )


def _prepare_comment_documents(comments: list) -> list:
    """Build normalized comment documents with key extracted fields.

    Args:
        comments: List of comment dicts with comment_id, post_id, and raw item.

    Returns:
        List of comment documents ready for MongoDB upsert.
    """
    documents = []
    for comment in comments:
        raw = comment.get("raw") or {}
        entity = raw.get("entity") or {}
        message = entity.get("message") or {}
        owner = entity.get("owner") or {}
        avatar = owner.get("avatar") or {}
        avatar_medium = avatar.get("medium")
        emotions_data = raw.get("emotionsData") or {}
        like_data = emotions_data.get("like") or {}
        like_paging = like_data.get("paging") or {}
        likes = int((like_paging.get("totalCount") or 0))
        replies_count = int(raw.get("repliesCount") or 0)
        created_raw = entity.get("created")
        created_at = None
        if created_raw:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    created_at = datetime.strptime(str(created_raw), fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

        documents.append(
            {
                "comment_id": comment.get("comment_id"),
                "post_id": comment.get("post_id"),
                "created": created_at,
                "text": message.get("text"),
                "language_code": message.get("languageCode"),
                "username": owner.get("username"),
                "owner_id": owner.get("id"),
                "avatar_medium": avatar_medium,
                "is_spam": entity.get("isSpam"),
                "edit_status": entity.get("editStatus"),
                "replies_count": replies_count,
                "likes": likes,
                "raw": raw,
            }
        )
    return documents


def _prepare_reply_documents(replies: list) -> list:
    """Build normalized reply documents with key extracted fields.

    Args:
        replies: List of reply dicts with reply_id, comment_id, post_id, and raw item.

    Returns:
        List of reply documents ready for MongoDB upsert.
    """
    documents = []
    for reply in replies:
        raw = reply.get("raw") or {}
        entity = raw.get("entity") or {}
        message = entity.get("message") or {}
        owner = entity.get("owner") or {}
        avatar = owner.get("avatar") or {}
        avatar_medium = avatar.get("medium")
        emotions_data = raw.get("emotionsData") or {}
        like_data = emotions_data.get("like") or {}
        like_paging = like_data.get("paging") or {}
        likes = int((like_paging.get("totalCount") or 0))
        replies_count = int(raw.get("repliesCount") or 0)
        created_raw = entity.get("created")
        created_at = None
        if created_raw:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    created_at = datetime.strptime(str(created_raw), fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

        documents.append(
            {
                "reply_id": reply.get("reply_id"),
                "comment_id": reply.get("comment_id"),
                "post_id": reply.get("post_id"),
                "created": created_at,
                "text": message.get("text"),
                "language_code": message.get("languageCode"),
                "username": owner.get("username"),
                "owner_id": owner.get("id"),
                "avatar_medium": avatar_medium,
                "is_spam": entity.get("isSpam"),
                "edit_status": entity.get("editStatus"),
                "replies_count": replies_count,
                "likes": likes,
                "raw": raw,
            }
        )
    return documents


def _fetch_user_feed(session_factory, user_id: str) -> list:
    """Fetch all posts for a user within the lookback window.

    Paginates using ``paging.next`` until posts are older than the lookback
    window or no more pages are available.

    Args:
        session_factory: Callable that returns a fresh authenticated
            ``requests.Session`` for eToro public API.
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
        session = session_factory()
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
            log_info("feed_get_posts_from_pi: got %d discussions for user %s" % (len(discussions), user_id))
            for discussion in discussions:
                metrics = _extract_post_metrics(discussion)
                if metrics is None:
                    continue
                if metrics["created_at"] < cutoff:
                    return posts
                if metrics["comments"] == 0:
                    continue
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


def _write_to_feed(posts: list, comments: list, replies: list) -> int:
    """Upsert post documents and their comments/replies into MongoDB.

    Posts are keyed by ``post_id`` in ``etoro_posts``.
    Comments are keyed by ``comment_id`` in ``etoro_comments``.
    Replies are keyed by ``reply_id`` in ``etoro_replies``.

    Args:
        posts: Post documents to store.
        comments: Comment documents to store.
        replies: Reply documents to store.

    Returns:
        Total number of documents successfully upserted.

    Raises:
        PyMongoError: If all MongoDB write attempts fail.
    """
    uri = os.getenv("MONGODB_URI_FEED", "")
    db_name = os.getenv("MONGODB_DATABASE_FEED", "alphasentra-feed")
    client = MongoClient(uri, serverSelectionTimeoutMS=30000)
    try:
        db = client[db_name]
        posts_collection = db["etoro_posts"]
        comments_collection = db["etoro_comments"]
        replies_collection = db["etoro_replies"]

        post_documents = _prepare_documents(posts)
        comment_documents = _prepare_comment_documents(comments)
        reply_documents = _prepare_reply_documents(replies)

        post_ops = [
            UpdateOne({"post_id": doc["post_id"]}, {"$set": doc}, upsert=True)
            for doc in post_documents
        ]
        comment_ops = [
            UpdateOne({"comment_id": doc["comment_id"]}, {"$set": doc}, upsert=True)
            for doc in comment_documents
        ]
        reply_ops = [
            UpdateOne({"reply_id": doc["reply_id"]}, {"$set": doc}, upsert=True)
            for doc in reply_documents
        ]

        if not post_ops and not comment_ops and not reply_ops:
            log_warning("No post, comment, or reply documents to store.")
            return 0

        last_exception = None
        for attempt in range(_MAX_RETRIES):
            try:
                if post_ops:
                    posts_collection.bulk_write(post_ops, ordered=False)
                if comment_ops:
                    comments_collection.bulk_write(comment_ops, ordered=False)
                if reply_ops:
                    replies_collection.bulk_write(reply_ops, ordered=False)
                return len(post_ops) + len(comment_ops) + len(reply_ops)
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

    session_factory = lambda: public_api_session(api_key, get_random_private_key(), timeout=30)

    seen_ids = set()
    pending_posts = []
    pending_comments = []
    pending_replies = []
    total_upserted = 0

    for idx, user_id in enumerate(user_ids, start=1):
        log_info(f"Fetching feed for user {user_id} ({idx}/{len(user_ids)})...")
        try:
            posts = _fetch_user_feed(session_factory, user_id)
            for post in posts:
                post_id = post.get("post_id")
                if not post_id:
                    continue
                if post_id not in seen_ids:
                    seen_ids.add(post_id)
                    pending_posts.append(post)
                else:
                    existing = next((p for p in pending_posts if p.get("post_id") == post_id), None)
                    if existing is not None and existing.get("created_at") is None and post.get("created_at") is not None:
                        existing.update(post)
                try:
                    comments = _fetch_post_comments(session_factory, post_id)
                    pending_comments.extend(comments)
                    if comments:
                        log_info(f"Collected {len(comments)} comments for post {post_id}.")
                    for comment in comments:
                        comment_id = comment.get("comment_id")
                        if not comment_id:
                            continue
                        try:
                            replies = _fetch_comment_replies(session_factory, post_id, comment_id)
                            pending_replies.extend(replies)
                            if replies:
                                log_info(f"Collected {len(replies)} replies for comment {comment_id}.")
                        except Exception as exc:
                            log_warning(f"Failed to fetch replies for comment {comment_id}: {exc}")
                except Exception as exc:
                    log_warning(f"Failed to fetch comments for post {post_id}: {exc}")
            log_info(f"Collected {len(posts)} posts for user {user_id}.")
        except Exception as exc:
            log_warning(f"Failed to fetch feed for user {user_id}: {exc}")
            continue

        if idx % _BATCH_WRITE_USERS == 0 and pending_posts:
            documents = _prepare_documents(pending_posts)
            if documents:
                upserted = _write_to_feed(documents, pending_comments, pending_replies)
                total_upserted += upserted
                log_info(
                    f"Upserted {upserted} documents into feed.etoro_posts/etoro_comments/etoro_replies "
                    f"(batch at user {idx})."
                )

            pending_posts.clear()
            pending_comments.clear()
            pending_replies.clear()

        if idx < len(user_ids):
            time.sleep(_RATE_LIMIT_DELAY_SECONDS)

    if pending_posts:
        documents = _prepare_documents(pending_posts)
        if documents:
            upserted = _write_to_feed(documents, pending_comments, pending_replies)
            total_upserted += upserted
            log_info("Upserted %d documents into feed.etoro_posts/etoro_comments/etoro_replies (final batch)." % upserted)

    if total_upserted > 0:
        log_info(f"Total upserted {total_upserted} documents across all batches.")
    else:
        log_warning("No posts collected or all posts were duplicates.")


if __name__ == "__main__":
    main()
