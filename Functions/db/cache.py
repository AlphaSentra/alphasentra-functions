import base64
import json
import os
import pickle
import random
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from Functions.logging_utils import log_info, log_error

load_dotenv()

_DEFAULT_CACHE_CLIENT_TIMEOUT_MS = 15000
_MAX_BSON_DOCUMENT_SIZE = 14 * 1024 * 1024  # 14MB stays safely under MongoDB 16MB limit


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
            client = MongoClient(uri, serverSelectionTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, connectTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, socketTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS)
            parsed = urlparse(uri)
            db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE_CACHE", "alphasentra-cache")
            db = client[db_name]
            collection = db["function_index_cache"]
            doc = collection.find_one({"_id": "index"})
            if doc and doc.get("value"):
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

    selected_uri = random.choice(uris)
    parsed = urlparse(selected_uri)
    db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE_CACHE", "alphasentra-cache")

    client = None
    try:
        client = MongoClient(selected_uri, serverSelectionTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, connectTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, socketTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS)
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


def _get_cache_db(uri: str):
    parsed = urlparse(uri)
    db_name = (parsed.path or "").lstrip("/") or os.getenv("MONGODB_DATABASE_CACHE", "alphasentra-cache")
    client = MongoClient(uri, serverSelectionTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, connectTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS, socketTimeoutMS=_DEFAULT_CACHE_CLIENT_TIMEOUT_MS)
    return client, client[db_name]


def _serialize_value(value: Any, ext: str = ".html") -> Any:
    if ext == ".json":
        return json.dumps(value)
    elif ext == ".pkl":
        return base64.b64encode(pickle.dumps(value)).decode("ascii")
    return value


def _deserialize_value(value: Any, ext: str = ".html") -> Any:
    if ext == ".json":
        return json.loads(value)
    elif ext == ".pkl":
        return pickle.loads(base64.b64decode(value.encode("ascii")))
    return value


def _get_chunk_ids(doc_id: str, num_chunks: int) -> list:
    return [f"{doc_id}_chunk_{i}" for i in range(num_chunks)]


def _chunk_value(value: str, doc_id: str):
    if len(value) <= _MAX_BSON_DOCUMENT_SIZE:
        return value, None, None

    chunk_size = _MAX_BSON_DOCUMENT_SIZE
    num_chunks = max(1, (len(value) + chunk_size - 1) // chunk_size)
    chunk_ids = _get_chunk_ids(doc_id, num_chunks)
    chunks = [value[i:i + chunk_size] for i in range(0, len(value), chunk_size)]
    return chunks[0], chunk_ids, chunks[1:]


def set_portfolio_cache_to_mongo(collection_name: str, doc_id: str, value: Any, ext: str = ".html", ttl_seconds: int = 86400) -> None:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return

    serialized_value = _serialize_value(value, ext)
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    main_value, chunk_ids, extra_chunks = _chunk_value(serialized_value, doc_id)

    base_payload = {
        "ext": ext,
        "created_at": datetime.utcnow(),
        "expires_at": expires_at,
    }

    if chunk_ids is not None:
        payload = {
            "$set": {
                "chunked": True,
                "chunk_ids": chunk_ids,
                "value": main_value,
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
    for uri in uris:
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            collection.create_index("expires_at", expireAfterSeconds=0)

            if chunk_ids is not None and extra_chunks:
                chunk_operations = [
                    {
                        "update_one": {
                            "filter": {"_id": chunk_id},
                            "update": {"$set": {"value": chunk, "expires_at": expires_at}},
                            "upsert": True,
                        }
                    }
                    for chunk_id, chunk in zip(chunk_ids[1:], extra_chunks)
                ]
                collection.bulk_write([cp["update_one"] for cp in chunk_operations])

            collection.update_one({"_id": doc_id}, payload, upsert=True)
            log_info(f"Cached portfolio data to MongoDB collection={collection_name} id={doc_id}.")
            return
        except PyMongoError as e:
            last_exception = e
            log_error(f"Failed to cache portfolio data to MongoDB uri={uri} collection={collection_name}", "MONGO_CACHE", e)
        finally:
            if client:
                client.close()

    if last_exception is not None:
        log_error(f"Failed to cache portfolio data to MongoDB after trying {len(uris)} URIs collection={collection_name}", "MONGO_CACHE", last_exception)


def delete_portfolio_cache_from_mongo(collection_name: str, doc_id: str) -> None:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return

    last_exception = None
    for uri in uris:
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
            return
        except PyMongoError as e:
            last_exception = e
            log_error(f"Failed to delete portfolio cache from MongoDB uri={uri} collection={collection_name}", "MONGO_CACHE", e)
        finally:
            if client:
                client.close()

    if last_exception is not None:
        log_error(f"Failed to delete portfolio cache from MongoDB after trying {len(uris)} URIs collection={collection_name}", "MONGO_CACHE", last_exception)


def get_portfolio_cache_from_mongo(collection_name: str, doc_id: str, ttl_seconds: int = 86400, ext: str = ".html") -> Optional[Any]:
    mongodb_uri_cache = os.getenv("MONGODB_URI_CACHE", "")
    if not mongodb_uri_cache:
        return None

    uris = [uri.strip() for uri in mongodb_uri_cache.split(",") if uri.strip()]
    if not uris:
        return None

    for uri in uris:
        client = None
        try:
            client, db = _get_cache_db(uri)
            collection = db[collection_name]
            doc = collection.find_one({"_id": doc_id})
            if doc and doc.get("value") is not None:
                if doc.get("chunked"):
                    chunk_ids = doc.get("chunk_ids") or []
                    if not chunk_ids:
                        return None
                    chunks = [doc.get("value", "")]
                    missing = False
                    for chunk_id in chunk_ids[1:]:
                        chunk_doc = collection.find_one({"_id": chunk_id})
                        if chunk_doc and chunk_doc.get("value") is not None:
                            chunks.append(chunk_doc["value"])
                        else:
                            missing = True
                            break
                    if missing:
                        return None
                    reassembled = "".join(chunks)
                    return _deserialize_value(reassembled, doc.get("ext", ext))
                return _deserialize_value(doc["value"], doc.get("ext", ext))
        except PyMongoError:
            continue
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

    return None
