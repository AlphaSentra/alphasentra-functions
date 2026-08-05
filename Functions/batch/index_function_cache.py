import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))

from Functions.db.cache import set_index_cache_to_mongo
from Functions.logging_utils import log_info
from Functions.port.config import CACHE_TTL_ETORO_PI as _INDEX_TTL
import Functions.routes as routes_mod

html_index_rows = [
    ("/", "Function Index"),
    ("/ana", "Analyse"),
    ("/port", "Portfolio & Risk Analytics"),
    ("/eqs", "Stocks AI Screener"),
    ("/wcr", "Forex AI Screener"),
    ("/cryp", "Cryptocurrency AI Screener"),
]
routes_mod.ROUTES += html_index_rows

from flask import Flask

app = Flask(__name__)

with app.app_context():
    html = routes_mod.index()
    set_index_cache_to_mongo(html, ext=".html", ttl_seconds=_INDEX_TTL)
    log_info(f"Cached index HTML ({len(html)} chars).")
