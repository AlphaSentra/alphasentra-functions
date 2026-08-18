"""Batch worker to remove duplicated documents from ``etoro_unmapped_instruments``.

A document is considered a duplicate when another document exists with the
same ``username`` and ``instrument_id``.  For each duplicate group the
document with the most recent ``detected_at`` timestamp is kept; all others
are deleted.  When ``detected_at`` is equal across duplicates the one with
the highest ``_id`` is retained (insertion order tie-break).

Environment variables:
    MONGODB_URI_LOGS        - MongoDB connection URI for the logs database.
    MONGODB_DATABASE_LOGS   - Logs database name (default: alphasentra-logs).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "Functions"))

from Functions.logging_utils import log_info, log_warning, log_error  # noqa: E402
from Functions.db.client import get_logs_client  # noqa: E402

_COLLECTION = "etoro_unmapped_instruments"
_BATCH_SIZE = 1000


def _remove_duplicates() -> int:
    """Delete duplicate documents from ``etoro_unmapped_instruments``.

    Groups documents by ``(username, instrument_id)`` and retains the one
    with the latest ``detected_at`` value (highest ``_id`` as tie-break).
    All other documents in the same group are removed.

    Returns:
        Total number of documents deleted.
    """
    logs_client, logs_db_name = get_logs_client()
    try:
        db = logs_client[logs_db_name]
        collection = db[_COLLECTION]

        pipeline = [
            {
                "$sort": {
                    "username": 1,
                    "instrument_id": 1,
                    "detected_at": -1,
                    "_id": -1,
                }
            },
            {
                "$group": {
                    "_id": {"username": "$username", "instrument_id": "$instrument_id"},
                    "kept_id": {"$first": "$_id"},
                }
            },
            {"$project": {"_id": 0, "kept_id": 1}},
        ]

        cursor = collection.aggregate(pipeline, allowDiskUse=True)
        keep_ids = [doc["kept_id"] for doc in cursor]

        if not keep_ids:
            log_info("No documents found in %s; nothing to deduplicate." % _COLLECTION)
            return 0

        log_info("Scanned %s; %d unique (username, instrument_id) groups identified." % (_COLLECTION, len(keep_ids)))

        total_deleted = 0
        for i in range(0, len(keep_ids), _BATCH_SIZE):
            batch = keep_ids[i : i + _BATCH_SIZE]
            result = collection.delete_many({"_id": {"$nin": batch}})
            total_deleted += result.deleted_count
            log_info(
                "Deleted %d duplicate documents (batch %d/%d)."
                % (result.deleted_count, i // _BATCH_SIZE + 1, -(-len(keep_ids) // _BATCH_SIZE))
            )

        return total_deleted
    finally:
        logs_client.close()


def main() -> None:
    """Entry point: remove duplicates and report the outcome."""
    try:
        log_info("Starting duplicate removal for %s..." % _COLLECTION)
        deleted = _remove_duplicates()
        log_info("Duplicate removal complete. Deleted %d documents from %s." % (deleted, _COLLECTION))
    except (PyMongoError, EnvironmentError) as exc:
        log_error("Failed to remove duplicates from %s" % _COLLECTION, "BATCH", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
