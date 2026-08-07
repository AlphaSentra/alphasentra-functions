import os
import time
from typing import Tuple, Dict, Any, List, Optional

from Functions.db.client import DatabaseManager


def get_ticker_by_etoro_symbol(internal_symbol_full: str) -> str:
    if not internal_symbol_full:
        return ""

    try:
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        tickers_collection = db[db_name]["tickers"]
        doc = tickers_collection.find_one(
            {"ticker_etoro": internal_symbol_full},
            {"ticker": 1},
        )
        if doc and doc.get("ticker"):
            return str(doc["ticker"])
    except Exception as exc:
        from Functions.logging_utils import log_error
        log_error("Failed to lookup ticker by eToro symbol", "MONGODB_LOOKUP", exc)

    return internal_symbol_full


def get_ticker_and_name_by_etoro_symbol(internal_symbol_full: str) -> Tuple[str, str]:
    if not internal_symbol_full:
        return "", ""

    try:
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        tickers_collection = db[db_name]["tickers"]
        doc = tickers_collection.find_one(
            {"ticker_etoro": internal_symbol_full},
            {"ticker": 1, "name": 1},
        )
        if doc:
            return str(doc.get("ticker", internal_symbol_full)), str(doc.get("name", ""))
    except Exception as exc:
        from Functions.logging_utils import log_error
        log_error("Failed to lookup ticker/name by eToro symbol", "MONGODB_LOOKUP", exc)

    return internal_symbol_full, ""


def ensure_etoro_pi_indexes(db_name: str, coll) -> None:
    try:
        existing = set(idx["key"] for idx in coll.list_indexes())
        target = {("userName", 1), ("fullName", 1), ("username", 1), ("isPi", 1)}
        if not target.issubset(existing):
            for field in ("userName", "fullName", "username"):
                try:
                    coll.create_index([(field, 1)], background=True)
                except Exception:
                    pass
            try:
                coll.create_index([("userName", 1), ("fullName", 1), ("username", 1)], background=True)
            except Exception:
                pass
    except Exception:
        pass


def search_etoro_pi_db(query: str, limit: int = 20) -> Dict[str, Any]:
    q = query.strip().lower()
    if not q:
        return {"results": []}

    try:
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        coll = db[db_name]["etoro_pi"]
        ensure_etoro_pi_indexes(db_name, coll)

        prefix = {"$regex": f"^{q}", "$options": "i"}
        cursor = coll.find(
            {
                "$or": [
                    {"userName": prefix},
                    {"fullName": prefix},
                    {"username": prefix},
                ]
            },
            {
                "userName": 1,
                "fullName": 1,
                "username": 1,
                "country": 1,
                "gain": 1,
                "copiers": 1,
                "baseLineCopiers": 1,
                "aumTierDesc": 1,
                "avatars": 1,
                "countryId": 1,
                "subType": 1,
            },
        ).limit(limit)

        results = []
        seen = set()
        for doc in cursor:
            username = str(doc.get("userName") or doc.get("username") or "").strip()
            if not username or username.lower() in seen:
                continue
            seen.add(username.lower())

            full_name = str(doc.get("fullName") or "").strip() or None
            avatar_url = None
            avatars = doc.get("avatars") or []
            if isinstance(avatars, list) and avatars:
                avatar_url = avatars[0].get("url") if isinstance(avatars[0], dict) else None

            results.append(
                {
                    "userName": username,
                    "username": username,
                    "fullName": full_name,
                    "displayName": full_name,
                    "avatarUrl": avatar_url,
                    "country": doc.get("country"),
                    "countryId": doc.get("countryId"),
                    "copiers": doc.get("copiers"),
                    "baseLineCopiers": doc.get("baseLineCopiers"),
                    "gain": doc.get("gain"),
                    "aumTierDesc": doc.get("aumTierDesc"),
                    "aumValue": None,
                    "subType": doc.get("subType") or "",
                    "isPi": doc.get("isPi", True),
                }
            )

        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


