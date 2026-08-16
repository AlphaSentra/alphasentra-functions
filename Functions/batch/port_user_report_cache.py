"""Long-lived worker to pre-cache portfolio reports and /port pages for active users.

Queries the alphasentra-core ``users`` collection for accounts that have a
valid ``etoro_username`` and a non-expired ``expiry_subscription``, then
generates and caches:

  * The full portfolio HTML report (and its static / AI variants) in the
    ``portfolio_report_cache`` collection.
  * The authenticated ``/port`` selection page in the
    ``portfolio_selection_cache`` collection.

This script runs indefinitely, polling every ``POLL_INTERVAL_SECONDS`` for
newly created users or users whose cache is missing. It is intended to be
run as a long-lived worker process.

Required environment variables:
    MONGODB_DATABASE  - Core database name (default: alphasentra-core).
    MONGODB_URI_CACHE - Cache database URI(s).
    ETORO_PUBLIC_KEY  - eToro API public key.
    ETORO_PRIVATE_KEY - eToro API private key.
    GEMINI_API_KEY    - Required for AI-enhanced report generation.
    POLL_INTERVAL_SECONDS - Optional. Seconds to wait between polling cycles (default: 10).
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

from Functions.db.cache import get_portfolio_cache_from_mongo, set_portfolio_cache_to_mongo, get_report_retry_count, increment_report_retry_count, reset_report_retry_count
from Functions.db.client import DatabaseManager
from Functions.logging_utils import log_info, log_error, log_warning
from Functions.port.config import CACHE_TTL_ETORO_PI as _ETORO_PI_TTL, CACHE_TTL_REPORT as _REPORT_TTL

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    log_info("Shutdown signal received. Finishing current cycle and exiting...")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

# ``generate_portfolio_html`` and ``get_portfolio_selection_html`` both
# import Flask-dependent modules under the hood, so we must provide an
# application context before importing them.
from flask import Flask, g

app = Flask(__name__)

with app.app_context():
    from Functions.port.main import generate_portfolio_html
    from Functions.port.selection import _selection_cache_suffix, get_portfolio_selection_html

    # ------------------------------------------------------------------
    # 1. Initialize long-lived resources (created once, reused forever).
    # ------------------------------------------------------------------
    db = DatabaseManager().get_client()
    db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
    coll = db[db_name]["users"]

    log_info(f"Starting infinite polling for portfolio report and /port page caching (interval: {POLL_INTERVAL}s)")

    # ------------------------------------------------------------------
    # 2. Cache generation logic per user.
    # ------------------------------------------------------------------
    MAX_REPORT_RETRIES = 5
    REPORT_RETRY_BASE_DELAY = 15
    MAX_RETRY_COUNT = 5

    def _cache_report(username: str) -> str:
        """Generate and cache portfolio artifacts and the /port selection page for a single user.

        Report artifacts include the AI-enhanced HTML report, a static HTML variant,
        and the raw AI content payload. The /port selection page is also warmed
        regardless of whether the report generation succeeds, fails, or is skipped.

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
            _cache_selection_page(username)
            return f"skip:{username}"

        retry_count = get_report_retry_count("portfolio_report_cache", ai_cache_key)
        if retry_count >= MAX_RETRY_COUNT:
            log_warning(
                f"Skipping report generation for {username} after {retry_count} cumulative failures (max {MAX_RETRY_COUNT}).",
                "PORT_USER_REPORT_RETRY_LIMIT",
            )
            static_html = generate_portfolio_html(
                etoro_username=username,
                benchmark_ticker="",
                etoro_cid="",
                skip_ai=True,
                log_header=False,
            )
            placeholder_ai_content = {
                "intel_commentary_text": "The AI has not detected any significant information to process at this time.",
                "overview_ai_interpretation": "",
            }
            set_portfolio_cache_to_mongo(
                "portfolio_report_cache",
                cache_key,
                static_html,
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
                placeholder_ai_content,
                ext=".json",
                ttl_seconds=_REPORT_TTL,
            )
            _cache_selection_page(username)
            return f"skip:{username}"

        from Functions.port.engine.analyzer import UnmappedInstrumentsError
        from Functions.etoro.client import InvalidSymbolError

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
                        log_header=False,
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
                    reset_report_retry_count("portfolio_report_cache", ai_cache_key)
                    _cache_selection_page(username)
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
                    log_header=False,
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
                reset_report_retry_count("portfolio_report_cache", ai_cache_key)
                _cache_selection_page(username)
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
                    increment_report_retry_count("portfolio_report_cache", ai_cache_key)
                    log_error(
                        f"Failed to cache report for {username} after {MAX_REPORT_RETRIES + 1} attempts "
                        f"due to unmapped instruments: {exc.unmapped_ids}",
                        "PORT_USER_REPORT_UNMAPPED_FAIL",
                    )
                    _cache_selection_page(username)
                    return f"error:{username}"
            except InvalidSymbolError as exc:
                if attempt < MAX_REPORT_RETRIES:
                    log_warning(
                        f"Attempt {attempt + 1}/{MAX_REPORT_RETRIES + 1} for {username}: "
                        f"Invalid symbol from eToro API: {exc}. "
                        f"Retrying in {REPORT_RETRY_BASE_DELAY * (2 ** attempt)}s...",
                        "PORT_USER_REPORT_INVALID_SYMBOL_RETRY",
                    )
                    time.sleep(REPORT_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    increment_report_retry_count("portfolio_report_cache", ai_cache_key)
                    log_warning(
                        f"Skipping report for {username} after {MAX_REPORT_RETRIES + 1} attempts "
                        f"due to invalid symbols: {exc}",
                        "PORT_USER_REPORT_INVALID_SYMBOL_SKIP",
                    )
                    _cache_selection_page(username)
                    return f"skip:{username}"
            except Exception as exc:
                if attempt < MAX_REPORT_RETRIES:
                    log_error(
                        f"Failed to cache report for {username} (attempt {attempt + 1}/{MAX_REPORT_RETRIES + 1}). "
                        f"Retrying in {REPORT_RETRY_BASE_DELAY * (2 ** attempt)}s. Error: {exc}",
                        "PORT_USER_REPORT_RETRY",
                    )
                    time.sleep(REPORT_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    increment_report_retry_count("portfolio_report_cache", ai_cache_key)
                    log_error(
                        f"Failed to cache report for {username} after {MAX_REPORT_RETRIES + 1} attempts: {exc}",
                        "PORT_USER_REPORT_FAIL",
                    )
                    _cache_selection_page(username)
                    return f"error:{username}"

        _cache_selection_page(username)
        return f"error:{username}"

    _SELECTION_COMBOS = [
        {"base_period": "OneMonthAgo", "sort": "-copiersGain", "page_size": 20, "page": 1},
    ]

    def _cache_selection_page(username: str) -> None:
        """Warm the authenticated ``/port`` selection page cache for ``username``.

        Checks whether the page HTML for each combo is already present in
        ``portfolio_selection_cache``. On a cache miss, renders the full page
        inside a temporary Flask app context (so ``flask.g.etoro_authuser`` is
        set correctly) and writes the result back with the shared
        ``_ETORO_PI_TTL`` TTL.

        Failures are logged but do not propagate; report caching continues
        independently.
        """
        for combo in _SELECTION_COMBOS:
            cache_suffix = _selection_cache_suffix(**combo)
            page_cache_key = f"portfolio_selection_page{cache_suffix}_{username}"
            cached_page = get_portfolio_cache_from_mongo(
                "portfolio_selection_cache",
                page_cache_key,
                ttl_seconds=_ETORO_PI_TTL,
                ext=".html",
            )
            if cached_page is not None:
                continue
            try:
                with app.app_context():
                    g.etoro_authuser = username
                    html = get_portfolio_selection_html(**combo)
                set_portfolio_cache_to_mongo(
                    "portfolio_selection_cache",
                    page_cache_key,
                    html,
                    ext=".html",
                    ttl_seconds=_ETORO_PI_TTL,
                )
            except Exception as exc:
                log_error(
                    f"Failed to cache /port selection page for {username} combo {combo}: {exc}",
                    "PORT_USER_SELECTION_CACHE_FAIL",
                )

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
            log_info(f"Portfolio report and /port page caching complete: {ok} generated, {skip} skipped, {err} errors.")
        else:
            log_info("No active users found to cache reports or /port pages for.")

        if _shutdown_requested:
            break

        log_info(f"Sleeping for {POLL_INTERVAL} seconds before next poll...")
        # Sleep in small increments so we can react to shutdown signals quickly.
        remaining = POLL_INTERVAL
        while remaining > 0 and not _shutdown_requested:
            time.sleep(min(1, remaining))
            remaining -= 1

    log_info("Portfolio report and /port page cache worker stopped.")
