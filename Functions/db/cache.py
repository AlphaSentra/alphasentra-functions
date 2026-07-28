import os
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from Functions.logging_utils import log_info, log_error

load_dotenv()


def get_index_cache_from_mongo() -> Optional[str]:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return None

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return None

    for uri in uris:
        client = None
        try:
            client = MongoClient(uri)
            parsed = urlparse(uri)
            db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE", "alphasentra-cache")
            db = client[db_name]
            collection = db["function_index_cache"]
            doc = collection.find_one({"_id": "index"})
            if doc and doc.get("value"):
                return doc["value"]
        except PyMongoError:
            continue
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    return None


def set_index_cache_to_mongo(value: str, ext: str = ".html", ttl_seconds: int = 86400) -> None:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        raise ValueError("MONGODB_URI_CACHE environment variable is not set")

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        raise ValueError("No valid URIs found in MONGODB_URI_CACHE")

    selected_uri = random.choice(uris)
    parsed = urlparse(selected_uri)
    db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE", "alphasentra-cache")

    client = None
    try:
        client = MongoClient(selected_uri)
        db = client[db_name]
        collection = db["function_index_cache"]

        collection.create_index("expires_at", expireAfterSeconds=0)

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        collection.update_one(
            {"_id": "index"},
            {
                "$set": {
                    "value": value,
                    "ext": ext,
                    "created_at": datetime.utcnow(),
                    "expires_at": expires_at,
                }
            },
            upsert=True,
        )
        log_info(f"Cached index HTML to MongoDB ({len(value)} chars).")
    except PyMongoError as e:
        log_error("Failed to cache index HTML to MongoDB", "MONGO_CACHE", e)
        raise
    finally:
        if client:
            client.close()
