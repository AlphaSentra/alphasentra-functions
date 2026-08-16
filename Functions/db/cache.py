import gzip
import json
import os
import pickle
from bson.binary import Binary
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError

from Functions.logging_utils import log_info, log_error, log_warning

load_dotenv()

_DEFAULT_CACHE_CLIENT_TIMEOUT_MS = 15000  # 15s for large payloads / slow network
_MAX_BSON_DOCUMENT_SIZE = 10 * 1024 * 1024


def get_index_cache_from_mongo() -> Optional[str]:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return None

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return None

    for idx, uri in enumerate(uris, start=1):
        log_warning(f"Attempting to read index cache from URI {idx}/{len(uris)}: {uri}", "FALLBACK")
        client = None
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, connectTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, socketTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS)
            parsed = urlparse(uri)
            db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE_CACHE", "alphasentra-cache")
            db = client[db_name]
            collection = db["function_index_cache"]
            doc = collection.find_one({"_id": "index"})
            if doc and doc.get("value") is not None:
                log_warning(f"Successfully read index cache from URI {idx}/{len(uris)}: {uri}", "FALLBACK")
                try:
                    return _deserialize_value(doc["value"], doc.get("ext", ".html"))
                except Exception:
                    return doc["value"]
            log_info(f"Checked index cache at {parsed.hostname} but no cached value found.")
        except PyMongoError as e:
            log_error(f"Failed to read index cache from {uri}", "MONGO_CACHE", e)
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    log_info(f"Index cache not found after checking {len(uris)} Mongo URIs.")
    return None


def set_index_cache_to_mongo(value: str, ext: str = ".html", ttl_seconds: int = 86400) -> None:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        raise ValueError("MONGODB_URI_CACHE environment variable is not set")

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        raise ValueError("No valid URIs found in MONGODB_URI_CACHE")

    serialized_value = _serialize_value(value, ext)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    last_exception = None
    for idx, uri in enumerate(uris, start=1):
        log_warning(f"Attempting to set index cache to URI {idx}/{len(uris)}: {uri}", "FALLBACK")
        client = None
        try:
            parsed = urlparse(uri)
            db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE_CACHE", "alphasentra-cache")
            client = MongoClient(uri, serverSelectionTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, connectTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, socketTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS)
            db = client[db_name]
            collection = db["function_index_cache"]

            collection.create_index("expires_at", expireAfterSeconds=0)

            collection.update_one(
                {"_id": "index"},
                {
                    "$set": {
                        "value": serialized_value,
                        "ext": ext,
                        "created_at": datetime.now(timezone.utc),
                        "expires_at": expires_at,
                    }
                },
                upsert=True,
            )
            log_info(f"Cached index HTML to MongoDB ({len(value)} chars).")
            log_warning(f"Successfully set index cache to URI {idx}/{len(uris)}: {uri}", "FALLBACK")
            return
        except PyMongoError as e:
            last_exception = e
            log_error(f"Failed to cache index HTML to MongoDB uri={uri}", "MONGO_CACHE", e)
        finally:
            if client:
                client.close()

    if last_exception is not None:
        raise last_exception


def _get_cache_db(uri: str):
    parsed = urlparse(uri)
    db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE_CACHE", "alphasentra-cache")
    client = MongoClient(uri, serverSelectionTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, connectTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, socketTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS)
    return client, client[db_name]


def _serialize_value(value: Any, ext: str = ".html") -> bytes:
    if ext == ".json":
        raw = json.dumps(value).encode("utf-8")
        return gzip.compress(raw)
    elif ext == ".pkl":
        raw = pickle.dumps(value)
        return gzip.compress(raw)
    elif ext == ".html":
        raw = value.encode("utf-8")
        return gzip.compress(raw)
    return value


def _deserialize_value(value: Any, ext: str = ".html") -> Any:
    if ext in (".json", ".pkl", ".html"):
        raw_bytes = value if isinstance(value, bytes) else value.binary_data
        raw = gzip.decompress(raw_bytes)
        if ext == ".json":
            return json.loads(raw)
        elif ext == ".pkl":
            return pickle.loads(raw)
        elif ext == ".html":
            return raw.decode("utf-8")
    return value


def _get_chunk_ids(doc_id: str, num_chunks: int) -> list:
    return [f"{doc_id}_chunk_{i}" for i in range(num_chunks)]


