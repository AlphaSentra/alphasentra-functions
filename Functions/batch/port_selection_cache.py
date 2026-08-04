import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))
sys.path.insert(0, str(_ROOT / "Functions" / "port"))

from Functions.db.cache import get_portfolio_cache_from_mongo, set_portfolio_cache_to_mongo
from Functions.logging_utils import log_info
from Functions.port.config import CACHE_TTL_ETORO_PI as _ETORO_PI_TTL, CACHE_TTL_REPORT as _REPORT_TTL

USERNAME = "etoroteam"
SKIP_AI = False

from flask import Flask, g

app = Flask(__name__)

_RANKING_COMBOS = [
    {"base_period": "OneMonthAgo", "sort": "-copiersGain", "page_size": 20, "page": 1},
    {"base_period": "OneMonthAgo", "sort": "-copiersGain", "page_size": 20, "page": 2},
    {"base_period": "CurrMonth", "sort": "-copiersGain", "page_size": 20, "page": 1},
    {"base_period": "ThreeMonthsAgo", "sort": "-copiersGain", "page_size": 20, "page": 1},
    {"base_period": "OneYearAgo", "sort": "-copiersGain", "page_size": 20, "page": 1},
]

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

        # Cache full unauthenticated page HTML (sign-in notice)
        try:
            g.etoro_authuser = None
            html = get_portfolio_selection_html(**combo)
            log_info(f"Cached unauthenticated /port page for combo {combo} ({len(html)} chars)")
        except Exception as exc:
            log_info(f"Failed to cache unauthenticated page for combo {combo}: {exc}")

        # Cache full authenticated page HTML for batch user
        if USERNAME:
            try:
                g.etoro_authuser = USERNAME
                html = get_portfolio_selection_html(**combo)
                log_info(f"Cached authenticated /port page for {USERNAME} combo {combo} ({len(html)} chars)")
            except Exception as exc:
                log_info(f"Failed to cache authenticated page for {USERNAME} combo {combo}: {exc}")

    set_portfolio_cache_to_mongo("portfolio_selection_cache", "portfolio_selection_top_investors", all_usernames, ext=".json", ttl_seconds=_ETORO_PI_TTL)
    log_info(f"Cached {len(all_usernames)} top investor usernames to MongoDB.")

    from Functions.port.main import generate_portfolio_html

    def _cache_report(username: str) -> str:
        cache_key = f"portfolio_report_{username.strip().lower()}"
        static_key = f"{cache_key}_static"
        ai_cache_key = f"portfolio_report_ai_{username.strip().lower()}"
        cached_html = get_portfolio_cache_from_mongo("portfolio_report_cache", cache_key, ttl_seconds=_REPORT_TTL, ext=".html")
        if cached_html is not None:
            return f"skip:{username}"
        try:
            if SKIP_AI:
                report_html = generate_portfolio_html(
                    etoro_username=username,
                    benchmark_ticker="",
                    etoro_cid="",
                    skip_ai=True,
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
                )
                set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, report_html, ext=".html", ttl_seconds=_REPORT_TTL)
                static_html = generate_portfolio_html(
                    etoro_username=username,
                    benchmark_ticker="",
                    etoro_cid="",
                    skip_ai=True,
                )
                set_portfolio_cache_to_mongo("portfolio_report_cache", static_key, static_html, ext=".html", ttl_seconds=_REPORT_TTL)
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
            set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, report_html, ext=".html", ttl_seconds=_REPORT_TTL)
            set_portfolio_cache_to_mongo("portfolio_report_cache", static_key, static_html, ext=".html", ttl_seconds=_REPORT_TTL)
            set_portfolio_cache_to_mongo("portfolio_report_cache", ai_cache_key, ai_content, ext=".json", ttl_seconds=_REPORT_TTL)
            return f"ok:{username}"
        except Exception as exc:
            log_info(f"Failed to cache report for {username}: {exc}")
            return f"error:{username}"

    if all_usernames:
        log_info(f"Caching portfolio reports for {len(all_usernames)} investors...")
        ok = skip = err = 0
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {executor.submit(_cache_report, u): u for u in all_usernames}
            for future in as_completed(futures):
                res = future.result()
                if res.startswith("ok:"):
                    ok += 1
                elif res.startswith("skip:"):
                    skip += 1
                else:
                    err += 1
        log_info(f"Portfolio report caching complete: {ok} generated, {skip} skipped, {err} errors.")
