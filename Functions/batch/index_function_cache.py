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
import Functions.routes as routes_mod

html_index_rows = [
    ("/", "Function Index"),
    ("/ana", "Analyse"),
    ("/port", "Portfolio Investor Selection"),
    ("/eqs", "Stocks AI Screener"),
    ("/wcr", "Forex AI Screener"),
    ("/cryp", "Cryptocurrency AI Screener"),
]
routes_mod.ROUTES += html_index_rows

from flask import Flask

app = Flask(__name__)

with app.app_context():
    html = routes_mod.index()
    cache_set(("index",), html, ext=".html")
    log_info(f"Cached index HTML ({len(html)} chars).")
