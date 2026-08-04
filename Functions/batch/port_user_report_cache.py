"""Batch script to pre-cache portfolio reports for active users.

Queries the alphasentra-core ``users`` collection for accounts that have a
valid ``etoro_username`` and a non-expired ``expiry_subscription``, then
generates and caches the full portfolio HTML report for each user when it
is not already present in the ``portfolio_report_cache`` collection.

This script is intended to run as part of the scheduled batch job sequence,
after portfolio selection rankings have been cached by
``port_selection_cache.py``.

Required environment variables:
    MONGODB_DATABASE  - Core database name (default: alphasentra-core).
    MONGODB_URI_CACHE - Cache database URI(s).
    ETORO_PUBLIC_KEY  - eToro API public key.
    ETORO_PRIVATE_KEY - eToro API private key.
    GEMINI_API_KEY    - Required for AI-enhanced report generation.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# Ensure project and Functions paths are importable when run as a script.
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))
sys.path.insert(0, str(_ROOT / "Functions" / "port"))

from Functions.db.cache import get_portfolio_cache_from_mongo, set_portfolio_cache_to_mongo
from Functions.db.client import DatabaseManager
from Functions.logging_utils import log_info, log_error
from Functions.port.config import CACHE_TTL_REPORT as _REPORT_TTL

# ``generate_portfolio_html`` imports Flask-dependent modules under the hood,
# so we must provide an application context before importing it.
from flask import Flask

app = Flask(__name__)

with app.app_context():
    from Functions.port.main import generate_portfolio_html

    # ------------------------------------------------------------------
    # 1. Load active users from the core database.
    # ------------------------------------------------------------------
    # Uses the singleton DatabaseManager so the connection is reused across
    # the batch run.
    db = DatabaseManager().get_client()
    db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
    coll = db[db_name]["users"]

    # Only users whose subscription has not expired at the time the batch
    # runs should receive a freshly generated report.
    now = datetime.now(timezone.utc)
    cursor = coll.find(
        {
            "etoro_username": {"$exists": True, "$ne": ""},
            "expiry_subscription": {"$gt": now},
        },
        {"etoro_username": 1, "_id": 0},
    )

    # Deduplicate usernames to avoid redundant work if duplicates exist in
    # the collection.
    users = []
    seen = set()
    for doc in cursor:
        username = str(doc.get("etoro_username", "")).strip()
        if username and username not in seen:
            seen.add(username)
            users.append(username)

    log_info(f"Found {len(users)} active users with etoro_username.")

    # ------------------------------------------------------------------
    # 2. Cache generation logic per user.
    # ------------------------------------------------------------------
    def _cache_report(username: str) -> str:
        """Generate and cache portfolio artifacts for a single user.

        Args:
            username: eToro username to process.

        Returns:
            A status tag string:
              - ``skip:<username>`` when the HTML report is already cached.
              - ``ok:<username>`` when generation and caching succeeded.
              - ``error:<username>`` when an exception occurred.
        """
        # Cache keys follow the same convention used by the web application
        # so that cached batch output is served transparently.
        cache_key = f"portfolio_report_{username.lower()}"
        static_key = f"{cache_key}_static"
        ai_cache_key = f"portfolio_report_ai_{username.lower()}"

        # Skip generation if the primary HTML cache already exists and is
        # within its TTL. This makes the batch script idempotent and avoids
        # redundant eToro API and LLM calls.
        cached_html = get_portfolio_cache_from_mongo(
            "portfolio_report_cache",
            cache_key,
            ttl_seconds=_REPORT_TTL,
            ext=".html",
        )
        if cached_html is not None:
            return f"skip:{username}"

        try:
            # ------------------------------------------------------------------
            # Case A: AI content is already cached but the HTML wrapper is not.
            # Re-use the cached AI fragment to avoid another LLM call, and
            # also generate a static (no-AI) fallback variant.
            # ------------------------------------------------------------------
            cached_ai = get_portfolio_cache_from_mongo(
                "portfolio_report_cache",
                ai_cache_key,
                ttl_seconds=_REPORT_TTL,
                ext=".json",
            )
            if cached_ai is not None:
                report_html = generate_portfolio_html(
                    etoro_username=username,
                    benchmark_ticker="",
                    etoro_cid="",
                    cached_ai_content=cached_ai,
                )
                static_html = generate_portfolio_html(
                    etoro_username=username,
                    benchmark_ticker="",
                    etoro_cid="",
                    skip_ai=True,
                )
                set_portfolio_cache_to_mongo(
                    "portfolio_report_cache",
                    cache_key,
                    report_html,
                    ext=".html",
                    ttl_seconds=_REPORT_TTL,
                )
                set_portfolio_cache_to_mongo(
                    "portfolio_report_cache",
                    static_key,
                    static_html,
                    ext=".html",
                    ttl_seconds=_REPORT_TTL,
                )
                return f"ok:{username}"

            # ------------------------------------------------------------------
            # Case B: Nothing is cached. Run the full pipeline:
            #   1. Generate AI-enhanced HTML and capture the AI content dict.
            #   2. Generate a static HTML variant (skip_ai=True) for
            #      fallback / no-AI contexts.
            #   3. Persist all three artifacts so subsequent requests and
            #      future batch runs hit the cache.
            # ------------------------------------------------------------------
            report_html, ai_content = generate_portfolio_html(
                etoro_username=username,
                benchmark_ticker="",
                etoro_cid="",
                return_ai_content=True,
            )
            static_html = generate_portfolio_html(
                etoro_username=username,
                benchmark_ticker="",
                etoro_cid="",
                skip_ai=True,
            )
            set_portfolio_cache_to_mongo(
                "portfolio_report_cache",
                cache_key,
                report_html,
                ext=".html",
                ttl_seconds=_REPORT_TTL,
            )
            set_portfolio_cache_to_mongo(
                "portfolio_report_cache",
                static_key,
                static_html,
                ext=".html",
                ttl_seconds=_REPORT_TTL,
            )
            set_portfolio_cache_to_mongo(
                "portfolio_report_cache",
                ai_cache_key,
                ai_content,
                ext=".json",
                ttl_seconds=_REPORT_TTL,
            )
            return f"ok:{username}"
        except Exception as exc:
            # Log the full traceback via the project's logging utility so
            # it is captured by the batch runner's output.
            log_error(f"Failed to cache report for {username}: {exc}", "PORT_USER_REPORT")
            return f"error:{username}"

    # ------------------------------------------------------------------
    # 3. Execute caching across all active users.
    # ------------------------------------------------------------------
    # ``max_workers=1`` keeps requests to the eToro API sequential. The
    # underlying client has a pause threshold (_ETORO_PAUSE_AFTER_API_CALLS
    # = 250) and running multiple users concurrently could trigger rate
    # limits or throttling. A single worker is the safest choice for a
    # batch pre-warming job that does not have a strict latency target.
    if users:
        log_info(f"Caching portfolio reports for {len(users)} users...")
        ok = skip = err = 0
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {executor.submit(_cache_report, u): u for u in users}
            for future in as_completed(futures):
                res = future.result()
                if res.startswith("ok:"):
                    ok += 1
                elif res.startswith("skip:"):
                    skip += 1
                else:
                    err += 1
        log_info(f"Portfolio report caching complete: {ok} generated, {skip} skipped, {err} errors.")
    else:
        log_info("No active users found to cache reports for.")
