import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))
sys.path.insert(0, str(_ROOT / "Functions" / "port"))

from Functions.logging_utils import log_info
from Functions.port.cache import set as cache_set
from Functions.port.config import CACHE_TTL_ETORO_PI as _ETORO_PI_TTL

USERNAME = "etoroteam"

from flask import Flask, g

app = Flask(__name__)

with app.app_context():
    g.etoro_authuser = USERNAME
    from Functions.port.selection import get_portfolio_selection_html
    html = get_portfolio_selection_html()
    cache_set(("portfolio_selection",), html, ext=".html")
    cache_set(("portfolio_selection_my_portfolio", USERNAME), html, ext=".html")
    log_info(f"Cached portfolio selection HTML for user {USERNAME} ({len(html)} chars).")