def _chunk_value(value: bytes, doc_id: str):
    if len(value) <= _MAX_BSON_DOCUMENT_SIZE:
        return value, None, None

    chunk_size = _MAX_BSON_DOCUMENT_SIZE
    num_chunks = max(1, (len(value) + chunk_size - 1) // chunk_size)
    chunk_ids = _get_chunk_ids(doc_id, num_chunks)
    chunks = [value[i:i + chunk_size] for i in range(0, len(value), chunk_size)]
    return None, chunk_ids, chunks


def set_portfolio_cache_to_mongo(collection_name: str, doc_id: str, value: Any, ext: str = ".html", ttl_seconds: int = 86400) -> None:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return

    serialized_value = _serialize_value(value, ext)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    main_value, chunk_ids, extra_chunks = _chunk_value(serialized_value, doc_id)

    base_payload = {
        "ext": ext,
        "created_at": datetime.now(timezone.utc),
        "expires_at": expires_at,
    }

    if chunk_ids is not None:
        payload = {
            "$set": {
                "chunked": True,
                "chunk_ids": chunk_ids,
                **base_payload,
            }
        }
    else:
        payload = {
            "$set": {
                "value": main_value,
                **base_payload,
            }
        }

    last_exception = None
    for idx, uri in enumerate(uris, start=1):
        log_warning(f"Attempting to cache portfolio data to URI {idx}/{len(uris)}: {uri} collection={collection_name}", "FALLBACK")
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            collection.create_index("expires_at", expireAfterSeconds=0)

            if chunk_ids is not None and extra_chunks:
                chunk_operations = [
                    UpdateOne(
                        {"_id": chunk_id},
                        {"$set": {"value": chunk, "expires_at": expires_at}},
                        upsert=True,
                    )
                    for chunk_id, chunk in zip(chunk_ids, extra_chunks)
                ]
                batch_size = 5
                for i in range(0, len(chunk_operations), batch_size):
                    log_info(f"Caching portfolio data to MongoDB collection={collection_name} id={doc_id} chunked batch {i // batch_size + 1}/{(len(chunk_operations) + batch_size - 1) // batch_size}.")
                    collection.bulk_write(chunk_operations[i:i + batch_size])
            log_info(f"Caching portfolio data to MongoDB collection={collection_name} id={doc_id}.")
            collection.update_one({"_id": doc_id}, payload, upsert=True)
            log_info(f"Cached portfolio data to MongoDB collection={collection_name} id={doc_id}.")
            log_warning(f"Successfully cached portfolio data to URI {idx}/{len(uris)}: {uri} collection={collection_name}", "FALLBACK")
            return
        except PyMongoError as e:
            last_exception = e
            log_error(f"Failed to cache portfolio data to MongoDB uri={uri} collection={collection_name}", "MONGO_CACHE", e)
        finally:
            if client:
                client.close()

    if last_exception is not None:
        raise last_exception


def delete_portfolio_cache_from_mongo(collection_name: str, doc_id: str) -> None:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return

    last_exception = None
    for idx, uri in enumerate(uris, start=1):
        log_warning(f"Attempting to delete portfolio cache from URI {idx}/{len(uris)}: {uri} collection={collection_name}", "FALLBACK")
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            if doc_id == "*":
                collection.delete_many({})
            else:
                doc = collection.find_one({"_id": doc_id})
                if doc and doc.get("chunked"):
                    chunk_ids = doc.get("chunk_ids", [])
                    collection.delete_many({"_id": {"$in": [doc_id] + chunk_ids}})
                else:
                    collection.delete_one({"_id": doc_id})
            log_warning(f"Successfully deleted portfolio cache from URI {idx}/{len(uris)}: {uri} collection={collection_name}", "FALLBACK")
        except PyMongoError as e:
            last_exception = e
            log_error(f"Failed to delete portfolio cache from MongoDB uri={uri} collection={collection_name}", "MONGO_CACHE", e)
        finally:
            if client:
                client.close()

    if last_exception is not None:
        raise last_exception


def get_portfolio_cache_from_mongo(collection_name: str, doc_id: str, ttl_seconds: int = 86400, ext: str = ".html") -> Optional[Any]:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return None

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return None

    for idx, uri in enumerate(uris, start=1):
        log_warning(f"Attempting to read portfolio cache from URI {idx}/{len(uris)}: {uri} collection={collection_name}", "FALLBACK")
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            doc = collection.find_one({"_id": doc_id})
            if doc and doc.get("chunked"):
                chunk_ids = doc.get("chunk_ids") or []
                if not chunk_ids:
                    return None
                chunks = []
                missing = False
                for chunk_id in chunk_ids:
                    chunk_doc = collection.find_one({"_id": chunk_id})
                    if chunk_doc and chunk_doc.get("value") is not None:
                        chunks.append(chunk_doc["value"])
                    else:
                        missing = True
                        break
                if missing:
                    return None
                reassembled = b"".join(bytes(c) for c in chunks)
                log_warning(f"Successfully read portfolio cache from URI {idx}/{len(uris)}: {uri} collection={collection_name}", "FALLBACK")
                return _deserialize_value(reassembled, doc.get("ext", ext))

            if doc and doc.get("value") is not None:
                log_warning(f"Successfully read portfolio cache from URI {idx}/{len(uris)}: {uri} collection={collection_name}", "FALLBACK")
                return _deserialize_value(doc["value"], doc.get("ext", ext))
            log_info(f"Portfolio cache not found at URI {idx}/{len(uris)}: {uri} collection={collection_name}")
        except PyMongoError:
            continue
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    return None


def get_report_retry_count(collection_name: str, doc_id: str) -> int:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return 0

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return 0

    max_count = 0
    for uri in uris:
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            doc = collection.find_one({"_id": doc_id}, {"retry_count": 1})
            if doc and doc.get("retry_count"):
                max_count = max(max_count, int(doc["retry_count"]))
        except PyMongoError:
            continue
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    return max_count


def increment_report_retry_count(collection_name: str, doc_id: str) -> int:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return 0

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return 0

    new_count = 0
    for uri in uris:
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            result = collection.update_one(
                {"_id": doc_id},
                {"$inc": {"retry_count": 1}},
                upsert=True,
            )
            if result.upserted_id is not None:
                new_count = max(new_count, 1)
            else:
                new_count = max(new_count, (result.modified_count or 0) + 1)
        except PyMongoError as e:
            log_error(f"Failed to increment report retry count for uri={uri} collection={collection_name} doc_id={doc_id}", "MONGO_CACHE", e)
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    return new_count


def reset_report_retry_count(collection_name: str, doc_id: str) -> None:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return

    for uri in uris:
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            collection.update_one(
                {"_id": doc_id},
                {"$unset": {"retry_count": ""}},
            )
        except PyMongoError as e:
            log_error(f"Failed to reset report retry count for uri={uri} collection={collection_name} doc_id={doc_id}", "MONGO_CACHE", e)
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
