"""
eToro Feed page - inbox-style list with reading panel.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=False)

from Functions.themes import (
    _TEXT_PRIMARY,
    _TEXT_HEADING,
    _BRAND_PRIMARY,
    _BORDER_DEFAULT,
    _BG_SUBTLE,
    _NEUTRAL_0,
    _BG_DEFAULT,
    _TEXT_MUTED,
    _GRID_LINE,
    _SEMANTIC_POSITIVE,
    _SEMANTIC_NEUTRAL,
    _SEMANTIC_WARNING,
    _SEMANTIC_NEGATIVE,
    _HOVER_SURFACE,
    _SEMANTIC_NEGATIVE_STRONG,
    font as _font_module,
)
from Functions.config import REPORT_LOGO_SRC

FONT_FAMILY = _font_module.FONT_PRIMARY

_FEED_URI_ENV = "MONGODB_URI_FEED"
_FEED_DB_ENV = "MONGODB_DATABASE_FEED"
_DEFAULT_FEED_DB = "alphasentra-feed"
_FEED_POSTS_PER_PAGE = 50


def _get_feed_client() -> MongoClient:
    uri = os.getenv(_FEED_URI_ENV, "")
    if not uri:
        raise EnvironmentError(f"{_FEED_URI_ENV} environment variable is required")
    client = MongoClient(uri, serverSelectionTimeoutMS=30000)
    client.admin.command("ping")
    return client


def _format_created(created: Any) -> str:
    if isinstance(created, datetime):
        return created.strftime("%Y-%m-%d %H:%M UTC")
    text = str(created)
    if text.endswith("Z"):
        text = text[:-1]
    try:
        dt = datetime.fromisoformat(text)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return text


def _format_relative_time(created: Any) -> str:
    if isinstance(created, datetime):
        dt = created
    else:
        text = str(created or "")
        if text.endswith("Z"):
            text = text[:-1]
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return _format_created(created)

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    diff = now - dt
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "just now"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"

    days = hours // 24
    if days < 7:
        return f"{days}d"

    weeks = days // 7
    if weeks < 4:
        return f"{weeks}w"

    return _format_created(created)


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _truncate(text: str, length: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


_VIDEO_EXT_RE = re.compile(r"\.(mp4|webm|mov|m4v)(\?.*)?$", re.IGNORECASE)


def _post_has_video(attachments: list) -> bool:
    for att in attachments:
        atype = (att.get("type") or att.get("mediaType") or "").lower() if isinstance(att, dict) else ""
        if atype == "video":
            return True
        url = ""
        if isinstance(att, dict):
            url = att.get("url") or att.get("src") or att.get("href") or att.get("link") or ""
        if url and _VIDEO_EXT_RE.search(str(url)):
            return True
    return False



def _transform_post(p: Dict[str, Any]) -> Dict[str, Any]:
    created = p.get("created")
    if isinstance(created, datetime):
        dt = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        ts = dt.timestamp()
    else:
        text = str(created or "")
        if text.endswith("Z"):
            text = text[:-1]
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts = dt.timestamp()
        except Exception:
            ts = 0
    return {
        "id": str(p.get("post_id") or ""),
        "owner": str(p.get("owner_username") or "Unknown"),
        "created_raw": _format_relative_time(created),
        "created_ts": ts,
        "preview": _truncate(str(p.get("message_text") or ""), 110),
        "message": str(p.get("message_text") or ""),
        "likes": _safe_int(p.get("likes")),
        "comments": _safe_int(p.get("comments")),
        "post_url": str(p.get("post_url") or "#"),
        "avatar": str(p.get("avatar_medium") or ""),
        "badges": [str(b) for b in (p.get("badges") or []) if b],
        "attachments": p.get("attachments") or [],
        "has_video": _post_has_video(p.get("attachments") or []),
        "sentiment": {
            "label": str((p.get("sentiment") or {}).get("label") or ""),
            "score": float((p.get("sentiment") or {}).get("score") or 0),
        },
    }


def fetch_feed_posts(page: int = 1, page_size: int = _FEED_POSTS_PER_PAGE) -> tuple[List[Dict[str, Any]], str]:
    client = None
    error_message = ""
    try:
        client = _get_feed_client()
        db_name = os.getenv(_FEED_DB_ENV, _DEFAULT_FEED_DB)
        db = client[db_name]
        coll = db["etoro_posts"]

        total_count = coll.count_documents({})

        skip = (page - 1) * page_size
        cursor = (
            coll.find(
                {},
                {
                    "post_id": 1,
                    "post_url": 1,
                    "badges": 1,
                    "created": 1,
                    "owner_username": 1,
                    "message_text": 1,
                    "likes": 1,
                    "comments": 1,
                    "avatar_medium": 1,
                    "attachments": 1,
                    "sentiment": 1,
                },
            )
            .sort("created", -1)
            .skip(skip)
            .limit(page_size)
        )
        raw_posts: List[Dict[str, Any]] = list(cursor)

        if not raw_posts and total_count > 0:
            error_message = f"Query returned 0 posts but collection has {total_count} posts. Check skip/limit parameters."
        elif not raw_posts and total_count == 0:
            error_message = "Collection is empty. No posts found in database."

        posts = [_transform_post(p) for p in raw_posts]
        return posts, error_message
    except PyMongoError as exc:
        error_message = f"Feed database error: {exc}"
        return [], error_message
    except EnvironmentError as exc:
        error_message = f"Feed configuration error: {exc}"
        return [], error_message
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def fetch_feed_comments(post_id: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    client = None
    try:
        client = _get_feed_client()
        db_name = os.getenv(_FEED_DB_ENV, _DEFAULT_FEED_DB)
        db = client[db_name]

        comments_cursor = db["etoro_comments"].find(
            {"post_id": post_id},
            {
                "comment_id": 1,
                "post_id": 1,
                "created": 1,
                "text": 1,
                "username": 1,
                "owner_id": 1,
                "likes": 1,
                "replies_count": 1,
                "avatar_medium": 1,
            },
        ).sort("created", 1)
        comments = [
            {
                "comment_id": str(c.get("comment_id") or ""),
                "created": c.get("created"),
                "text": str(c.get("text") or ""),
                "username": str(c.get("username") or "Unknown"),
                "owner_id": str(c.get("owner_id") or ""),
                "likes": _safe_int(c.get("likes")),
                "replies_count": _safe_int(c.get("replies_count")),
                "avatar_medium": str(c.get("avatar_medium") or ""),
            }
            for c in comments_cursor
        ]

        replies_cursor = db["etoro_replies"].find(
            {"post_id": post_id},
            {
                "reply_id": 1,
                "comment_id": 1,
                "post_id": 1,
                "created": 1,
                "text": 1,
                "username": 1,
                "owner_id": 1,
                "likes": 1,
                "replies_count": 1,
                "avatar_medium": 1,
            },
        ).sort("created", 1)
        replies = [
            {
                "reply_id": str(r.get("reply_id") or ""),
                "comment_id": str(r.get("comment_id") or ""),
                "created": r.get("created"),
                "text": str(r.get("text") or ""),
                "username": str(r.get("username") or "Unknown"),
                "owner_id": str(r.get("owner_id") or ""),
                "likes": _safe_int(r.get("likes")),
                "replies_count": _safe_int(r.get("replies_count")),
                "avatar_medium": str(r.get("avatar_medium") or ""),
            }
            for r in replies_cursor
        ]

        return comments, replies
    except PyMongoError:
        return [], []
    except EnvironmentError:
        return [], []
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass


def get_feed_posts_json(page: int = 1, page_size: int = _FEED_POSTS_PER_PAGE) -> str:
    posts, error_message = fetch_feed_posts(page, page_size)
    payload: Dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "posts": posts,
        "error": error_message or None,
    }
    return json.dumps(payload, ensure_ascii=False)


def get_feed_comments_json(post_id: str) -> str:
    comments, replies = fetch_feed_comments(post_id)
    payload: Dict[str, Any] = {
        "post_id": post_id,
        "comments": comments,
        "replies": replies,
    }
    return json.dumps(payload, ensure_ascii=False)


def get_feed_html(page: int = 1, page_size: int = _FEED_POSTS_PER_PAGE, redirect_url: str = "") -> str:
    posts, error_message = fetch_feed_posts(page, page_size)
    posts_json = json.dumps(posts, ensure_ascii=False)

    _error_list_html = ""
    if error_message:
        _error_list_html = f"""
        <div class="feed-list-error">
            <div class="feed-list-error-title">Unable to load feed</div>
            <div>{_escape_html(error_message)}</div>
        </div>
        """

    _redirect_script = ""
    if redirect_url:
        _redirect_script = f"""
        setTimeout(function() {{
            window.top.location.href = {json.dumps(redirect_url)};
        }}, 10000);
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Feed</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {{
            --brand-primary: {_BRAND_PRIMARY};
            --color-accent: {_BRAND_PRIMARY};
            --neutral-0: {_NEUTRAL_0};
            --text-primary: {_TEXT_PRIMARY};
            --text-heading: {_TEXT_HEADING};
            --text-muted: {_TEXT_MUTED};
            --border-default: {_BORDER_DEFAULT};
            --bg-subtle: {_BG_SUBTLE};
            --bg-default: {_BG_DEFAULT};
            --hover-surface: {_HOVER_SURFACE};
            --semantic-positive: {_SEMANTIC_POSITIVE};
            --semantic-warning: {_SEMANTIC_WARNING};
            --semantic-neutral: {_SEMANTIC_NEUTRAL};
            --semantic-negative: {_SEMANTIC_NEGATIVE};
            --semantic-negative-strong: {_SEMANTIC_NEGATIVE_STRONG};
            --grid-line: {_GRID_LINE};
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: {FONT_FAMILY};
            background: var(--bg-default);
            color: var(--text-primary);
            height: 100vh;
            margin: 20px auto;
            padding: 0;
            max-width: 1380px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}

        .feed-toolbar {{
            display: flex;
            align-items: center;
            padding: 12px 20px;
            border-bottom: 1px solid var(--border-default);
            background: var(--bg-default);
            flex-shrink: 0;
        }}

        .feed-header-link {{
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            color: inherit;
            cursor: pointer;
        }}

        .feed-header-logo {{
            height: 40px;
            flex-shrink: 0;
        }}

        .feed-header-title {{
            margin: 0;
            flex-shrink: 0;
            display: flex;
            align-items: center;
            font-family: {FONT_FAMILY};
            font-size: 1em;
            font-weight: bold;
            color: var(--text-heading);
            border-bottom: 2px solid var(--color-accent);
            padding-bottom: 4px;
        }}

        .feed-header-caret {{
            display: inline-block;
            width: 10px;
            height: 1em;
            background-color: {_BRAND_PRIMARY};
            margin-left: 6px;
            vertical-align: text-bottom;
            animation: blink-caret 1s step-end infinite;
        }}

        .feed-header-caret.hidden {{
            opacity: 0;
            animation: none;
        }}

        @keyframes blink-caret {{
            from, to {{ opacity: 1; }}
            50% {{ opacity: 0; }}
        }}

        .feed-layout {{
            display: grid;
            grid-template-columns: 1fr;
            flex: 1;
            min-height: 0;
            padding-bottom: 50px;
        }}

        .feed-layout.has-selection {{
            grid-template-columns: 420px 1fr;
        }}

        .feed-layout.has-selection .feed-list-ticker-pill,
        .feed-layout.has-selection .feed-list-ticker-more {{
            display: none;
        }}

        .feed-list-panel {{
            overflow-y: auto;
            min-height: 0;
            background: var(--bg-default);
        }}

        .feed-list-item {{
            display: flex;
            gap: 12px;
            padding: 14px 16px;
            border-bottom: 1px solid var(--border-default);
            cursor: pointer;
            transition: background-color 0.12s ease;
        }}

        .feed-list-item:hover {{
            background: var(--bg-subtle);
        }}

        .feed-list-item.active {{
            background: var(--hover-surface);
            border-left: 3px solid var(--brand-primary);
            padding-left: 13px;
        }}

        .feed-list-item.fresh {{
            animation: freshBlink 1s ease-in-out 10;
            transition: none;
        }}

        @keyframes freshBlink {{
            0%, 100% {{ background-color: transparent; }}
            50% {{ background-color: rgba(0, 128, 255, 0.35); }}
        }}

        .feed-list-avatar {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            overflow: hidden;
            flex-shrink: 0;
            background: var(--semantic-neutral);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-top: 2px;
        }}

        .feed-list-avatar img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }}

        .feed-list-avatar-placeholder {{
            color: var(--neutral-0);
            font-weight: bold;
            font-size: 14px;
        }}

        .feed-list-content {{
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .feed-list-row-top {{
            display: flex;
            align-items: baseline;
            gap: 8px;
        }}

        .feed-list-owner {{
            font-weight: bold;
            color: var(--text-heading);
            font-size: 13px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex-shrink: 1;
            min-width: 0;
        }}

        .feed-list-date {{
            color: var(--text-muted);
            font-size: 11px;
            white-space: nowrap;
            margin-left: auto;
        }}

        .feed-list-video-pill {{
            display: inline-flex;
            align-items: center;
            gap: 3px;
            padding: 1px 8px;
            border-radius: 999px;
            background: rgba(253, 255, 103, 0.2);
            border: 1px solid rgba(253, 255, 103, 0.7);
            color: #fdff67;
            font-size: 10px;
            font-weight: 600;
            white-space: nowrap;
            flex-shrink: 0;
        }}

        .feed-list-stat-pill {{
            display: inline-flex;
            align-items: center;
            gap: 3px;
            padding: 1px 8px;
            border-radius: 999px;
            background: var(--bg-subtle);
            border: 1px solid var(--border-default);
            color: var(--text-muted);
            font-size: 10px;
            font-weight: 600;
            white-space: nowrap;
            flex-shrink: 0;
        }}

        .feed-list-stat-pill.sentiment-bullish {{
            color: var(--semantic-positive);
            border-color: var(--semantic-positive);
        }}

        .feed-list-stat-pill.sentiment-bearish {{
            color: var(--semantic-negative);
            border-color: var(--semantic-negative);
        }}

        .feed-list-stat-pill.sentiment-neutral {{
            color: var(--semantic-neutral);
            border-color: var(--semantic-neutral);
        }}

        .feed-list-preview {{
            color: var(--text-muted);
            font-size: 12px;
            line-height: 1.4;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            flex: 1 1 auto;
            min-width: 0;
        }}

        .feed-list-preview-row {{
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }}

        .feed-list-ticker-pill {{
            display: inline-flex;
            align-items: center;
            padding: 1px 6px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--color-accent);
            color: var(--color-accent);
            font-size: 10px;
            font-weight: 600;
            white-space: nowrap;
        }}

        .feed-list-ticker-more {{
            display: inline-flex;
            align-items: center;
            padding: 1px 6px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--color-accent);
            color: var(--color-accent);
            font-size: 10px;
            font-weight: 600;
            white-space: nowrap;
        }}

        .feed-reading-panel {{
            display: flex;
            flex-direction: column;
            overflow: hidden;
            padding: 0;
            display: none;
            position: relative;
            min-height: 0;
        }}

        .feed-layout.has-selection .feed-reading-panel {{
            display: flex;
        }}

        .feed-reading-scroll {{
            flex: 1 1 auto;
            overflow-y: auto;
            min-height: 0;
        }}

        .feed-reading-scroll-inner {{
            padding: 24px 28px 0 28px;
        }}

        .feed-reading-close {{
            position: absolute;
            top: 12px;
            right: 12px;
        }}

        .feed-reading-close-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-family: {FONT_FAMILY};
            font-size: 20px;
            line-height: 1;
            padding: 4px 8px;
            cursor: pointer;
            transition: color 0.15s ease;
            border-radius: 4px;
        }}

        .feed-reading-close-btn:hover {{
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.06);
        }}

        .feed-reading-empty {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            gap: 12px;
            padding: 40px;
            text-align: center;
        }}

        .feed-reading-empty-icon {{
            font-size: 40px;
            opacity: 0.6;
        }}

        .feed-reading-empty-text {{
            font-size: 14px;
        }}

        .feed-detail-header {{
            display: flex;
            align-items: flex-start;
            gap: 14px;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-default);
        }}

        .feed-detail-avatar {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            overflow: hidden;
            flex-shrink: 0;
            background: var(--semantic-neutral);
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .feed-detail-avatar-link {{
            display: block;
            text-decoration: none;
            flex-shrink: 0;
            transition: opacity 0.15s ease;
        }}

        .feed-detail-avatar-link:hover {{
            opacity: 0.85;
        }}

        .feed-detail-avatar-img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }}

        .feed-detail-avatar-placeholder {{
            color: var(--neutral-0);
            font-weight: bold;
            font-size: 18px;
        }}

        .feed-detail-meta {{
            flex: 1;
            min-width: 0;
        }}

        .feed-detail-owner {{
            font-weight: bold;
            color: var(--text-heading);
            font-size: 16px;
            margin-bottom: 2px;
        }}

        .feed-detail-owner-link {{
            font-weight: bold;
            color: var(--text-heading);
            font-size: 16px;
            text-decoration: none;
            margin-bottom: 2px;
            display: inline-block;
            transition: color 0.15s ease;
        }}

        .feed-detail-owner-link:hover {{
            color: var(--brand-primary);
            text-decoration: underline;
        }}

        .feed-detail-date {{
            color: var(--text-muted);
            font-size: 12px;
        }}

        .feed-detail-body {{
            color: var(--text-primary);
            font-size: 14px;
            line-height: 1.7;
            margin-bottom: 14px;
            white-space: pre-wrap;
            word-break: break-word;
        }}

        .feed-badges {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 14px;
        }}

        .feed-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 4px;
            background: rgba(148, 163, 184, 0.12);
            border: 1px solid var(--border-default);
            color: var(--text-primary);
            font-size: 12px;
        }}

        .feed-detail-footer {{
            display: flex;
            gap: 16px;
            padding-top: 12px;
            border-top: 1px solid var(--border-default);
        }}

        .feed-detail-stat {{
            color: var(--text-muted);
            font-size: 13px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}

        .feed-detail-stat-icon {{
            color: var(--semantic-negative-strong);
            font-size: 14px;
        }}

        .feed-comment-box {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 12px;
            border-radius: 0;
            border: 1px solid var(--color-accent);
            color: var(--text-muted);
            font-size: 13px;
            cursor: pointer;
            transition: border-color 0.15s ease, color 0.15s ease;
            flex-shrink: 0;
            margin-right: 35px;
            margin-left: 28px;
        }}

        .feed-comment-box:hover {{
            border-color: var(--color-accent);
            color: var(--text-primary);
        }}

        .feed-comment-caret {{
            display: inline-block;
            width: 8px;
            height: 1em;
            background-color: var(--brand-primary);
            flex-shrink: 0;
            animation: blink-caret 1s step-end infinite;
        }}

        .feed-comments-section {{
            margin-top: 20px;
            padding-top: 16px;
            border-top: 1px solid var(--border-default);
        }}

        .feed-comments-title {{
            font-weight: bold;
            color: var(--text-heading);
            font-size: 14px;
            margin-bottom: 12px;
        }}

        .feed-comments-loading {{
            color: var(--text-muted);
            font-size: 12px;
            padding: 8px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .feed-comments-spinner {{
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255, 255, 255, 0.2);
            border-top-color: var(--brand-primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            flex-shrink: 0;
        }}

        .feed-comment-item {{
            display: flex;
            gap: 10px;
            padding: 10px 0;
            border-bottom: 1px solid var(--border-default);
        }}

        .feed-comment-item:last-child {{
            border-bottom: none;
        }}

        .feed-comment-avatar {{
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: var(--semantic-neutral);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            color: var(--neutral-0);
            font-weight: bold;
            font-size: 13px;
        }}

        .feed-comment-body {{
            flex: 1;
            min-width: 0;
        }}

        .feed-comment-meta {{
            display: flex;
            align-items: baseline;
            gap: 8px;
            margin-bottom: 4px;
        }}

        .feed-comment-username {{
            font-weight: bold;
            color: var(--text-heading);
            font-size: 13px;
        }}

        .feed-comment-date {{
            color: var(--text-muted);
            font-size: 11px;
        }}

        .feed-comment-text {{
            color: var(--text-primary);
            font-size: 13px;
            line-height: 1.6;
            word-break: break-word;
            white-space: pre-wrap;
        }}

        .feed-comment-stats {{
            display: flex;
            gap: 12px;
            margin-top: 6px;
            color: var(--text-muted);
            font-size: 11px;
        }}

        .feed-reply-item {{
            display: flex;
            gap: 8px;
            padding: 10px 0 10px 42px;
            border-bottom: 1px solid var(--border-default);
        }}

        .feed-reply-item:last-child {{
            border-bottom: none;
        }}

        .feed-reply-avatar {{
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: var(--semantic-neutral);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            color: var(--neutral-0);
            font-weight: bold;
            font-size: 11px;
        }}

        .feed-reply-body {{
            flex: 1;
            min-width: 0;
        }}

        .feed-reply-meta {{
            display: flex;
            align-items: baseline;
            gap: 8px;
            margin-bottom: 4px;
        }}

        .feed-reply-username {{
            font-weight: bold;
            color: var(--text-heading);
            font-size: 12px;
        }}

        .feed-reply-date {{
            color: var(--text-muted);
            font-size: 10px;
        }}

        .feed-reply-text {{
            color: var(--text-primary);
            font-size: 12px;
            line-height: 1.6;
            word-break: break-word;
            white-space: pre-wrap;
        }}

        .feed-reply-stats {{
            display: flex;
            gap: 10px;
            margin-top: 6px;
            color: var(--text-muted);
            font-size: 10px;
        }}

        .feed-no-comments {{
            color: var(--text-muted);
            font-size: 12px;
            padding: 8px 0;
        }}

        .feed-media {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 16px;
        }}

        .feed-media img {{
            max-width: 100%;
            max-height: 400px;
            height: auto;
            object-fit: contain;
            display: block;
        }}

        .feed-media video,
        .feed-media iframe {{
            max-width: 100%;
            max-height: 400px;
            display: block;
        }}

        .feed-media video {{
            background: #000;
        }}

        .feed-media iframe {{
            width: 100%;
            aspect-ratio: 16 / 9;
            border: none;
        }}

        .youtube-container {{
            width: 100%;
            max-width: 100%;
            aspect-ratio: 16 / 9;
            max-height: 400px;
        }}

        .youtube-container iframe {{
            width: 100%;
            height: 100%;
            border: none;
            display: block;
        }}

        .feed-media-overlay .youtube-container {{
            max-width: 90vw;
            max-height: 90vh;
        }}

        .feed-list-empty {{
            text-align: center;
            padding: 40px 16px;
            color: var(--text-muted);
            font-size: 13px;
        }}

        .feed-list-loading {{
            text-align: center;
            padding: 16px;
            color: var(--text-muted);
            font-size: 12px;
        }}

        .feed-list-spinner {{
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255, 255, 255, 0.2);
            border-top-color: var(--brand-primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }}

        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}

        .feed-list-error {{
            text-align: center;
            padding: 40px 16px;
            color: var(--semantic-negative);
            font-size: 13px;
            background: rgba(248, 113, 113, 0.08);
            border: 1px dashed var(--semantic-negative);
            border-radius: 8px;
            margin: 16px;
        }}

        .feed-list-error-title {{
            font-weight: bold;
            margin-bottom: 8px;
        }}

        .feed-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.65);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        }}

        .feed-overlay.active {{
            display: flex;
        }}

        .feed-overlay-panel {{
            background: var(--bg-default);
            border-radius: 10px;
            padding: 20px;
            width: 320px;
            max-width: 90vw;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.25);
            position: relative;
        }}

        .feed-overlay-panel h2 {{
            margin: 0 0 14px 0;
            font-size: 1.1em;
            color: var(--text-heading);
            padding-right: 24px;
        }}

        .feed-overlay-close {{
            position: absolute;
            top: 12px;
            right: 12px;
            width: 24px;
            height: 24px;
            padding: 0;
            border: none;
            border-radius: 50%;
            background: transparent;
            color: var(--text-muted);
            font-family: {FONT_FAMILY};
            font-size: 18px;
            line-height: 1;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .feed-overlay-close:hover {{
            background: var(--bg-subtle);
            color: var(--text-primary);
        }}

        .feed-media-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.85);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 10001;
            padding: 24px;
        }}

        .feed-media-overlay.active {{
            display: flex;
        }}

        .feed-media-overlay-content {{
            position: relative;
            max-width: 90vw;
            max-height: 90vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .feed-media-overlay-content img,
        .feed-media-overlay-content video,
        .feed-media-overlay-content iframe {{
            max-width: 90vw;
            max-height: 90vh;
            object-fit: contain;
            display: block;
            border-radius: 0;
        }}

        .feed-media-overlay-close {{
            position: absolute;
            top: -36px;
            right: 0;
            width: 32px;
            height: 32px;
            border: none;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            font-family: {FONT_FAMILY};
            font-size: 20px;
            line-height: 1;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.15s ease;
        }}

        .feed-media-overlay-close:hover {{
            background: rgba(255, 255, 255, 0.25);
        }}

        .feed-option-group {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .feed-option-group + .feed-option-group {{
            margin-top: 18px;
        }}

        .feed-option-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            font-weight: bold;
        }}

        .feed-sort-options {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }}

        .feed-sort-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            padding: 10px;
            border-radius: 6px;
            border: none;
            background: var(--bg-subtle);
            color: var(--text-primary);
            font-family: {FONT_FAMILY};
            font-size: 0.9em;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.15s ease;
        }}

        .feed-sort-btn:hover {{
            background: var(--hover-surface);
        }}

        .feed-sort-btn.active {{
            background: var(--brand-primary);
            color: var(--neutral-0);
        }}

        .feed-sort-icon {{
            font-size: 14px;
        }}

        .feed-option-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }}

        .feed-option-header .feed-option-label {{
            margin: 0;
        }}

        .feed-ticker-reset {{
            display: none;
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid var(--border-default);
            background: transparent;
            color: var(--text-muted);
            font-family: {FONT_FAMILY};
            font-size: 11px;
            font-weight: bold;
            cursor: pointer;
            transition: color 0.15s ease, border-color 0.15s ease;
        }}

        .feed-ticker-reset:hover {{
            color: var(--text-primary);
            border-color: var(--brand-primary);
        }}

        .feed-ticker-pills {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}

        .feed-ticker-pill {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid var(--border-default);
            background: var(--bg-subtle);
            color: var(--text-primary);
            font-family: {FONT_FAMILY};
            font-size: 12px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.15s ease, border-color 0.15s ease;
        }}

        .feed-ticker-pill:hover {{
            background: var(--hover-surface);
            border-color: var(--brand-primary);
        }}

        .feed-ticker-pill.selected {{
            background: var(--brand-primary);
            color: var(--neutral-0);
            border-color: var(--brand-primary);
        }}

        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-subtle); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border-default); border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="feed-toolbar">
        <div class="feed-header-link" id="feedHeaderBtn" role="button" tabindex="0" aria-label="Open feed options">
            <img src="{REPORT_LOGO_SRC}" height="40" class="feed-header-logo" alt="Logo">
            <h1 class="feed-header-title">Trending Feed · Sort & Filter<span class="feed-header-caret"></span></h1>
        </div>
    </div>

    <div class="feed-overlay" id="feedOverlay" onclick="if(event.target===this){{closeOverlay();}}">
        <div class="feed-overlay-panel">
            <button class="feed-overlay-close" id="feedOverlayClose" type="button" aria-label="Close">&times;</button>
            <h2>Feed Options</h2>
            <div class="feed-option-group">
                <label class="feed-option-label">Sort by</label>
                <div class="feed-sort-options" id="feedSortOptions">
                    <button class="feed-sort-btn active" data-sort="recent" type="button">
                        <span class="feed-sort-icon">&#128336;</span> Most Recent
                    </button>
                    <button class="feed-sort-btn" data-sort="engaging" type="button">
                        <span class="feed-sort-icon">&#128293;</span> Most Engaging
                    </button>
                </div>
            </div>
            <div class="feed-option-group">
                <div class="feed-option-header">
                    <label class="feed-option-label">Filter by instruments</label>
                    <button class="feed-ticker-reset" id="feedTickerReset" type="button">Reset</button>
                </div>
                <div class="feed-ticker-pills" id="feedTickerPills"></div>
            </div>
        </div>
    </div>
    <div class="feed-layout">
        <div class="feed-list-panel" id="feedListPanel">
            {_error_list_html if error_message else '<div class="feed-list-empty" id="feedListEmpty">No posts available yet.</div>'}
            <div id="feedListItems"></div>
        </div>
        <div class="feed-reading-panel" id="feedReadingPanel">
            <div class="feed-reading-close">
                <button class="feed-reading-close-btn" id="feedReadingClose" type="button">×</button>
            </div>
            <div class="feed-reading-empty" id="feedReadingEmpty">
                <div class="feed-reading-empty-icon">&#9993;</div>
                <div class="feed-reading-empty-text">Select a post to read</div>
            </div>
            <div class="feed-reading-scroll" id="feedReadingScroll">
                <div class="feed-reading-scroll-inner" id="feedReadingScrollInner"></div>
            </div>
            <div class="feed-comment-box" id="feedCommentBox" style="display:none;">
                <span class="feed-comment-caret"></span>
                <span>Write a comment...</span>
            </div>
        </div>
    </div>
    <script>
        const posts = {posts_json};
        const listContainer = document.getElementById('feedListItems');
        const listEmpty = document.getElementById('feedListEmpty');
        const readingEmpty = document.getElementById('feedReadingEmpty');
        const readingScroll = document.getElementById('feedReadingScroll');
        const readingScrollInner = document.getElementById('feedReadingScrollInner');
        const commentBox = document.getElementById('feedCommentBox');
        const layout = document.querySelector('.feed-layout');
        const readingPanel = document.getElementById('feedReadingPanel');
        const readingClose = document.getElementById('feedReadingClose');
        const feedHeaderBtn = document.getElementById('feedHeaderBtn');
        const feedHeaderCaret = document.querySelector('.feed-header-caret');
        const feedOverlay = document.getElementById('feedOverlay');
        const feedOverlayClose = document.getElementById('feedOverlayClose');
        const feedSortOptions = document.getElementById('feedSortOptions');
        const feedTickerPills = document.getElementById('feedTickerPills');
        const feedTickerReset = document.getElementById('feedTickerReset');
        let selectedIndex = -1;
        let currentPage = 1;
        let hasMore = true;
        let loadingMore = false;
        let currentSort = 'recent';
        const selectedTickers = new Set();

        function openOverlay() {{
            feedOverlay.classList.add('active');
        }}

        function closeOverlay() {{
            feedOverlay.classList.remove('active');
        }}

        function openMediaOverlay(url, mediaType) {{
            const overlay = document.getElementById('feedMediaOverlay');
            const content = document.getElementById('feedMediaOverlayContent');
            if (!overlay || !content) return;

            const youtubeEmbed = getYoutubeEmbedUrl(url);
            const videoId = getYoutubeVideoId(url);
            if (youtubeEmbed) {{
                html = `<div class="youtube-container"><iframe src="${{_escape_js(youtubeEmbed)}}?si=${{_escape_js(videoId)}}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen style="cursor:pointer;"></iframe></div>`;
            }} else if (isYoutubeUrl(url)) {{
                const fallbackId = getYoutubeVideoId(url);
                if (fallbackId) {{
                    const embedUrl = `https://www.youtube.com/embed/${{_escape_js(fallbackId)}}`;
                    html = `<div class="youtube-container"><iframe src="${{embedUrl}}?si=${{_escape_js(fallbackId)}}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen style="cursor:pointer;"></iframe></div>`;
                }}
            }} else if (mediaType === 'video') {{
                html = `<video controls autoplay style="max-width:90vw;max-height:90vh;width:100%;height:100%;"><source src="${{_escape_js(url)}}"></video>`;
            }} else {{
                html = `<img src="${{_escape_js(url)}}" alt="" style="max-width:90vw;max-height:90vh;object-fit:contain;">`;
            }}

            content.innerHTML = `
                <button class="feed-media-overlay-close" id="feedMediaOverlayClose" type="button" aria-label="Close">&times;</button>
                ${{html}}
            `;

            overlay.classList.add('active');
            document.getElementById('feedMediaOverlayClose').addEventListener('click', closeMediaOverlay);
        }}

        function closeMediaOverlay() {{
            const overlay = document.getElementById('feedMediaOverlay');
            const content = document.getElementById('feedMediaOverlayContent');
            if (overlay) overlay.classList.remove('active');
            if (content) content.innerHTML = `
                <button class="feed-media-overlay-close" id="feedMediaOverlayClose" type="button" aria-label="Close">&times;</button>
            `;
        }}

        function getYoutubeEmbedUrl(url) {{
            if (!url) return null;
            const videoId = getYoutubeVideoId(url);
            if (videoId) {{
                return `https://www.youtube.com/embed/${{videoId}}`;
            }}
            return null;
        }}

        function getYoutubeVideoId(url) {{
            if (!url) return null;
            let id = null;
            if (url.indexOf('youtube.com/watch') !== -1) {{
                const start = url.indexOf('v=');
                if (start !== -1) {{
                    const raw = url.substring(start + 2);
                    const end = raw.indexOf('&');
                    id = end === -1 ? raw : raw.substring(0, end);
                }}
            }} else if (url.indexOf('youtu.be/') !== -1) {{
                const start = url.indexOf('youtu.be/') + 9;
                const raw = url.substring(start);
                const end = raw.indexOf('?');
                id = end === -1 ? raw : raw.substring(0, end);
            }} else if (url.indexOf('youtube.com/embed/') !== -1) {{
                const start = url.indexOf('youtube.com/embed/') + 17;
                const raw = url.substring(start);
                const end = raw.indexOf('?');
                id = end === -1 ? raw : raw.substring(0, end);
            }} else if (url.indexOf('youtube.com/shorts/') !== -1) {{
                const start = url.indexOf('youtube.com/shorts/') + 20;
                const raw = url.substring(start);
                const end = raw.indexOf('?');
                id = end === -1 ? raw : raw.substring(0, end);
            }}
            if (id) {{
                id = id.split('/')[0].split('?')[0];
            }}
            return id || null;
        }}

        function isYoutubeUrl(url) {{
            if (!url) return false;
            const result = url.indexOf('youtube.com') !== -1 || url.indexOf('youtu.be') !== -1;
            return result;
        }}

        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                const mediaOverlay = document.getElementById('feedMediaOverlay');
                if (mediaOverlay && mediaOverlay.classList.contains('active')) {{
                    closeMediaOverlay();
                    return;
                }}
                if (feedOverlay.classList.contains('active')) {{
                    closeOverlay();
                }}
            }}
        }});

        feedHeaderBtn.addEventListener('click', openOverlay);
        feedHeaderBtn.addEventListener('keydown', function(e) {{
            if (e.key === 'Enter' || e.key === ' ') {{
                e.preventDefault();
                openOverlay();
            }}
        }});
        feedOverlayClose.addEventListener('click', closeOverlay);

        function sortPosts(postsArray, sortMode) {{
            const arr = postsArray.slice();
            if (sortMode === 'engaging') {{
                arr.sort(function(a, b) {{
                    const scoreA = a.comments || 0;
                    const scoreB = b.comments || 0;
                    if (scoreB !== scoreA) return scoreB - scoreA;
                    return (b.created_ts || 0) - (a.created_ts || 0);
                }});
            }} else {{
                arr.sort(function(a, b) {{
                    return (b.created_ts || 0) - (a.created_ts || 0);
                }});
            }}
            return arr;
        }}

        function applySort(sortMode) {{
            currentSort = sortMode;
            closeOverlay();
            selectPostByIndex(-1);
            const listPanel = document.getElementById('feedListPanel');
            if (listPanel) listPanel.scrollTop = 0;
            const displayPosts = getDisplayPosts();
            renderSortedList(displayPosts);
        }}

        feedSortOptions.addEventListener('click', function(e) {{
            const btn = e.target.closest('.feed-sort-btn');
            if (!btn) return;
            const sortMode = btn.getAttribute('data-sort');
            if (!sortMode || sortMode === currentSort) return;

            feedSortOptions.querySelectorAll('.feed-sort-btn').forEach(function(b) {{
                b.classList.toggle('active', b === btn);
            }});
            applySort(sortMode);
        }});

        function extractUniqueTickers() {{
            const counts = {{}};
            posts.forEach(function(post) {{
                const seen = new Set();
                (post.badges || []).forEach(function(badge) {{
                    if (!badge) return;
                    if (seen.has(badge)) return;
                    seen.add(badge);
                    counts[badge] = (counts[badge] || 0) + 1;
                }});
            }});
            return Object.keys(counts)
                .sort(function(a, b) {{
                    if (counts[b] !== counts[a]) return counts[b] - counts[a];
                    return a.localeCompare(b);
                }})
                .slice(0, 20);
        }}

        function renderTickerPills() {{
            if (!feedTickerPills) return;
            const tickers = extractUniqueTickers();
            feedTickerPills.innerHTML = '';

            tickers.forEach(function(ticker) {{
                const pill = document.createElement('button');
                pill.className = 'feed-ticker-pill' + (selectedTickers.has(ticker) ? ' selected' : '');
                pill.type = 'button';
                pill.textContent = ticker;
                pill.addEventListener('click', function() {{
                    if (selectedTickers.has(ticker)) {{
                        selectedTickers.delete(ticker);
                    }} else {{
                        selectedTickers.add(ticker);
                    }}
                    renderTickerPills();
                    applyTickerFilter();
                }});
                feedTickerPills.appendChild(pill);
            }});

            updateClearButton();
        }}

        function getDisplayPosts() {{
            let filtered = posts;
            if (selectedTickers.size > 0) {{
                filtered = posts.filter(function(post) {{
                    return (post.badges || []).some(function(badge) {{
                        return selectedTickers.has(badge);
                    }});
                }});
            }}
            return sortPosts(filtered, currentSort);
        }}

        function applyTickerFilter() {{
            selectPostByIndex(-1);
            const displayPosts = getDisplayPosts();
            renderSortedList(displayPosts);
        }}

        function updateClearButton() {{
            if (!feedTickerReset) return;
            feedTickerReset.style.display = selectedTickers.size > 0 ? '' : 'none';
        }}

        function clearTickerFilter() {{
            selectedTickers.clear();
            renderTickerPills();
            applyTickerFilter();
        }}

        if (feedTickerReset) {{
            feedTickerReset.addEventListener('click', clearTickerFilter);
        }}

        function renderSortedList(sortedPosts) {{
            if (!sortedPosts.length) {{
                if (listEmpty) listEmpty.style.display = '';
                listContainer.innerHTML = '';
                return;
            }}
            if (listEmpty) listEmpty.style.display = 'none';

            const fragment = document.createDocumentFragment();
            sortedPosts.forEach(function(post) {{
                fragment.appendChild(createPostItem(post));
            }});
            listContainer.innerHTML = '';
            listContainer.appendChild(fragment);
        }}

        function openEtoroPost(url) {{
            window.open(url, '_blank', 'width=900,height=700');
        }}

        function createPostItem(post) {{
            const item = document.createElement('div');
            item.className = 'feed-list-item';
            item.setAttribute('data-post-id', post.id);

            const now = Date.now() / 1000;
            if (post.created_ts && (now - post.created_ts) < 7200) {{
                item.classList.add('fresh');
                item.style.boxShadow = 'inset 3px 0 0 #0080ff';
                setTimeout(function() {{
                    item.classList.remove('fresh');
                    item.style.boxShadow = '';
                }}, 5000);
            }}

            const avatarHtml = post.avatar
                ? `<img src="${{_escape_js(post.avatar)}}" alt="" loading="lazy">`
                : `<div class="feed-list-avatar-placeholder">${{_escape_js(post.owner)[0].toUpperCase()}}</div>`;

            item.innerHTML = `
                <div class="feed-list-avatar">${{avatarHtml}}</div>
                <div class="feed-list-content">
                    <div class="feed-list-row-top">
                        <span class="feed-list-owner">${{_escape_js(post.owner)}}</span>
                        ${{post.has_video ? '<span class="feed-list-video-pill">&#9654; Video</span>' : ''}}
                        <span class="feed-list-stat-pill">&#9829; ${{post.likes}}</span>
                        <span class="feed-list-stat-pill">&#9993; ${{post.comments}}</span>
                        ${{(post.sentiment && post.sentiment.label) ? '<span class="feed-list-stat-pill sentiment-' + _escape_js(post.sentiment.label) + '">' + _escape_js(post.sentiment.label) + '</span>' : ''}}
                        <span class="feed-list-date">${{_escape_js(post.created_raw)}}</span>
                    </div>
                    <div class="feed-list-preview-row">
                        <div class="feed-list-preview">${{_escape_js(post.preview)}}</div>
                        ${{(post.badges || []).slice(0, 5).map(function(b) {{ return '<span class="feed-list-ticker-pill">' + _escape_js(b) + '</span>'; }}).join('')}}
                        ${{(post.badges || []).length > 5 ? '<span class="feed-list-ticker-more">+' + ((post.badges || []).length - 5) + '</span>' : ''}}
                    </div>
                </div>
            `;

            item.addEventListener('click', () => selectPostByIndex(posts.indexOf(post)));
            return item;
        }}

        function renderList(reset) {{
            const displayPosts = getDisplayPosts();
            renderSortedList(displayPosts);
        }}

        function showLoading() {{
            if (!document.getElementById('feedListLoading')) {{
                const loader = document.createElement('div');
                loader.className = 'feed-list-loading';
                loader.id = 'feedListLoading';
                loader.innerHTML = '<span class="feed-list-spinner"></span> Loading...';
                listContainer.appendChild(loader);
            }}
        }}

        function hideLoading() {{
            const loader = document.getElementById('feedListLoading');
            if (loader) loader.remove();
        }}

        function loadMorePosts() {{
            if (loadingMore || !hasMore) return;
            loadingMore = true;
            showLoading();

            fetch('/feed/posts?page=' + (currentPage + 1))
                .then(function(response) {{ return response.json(); }})
                .then(function(data) {{
                    hideLoading();
                    loadingMore = false;

                    if (!data || !data.posts || !data.posts.length) {{
                        hasMore = false;
                        return;
                    }}

                    currentPage = data.page || currentPage;
                    hasMore = data.posts.length >= (data.page_size || 50);

                    data.posts.forEach(function(post) {{
                        posts.push(post);
                    }});

                    const displayPosts = getDisplayPosts();
                    renderSortedList(displayPosts);
                }})
                .catch(function() {{
                    hideLoading();
                    loadingMore = false;
                }});
        }}

        function onListScroll() {{
            const panel = document.getElementById('feedListPanel');
            if (!panel) return;
            const threshold = 200;
            if (panel.scrollHeight - panel.scrollTop - panel.clientHeight <= threshold) {{
                loadMorePosts();
            }}
        }}

        function selectPostByIndex(index) {{
            if (selectedIndex === index && index >= 0) return;
            selectedIndex = index;

            const selectedPostId = posts[index] ? posts[index].id : null;
            document.querySelectorAll('.feed-list-item').forEach((el) => {{
                el.classList.toggle('active', el.getAttribute('data-post-id') === selectedPostId);
            }});

            const post = posts[index];
            if (!post || index < 0) {{
                layout.classList.remove('has-selection');
                readingPanel.classList.remove('open');
                readingEmpty.style.display = 'none';
                readingScrollInner.innerHTML = '';
                commentBox.style.display = 'none';
                if (feedHeaderCaret) feedHeaderCaret.classList.remove('hidden');
                return;
            }}

            layout.classList.add('has-selection');
            readingEmpty.style.display = 'none';
            document.getElementById('feedReadingPanel').classList.add('open');
            if (feedHeaderCaret) feedHeaderCaret.classList.add('hidden');
            readingScroll.scrollTop = 0;
            const badgesHtml = post.badges.map(b => `<span class="feed-badge">${{_escape_js(b)}}</span>`).join('');
            const avatarHtml = post.avatar
                ? `<img class="feed-detail-avatar-img" src="${{_escape_js(post.avatar)}}" alt="" loading="lazy">`
                : `<div class="feed-detail-avatar-placeholder">${{_escape_js(post.owner)[0].toUpperCase()}}</div>`;

            function renderAttachments(attachments) {{
                if (!attachments || !attachments.length) return '';
                const mediaHtml = attachments.map(function(att, idx) {{
                    const type = (att.type || att.mediaType || '').toString().toLowerCase();
                    const url = att.url || att.src || att.href || att.link || '';
                    if (!url) return '';

                    const youtubeEmbed = getYoutubeEmbedUrl(url);
                    const videoId = getYoutubeVideoId(url);
                    const isYoutube = !!(youtubeEmbed || (isYoutubeUrl(url) && videoId));
                    if (isYoutube) {{
                        const embedUrl = youtubeEmbed || `https://www.youtube.com/embed/${{_escape_js(videoId)}}`;
                        return `<div class="youtube-container"><iframe src="${{_escape_js(embedUrl)}}?si=${{_escape_js(videoId)}}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen style="cursor:pointer;" onclick="openMediaOverlay('${{_escape_js(embedUrl)}}','video')"></iframe></div>`;
                    }}

                    const isImage = type === 'image' || /\\.(jpg|jpeg|png|gif|webp|svg)(\\?.*)?$/i.test(url);
                    const isVideoFile = type === 'video' || /\\.(mp4|webm|mov|m4v)(\\?.*)?$/i.test(url);
                    if (isImage) {{
                        return `<img src="${{_escape_js(url)}}" alt="" loading="lazy" style="cursor:pointer;" onclick="openMediaOverlay('${{_escape_js(url)}}','image')">`;
                    }}
                    if (isVideoFile) {{
                        return `<video controls preload="metadata" style="cursor:pointer;" onclick="openMediaOverlay('${{_escape_js(url)}}','video')"><source src="${{_escape_js(url)}}"></video>`;
                    }}
                    return '';
                }}).join('');
                if (!mediaHtml) return '';
                return `<div class="feed-media">${{mediaHtml}}</div>`;
            }}

            const attachmentsHtml = renderAttachments(post.attachments);

            readingScrollInner.innerHTML = `
                <div class="feed-detail-header">
                    <a class="feed-detail-avatar-link" href="javascript:void(0)" onclick="openEtoroPost('${{_escape_js(post.post_url)}}')">
                        ${{avatarHtml}}
                    </a>
                    <div class="feed-detail-meta">
                        <a class="feed-detail-owner-link" href="javascript:void(0)" onclick="openEtoroPost('${{_escape_js(post.post_url)}}')">${{_escape_js(post.owner)}}</a>
                        <div class="feed-detail-date">${{_escape_js(post.created_raw)}}</div>
                    </div>
                </div>
                ${{attachmentsHtml}}
                <div class="feed-detail-body">${{_escape_js(post.message)}}</div>
                ${{badgesHtml ? `<div class="feed-badges">${{badgesHtml}}</div>` : ''}}
                <div class="feed-detail-footer">
                    <span class="feed-detail-stat">
                        <span class="feed-detail-stat-icon">&#9829;</span> ${{post.likes}}
                    </span>
                    <span class="feed-detail-stat">
                        <span class="feed-detail-stat-icon">&#9993;</span> ${{post.comments}}
                    </span>
                </div>
                <div class="feed-comments-section" id="feedCommentsContainer">
                    <div class="feed-comments-title">Comments</div>
                    <div class="feed-comments-loading"><span class="feed-comments-spinner"></span>Loading comments...</div>
                </div>
            `;
            commentBox.style.display = '';
            commentBox.onclick = function() {{ openEtoroPost(post.post_url); }};

            fetch('/feed/comments?post_id=' + encodeURIComponent(post.id))
                .then(function(response) {{ return response.json(); }})
                .then(function(data) {{
                    renderCommentsAndReplies(data.comments || [], data.replies || []);
                }})
                .catch(function() {{
                    const container = document.getElementById('feedCommentsContainer');
                    if (container) {{
                        container.innerHTML = '<div class="feed-no-comments">Unable to load comments.</div>';
                    }}
                }});

            function renderCommentsAndReplies(comments, replies) {{
                const container = document.getElementById('feedCommentsContainer');
                if (!container) return;

                if (!comments.length && !replies.length) {{
                    container.innerHTML = '<div class="feed-no-comments">No comments yet.</div>';
                    return;
                }}

                const repliesByComment = {{}};
                replies.forEach(function(r) {{
                    const key = r.comment_id || r.reply_id;
                    if (!repliesByComment[key]) repliesByComment[key] = [];
                    repliesByComment[key].push(r);
                }});

                let html = '';
                comments.forEach(function(c) {{
                    const cReplies = repliesByComment[c.comment_id] || [];
                    const cAvatarHtml = c.avatar_medium
                        ? '<img src="' + _escape_js(c.avatar_medium) + '" alt="" loading="lazy" style="width:32px;height:32px;border-radius:50%;object-fit:cover;display:block;">'
                        : '<div class="feed-comment-avatar">' + _escape_js((c.username || 'U')[0].toUpperCase()) + '</div>';
                    html += '<div class="feed-comment-item">';
                    html += '    ' + cAvatarHtml;
                    html += '    <div class="feed-comment-body">';
                    html += '        <div class="feed-comment-meta">';
                    html += '            <span class="feed-comment-username">' + _escape_js(c.username) + '</span>';
                    html += '            <span class="feed-comment-date">' + _escape_js(c.created ? _formatDate(c.created) : '') + '</span>';
                    html += '        </div>';
                    html += '        <div class="feed-comment-text">' + _escape_js(c.text) + '</div>';
                    html += '        <div class="feed-comment-stats">';
                    html += '            <span>&#9829; ' + (c.likes || 0) + '</span>';
                    if (c.replies_count) {{
                        html += '            <span>&#9993; ' + c.replies_count + ' replies</span>';
                    }}
                    html += '        </div>';
                    html += '    </div>';
                    html += '</div>';

                    cReplies.forEach(function(r) {{
                        const rAvatarHtml = r.avatar_medium
                            ? '<img src="' + _escape_js(r.avatar_medium) + '" alt="" loading="lazy" style="width:26px;height:26px;border-radius:50%;object-fit:cover;display:block;">'
                            : '<div class="feed-reply-avatar">' + _escape_js((r.username || 'U')[0].toUpperCase()) + '</div>';
                        html += '<div class="feed-reply-item">';
                        html += '    ' + rAvatarHtml;
                        html += '    <div class="feed-reply-body">';
                        html += '        <div class="feed-reply-meta">';
                        html += '            <span class="feed-reply-username">' + _escape_js(r.username) + '</span>';
                        html += '            <span class="feed-reply-date">' + _escape_js(r.created ? _formatDate(r.created) : '') + '</span>';
                        html += '        </div>';
                        html += '        <div class="feed-reply-text">' + _escape_js(r.text) + '</div>';
                        html += '        <div class="feed-reply-stats">';
                        html += '            <span>&#9829; ' + (r.likes || 0) + '</span>';
                        if (r.replies_count) {{
                            html += '            <span>&#9993; ' + r.replies_count + ' replies</span>';
                        }}
                        html += '        </div>';
                        html += '    </div>';
                        html += '</div>';
                    }});
                }});

                container.innerHTML = html;
            }}
        }}

        readingClose.addEventListener('click', () => selectPostByIndex(-1));

        function _escape_js(text) {{
            if (text == null) return '';
            return String(text)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        function _formatDate(created) {{
            if (!created) return '';
            if (typeof created === 'string') {{
                let text = created;
                if (text.endsWith('Z')) text = text.slice(0, -1);
                const d = new Date(text);
                if (!isNaN(d.getTime())) {{
                    return d.toLocaleString('en-US', {{ year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }}) + ' UTC';
                }}
                return text;
            }}
            if (created instanceof Date) {{
                return created.toLocaleString('en-US', {{ year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }}) + ' UTC';
            }}
            return String(created);
        }}

        renderList(true);
        renderTickerPills();
        document.getElementById('feedListPanel').addEventListener('scroll', onListScroll);
        {_redirect_script}
    </script>
    <div class="feed-media-overlay" id="feedMediaOverlay" onclick="if(event.target===this){{closeMediaOverlay();}}">
        <div class="feed-media-overlay-content" id="feedMediaOverlayContent">
            <button class="feed-media-overlay-close" id="feedMediaOverlayClose" type="button" aria-label="Close">&times;</button>
        </div>
    </div>
</body>
</html>
"""
