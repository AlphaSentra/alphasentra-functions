import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))
sys.path.insert(0, str(_ROOT / "Functions" / "port"))

from Functions.logging_utils import log_info
from Functions.port.cache import get as cache_get, set as cache_set
from Functions.port.config import CACHE_TTL_ETORO_PI as _ETORO_PI_TTL, CACHE_TTL_REPORT as _REPORT_TTL

USERNAME = "etoroteam"

from flask import Flask, g

app = Flask(__name__)

with app.app_context():
    g.etoro_authuser = USERNAME
    from Functions.port.selection import get_portfolio_selection_html, _fetch_rankings
    html = get_portfolio_selection_html()
    cache_set(("portfolio_selection",), html, ext=".html")
    cache_set(("portfolio_selection_my_portfolio", USERNAME), html, ext=".html")

    rankings_cache_key = ("portfolio_selection_rankings",)
    cached_rankings = cache_get(rankings_cache_key, _ETORO_PI_TTL, ext=".pkl")
    merged = []
    if cached_rankings is not None:
        merged = cached_rankings[0] if isinstance(cached_rankings, tuple) else []
    if not merged:
        try:
            merged, _, _, _ = _fetch_rankings()
        except Exception as exc:
            log_info(f"Failed to fetch rankings for top investors JSON: {exc}")

    usernames = []
    for item in merged or []:
        username = str(item.get("userName", item.get("cid", ""))).strip()
        if username:
            usernames.append(username)

    cache_set(("portfolio_selection_top_investors",), usernames, ext=".json", filename="port_top_investors_username.json")
    log_info(f"Cached portfolio selection HTML for user {USERNAME} ({len(html)} chars).")
    log_info(f"Cached {len(usernames)} top investor usernames to port_top_investors_username.json.")

    from Functions.port.main import generate_portfolio_html

    def _cache_report(username: str) -> str:
        cache_key = (
            username.strip().lower(),
            "",
            "",
        )
        if cache_get(cache_key, _REPORT_TTL, ext=".html") is not None:
            return f"skip:{username}"
        try:
            report_html = generate_portfolio_html(etoro_username=username, benchmark_ticker="", etoro_cid="")
            cache_set(cache_key, report_html, ext=".html")
            return f"ok:{username}"
        except Exception as exc:
            log_info(f"Failed to cache report for {username}: {exc}")
            return f"error:{username}"

    if usernames:
        log_info(f"Caching portfolio reports for {len(usernames)} investors...")
        ok = skip = err = 0
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(_cache_report, u): u for u in usernames}
            for future in as_completed(futures):
                res = future.result()
                if res.startswith("ok:"):
                    ok += 1
                elif res.startswith("skip:"):
                    skip += 1
                else:
                    err += 1
        log_info(f"Portfolio report caching complete: {ok} generated, {skip} skipped, {err} errors.")