import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))

from Functions.db.cache import set_index_cache_to_mongo
from Functions.logging_utils import log_info
from Functions.config import CACHE_TTL_ETORO_PI as _INDEX_TTL
from Functions.routes import register_all_routes

from flask import Flask

app = Flask(__name__)

# Populate the Function Index route metadata without binding to a Flask
# app. Passing ``None`` means the routes are recorded in ``ROUTES`` but
# not added to any running server instance.
register_all_routes(None)

with app.app_context():
    from Functions.routes import index
    html = index()
    set_index_cache_to_mongo(html, ext=".html", ttl_seconds=_INDEX_TTL)
    log_info(f"Cached index HTML ({len(html)} chars).")