def get_pro_investor_by_username(username: str) -> Optional[Dict[str, Any]]:
    if not username:
        return None
    try:
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        coll = db[db_name]["etoro_pi"]
        doc = coll.find_one(
            {"userName": {"$regex": f"^{username}$", "$options": "i"}},
            {
                "userName": 1,
                "fullName": 1,
                "username": 1,
                "country": 1,
                "countryId": 1,
                "copiers": 1,
                "baseLineCopiers": 1,
                "gain": 1,
                "aumTierDesc": 1,
                "avatars": 1,
                "subType": 1,
                "userBio": 1,
                "riskScore": 1,
            },
        )
        if not doc:
            return None

        uname = str(doc.get("userName") or doc.get("username") or "").strip()
        full_name = str(doc.get("fullName") or "").strip() or None
        avatar_url = None
        avatars = doc.get("avatars") or []
        if isinstance(avatars, list) and avatars:
            avatar_url = avatars[0].get("url") if isinstance(avatars[0], dict) else None

        return {
            "userName": uname,
            "username": uname,
            "fullName": full_name,
            "displayName": full_name,
            "avatarUrl": avatar_url,
            "country": doc.get("country"),
            "countryId": doc.get("countryId"),
            "copiers": doc.get("copiers"),
            "baseLineCopiers": doc.get("baseLineCopiers"),
            "gain": doc.get("gain"),
            "aumTierDesc": doc.get("aumTierDesc"),
            "aumValue": None,
            "subType": doc.get("subType") or "",
            "isPi": doc.get("isPi", True),
            "aboutMe": (doc.get("userBio") or {}).get("aboutMe"),
            "aboutMeShort": (doc.get("userBio") or {}).get("aboutMeShort"),
            "riskScore": doc.get("riskScore"),
        }
    except Exception:
        return None


def get_ai_settings() -> Optional[Dict[str, Any]]:
    try:
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        settings_collection = db[db_name]["settings"]
        return settings_collection.find_one({"key": "batch_settings", "value": "default"})
    except Exception as e:
        from Functions.logging_utils import log_error
        log_error(f"Error fetching AI settings: {e}", "MONGO_OPERATION", e)
        return None


def increment_ai_prompt_count() -> Optional[str]:
    try:
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        settings_collection = db[db_name]["settings"]

        batch_settings = get_ai_settings()
        if batch_settings:
            current_ai_prompt_count = batch_settings.get("ai_prompt_count", 0)
            max_daily_ai_prompt_count = batch_settings.get("max_daily_ai_prompt_count")

            if max_daily_ai_prompt_count is not None and current_ai_prompt_count >= max_daily_ai_prompt_count:
                error_message = f"Daily AI prompt limit reached ({current_ai_prompt_count}/{max_daily_ai_prompt_count})."
                from Functions.logging_utils import log_error
                log_error(error_message, "AI_PROMPT_LIMIT_REACHED", None)
                return error_message

        settings_collection.update_one(
            {"key": "batch_settings", "value": "default"},
            {"$inc": {"ai_prompt_count": 1}},
        )
        from Functions.logging_utils import log_info
        log_info("Incremented ai_prompt_count in settings collection.")
        return None
    except Exception as e:
        from Functions.logging_utils import log_error
        log_error(f"Error incrementing ai_prompt_count: {e}", "AI_PROMPT_COUNT_INCREMENT", e)
        return str(e)


def lookup_etoro_instrument_symbols(instrument_ids: List[str], symbol_fulls: List[str]) -> Dict[str, str]:
    db_symbol_map: Dict[str, str] = {}
    if not instrument_ids and not symbol_fulls:
        return db_symbol_map

    max_retries = 5
    base_delay = 1

    for attempt in range(max_retries + 1):
        try:
            db = DatabaseManager().get_client()
            db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
            tickers_collection = db[db_name]["tickers"]

            query: Dict[str, Any] = {"$or": []}
            if instrument_ids:
                query["$or"].append({"ticker_etoro": {"$in": instrument_ids}})
            if symbol_fulls:
                query["$or"].append({"ticker_etoro": {"$in": symbol_fulls}})

            cursor = tickers_collection.find(query, {"ticker_etoro": 1, "ticker": 1})
            for doc in cursor:
                key = str(doc.get("ticker_etoro", ""))
                db_ticker = doc.get("ticker")
                if key and db_ticker is not None:
                    db_symbol_map[key] = str(db_ticker)
            return db_symbol_map
        except Exception as exc:
            if attempt < max_retries:
                from Functions.logging_utils import log_warning
                log_warning(
                    f"DB lookup failed for instrument symbols (attempt {attempt + 1}/{max_retries + 1}). Retrying in {base_delay * (2 ** attempt)}s. Error: {exc}",
                    "MONGODB_LOOKUP_RETRY",
                )
                time.sleep(base_delay * (2 ** attempt))
            else:
                from Functions.logging_utils import log_error
                log_error("Failed to lookup eToro instrument symbols from DB after multiple retries", "MONGODB_LOOKUP", exc)
                return db_symbol_map

    return db_symbol_map
