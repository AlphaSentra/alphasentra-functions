import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))

from Functions.logging_utils import log_info, log_error  # noqa: E402
from Functions.db.cache import delete_portfolio_cache_from_mongo


_COLLECTIONS = [
    "portfolio_selection_cache",
    "portfolio_report_cache",
    "yfinance_cache",
    "etoro_cache",
    "function_index_cache",
]


def clear_cache() -> None:
    """Drop all known cache collections from MongoDB.

    Logs the outcome so that Render cron runs and local batch jobs can
    distinguish success from silent failure.
    """
    for collection in _COLLECTIONS:
        try:
            delete_portfolio_cache_from_mongo(collection, "*")
            log_info(f"Cleared MongoDB cache collection: {collection}")
        except Exception as exc:
            log_error(f"Failed to clear MongoDB cache collection {collection}", "CACHE", exc)
            raise


if __name__ == "__main__":
    clear_cache()
