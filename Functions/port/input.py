"""
Portfolio input handler - form display and request processing.
"""

import json
import time
from flask import request, jsonify, make_response
import logging
from Functions.port.cache import get as cache_get, set as cache_set, exists as cache_exists, _REPORT_TTL
from Functions.port.form import PORTFOLIO_FORM_HTML
from Functions.port.engine.analyzer import PortfolioFunctionsError

logger = logging.getLogger(__name__)

_ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Function - Error</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <style>
        @keyframes fade-in {{ 0%, 100% {{ opacity: 0; }} 50% {{ opacity: 1; }} }}
        @keyframes fade-out {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0; }} }}
        .animated-gradient-background {{
          position: absolute; top: 0; left: 0; width: 100%; height: 100%;
          background-color: #000; z-index: 0;
        }}
        .animated-gradient-background::before,
        .animated-gradient-background::after {{
          content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
          background-size: 100% 100%; background-repeat: no-repeat;
        }}
        .animated-gradient-background::before {{
          background-image: radial-gradient(ellipse 80% 50% at 50% 120%, rgba(180, 50, 50, 0.4), transparent);
          animation: fade-out 10s infinite;
        }}
        .animated-gradient-background::after {{
          background-image: radial-gradient(ellipse 80% 50% at 50% 120%, rgba(255, 100, 50, 0.3), transparent);
          animation: fade-in 10s infinite;
        }}
        body {{ margin: 0; padding: 0; font-family: 'Inter', system-ui, -apple-system, sans-serif; background-color: #000; color: #e0e0e0; }}
        .form-background-wrapper {{ position: relative; min-height: 100vh; overflow: hidden; background-color: #000; }}
        .form-foreground {{ position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 2rem; box-sizing: border-box; }}
        .error-card {{
          background: #1a1a1a; border: 1px solid #3a2020; border-radius: 12px;
          max-width: 600px; width: 100%; padding: 2.5rem; box-shadow: 0 0 40px rgba(255, 60, 60, 0.08);
        }}
        .error-icon {{ font-size: 2.5rem; margin-bottom: 1rem; }}
        .error-title {{ font-size: 1.4rem; font-weight: 700; color: #ff6b6b; margin-bottom: 0.75rem; letter-spacing: 0.02em; }}
        .error-message {{ font-size: 0.95rem; color: #b0b0b0; line-height: 1.6; margin-bottom: 1.25rem; }}
        .error-details {{ font-size: 0.8rem; color: #777; background: #111; padding: 0.75rem 1rem; border-radius: 6px; border: 1px solid #2a2a2a; word-break: break-word; white-space: pre-wrap; font-family: 'Courier New', monospace; }}
        .back-link {{ display: inline-block; margin-top: 1.5rem; color: #5ce0d8; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: color 0.2s; }}
        .back-link:hover {{ color: #7fecf5; }}
    </style>
</head>
<body>
    <div class="animated-gradient-background"></div>
    <div class="form-background-wrapper">
        <div class="form-foreground">
            <div class="error-card">
                <div class="error-icon">&#9888;</div>
                <div class="error-title">Portfolio Report Failed to Generate</div>
                <div class="error-message">
                    The eToro portfolio for username <strong>{username}</strong> could not be loaded.
                    This is usually caused by an invalid or non-existent eToro username, or a temporary issue with the eToro API.
                    Please verify the username and try again.
                </div>
                <div class="error-details">{detail}</div>
                <a class="back-link" href="/port">Back to portfolio selection</a>
            </div>
        </div>
    </div>
</body>
</html>"""

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

def _get_cookie_policy():
    origin = request.headers.get('Origin', '')
    if origin:
        try:
            target = request.host_url.rstrip('/')
            same = origin == target or origin == target.replace('http://', 'https://')
            if same:
                return {'samesite': 'Lax', 'secure': False}
            return {'samesite': 'None', 'secure': True}
        except Exception:
            pass
    return {'samesite': 'Lax', 'secure': False}

def handle_portfolio_input():
    etoro_username = ""
    etoro_cid = ""
    benchmark_ticker = ""
    if request.method == "POST":
        etoro_username = request.form.get("etoro_username", "").strip()
        etoro_cid = request.form.get("etoro_cid", "").strip()
        benchmark_ticker = request.form.get("benchmark_ticker", "").strip()

    if request.method == "POST" and etoro_username:
        cache_key = (
            etoro_username.strip().lower(),
            (benchmark_ticker or "").strip().upper(),
            etoro_cid.strip().lower(),
        )

        cached_html = _get_cached_portfolio_html(etoro_username, etoro_cid, benchmark_ticker)
        if cached_html is not None:
            policy = _get_cookie_policy()
            payload = json.dumps({'u': etoro_username, 'ts': time.time()})
            resp = make_response(cached_html)
            resp.set_cookie('etoro_authuser', payload, max_age=86400,
                            httponly=False, samesite=policy['samesite'], secure=policy['secure'], path='/')
            return resp

        from Functions.port.main import generate_portfolio_html
        try:
            html = generate_portfolio_html(etoro_username=etoro_username,
                                           benchmark_ticker=benchmark_ticker,
                                           etoro_cid=etoro_cid)
        except PortfolioFunctionsError as exc:
            logger.error("PortfolioFunctionsError for username=%s: %s", etoro_username, exc)
            error_html = _ERROR_HTML.format(
                username=etoro_username,
                detail=str(exc).replace("{", "{{").replace("}", "}}"),
            )
            return make_response(error_html)
        cache_set(cache_key, html, ext=".html")
        policy = _get_cookie_policy()
        payload = json.dumps({'u': etoro_username, 'ts': time.time()})
        resp = make_response(html)
        resp.set_cookie('etoro_authuser', payload, max_age=86400,
                        httponly=False, samesite=policy['samesite'], secure=policy['secure'], path='/')
        return resp

    if request.method == "GET":
        return PORTFOLIO_FORM_HTML

    return jsonify({'error': 'Unauthorized', 'message': 'Authentication required'}), 403
