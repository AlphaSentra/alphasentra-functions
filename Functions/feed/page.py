"""
eToro Feed page - inbox-style list with reading panel.
"""

import json
import os
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


def _post_preview(post: Dict[str, Any]) -> str:
    owner = str(post.get("owner_username") or "Unknown")
    created = _format_created(post.get("created"))
    message = str(post.get("message_text") or "")
    preview = _truncate(message, 110)
    return f"{owner} — {created}\n{preview}"


def get_feed_html(page: int = 1, page_size: int = _FEED_POSTS_PER_PAGE, redirect_url: str = "") -> str:
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
    except PyMongoError as exc:
        error_message = f"Feed database error: {exc}"
        raw_posts = []
    except EnvironmentError as exc:
        error_message = f"Feed configuration error: {exc}"
        raw_posts = []
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass

    posts: List[Dict[str, Any]] = []
    for p in raw_posts:
        created = p.get("created")
        if isinstance(created, datetime):
            ts = created.timestamp()
        else:
            text = str(created or "")
            if text.endswith("Z"):
                text = text[:-1]
            try:
                ts = datetime.fromisoformat(text).timestamp()
            except Exception:
                ts = 0
        posts.append({
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
        })

    posts_json = json.dumps(posts, ensure_ascii=False)
    total = len(posts)

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
            window.location.href = {json.dumps(redirect_url)};
        }}, 10000);
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>eToro Feed</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {{
            --brand-primary: {_BRAND_PRIMARY};
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
            justify-content: space-between;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-default);
            background: var(--bg-default);
            flex-shrink: 0;
        }}

        .feed-title {{
            color: var(--text-heading);
            font-size: 18px;
            font-weight: bold;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}

        .feed-count {{
            color: var(--text-muted);
            font-size: 12px;
        }}

        .feed-layout {{
            display: grid;
            grid-template-columns: 1fr;
            flex: 1;
            min-height: 0;
        }}

        .feed-layout.has-selection {{
            grid-template-columns: 420px 1fr;
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
            justify-content: space-between;
            gap: 8px;
        }}

        .feed-list-owner {{
            font-weight: bold;
            color: var(--text-heading);
            font-size: 13px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .feed-list-date {{
            color: var(--text-muted);
            font-size: 11px;
            white-space: nowrap;
        }}

        .feed-list-preview {{
            color: var(--text-muted);
            font-size: 12px;
            line-height: 1.4;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }}

        .feed-reading-panel {{
            overflow-y: auto;
            background: var(--bg-subtle);
            padding: 24px 28px;
            display: none;
            position: relative;
            min-height: 0;
        }}

        .feed-layout.has-selection .feed-reading-panel {{
            display: block;
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

        .feed-list-empty {{
            text-align: center;
            padding: 40px 16px;
            color: var(--text-muted);
            font-size: 13px;
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

        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-subtle); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border-default); border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="feed-toolbar">
        <div class="feed-title">eToro Feed</div>
        <div class="feed-count">{total} post{total != 1 and 's' or ''}</div>
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
            <div id="feedReadingContent"></div>
        </div>
    </div>
    <script>
        const posts = {posts_json};
        const listContainer = document.getElementById('feedListItems');
        const listEmpty = document.getElementById('feedListEmpty');
        const readingEmpty = document.getElementById('feedReadingEmpty');
        const readingContent = document.getElementById('feedReadingContent');
        const layout = document.querySelector('.feed-layout');
        const readingPanel = document.getElementById('feedReadingPanel');
        const readingClose = document.getElementById('feedReadingClose');
        let selectedIndex = -1;

        readingClose.addEventListener('click', () => selectPost(-1));

        function openEtoroPost(url) {{
            window.open(url, '_blank', 'width=900,height=700');
        }}

        function renderList() {{
            if (!posts.length) {{
                if (listEmpty) listEmpty.style.display = '';
                return;
            }}
            if (listEmpty) listEmpty.style.display = 'none';

            const fragment = document.createDocumentFragment();
            posts.forEach((post, index) => {{
                const item = document.createElement('div');
                item.className = 'feed-list-item';
                item.setAttribute('data-index', index);

                const avatarHtml = post.avatar
                    ? `<img src="${{_escape_js(post.avatar)}}" alt="" loading="lazy">`
                    : `<div class="feed-list-avatar-placeholder">${{_escape_js(post.owner)[0].toUpperCase()}}</div>`;

                item.innerHTML = `
                    <div class="feed-list-avatar">${{avatarHtml}}</div>
                    <div class="feed-list-content">
                        <div class="feed-list-row-top">
                            <span class="feed-list-owner">${{_escape_js(post.owner)}}</span>
                            <span class="feed-list-date">${{_escape_js(post.created_raw)}}</span>
                        </div>
                        <div class="feed-list-preview">${{_escape_js(post.preview)}}</div>
                    </div>
                `;

                item.addEventListener('click', () => selectPost(index));
                fragment.appendChild(item);
            }});

            listContainer.innerHTML = '';
            listContainer.appendChild(fragment);
        }}

        function selectPost(index) {{
            if (selectedIndex === index && index >= 0) return;
            selectedIndex = index;

            document.querySelectorAll('.feed-list-item').forEach((el, i) => {{
                el.classList.toggle('active', i === index);
            }});

            const post = posts[index];
            if (!post || index < 0) {{
                layout.classList.remove('has-selection');
                readingPanel.classList.remove('open');
                readingEmpty.style.display = 'none';
                readingContent.innerHTML = '';
                return;
            }}

            layout.classList.add('has-selection');
            readingEmpty.style.display = 'none';
            document.getElementById('feedReadingPanel').classList.add('open');
            const badgesHtml = post.badges.map(b => `<span class="feed-badge">${{_escape_js(b)}}</span>`).join('');
            const avatarHtml = post.avatar
                ? `<img class="feed-detail-avatar-img" src="${{_escape_js(post.avatar)}}" alt="" loading="lazy">`
                : `<div class="feed-detail-avatar-placeholder">${{_escape_js(post.owner)[0].toUpperCase()}}</div>`;

            readingContent.innerHTML = `
                <div class="feed-detail-header">
                    <a class="feed-detail-avatar-link" href="javascript:void(0)" onclick="openEtoroPost('${{_escape_js(post.post_url)}}')">
                        ${{avatarHtml}}
                    </a>
                    <div class="feed-detail-meta">
                        <a class="feed-detail-owner-link" href="javascript:void(0)" onclick="openEtoroPost('${{_escape_js(post.post_url)}}')">${{_escape_js(post.owner)}}</a>
                        <div class="feed-detail-date">${{_escape_js(post.created_raw)}}</div>
                    </div>
                </div>
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
            `;
        }}

        function _escape_js(text) {{
            if (text == null) return '';
            return String(text)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        renderList();
        {_redirect_script}
    </script>
</body>
</html>
"""
