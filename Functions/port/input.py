"""
Portfolio input handler - form display and request processing.
"""

import json
import os
from flask import request, jsonify, make_response
import logging
from Functions.db.cache import get_portfolio_cache_from_mongo, set_portfolio_cache_to_mongo
from Functions.port.config import CACHE_TTL_REPORT as _REPORT_TTL
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

        /* Navigation loading overlay */
        .nav-loading-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 99999;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
        }}

        .nav-loading-overlay.active {{
            opacity: 1;
            pointer-events: auto;
        }}

        .nav-loading-spinner {{
            width: 48px;
            height: 48px;
            border: 4px solid rgba(255, 255, 255, 0.2);
            border-top-color: #fff;
            border-radius: 50%;
            animation: nav-spin 0.8s linear infinite;
        }}

        .nav-loading-text {{
            margin-top: 16px;
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            letter-spacing: 0.05em;
        }}

        @keyframes nav-spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="nav-loading-overlay" id="nav-loading-overlay">
        <div class="nav-loading-spinner"></div>
        <div class="nav-loading-text">Loading...</div>
    </div>
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
    <script>
        (function() {{
            const overlay = document.getElementById('nav-loading-overlay');
            if (!overlay) return;

            function showOverlay() {{
                overlay.classList.add('active');
            }}

            function hideOverlay() {{
                overlay.classList.remove('active');
            }}

            document.addEventListener('click', function(e) {{
                const link = e.target.closest('a');
                if (link && link.href && !link.href.startsWith('javascript:') && !link.target && !link.hasAttribute('download')) {{
                    showOverlay();
                    return;
                }}

                const el = e.target.closest('[onclick]');
                if (el) {{
                    const onclick = (el.getAttribute('onclick') || '');
                    if (onclick.includes('window.location') || onclick.includes('window.top.location')) {{
                        showOverlay();
                        return;
                    }}
                }}

                const btn = e.target.closest('button[type="submit"]');
                if (btn && btn.closest('form')) {{
                    showOverlay();
                }}
            }});

            window.addEventListener('pageshow', function(e) {{
                if (e.persisted) {{
                    hideOverlay();
                }}
            }});

            document.addEventListener('visibilitychange', function() {{
                if (document.visibilityState === 'visible') {{
                    hideOverlay();
                }}
            }});
        }})();
    </script>
</body>
</html>"""


def _user_exists_in_core_db(etoro_username: str) -> bool:
    if not etoro_username:
        return False
    try:
        from Functions.db.client import DatabaseManager
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        coll = db[db_name]["users"]
        username = etoro_username.strip()
        doc = coll.find_one(
            {"etoro_username": {"$regex": f"^{username}$", "$options": "i"}},
            {"_id": 1},
        )
        return doc is not None
    except Exception:
        return False


_USER_NOT_FOUND_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Not Available</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
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
        .message-card {{
          background: #1a1a1a; border: 1px solid #3a2020; border-radius: 12px;
          max-width: 600px; width: 100%; padding: 2.5rem; box-shadow: 0 0 40px rgba(255, 60, 60, 0.08);
        }}
        .message-icon {{ font-size: 2.5rem; margin-bottom: 1rem; }}
        .message-title {{ font-size: 1.4rem; font-weight: 700; color: #ff6b6b; margin-bottom: 0.75rem; letter-spacing: 0.02em; }}
        .message-text {{ font-size: 0.95rem; color: #b0b0b0; line-height: 1.6; margin-bottom: 1.25rem; }}
        .back-link {{ display: inline-block; margin-top: 1.5rem; color: #5ce0d8; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: color 0.2s; }}
        .back-link:hover {{ color: #7fecf5; }}
    
        /* Navigation loading overlay */
        .nav-loading-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 99999;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
        }}

        .nav-loading-overlay.active {{
            opacity: 1;
            pointer-events: auto;
        }}

        .nav-loading-spinner {{
            width: 48px;
            height: 48px;
            border: 4px solid rgba(255, 255, 255, 0.2);
            border-top-color: #fff;
            border-radius: 50%;
            animation: nav-spin 0.8s linear infinite;
        }}

        .nav-loading-text {{
            margin-top: 16px;
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            letter-spacing: 0.05em;
        }}

        @keyframes nav-spin {{
            to {{ transform: rotate(360deg); }}
        }}
</style>
</head>
<body>
    <div class="nav-loading-overlay" id="nav-loading-overlay">
        <div class="nav-loading-spinner"></div>
        <div class="nav-loading-text">Loading...</div>
    </div>

    <div class="animated-gradient-background"></div>
    <div class="form-background-wrapper">
        <div class="form-foreground">
            <div class="message-card">
                <div class="message-icon">&#9888;</div>
                <div class="message-title">Portfolio Not Available</div>
                <div class="message-text">
                    This portfolio has not been analysed yet. It is only reserved for member's portfolio.
                </div>
                <a class="back-link" href="/port">Back to portfolio selection</a>
            </div>
        </div>
    </div>
    <script>
        (function() {{
            const overlay = document.getElementById('nav-loading-overlay');
            if (!overlay) return;

            function showOverlay() {{
                overlay.classList.add('active');
            }}

            function hideOverlay() {{
                overlay.classList.remove('active');
            }}

            document.addEventListener('click', function(e) {{
                const link = e.target.closest('a');
                if (link && link.href && !link.href.startsWith('javascript:') && !link.target && !link.hasAttribute('download')) {{
                    showOverlay();
                    return;
                }}

                const el = e.target.closest('[onclick]');
                if (el) {{
                    const onclick = (el.getAttribute('onclick') || '');
                    if (onclick.includes('window.location') || onclick.includes('window.top.location')) {{
                        showOverlay();
                        return;
                    }}
                }}

                const btn = e.target.closest('button[type="submit"]');
                if (btn && btn.closest('form')) {{
                    showOverlay();
                }}
            }});

            window.addEventListener('pageshow', function(e) {{
                if (e.persisted) {{
                    hideOverlay();
                }}
            }});

            document.addEventListener('visibilitychange', function() {{
                if (document.visibilityState === 'visible') {{
                    hideOverlay();
                }}
            }});
        }})();
    </script>
</body>
</html>"""

