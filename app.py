import os
from urllib.parse import urlparse
from flask import Flask, request, g, jsonify, make_response
from Functions.routes import index, port, register_route, eqs, wcr, cryp, ana, port_cache_status, sel
from Functions.port.config import PARENT_APP_DOMAIN, PARENT_APP_ALLOWED_ORIGINS, LOGIN_REDIRECT_URL
from Functions.port.cache import exists as cache_exists, get as cache_get, _REPORT_TTL, _ETORO_PI_TTL

app = Flask(__name__)

@app.after_request
def _apply_cors_and_auth(response):
    public_paths = (
        '/auth',
        '/etopi/check_cache',
    )
    if request.path in public_paths or request.path.startswith('/static'):
        origin = request.headers.get('Origin')
        if origin:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Max-Age'] = '86400'
    return response

@app.before_request
def _require_etoro_auth():
    public_paths = (
        '/auth',
        '/etopi/check_cache',
        '/test_iframe_auth.html',
    )
    if request.path in public_paths or request.path.startswith('/static'):
        return

    if request.method == 'OPTIONS':
        return make_response('', 204)

    username = request.cookies.get('etoro_authuser', '').strip()
    if not username:
        if request.path == '/etopi' and request.method == 'POST':
            etoro_username = request.form.get('etoro_username', '').strip()
            etoro_cid = request.form.get('etoro_cid', '').strip()
            benchmark_ticker = request.form.get('benchmark_ticker', '').strip()
            if etoro_username:
                cache_key = (
                    etoro_username.strip().lower(),
                    (benchmark_ticker or "").strip().upper(),
                    etoro_cid.strip().lower(),
                )
                if cache_exists(cache_key, _REPORT_TTL, ext=".html"):
                    return

        if request.path == '/port' and request.method == 'GET':
            if cache_exists(("portfolio_selection",), _ETORO_PI_TTL, ext=".html"):
                return

        return _unauthorized_response()

    g.etoro_authuser = username

def _unauthorized_response():
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <script>
        if (window.top !== window.self) {{
            window.top.location.href = "{LOGIN_REDIRECT_URL}";
        }} else {{
            window.location.href = "{LOGIN_REDIRECT_URL}";
        }}
    </script>
</head>
<body>
    <p>Redirecting to login...</p>
    <noscript>
        <meta http-equiv="refresh" content="0;url={LOGIN_REDIRECT_URL}">
        <a href="{LOGIN_REDIRECT_URL}">Click here if not redirected</a>
    </noscript>
</body>
</html>
"""
    return html, 403

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

def _is_allowed_origin():
    origin = request.headers.get('Origin', '')
    if not origin:
        return True
    if origin in PARENT_APP_ALLOWED_ORIGINS:
        return True
    parsed = urlparse(origin)
    hostname = parsed.hostname or ''
    if not hostname:
        return False
    return hostname == PARENT_APP_DOMAIN or hostname.endswith('.' + PARENT_APP_DOMAIN)

@app.route('/auth', methods=['POST', 'OPTIONS'])
def auth():
    if request.method == 'OPTIONS':
        return make_response('', 204)

    if not _is_allowed_origin():
        return jsonify({'ok': False, 'error': 'Unauthorized origin'}), 403

    username = request.form.get('etoro_authuser', '').strip()
    if not username:
        return jsonify({'ok': False, 'error': 'etoro_authuser is required'}), 400

    policy = _get_cookie_policy()
    resp = jsonify({'ok': True})
    resp.set_cookie(
        'etoro_authuser',
        username,
        max_age=86400,
        httponly=False,
        samesite=policy['samesite'],
        secure=policy['secure'],
        path='/'
    )
    return resp

register_route(app, '/', 'Function Index', index)
register_route(app, '/ana', 'Analyse', ana)
register_route(app, '/etopi', 'Portfolio & Risk Analytics', port, methods=['GET', 'POST'], show_in_index=False)
app.route('/etopi/check_cache', methods=['POST'])(port_cache_status)
register_route(app, '/port', 'Portfolio Investor Selection', sel)
register_route(app, '/eqs', 'Stocks AI Screener', eqs)
register_route(app, '/wcr', 'Forex AI Screener', wcr)
register_route(app, '/cryp', 'Cryptocurrency AI Screener', cryp)

@app.route('/test_iframe_auth.html')
def test_iframe_auth_page():
    with open(os.path.join(os.path.dirname(__file__), 'test_iframe_auth.html'), 'r') as f:
        return f.read()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=True)
