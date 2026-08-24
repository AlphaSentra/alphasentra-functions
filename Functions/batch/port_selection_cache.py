"""
Batch pre-cache the portfolio selection (/port) page and portfolio reports.

This script is executed as a standalone job (not as a web request). It:
  1. Pre-fetches ranking data and the unauthenticated /port page for each
     ranking combo so the first real browser request hits cache.
  2. Caches the authenticated /port page for the batch user (etoroteam).
  3. Caches the full /port page for every user in MongoDB that has an
     ``etoro_username`` value.
  4. Caches the portfolio report page (and its AI/static variants) for the
     top investors discovered in step 1.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap
# The repository layout places shared code under ``Functions/``, so we inject
# the project root and key sub-packages onto ``sys.path`` before importing.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))
sys.path.insert(0, str(_ROOT / "Functions" / "port"))

from Functions.db.cache import get_portfolio_cache_from_mongo, set_portfolio_cache_to_mongo
from Functions.db.client import DatabaseManager
from Functions.logging_utils import log_info, log_error, log_warning
from Functions.config import CACHE_TTL_ETORO_PI as _ETORO_PI_TTL, CACHE_TTL_REPORT as _REPORT_TTL

# ---------------------------------------------------------------------------
# Batch configuration
# ``USERNAME`` is used to warm the authenticated /port page cache.
# ``SKIP_AI`` controls whether AI content is generated for portfolio reports.
# ---------------------------------------------------------------------------
USERNAME = "etoroteam"
SKIP_AI = False

from flask import Flask, g

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Ranking combos to pre-cache.
# Each combo represents a different sort/filter view of the Pro Investor
# rankings table that the /port page can display.
# ---------------------------------------------------------------------------
_RANKING_COMBOS = [
    {"base_period": "OneMonthAgo", "sort": "-copiersGain", "page_size": 20, "page": 1},
    {"base_period": "OneMonthAgo", "sort": "-copiersGain", "page_size": 20, "page": 2},
    {"base_period": "CurrMonth", "sort": "-copiersGain", "page_size": 20, "page": 1},
    {"base_period": "ThreeMonthsAgo", "sort": "-copiersGain", "page_size": 20, "page": 1},
    {"base_period": "OneYearAgo", "sort": "-copiersGain", "page_size": 20, "page": 1},
]

# ---------------------------------------------------------------------------
# Phase 1: warm ranking and /port page caches.
# We need a Flask app context because ``get_portfolio_selection_html`` reads
# ``flask.g.etoro_authuser`` to decide which portfolio row to render.
# ---------------------------------------------------------------------------
with app.app_context():
    from Functions.port.selection import _fetch_rankings, _selection_cache_suffix, get_portfolio_selection_html

    all_usernames = []
    seen = set()

    for combo in _RANKING_COMBOS:
        cache_suffix = _selection_cache_suffix(**combo)
        rankings_cache_key = f"portfolio_selection_rankings{cache_suffix}"
        cached_rankings = get_portfolio_cache_from_mongo("portfolio_selection_cache", rankings_cache_key, ttl_seconds=_ETORO_PI_TTL, ext=".pkl")
        merged = []
        if cached_rankings is not None:
            merged = cached_rankings[0] if isinstance(cached_rankings, tuple) else []
        if not merged:
            try:
                merged, week_map, month_map, year_map = _fetch_rankings(**combo)
                set_portfolio_cache_to_mongo("portfolio_selection_cache", rankings_cache_key, (merged, week_map, month_map, year_map), ext=".pkl", ttl_seconds=_ETORO_PI_TTL)
            except Exception as exc:
                log_info(f"Failed to fetch rankings for combo {combo}: {exc}")

        # Cache full unauthenticated page HTML (shows sign-in prompt)
        try:
            g.etoro_authuser = None
            html = get_portfolio_selection_html(**combo)
            log_info(f"Cached unauthenticated /port page for combo {combo} ({len(html)} chars)")
        except Exception as exc:
            log_info(f"Failed to cache unauthenticated page for combo {combo}: {exc}")

        # Cache full authenticated page HTML for the batch user
        if USERNAME:
            try:
                g.etoro_authuser = USERNAME
                html = get_portfolio_selection_html(**combo)
                log_info(f"Cached authenticated /port page for {USERNAME} combo {combo} ({len(html)} chars)")
            except Exception as exc:
                log_info(f"Failed to cache authenticated page for {USERNAME} combo {combo}: {exc}")

        for item in merged or []:
            username = None
            if "userName" in item and str(item["userName"]).strip():
                username = str(item["userName"]).strip()
            elif "cid" in item:
                username = str(item["cid"]).strip()
            if username and username not in seen:
                seen.add(username)
                all_usernames.append(username)
                if len(all_usernames) >= 20:
                    break

        if len(all_usernames) >= 20:
            break

    set_portfolio_cache_to_mongo("portfolio_selection_cache", "portfolio_selection_top_investors", all_usernames, ext=".json", ttl_seconds=_ETORO_PI_TTL)
    log_info(f"Cached {len(all_usernames)} top investor usernames to MongoDB.")

    # ------------------------------------------------------------------
    # Cache /port page for all users in the database with etoro_username
    # ------------------------------------------------------------------
    db = DatabaseManager().get_client()
    db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
    coll = db[db_name]["users"]

    cursor = coll.find(
        {"etoro_username": {"$exists": True, "$ne": ""}},
        {"etoro_username": 1, "_id": 0},
    )

    db_users = []
    seen_users = set()
    for doc in cursor:
        username = str(doc.get("etoro_username", "")).strip()
        if username and username not in seen_users:
            seen_users.add(username)
            db_users.append(username)

    log_info(f"Found {len(db_users)} users in database with etoro_username.")

    def _cache_port_page(username: str, combo: dict) -> str:
        # ``ThreadPoolExecutor`` runs this in a worker thread that has no Flask
        # app context, so we must push one here before touching ``flask.g`` or
        # calling ``get_portfolio_selection_html``.
        with app.app_context():
            try:
                g.etoro_authuser = username
                html = get_portfolio_selection_html(**combo)
                log_info(f"Cached /port page for {username} combo {combo} ({len(html)} chars)")
                return "ok"
            except Exception as exc:
                log_info(f"Failed to cache /port page for {username} combo {combo}: {exc}")
                return "error"

    if db_users:
        log_info(f"Caching /port pages for {len(db_users)} database users across {len(_RANKING_COMBOS)} combos...")
        ok = err = 0
        total = len(db_users) * len(_RANKING_COMBOS)
        done = 0
        # ``max_workers=1`` is intentional: eToro's public API is rate-limited
        # and parallel requests cause 429 / IP bans.
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {}
            for combo in _RANKING_COMBOS:
                for username in db_users:
                    futures[executor.submit(_cache_port_page, username, combo)] = (username, combo)

            for future in as_completed(futures):
                username, combo = futures[future]
                try:
                    result = future.result()
                    if result == "ok":
                        ok += 1
                    else:
                        err += 1
                except Exception as exc:
                    log_info(f"Failed to cache /port page for {username} combo {combo}: {exc}")
                    err += 1
                done += 1
                if done % 100 == 0 or done == total:
                    log_info(f"Progress: {done}/{total} /port pages cached ({ok} ok, {err} err)")
        log_info(f"/port page caching complete for database users: {ok} generated, {err} errors.")

    from Functions.port.main import generate_portfolio_html

    MAX_REPORT_RETRIES = 5
    REPORT_RETRY_BASE_DELAY = 15

    def _cache_report(username: str, index: int = 0, total: int = 0) -> str:
        cache_key = f"portfolio_report_{username.strip().lower()}"
        static_key = f"{cache_key}_static"
        ai_cache_key = f"portfolio_report_ai_{username.strip().lower()}"
        base_retry_info = f"[{index + 1}/{total}]" if total > 0 else ""
        cached_html = get_portfolio_cache_from_mongo("portfolio_report_cache", cache_key, ttl_seconds=_REPORT_TTL, ext=".html")
        if cached_html is not None:
            return f"skip:{username}"

        from Functions.port.engine.analyzer import UnmappedInstrumentsError
        from Functions.etoro.client import InvalidSymbolError

        for attempt in range(MAX_REPORT_RETRIES + 1):
            try:
                if SKIP_AI:
                    report_html = generate_portfolio_html(
                        etoro_username=username,
                        benchmark_ticker="",
                        etoro_cid="",
                        skip_ai=True,
                        retry_info=base_retry_info,
                    )
                    set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, report_html, ext=".html", ttl_seconds=_REPORT_TTL)
                    return f"ok:{username}"

                cached_ai = get_portfolio_cache_from_mongo("portfolio_report_cache", ai_cache_key, ttl_seconds=_REPORT_TTL, ext=".json")
                if cached_ai is not None:
                    report_html = generate_portfolio_html(
                        etoro_username=username,
                        benchmark_ticker="",
                        etoro_cid="",
                        cached_ai_content=cached_ai,
                        retry_info=base_retry_info,
                    )
                    set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, report_html, ext=".html", ttl_seconds=_REPORT_TTL)
                    static_html = generate_portfolio_html(
                        etoro_username=username,
                        benchmark_ticker="",
                        etoro_cid="",
                        skip_ai=True,
                        log_header=False,
                    )
                    set_portfolio_cache_to_mongo("portfolio_report_cache", static_key, static_html, ext=".html", ttl_seconds=_REPORT_TTL)
                    return f"ok:{username}"

                report_html, ai_content = generate_portfolio_html(
                    etoro_username=username,
                    benchmark_ticker="",
                    etoro_cid="",
                    return_ai_content=True,
                    retry_info=base_retry_info,
                )
                static_html = generate_portfolio_html(
                    etoro_username=username,
                    benchmark_ticker="",
                    etoro_cid="",
                    skip_ai=True,
                    log_header=False,
                )
                set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, report_html, ext=".html", ttl_seconds=_REPORT_TTL)
                set_portfolio_cache_to_mongo("portfolio_report_cache", static_key, static_html, ext=".html", ttl_seconds=_REPORT_TTL)
                set_portfolio_cache_to_mongo("portfolio_report_cache", ai_cache_key, ai_content, ext=".json", ttl_seconds=_REPORT_TTL)
                return f"ok:{username}"
            except UnmappedInstrumentsError as exc:
                if attempt < MAX_REPORT_RETRIES:
                    log_warning(
                        f"Attempt {attempt + 1}/{MAX_REPORT_RETRIES + 1} for {username}: "
                        f"Unmapped instruments found {exc.unmapped_ids}. "
                        f"Retrying in {REPORT_RETRY_BASE_DELAY * (2 ** attempt)}s...",
                    )
                    time.sleep(REPORT_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    log_error(
                        f"Failed to cache report for {username} {base_retry_info} after {MAX_REPORT_RETRIES + 1} attempts "
                        f"due to unmapped instruments: {exc.unmapped_ids}",
                    )
                    return f"error:{username}"
            except InvalidSymbolError as exc:
                if attempt < MAX_REPORT_RETRIES:
                    log_warning(
                        f"Attempt {attempt + 1}/{MAX_REPORT_RETRIES + 1} for {username}: "
                        f"Invalid symbol from eToro API: {exc}. "
                        f"Retrying in {REPORT_RETRY_BASE_DELAY * (2 ** attempt)}s...",
                    )
                    time.sleep(REPORT_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    log_warning(
                        f"Skipping report for {username} {base_retry_info} after {MAX_REPORT_RETRIES + 1} attempts "
                        f"due to invalid symbols: {exc}",
                    )
                    return f"skip:{username}"
            except Exception as exc:
                if attempt < MAX_REPORT_RETRIES:
                    log_error(
                        f"Failed to cache report for {username} {base_retry_info} (attempt {attempt + 1}/{MAX_REPORT_RETRIES + 1}). "
                        f"Retrying in {REPORT_RETRY_BASE_DELAY * (2 ** attempt)}s. Error: {exc}",
                    )
                    time.sleep(REPORT_RETRY_BASE_DELAY * (2 ** attempt))
                else:
                    log_error(
                        f"Failed to cache report for {username} {base_retry_info} after {MAX_REPORT_RETRIES + 1} attempts: {exc}",
                    )
                    return f"error:{username}"

        return f"error:{username}"

    if all_usernames:
        log_info(f"Caching portfolio reports for {len(all_usernames)} investors...")
        ok = skip = err = 0
        # ``max_workers=1`` is intentional: eToro's public API is rate-limited
        # and parallel requests cause 429 / IP bans.
        with ThreadPoolExecutor(max_workers=1) as executor:
            total_reports = len(all_usernames)
            futures = {executor.submit(_cache_report, u, i, total_reports): u for i, u in enumerate(all_usernames)}
            for future in as_completed(futures):
                res = future.result()
                if res.startswith("ok:"):
                    ok += 1
                elif res.startswith("skip:"):
                    skip += 1
                else:
                    err += 1
        log_info(f"Portfolio report caching complete: {ok} generated, {skip} skipped, {err} errors.")