_PROCESSING_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Processing</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
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
        .message-card {{
          background: #1a1a1a; border: 1px solid #3a2020; border-radius: 12px;
          max-width: 600px; width: 100%; padding: 2.5rem; box-shadow: 0 0 40px rgba(255, 60, 60, 0.08);
        }}
        .message-icon {{ font-size: 2.5rem; margin-bottom: 1rem; }}
        .message-title {{ font-size: 1.4rem; font-weight: 700; color: #ff6b6b; margin-bottom: 0.75rem; letter-spacing: 0.02em; }}
        .message-text {{ font-size: 0.95rem; color: #b0b0b0; line-height: 1.6; margin-bottom: 1.25rem; }}
        .back-link {{ display: inline-block; margin-top: 1.5rem; color: #5ce0d8; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: color 0.2s; }}
        .back-link:hover {{ color: #7fecf5; }}
    
        /* Navigation loading overlay */
        .nav-loading-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 99999;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
        }}

        .nav-loading-overlay.active {{
            opacity: 1;
            pointer-events: auto;
        }}

        .nav-loading-spinner {{
            width: 48px;
            height: 48px;
            border: 4px solid rgba(255, 255, 255, 0.2);
            border-top-color: #fff;
            border-radius: 50%;
            animation: nav-spin 0.8s linear infinite;
        }}

        .nav-loading-text {{
            margin-top: 16px;
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            letter-spacing: 0.05em;
        }}

        @keyframes nav-spin {{
            to {{ transform: rotate(360deg); }}
        }}
</style>
</head>
<body>
    <div class="nav-loading-overlay" id="nav-loading-overlay">
        <div class="nav-loading-spinner"></div>
        <div class="nav-loading-text">Loading...</div>
    </div>

    <div class="animated-gradient-background"></div>
    <div class="form-background-wrapper">
        <div class="form-foreground">
            <div class="message-card">
                <div class="message-icon">&#8987;</div>
                <div class="message-title">Portfolio Processing</div>
                <div class="message-text">
                    The portfolio for <strong>{username}</strong> is being processed and will be accessible in about 10 to 15 minutes. Please check back later.
                </div>
                <a class="back-link" href="/port">Back to portfolio selection</a>
            </div>
        </div>
    </div>
    <script>
        (function() {{
            const overlay = document.getElementById('nav-loading-overlay');
            if (!overlay) return;

            function showOverlay() {{
                overlay.classList.add('active');
            }}

            function hideOverlay() {{
                overlay.classList.remove('active');
            }}

            document.addEventListener('click', function(e) {{
                const link = e.target.closest('a');
                if (link && link.href && !link.href.startsWith('javascript:') && !link.target && !link.hasAttribute('download')) {{
                    showOverlay();
                    return;
                }}

                const el = e.target.closest('[onclick]');
                if (el) {{
                    const onclick = (el.getAttribute('onclick') || '');
                    if (onclick.includes('window.location') || onclick.includes('window.top.location')) {{
                        showOverlay();
                        return;
                    }}
                }}

                const btn = e.target.closest('button[type="submit"]');
                if (btn && btn.closest('form')) {{
                    showOverlay();
                }}
            }});

            window.addEventListener('pageshow', function(e) {{
                if (e.persisted) {{
                    hideOverlay();
                }}
            }});

            document.addEventListener('visibilitychange', function() {{
                if (document.visibilityState === 'visible') {{
                    hideOverlay();
                }}
            }});
        }})();
    </script>
</body>
</html>"""


def _cache_key(etoro_username, etoro_cid, benchmark_ticker):
    if benchmark_ticker or etoro_cid:
        return f"portfolio_report_{etoro_username.strip().lower()}_{(benchmark_ticker or '').strip().upper()}_{etoro_cid.strip().lower()}"
    return f"portfolio_report_{etoro_username.strip().lower()}"

def _ai_cache_key(etoro_username: str, etoro_cid: str, benchmark_ticker: str) -> str:
    suffix = f"_{(benchmark_ticker or '').strip().upper()}_{(etoro_cid or '').strip().lower()}" if benchmark_ticker or etoro_cid else ""
    return f"portfolio_report_ai_{etoro_username.strip().lower()}{suffix}"

def _get_cached_portfolio_html(etoro_username, etoro_cid, benchmark_ticker):
    if not etoro_username:
        return None
    cache_key = _cache_key(etoro_username, etoro_cid, benchmark_ticker)
    cached_html = get_portfolio_cache_from_mongo("portfolio_report_cache", cache_key, ttl_seconds=_REPORT_TTL, ext=".html")
    if cached_html is not None:
        logger.info("Portfolio cache hit username=%s benchmark=%s", etoro_username, benchmark_ticker)
    return cached_html

def _get_cached_ai_content(etoro_username, etoro_cid, benchmark_ticker):
    if not etoro_username:
        return None
    ai_key = _ai_cache_key(etoro_username, etoro_cid, benchmark_ticker)
    return get_portfolio_cache_from_mongo("portfolio_report_cache", ai_key, ttl_seconds=_REPORT_TTL, ext=".json")

def get_portfolio_cache_status():
    etoro_username = request.form.get("etoro_username", "").strip()
    etoro_cid = request.form.get("etoro_cid", "").strip()
    benchmark_ticker = request.form.get("benchmark_ticker", "").strip()

    if not etoro_username:
        return jsonify({"cached": False})

    cache_key = _cache_key(etoro_username, etoro_cid, benchmark_ticker)
    is_cached = get_portfolio_cache_from_mongo("portfolio_report_cache", cache_key, ttl_seconds=_REPORT_TTL, ext=".html") is not None
    return jsonify({"cached": is_cached})

def handle_portfolio_input():
    etoro_username = ""
    etoro_cid = ""
    benchmark_ticker = ""
    if request.method == "POST":
        etoro_username = request.form.get("etoro_username", "").strip()
        etoro_cid = request.form.get("etoro_cid", "").strip()
        benchmark_ticker = request.form.get("benchmark_ticker", "").strip()
    elif request.method == "GET":
        etoro_username = request.args.get("etoro_username", "").strip()
        etoro_cid = request.args.get("etoro_cid", "").strip()
        benchmark_ticker = request.args.get("benchmark_ticker", "").strip()

    if etoro_username:
        cache_key = _cache_key(etoro_username, etoro_cid, benchmark_ticker)
        cached_html = get_portfolio_cache_from_mongo("portfolio_report_cache", cache_key, ttl_seconds=_REPORT_TTL, ext=".html")
        if cached_html is not None:
            return make_response(cached_html)

        if not _user_exists_in_core_db(etoro_username):
            return make_response(_USER_NOT_FOUND_HTML.format(username=etoro_username))

        return make_response(_PROCESSING_HTML.format(username=etoro_username))

    if request.method == "POST" and etoro_username:
        cache_key = _cache_key(etoro_username, etoro_cid, benchmark_ticker)
        static_key = f"{cache_key}_static"
        ai_key = _ai_cache_key(etoro_username, etoro_cid, benchmark_ticker)

        from Functions.port.main import generate_portfolio_html, merge_static_html_with_ai

        cached_html = _get_cached_portfolio_html(etoro_username, etoro_cid, benchmark_ticker)
        if cached_html is not None:
            cached_ai = _get_cached_ai_content(etoro_username, etoro_cid, benchmark_ticker)
            if cached_ai is None:
                try:
                    html, ai_content = generate_portfolio_html(
                        etoro_username=etoro_username,
                        benchmark_ticker=benchmark_ticker,
                        etoro_cid=etoro_cid,
                        return_ai_content=True,
                    )
                    set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, html, ext=".html", ttl_seconds=_REPORT_TTL)
                    set_portfolio_cache_to_mongo("portfolio_report_cache", ai_key, ai_content, ext=".json", ttl_seconds=_REPORT_TTL)
                    return make_response(html)
                except PortfolioFunctionsError as exc:
                    logger.error("PortfolioFunctionsError while backfilling AI for username=%s: %s", etoro_username, exc)
                except Exception as exc:
                    logger.error("Failed to backfill AI cache for username=%s: %s", etoro_username, exc)
            return make_response(cached_html)

        cached_static = get_portfolio_cache_from_mongo("portfolio_report_cache", static_key, ttl_seconds=_REPORT_TTL, ext=".html")
        cached_ai = _get_cached_ai_content(etoro_username, etoro_cid, benchmark_ticker)

        try:
            if cached_static is not None and cached_ai is not None:
                html = merge_static_html_with_ai(cached_static, cached_ai, etoro_username=etoro_username, benchmark_ticker=benchmark_ticker, etoro_cid=etoro_cid)
                set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, html, ext=".html", ttl_seconds=_REPORT_TTL)
                return make_response(html)

            html, ai_content = generate_portfolio_html(
                etoro_username=etoro_username,
                benchmark_ticker=benchmark_ticker,
                etoro_cid=etoro_cid,
                return_ai_content=True,
            )
            if html is None:
                return make_response("", 204)

            static_html = generate_portfolio_html(
                etoro_username=etoro_username,
                benchmark_ticker=benchmark_ticker,
                etoro_cid=etoro_cid,
                skip_ai=True,
            )
            if static_html is None:
                return make_response("", 204)

            set_portfolio_cache_to_mongo("portfolio_report_cache", static_key, static_html, ext=".html", ttl_seconds=_REPORT_TTL)
            set_portfolio_cache_to_mongo("portfolio_report_cache", ai_key, ai_content, ext=".json", ttl_seconds=_REPORT_TTL)
            set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, html, ext=".html", ttl_seconds=_REPORT_TTL)
            return make_response(html)
        except PortfolioFunctionsError as exc:
            logger.error("PortfolioFunctionsError for username=%s: %s", etoro_username, exc)
            error_html = _ERROR_HTML.format(
                username=etoro_username,
                detail=str(exc).replace("{", "{{").replace("}", "}}"),
            )
            return make_response(error_html)

    if request.method == "GET" and etoro_username:
        if benchmark_ticker or etoro_cid:
            cache_key = f"portfolio_report_{etoro_username.strip().lower()}_{(benchmark_ticker or '').strip().upper()}_{etoro_cid.strip().lower()}"
        else:
            cache_key = f"portfolio_report_{etoro_username.strip().lower()}"
        cached_html = get_portfolio_cache_from_mongo("portfolio_report_cache", cache_key, ttl_seconds=_REPORT_TTL, ext=".html")
        if cached_html is not None:
            logger.info("Portfolio cache hit username=%s benchmark=%s", etoro_username, benchmark_ticker)
            cached_ai = _get_cached_ai_content(etoro_username, etoro_cid, benchmark_ticker)
            if cached_ai is None:
                from Functions.port.main import generate_portfolio_html
                try:
                    html, ai_content = generate_portfolio_html(
                        etoro_username=etoro_username,
                        benchmark_ticker=benchmark_ticker,
                        etoro_cid=etoro_cid,
                        return_ai_content=True,
                    )
                    ai_key = _ai_cache_key(etoro_username, etoro_cid, benchmark_ticker)
                    set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, html, ext=".html", ttl_seconds=_REPORT_TTL)
                    set_portfolio_cache_to_mongo("portfolio_report_cache", ai_key, ai_content, ext=".json", ttl_seconds=_REPORT_TTL)
                    return make_response(html)
                except PortfolioFunctionsError as exc:
                    logger.error("PortfolioFunctionsError while backfilling AI for username=%s: %s", etoro_username, exc)
                except Exception as exc:
                    logger.error("Failed to backfill AI cache for username=%s: %s", etoro_username, exc)
            return make_response(cached_html)

        static_key = f"{cache_key}_static"
        cached_static = get_portfolio_cache_from_mongo("portfolio_report_cache", static_key, ttl_seconds=_REPORT_TTL, ext=".html")
        cached_ai = _get_cached_ai_content(etoro_username, etoro_cid, benchmark_ticker)
        if cached_static is not None and cached_ai is not None:
            from Functions.port.main import merge_static_html_with_ai
            html = merge_static_html_with_ai(cached_static, cached_ai, etoro_username=etoro_username, benchmark_ticker=benchmark_ticker, etoro_cid=etoro_cid)
            set_portfolio_cache_to_mongo("portfolio_report_cache", cache_key, html, ext=".html", ttl_seconds=_REPORT_TTL)
            return make_response(html)

        return PORTFOLIO_FORM_HTML

    if request.method == "GET":
        return PORTFOLIO_FORM_HTML

    return jsonify({'error': 'Unauthorized', 'message': 'Authentication required'}), 403
