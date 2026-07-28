import importlib.util
from pathlib import Path
from flask import render_template_string

base_path = Path(__file__).resolve().parent.parent

theme_path = base_path / "Functions" / "themes" / "theme.py"
theme_spec = importlib.util.spec_from_file_location("theme", theme_path)
theme = importlib.util.module_from_spec(theme_spec)
theme_spec.loader.exec_module(theme)

font_path = base_path / "Functions" / "themes" / "font.py"
font_spec = importlib.util.spec_from_file_location("font", font_path)
font = importlib.util.module_from_spec(font_spec)
font_spec.loader.exec_module(font)

main_path = base_path / "Functions" / "port" / "main.py"
main_spec = importlib.util.spec_from_file_location("main", main_path)
main = importlib.util.module_from_spec(main_spec)
main_spec.loader.exec_module(main)

ROUTES = []

index_template_path = base_path / "Functions" / "index" / "index.html"
with open(index_template_path, 'r') as f:
    _INDEX_HTML = f.read()



from Functions.port.input import handle_portfolio_input, get_portfolio_cache_status # Import get_portfolio_cache_status
from Functions.port.selection import get_portfolio_selection_html, cached_portfolio_selection_html
from Functions.db.cache import get_index_cache_from_mongo


def index():
    cached = get_index_cache_from_mongo()
    if cached is not None:
        return cached
    return render_template_string(_INDEX_HTML, routes=ROUTES, theme=theme, font=font)


def port():
    return handle_portfolio_input()

def port_cache_status(): # New route function
    return get_portfolio_cache_status()

def sel():
    import os as _os
    _debug_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "port_debug.log")
    with open(_debug_path, "a") as _f:
        _f.write("[ROUTE] /port hit\n")
    print("[ROUTE] /port hit, calling cached_portfolio_selection_html()", flush=True)
    result = cached_portfolio_selection_html()
    with open(_debug_path, "a") as _f:
        _f.write(f"[ROUTE] /port returned {len(result)} chars\n")
    print(f"[ROUTE] /port returned {len(result)} chars", flush=True)
    return result


def eqs():
    url = "https://app.alphasentra.com/screener?asset_class=EQ"
    html = f"""
    <html>
    <head>
        <title>EQS Screener</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Screener...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html


def wcr():
    url = "https://app.alphasentra.com/screener?asset_class=FX"
    html = f"""
    <html>
    <head>
        <title>WCR Screener</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Screener...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html


def ana():
    url = "https://app.alphasentra.com/search"
    html = f"""
    <html>
    <head>
        <title>Analyse</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Analyse...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html


def cryp():
    url = "https://app.alphasentra.com/screener?asset_class=CR"
    html = f"""
    <html>
    <head>
        <title>CRYP Screener</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Screener...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html



def register_route(app, path, description, handler, methods=None, show_in_index=True):
    if show_in_index:
        ROUTES.append((path, description))
    app.route(path, methods=methods)(handler)
