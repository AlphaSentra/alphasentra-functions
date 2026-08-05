"""Long-lived worker to pre-cache portfolio reports for active users.

Queries the alphasentra-core ``users`` collection for accounts that have a
valid ``etoro_username`` and a non-expired ``expiry_subscription``, then
generates and caches the full portfolio HTML report for each user when it
is not already present in the ``portfolio_report_cache`` collection.

This script runs indefinitely, polling every ``POLL_INTERVAL_SECONDS`` for
newly created users or users whose cache is missing. It is intended to be
run as a long-lived worker process.

Required environment variables:
    MONGODB_DATABASE  - Core database name (default: alphasentra-core).
    MONGODB_URI_CACHE - Cache database URI(s).
    ETORO_PUBLIC_KEY  - eToro API public key.
    ETORO_PRIVATE_KEY - eToro API private key.
    GEMINI_API_KEY    - Required for AI-enhanced report generation.
    POLL_INTERVAL_SECONDS - Optional. Seconds to wait between polling cycles (default: 30).
"""

import os
import signal
import sys
import time
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
from Functions.logging_utils import log_info, log_error, log_warning
from Functions.port.config import CACHE_TTL_REPORT as _REPORT_TTL

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    log_info("Shutdown signal received. Finishing current cycle and exiting...")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

# ``generate_portfolio_html`` imports Flask-dependent modules under the hood,
# so we must provide an application context before importing it.
from flask import Flask

app = Flask(__name__)

with app.app_context():
    from Functions.port.main import generate_portfolio_html

    # ------------------------------------------------------------------
    # 1. Initialize long-lived resources (created once, reused forever).
    # ------------------------------------------------------------------
    db = DatabaseManager().get_client()
    db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
    coll = db[db_name]["users"]

    log_info(f"Starting infinite polling for portfolio report caching (interval: {POLL_INTERVAL}s)")

    # ------------------------------------------------------------------
    # 2. Cache generation logic per user.
    # ------------------------------------------------------------------
    MAX_REPORT_RETRIES = 5
    REPORT_RETRY_BASE_DELAY = 15

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
        cache_key = f"portfolio_report_{username.lower()}"
        static_key = f"{cache_key}_static"
        ai_cache_key = f"portfolio_report_ai_{username.lower()}"

        cached_html = get_portfolio_cache_from_mongo(
            "portfolio_report_cache",
            cache_key,
            ttl_seconds=_REPORT_TTL,
            ext=".html",
        )
        if cached_html is not None:
            return f"skip:{username}"

        from Functions.port.engine.analyzer import UnmappedInstrumentsError

        for attempt in range(MAX_REPORT_RETRIES + 1):
            try:
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
            except UnmappedInstrumentsError as exc:
                if attempt < MAX_REPORT_RETRIES:
                    log_warning(
                        f"Attempt {attempt + 1}/{MAX_REPORT_RETRIES + 1} for {username}: "
                        f"Unmapped instruments found {exc.unmapped_ids}. "
                        f"Retrying in {REPORT_RETRY_BASE_DELAY * (2 ** attempt)}s...",
                        "PORT_USER_REPORT_UNMAPPED_RETRY",
                    )
                    time.sleep(REPORT_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    log_error(
                        f"Failed to cache report for {username} after {MAX_REPORT_RETRIES + 1} attempts "
                        f"due to unmapped instruments: {exc.unmapped_ids}",
                        "PORT_USER_REPORT_UNMAPPED_FAIL",
                    )
                    return f"error:{username}"
            except Exception as exc:
                if attempt < MAX_REPORT_RETRIES:
                    log_error(
                        f"Failed to cache report for {username} (attempt {attempt + 1}/{MAX_REPORT_RETRIES + 1}). "
                        f"Retrying in {REPORT_RETRY_BASE_DELAY * (2 ** attempt)}s. Error: {exc}",
                        "PORT_USER_REPORT_RETRY",
                    )
                    time.sleep(REPORT_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    log_error(
                        f"Failed to cache report for {username} after {MAX_REPORT_RETRIES + 1} attempts: {exc}",
                        "PORT_USER_REPORT_FAIL",
                    )
                    return f"error:{username}"

        return f"error:{username}"

    # ------------------------------------------------------------------
    # 3. Execute caching across all active users, then sleep and repeat.
    # ------------------------------------------------------------------
    while not _shutdown_requested:
        now = datetime.now(timezone.utc)
        cursor = coll.find(
            {
                "etoro_username": {"$exists": True, "$ne": ""},
                "expiry_subscription": {"$gt": now},
            },
            {"etoro_username": 1, "_id": 0},
        )

        users = []
        seen = set()
        for doc in cursor:
            username = str(doc.get("etoro_username", "")).strip()
            if username and username not in seen:
                seen.add(username)
                users.append(username)

        if users:
            log_info(f"Found {len(users)} active users with etoro_username.")
            log_info(f"Caching portfolio reports for {len(users)} users...")
            ok = skip = err = 0
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(_cache_report, u): u for u in users}
                for future in as_completed(futures):
                    if _shutdown_requested:
                        break
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

        if _shutdown_requested:
            break

        log_info(f"Sleeping for {POLL_INTERVAL} seconds before next poll...")
        # Sleep in small increments so we can react to shutdown signals quickly.
        remaining = POLL_INTERVAL
        while remaining > 0 and not _shutdown_requested:
            time.sleep(min(1, remaining))
            remaining -= 1

    log_info("Portfolio report cache worker stopped.")
