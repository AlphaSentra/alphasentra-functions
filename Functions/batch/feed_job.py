"""Batch feed job runner for executing a sequence of feed-related scripts.

This module defines the execution order for batch scripts that handle eToro
feed data collection, and provides a simple runner to execute them sequentially.
"""

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_ORDER = [
    "clear_feed.py",
    "feed_get_pi.py",
    "feed_get_instruments.py",
    "feed_get_posts_from_pi.py",
    "feed_get_posts_from_instruments.py",
]

SCRIPT_TIMEOUT_SECONDS = 3 * 60 * 60


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {seconds:.0f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {seconds:.0f}s"


def run_script(script_path: Path) -> dict:
    """Execute a single Python script using the current interpreter.

    Args:
        script_path: Absolute path to the Python script to execute.

    Returns:
        dict with keys:
            name: script filename
            status: "ok" | "failed" | "timeout"
            duration_seconds: elapsed wall-clock time
            returncode: process exit code, or None if timed out
    """
    script_name = script_path.name
    start = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            timeout=SCRIPT_TIMEOUT_SECONDS,
        )
        duration = time.perf_counter() - start
        return {
            "name": script_name,
            "status": "ok",
            "duration_seconds": duration,
            "returncode": result.returncode,
        }
    except subprocess.CalledProcessError as exc:
        duration = time.perf_counter() - start
        print(f"\n[ERROR] {script_name} exited with code {exc.returncode}")
        return {
            "name": script_name,
            "status": "failed",
            "duration_seconds": duration,
            "returncode": exc.returncode,
        }
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - start
        print(f"\n[TIMEOUT] {script_name} exceeded {SCRIPT_TIMEOUT_SECONDS}s limit")
        return {
            "name": script_name,
            "status": "timeout",
            "duration_seconds": duration,
            "returncode": None,
        }


PAUSE_SECONDS = 5 * 60


def run_batch() -> bool:
    """Run all batch scripts in the predefined order and return True if all passed."""
    base_dir = Path(__file__).resolve().parent
    started_at = datetime.now(timezone.utc)

    print("=" * 60)
    print(f"Batch job started: {started_at.isoformat()}")
    print(f"Scripts to run: {len(SCRIPT_ORDER)}")
    for idx, script_name in enumerate(SCRIPT_ORDER, 1):
        print(f"  {idx}. {script_name}")
    print("=" * 60)

    results = []
    failed = False
    for script_name in SCRIPT_ORDER:
        script_path = base_dir / script_name
        print(f"\n[RUNNING] {script_name} ...")
        result = run_script(script_path)
        results.append(result)
        status_symbol = "OK" if result["status"] == "ok" else result["status"].upper()
        print(f"[{status_symbol}] {script_name} finished in {_format_duration(result['duration_seconds'])}")
        if result["status"] != "ok":
            failed = True

    finished_at = datetime.now(timezone.utc)
    total_duration = finished_at.timestamp() - started_at.timestamp()

    print("\n" + "=" * 60)
    print("BATCH JOB SUMMARY")
    print("=" * 60)
    print(f"Started : {started_at.isoformat()}")
    print(f"Finished: {finished_at.isoformat()}")
    print(f"Total   : {_format_duration(total_duration)}")
    print()
    for result in results:
        status_symbol = "OK" if result["status"] == "ok" else result["status"].upper()
        print(f"  [{status_symbol:6s}] {result['name']:<30s} {_format_duration(result['duration_seconds']):>10s}")
    print()
    ok_count = sum(1 for r in results if r["status"] == "ok")
    fail_count = len(results) - ok_count
    print(f"Result  : {ok_count} passed, {fail_count} failed out of {len(results)} scripts")
    print("=" * 60)

    return not failed


def main() -> None:
    """Run the batch job indefinitely, pausing between runs."""
    run_number = 0
    while True:
        run_number += 1
        print(f"\n>>> Starting run #{run_number}")
        run_batch()
        print(f"\n[PAUSE] Sleeping for {_format_duration(PAUSE_SECONDS)} before next run...")
        time.sleep(PAUSE_SECONDS)


if __name__ == "__main__":
    main()
