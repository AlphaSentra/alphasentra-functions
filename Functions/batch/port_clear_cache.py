import sys
from pathlib import Path
import shutil

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))

from Functions.logging_utils import log_info, log_error  # noqa: E402


def clear_cache() -> None:
    """Remove the .cache directory from the project tree.

    Logs the outcome so that Render cron runs and local batch jobs can
    distinguish success from silent failure.
    """
    cache_dir = _HERE.parent.parent.parent / ".cache"
    try:
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
            log_info(f"Cleared cache directory: {cache_dir}")
        else:
            log_info(f"Cache directory does not exist, nothing to clear: {cache_dir}")
    except Exception as exc:
        log_error(f"Failed to clear cache directory {cache_dir}", "CACHE", exc)
        raise


if __name__ == "__main__":
    clear_cache()
