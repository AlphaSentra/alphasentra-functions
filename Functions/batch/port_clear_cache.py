from pathlib import Path
import shutil


def clear_cache() -> None:
		"""Remove the .cache directory from the current working directory."""
		cache_dir = Path(__file__).resolve().parent.parent / "port" / ".cache"
		if cache_dir.is_dir():
				shutil.rmtree(cache_dir)


if __name__ == "__main__":
	clear_cache()
