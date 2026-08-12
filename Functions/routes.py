import importlib.util
from pathlib import Path
from flask import render_template_string, request

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


def _redirect_html(title: str, message: str, url: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: {font.FONT_PRIMARY};
                background-color: {theme._BG_DEFAULT};
                color: {theme._TEXT_PRIMARY};
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
            }}
            .redirect-container {{
                text-align: center;
            }}
            .spinner {{
                width: 40px;
                height: 40px;
                border: 3px solid rgba(255, 255, 255, 0.2);
                border-top-color: {theme._BRAND_PRIMARY};
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                margin: 0 auto 16px;
            }}
            .message {{
                font-size: 14px;
                color: {theme._TEXT_MUTED};
                margin-bottom: 16px;
            }}
            .fallback-link {{
                color: {theme._BRAND_PRIMARY};
                text-decoration: none;
                font-size: 13px;
            }}
            .fallback-link:hover {{
                text-decoration: underline;
            }}
            @keyframes spin {{
                to {{ transform: rotate(360deg); }}
            }}
        </style>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <div class="redirect-container">
            <div class="spinner"></div>
            <div class="message">{message}</div>
            <a class="fallback-link" href="{url}">Click here if not redirected</a>
        </div>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
        </noscript>
    </body>
    </html>
    """


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
    print("[ROUTE] /port hit, calling cached_portfolio_selection_html()", flush=True)
    
    base_period = request.args.get('period', 'OneMonthAgo')
    sort = request.args.get('sort', '-copiersGain')
    page_size = request.args.get('pageSize', 20, type=int)
    page = request.args.get('page', 1, type=int)
    search_text = request.args.get('searchText', '')
    if search_text:
        search_text = search_text.strip()
    else:
        search_text = None
    
    result = cached_portfolio_selection_html(base_period=base_period, sort=sort, page_size=page_size, page=page, search_text=search_text)
    print(f"[ROUTE] /port returned {len(result)} chars", flush=True)
    return result


def eqs():
    return _redirect_html("EQS Screener", "Redirecting to Screener...", "https://app.alphasentra.com/screener?asset_class=EQ")


def wcr():
    return _redirect_html("WCR Screener", "Redirecting to Screener...", "https://app.alphasentra.com/screener?asset_class=FX")


def ana():
    return _redirect_html("Analyse", "Redirecting to Analyse...", "https://app.alphasentra.com/search")


def cryp():
    return _redirect_html("CRYP Screener", "Redirecting to Screener...", "https://app.alphasentra.com/screener?asset_class=CR")



def register_route(app, path, description, handler, methods=None, show_in_index=True):
    if show_in_index:
        ROUTES.append((path, description))
    app.route(path, methods=methods)(handler)
