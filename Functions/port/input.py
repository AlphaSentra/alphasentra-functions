"""
Portfolio input handler - form display and request processing.
"""

from flask import request, jsonify # Import jsonify
import logging
from Functions.port.cache import get as cache_get, set as cache_set, exists as cache_exists, _REPORT_TTL
from Functions.port.form import PORTFOLIO_FORM_HTML

logger = logging.getLogger(__name__)

def _get_cached_portfolio_html(etoro_username: str, etoro_cid: str, benchmark_ticker: str) -> str | None:
    """
    Checks if a portfolio report is cached and returns its HTML content.
    """
    if not etoro_username:
        return None
    cache_key = (
        etoro_username.strip().lower(),
        (benchmark_ticker or "").strip().upper(),
        etoro_cid.strip().lower(),
    )
    if not cache_exists(cache_key, _REPORT_TTL, ext=".html"):
        return None
    cached_html = cache_get(cache_key, _REPORT_TTL, ext=".html")
    if cached_html is not None:
        logger.info("Portfolio cache hit username=%s benchmark=%s", etoro_username, benchmark_ticker)
    return cached_html

def get_portfolio_cache_status():
    """
    API endpoint to check if a portfolio report is cached.
    Returns JSON: {"cached": true/false}
    """
    etoro_username = request.form.get("etoro_username", "").strip()
    etoro_cid = request.form.get("etoro_cid", "").strip()
    benchmark_ticker = request.form.get("benchmark_ticker", "").strip()

    if not etoro_username:
        return jsonify({"cached": False})

    cache_key = (
        etoro_username.strip().lower(),
        (benchmark_ticker or "").strip().upper(),
        etoro_cid.strip().lower(),
    )
    is_cached = cache_exists(cache_key, _REPORT_TTL, ext=".html")
    return jsonify({"cached": is_cached})

def handle_portfolio_input():
    etoro_username = ""
    etoro_cid = ""
    benchmark_ticker = ""
    if request.method == "POST":
        etoro_username = request.form.get("etoro_username", "").strip()
        etoro_cid = request.form.get("etoro_cid", "").strip()
        benchmark_ticker = request.form.get("benchmark_ticker", "").strip()
    elif request.args.get("etoro_username"):
        etoro_username = request.args.get("etoro_username", "").strip()
        etoro_cid = request.args.get("etoro_cid", "").strip()
        benchmark_ticker = request.args.get("benchmark_ticker", "").strip()

    if etoro_username:
        # Define cache_key here so it's available for cache_set on a miss
        cache_key = (
            etoro_username.strip().lower(),
            (benchmark_ticker or "").strip().upper(),
            etoro_cid.strip().lower(),
        )

        cached_html = _get_cached_portfolio_html(etoro_username, etoro_cid, benchmark_ticker)
        if cached_html is not None:
            return cached_html
        logger.info("Portfolio cache miss username=%s benchmark=%s", etoro_username, benchmark_ticker)
        from Functions.port.main import generate_portfolio_html
        html = generate_portfolio_html(etoro_username=etoro_username, benchmark_ticker=benchmark_ticker, etoro_cid=etoro_cid)
        cache_set(cache_key, html, ext=".html")
        return html
    return PORTFOLIO_FORM_HTML
