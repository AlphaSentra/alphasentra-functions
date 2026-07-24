import json
import os
import sys
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from Functions.port.cache import get as cache_get, set as cache_set
from Functions.port.config import CACHE_TTL_ETORO as _ETORO_TTL

_current_dir = Path(__file__).resolve().parent
_parent_dir = _current_dir.parent
if str(_parent_dir) not in sys.path:
    sys.path.append(str(_parent_dir))

try:
    from helpers import DatabaseManager
except ImportError:
    DatabaseManager = None

from .auth import public_api_session, get_random_private_key
from .models import (
    EToroAggregatedPosition,
    EToroGainHistory,
    EToroGainPoint,
    EToroInvestorPortfolio,
    EToroPortfolioPosition,
    EToroTradeHistory,
    EToroTradeRecord,
    EToroUser,
    EToroUserLookupResult,
)

_INSTRUMENT_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / ".etoro_instrument_cache.json"
_INSTRUMENT_CACHE_TTL = 24 * 60 * 60
_ETORO_MAX_RETRIES = 10
_ETORO_STALE_TTL = 24 * 60 * 60
_ETORO_PAUSE_AFTER_API_CALLS = 250
_ETORO_PAUSE_DURATION_SECONDS = 60

_etoro_api_call_count = 0
_etoro_api_lock = threading.Lock()

_ETORO_PUBLIC_API_BASE = "https://public-api.etoro.com"
_ETORO_SAPI_BASE = "https://www.etoro.com/sapi"

_ETORO_ENDPOINT_USER_INFO = f"{_ETORO_PUBLIC_API_BASE}/api/v1/user-info/people"
_ETORO_ENDPOINT_DAILY_GAIN = f"{_ETORO_PUBLIC_API_BASE}/api/v1/user-info/people/{{username}}/daily-gain"
_ETORO_ENDPOINT_PORTFOLIO_LIVE = f"{_ETORO_PUBLIC_API_BASE}/api/v1/user-info/people/{{username}}/portfolio/live"
_ETORO_ENDPOINT_PEOPLE_SEARCH = f"{_ETORO_PUBLIC_API_BASE}/api/v1/user-info/people/search"
_ETORO_ENDPOINT_MARKET_DATA_SEARCH = f"{_ETORO_PUBLIC_API_BASE}/api/v1/market-data/search"
_ETORO_ENDPOINT_PORTFOLIO_RANKINGS = f"{_ETORO_PUBLIC_API_BASE}/api/v2/portfolios/{{username}}/rankings"
_ETORO_ENDPOINT_TRADE_HISTORY = f"{_ETORO_SAPI_BASE}/trade-data-real/history/public/credit/flat"


def _maybe_pause_after_api_call() -> None:
    global _etoro_api_call_count
    with _etoro_api_lock:
        _etoro_api_call_count += 1
        if _etoro_api_call_count >= _ETORO_PAUSE_AFTER_API_CALLS:
            _etoro_api_call_count = 0
            logger.info(
                "Pausing eToro API calls for %ds after %d requests...",
                _ETORO_PAUSE_DURATION_SECONDS,
                _ETORO_PAUSE_AFTER_API_CALLS,
            )
            time.sleep(_ETORO_PAUSE_DURATION_SECONDS)


def _session_get_with_retry(session_factory, url: str, **kwargs) -> requests.Response:
    max_retries = _ETORO_MAX_RETRIES
    base_delay = 2.0
    last_status = None
    last_body_preview = ""
    for attempt in range(max_retries):
        session = session_factory()
        try:
            resp = session.get(url, **kwargs)
        except requests.RequestException:
            _maybe_pause_after_api_call()
            raise
        _maybe_pause_after_api_call()
        try:
            if resp.status_code == 401:
                logger.warning("eToro API 401 on attempt %d for %s", attempt + 1, url)
            elif 200 <= resp.status_code < 300:
                return resp
            else:
                last_status = resp.status_code
                try:
                    body = resp.json()
                    last_body_preview = str(body)[:200]
                except Exception:
                    last_body_preview = resp.text[:200]
                logger.warning(
                    "eToro API HTTP %d on attempt %d for %s body=%s",
                    last_status, attempt + 1, url, last_body_preview,
                )
        except requests.RequestException as exc:
            logger.warning("eToro API error on attempt %d for %s: %s", attempt + 1, url, exc)
            if attempt == max_retries - 1:
                raise EToroClientError(
                    f"GET {url} failed after {max_retries} attempts: {exc}"
                ) from exc
        if attempt < max_retries - 1:
            delay = base_delay * (1.1 ** attempt) + __import__('random').uniform(0, 1.0)
            logger.info("Retrying %s in %.1fs...", url, delay)
            time.sleep(delay)
    raise EToroClientError(
        f"GET {url} failed after {max_retries} attempts: "
        f"last_status={last_status}, body={last_body_preview!r}",
        status_code=last_status,
    )


def _load_instrument_cache() -> Dict[str, Dict[str, str]]:
    if not _INSTRUMENT_CACHE_PATH.exists():
        return {}
    try:
        with open(_INSTRUMENT_CACHE_PATH, "r", encoding="utf-8") as f:
            cache: Dict[str, Any] = json.load(f)
        now = time.time()
        return {k: v for k, v in cache.items() if now - v.get("_ts", 0) < _INSTRUMENT_CACHE_TTL}
    except Exception:
        return {}


def _save_instrument_cache(metadata: Dict[str, Dict[str, str]]) -> None:
    try:
        cache = _load_instrument_cache()
        for k, v in metadata.items():
            cache[k] = {"_ts": time.time(), **v}
        with open(_INSTRUMENT_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception as exc:
        logger.debug("Failed to save instrument metadata cache: %s", exc)


def _fetch_instrument_metadata(session: requests.Session, search_url: str, iid: str) -> Optional[Dict[str, str]]:
    try:
        resp = session.get(search_url, params={"instrumentId": iid}, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return None
        item = items[0]
        symbol = item.get("internalSymbolFull") or item.get("internalSymbol") or item.get("symbol")
        if isinstance(symbol, str) and symbol.endswith(".RTH"):
            symbol = symbol[:-4]
        name = (
            item.get("internalInstrumentDisplayName")
            or item.get("displayname")
            or item.get("displayName")
            or item.get("instrumentDisplayName")
            or item.get("name")
            or item.get("instrumentName")
            or item.get("title")
            or ""
        )
        if symbol:
            return {"symbol": str(symbol), "name": str(name)}
    except Exception as exc:
        logger.debug("Failed to resolve instrument %s: %s", iid, exc)
    return None


logger = logging.getLogger(__name__)


class EToroClientError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class ETPublicClient:
    def __init__(self, api_key: str, user_key: str, *, timeout: int = 30):
        self._api_key = api_key
        self._user_key = user_key
        self._timeout = timeout

    def get_investor_gain_timeseries(
        self,
        username: str,
        granularity: str,
        *,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
        count: Optional[int] = None,
    ) -> EToroGainHistory:
        """
        Fetch public gain time-series for an investor.

        GET https://public-api.etoro.com/api/v1/user-info/people/{username}/daily-gain

        Args:
            username: eToro username to query.
            granularity: ``Daily`` or ``Period``. Daily returns individual data points;
                Period returns aggregated period statistics.
            min_date: Optional inclusive start date filter (``YYYY-MM-DD``).
            max_date: Optional inclusive end date filter (``YYYY-MM-DD``).
            count: Ignored when ``granularity`` is ``Daily``.

        Returns:
            EToroGainHistory containing ``username``, ``granularity``,
            ``total_gain`` (decimal fraction), and a list of ``EToroGainPoint``
            with ``timestamp``/``gain`` pairs.

        Raises:
            EToroClientError: If the request fails or returns a non-2xx status.
        """
        cache_key = ("gains", username, granularity, min_date, max_date)
        cached = cache_get(cache_key, _ETORO_TTL, ext=".pkl")
        if cached is not None:
            return cached
        granularity = granularity.capitalize()
        if granularity not in {"Daily", "Period"}:
            raise ValueError("granularity must be one of: Daily, Period")

        url = _ETORO_ENDPOINT_DAILY_GAIN.format(username=username)

        params: Dict[str, Any] = {"type": granularity}
        if min_date:
            params["minDate"] = min_date
        if max_date:
            params["maxDate"] = max_date

        req = requests.Request("GET", url, params=params)
        _preview_session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)
        prepared = _preview_session.prepare_request(req)
        logger.info("EToro request URL: %s", prepared.url)

        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET gain time-series failed: {exc}") from exc

        if not isinstance(data, list):
            if isinstance(data, dict):
                data = data.get("dailyExample", data.get("daily", []))
            else:
                data = []

        gains = []
        for point in data:
            if not isinstance(point, dict):
                continue
            raw_timestamp = point.get("timestamp") or point.get("date")
            raw_gain = point.get("gain")
            if raw_timestamp is None or raw_gain is None:
                continue
            parsed_date = _parse_date(raw_timestamp)
            if parsed_date is None:
                continue
            gains.append(EToroGainPoint(date=parsed_date, gain=float(raw_gain)))

        total_gain = gains[-1].gain if gains else None

        result = EToroGainHistory(
            username=username,
            granularity=granularity,
            total_gain=total_gain,
            gains=gains,
        )
        cache_set(cache_key, result, ext=".pkl")
        return result

    def get_investor_portfolio(self, username: str) -> EToroInvestorPortfolio:
        """
        Fetch live open portfolio positions for a Popular Investor and match symbols.
        """
        cache_key = ("portfolio", username)
        cached = cache_get(cache_key, _ETORO_TTL, ext=".pkl")
        if cached is not None:
            return cached
        stale = cache_get(cache_key, _ETORO_STALE_TTL, ext=".pkl")
        url = _ETORO_ENDPOINT_PORTFOLIO_LIVE.format(username=username)

        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except EToroClientError:
            if stale is not None:
                logger.warning("Live portfolio API failed for %s; using stale cache", username)
                return stale
            raise
        except requests.RequestException as exc:
            if stale is not None:
                logger.warning("Live portfolio API error for %s (%s); using stale cache", username, exc)
                return stale
            raise EToroClientError(f"GET investor portfolio failed: {exc}") from exc

        raw_positions = data.get("positions", [])
        if not raw_positions:
            empty_result = EToroInvestorPortfolio(username=username, positions=[])
            cache_set(cache_key, empty_result, ext=".pkl")
            return empty_result

        # Extract unique instrument IDs
        instrument_ids = list({str(item["instrumentId"]) for item in raw_positions if item.get("instrumentId")})

        # --- 2. Identify symbols directly from eToro search API ---
        etoro_symbol_map: Dict[str, str] = {}
        try:
            metadata = self.resolve_instrument_metadata(instrument_ids)
            etoro_symbol_map = {
                iid: meta["symbol"]
                for iid, meta in metadata.items()
                if meta.get("symbol")
            }
        except Exception as exc:
            logger.warning("Failed to resolve live symbols from eToro search API: %s", exc)

        # --- 3. Pull from MongoDB and compare fields ---
        db_symbol_map: Dict[str, str] = {}
        instrument_ids = list({str(item["instrumentId"]) for item in raw_positions if item.get("instrumentId")})
        symbol_fulls = list({v for v in etoro_symbol_map.values() if v})
        if DatabaseManager is not None and (instrument_ids or symbol_fulls):
            try:
                db = DatabaseManager().get_client()
                db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
                tickers_collection = db[db_name]["tickers"]

                query = {"$or": []}
                if instrument_ids:
                    query["$or"].append({"ticker_etoro": {"$in": instrument_ids}})
                if symbol_fulls:
                    query["$or"].append({"ticker_etoro": {"$in": symbol_fulls}})

                cursor = tickers_collection.find(
                    query,
                    {"ticker_etoro": 1, "ticker": 1},
                )
                for doc in cursor:
                    key = str(doc.get("ticker_etoro", ""))
                    db_ticker = doc.get("ticker")
                    if key and db_ticker is not None:
                        db_symbol_map[key] = str(db_ticker)

                        matched_symbol = etoro_symbol_map.get(key)
                        if matched_symbol and matched_symbol != str(db_ticker):
                            logger.info(
                                f"Symbol mismatch for key '{key}': "
                                f"eToro says '{matched_symbol}', DB mapping says '{db_ticker}'. "
                                f"Using DB canonical ticker '{db_ticker}'."
                            )
            except Exception as exc:
                logger.warning("Failed to lookup eToro instrument symbols from DB: %s", exc)

        # --- 4. Build positions list with a progressive fallback chain ---
        positions = []
        for item in raw_positions:
            iid = str(item.get("instrumentId", ""))
            symbol_full = etoro_symbol_map.get(iid)

            resolved_symbol = None
            if symbol_full and symbol_full in db_symbol_map:
                resolved_symbol = db_symbol_map[symbol_full]
            elif iid in db_symbol_map:
                resolved_symbol = db_symbol_map[iid]

            if isinstance(resolved_symbol, str) and resolved_symbol.endswith(".RTH"):
                resolved_symbol = resolved_symbol[:-4]

            if resolved_symbol is None:
                logger.warning(
                    "No DB mapping for instrumentId=%s or symbol_full=%s; "
                    "position will be skipped (tickers.ticker is mandatory).",
                    iid, symbol_full,
                )
                continue

            logger.info(
                "Resolved instrumentId=%s symbol_full=%s -> canonical ticker=%s",
                iid, symbol_full, resolved_symbol,
            )
    
            positions.append(
                EToroPortfolioPosition(
                    position_id=str(item.get("positionId", "")),
                    instrument_id=iid,
                    symbol=resolved_symbol,
                    symbol_full=etoro_symbol_map.get(iid),
                    display_name=None,
                    open_timestamp=_parse_time(item.get("openTimestamp")),
                    open_rate=_safe_float(item.get("openRate")),
                    is_buy=bool(item.get("isBuy", True)),
                    leverage=_safe_float(item.get("leverage"), default=1.0),
                    take_profit_rate=_safe_float(item.get("takeProfitRate")),
                    stop_loss_rate=_safe_float(item.get("stopLossRate")),
                    investment_pct=_safe_float(item.get("investmentPct")),
                    net_profit=_safe_float(item.get("netProfit")),
                )
            )

        aggregated: Dict[str, Dict[str, Any]] = {}
        for pos in positions:
            if not pos.symbol:
                continue
            sym = pos.symbol
            pct = pos.investment_pct or 0.0
            rate = pos.open_rate or 0.0
            if sym not in aggregated:
                aggregated[sym] = {
                    "weight": 0.0,
                    "invested": 0.0,
                    "buy_weight": 0.0,
                    "sell_weight": 0.0,
                    "position_count": 0,
                    "instrument_ids": [],
                    "symbol_fulls": [],
                }
            entry = aggregated[sym]
            entry["weight"] += abs(pct)
            entry["invested"] += pct * rate
            entry["position_count"] += 1
            if pos.is_buy:
                entry["buy_weight"] += abs(pct)
            else:
                entry["sell_weight"] += abs(pct)
            if hasattr(pos, 'instrument_id') and pos.instrument_id:
                entry["instrument_ids"].append(pos.instrument_id)
            if hasattr(pos, 'symbol_full') and pos.symbol_full:
                entry["symbol_fulls"].append(pos.symbol_full)

        aggregated_positions = []
        total_weight = 0.0
        for sym, entry in aggregated.items():
            weight = entry["weight"]
            total_weight += weight
            buy_weight = entry["buy_weight"]
            sell_weight = entry["sell_weight"]
            direction = (
                "BUY" if buy_weight > sell_weight
                else "SELL" if sell_weight > buy_weight
                else "MIXED"
            )
            avg_price = (entry["invested"] / weight) if weight else 0.0
            first_iid = entry["instrument_ids"][0] if entry["instrument_ids"] else None
            first_symfull = entry["symbol_fulls"][0] if entry["symbol_fulls"] else None
            aggregated_positions.append(
                EToroAggregatedPosition(
                    symbol=sym,
                    weight=weight,
                    trade_direction=direction,
                    average_entry_price=avg_price,
                    position_count=entry["position_count"],
                    instrument_id=first_iid,
                    symbol_full=first_symfull,
                )
            )

        remainder = max(0.0, 100.0 - total_weight)
        if remainder > 0.0001:
            aggregated_positions.append(
                EToroAggregatedPosition(
                    symbol="USD=X",
                    weight=remainder,
                    trade_direction="BUY",
                    average_entry_price=1.0,
                    position_count=0,
                )
            )

        result = EToroInvestorPortfolio(
            username=username,
            positions=positions,
            aggregated_positions=aggregated_positions,
        )
        cache_set(cache_key, result, ext=".pkl")
        return result
    
    def get_trade_history(
        self,
        *,
        username: str,
        page: int = 1,
        items_per_page: int = 9999999,
        explicit_cid: Optional[str] = None,
    ) -> EToroTradeHistory:
        """
        Fetch flat public credit/trade history for a user by CID or username.

        If `explicit_cid` is provided, it is used directly. Otherwise the
        client resolves the username to a customer ID via the public
        user-info API before fetching trade history. History is automatically
        fetched from 10 years back from the current UTC date.

        GET https://www.etoro.com/sapi/trade-data-real/history/public/credit/flat

        Args:
            username: eToro username to resolve and query.
            page: 1-based page number.
            items_per_page: Number of records per page.
            explicit_cid: Optional explicit customer ID to skip username
                resolution.

        Returns:
            EToroTradeHistory containing a list of ``EToroTradeRecord`` objects
            with the raw JSON fields for each trade credit entry.

        Raises:
            EToroClientError: If the request fails or returns a non-2xx status.
        """
        start_time = (
            datetime.now(timezone.utc)
            .replace(year=datetime.now(timezone.utc).year - 10)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        if explicit_cid:
            resolved_cid = str(explicit_cid)
        else:
            resolved_cid = self.resolve_cid(username)
        cache_key = ("history", username, resolved_cid, page, items_per_page)
        cached = cache_get(cache_key, _ETORO_TTL, ext=".pkl")
        if cached is not None:
            return cached
    
        session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)
        url = _ETORO_ENDPOINT_TRADE_HISTORY
    
        params: Dict[str, Any] = {
            "cid": resolved_cid,
            "startTime": start_time,
            "pageNumber": page,
            "itemsPerPage": items_per_page,
        }
    
        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET trade history failed: {exc}") from exc
    
        raw_items = data.get("PublicHistoryPositions", data if isinstance(data, list) else [])
        records = [EToroTradeRecord(raw=item) for item in raw_items]

        result = EToroTradeHistory(
            cid=str(resolved_cid),
            records=records,
            page=data.get("pageNumber", page),
            items_per_page=data.get("itemsPerPage", items_per_page),
            total_items=len(records),
        )
        cache_set(cache_key, result, ext=".pkl")
        return result
    
    def _resolve_cid_from_username(self, username: str) -> str:
        url = _ETORO_ENDPOINT_USER_INFO
        params: Dict[str, Any] = {"usernames": username}

        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET user by username failed: {exc}") from exc

        users = data.get("users", [])
        if not users and isinstance(data, dict):
            users = [data]

        user = users[0] if users else {}
        cid = user.get("realCID") or user.get("demoCID") or user.get("gcid")
        if not cid:
            raise EToroClientError(f"Could not resolve CID for username={username}")
        return str(cid)

    def resolve_cid(self, username: str) -> str:
        """
        Resolve an eToro username to a numeric customer ID (CID).

        This requires either:
        - ETORO_PUBLIC_KEY and ETORO_PRIVATE_KEY env vars set on this client,
        - Or a pre-authenticated ``ETPublicClient`` instance.

        Returns:
            str: Numeric customer ID.

        Raises:
            EToroClientError: If resolution fails.
        """
        cache_key = ("cid", username)
        cached = cache_get(cache_key, _ETORO_TTL, ext=".pkl")
        if cached is not None:
            return cached
        result = self._resolve_cid_from_username(username)
        cache_set(cache_key, result, ext=".pkl")
        return result
    
    def resolve_instrument_metadata(self, instrument_ids: list) -> Dict[str, Dict[str, str]]:
        """
        Resolve eToro InstrumentIDs to full symbol and display name via the search API.
        Results are cached on disk for 24 hours.

        Returns a dict keyed by InstrumentID with values like:
            {"symbol": "AAPL", "name": "Apple Inc."}
        """
        result: Dict[str, Dict[str, str]] = {}
        if not instrument_ids:
            return result

        cache = _load_instrument_cache()
        remaining = [iid for iid in instrument_ids if str(iid) not in cache]
        for iid in instrument_ids:
            iid_str = str(iid)
            if iid_str in cache:
                entry = {k: v for k, v in cache[iid_str].items() if k != "_ts"}
                if isinstance(entry.get("symbol"), str) and entry["symbol"].endswith(".RTH"):
                    entry = {**entry, "symbol": entry["symbol"][:-4]}
                result[iid_str] = entry

        if not remaining:
            return result

        session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)
        search_url = _ETORO_ENDPOINT_MARKET_DATA_SEARCH

        with ThreadPoolExecutor(max_workers=min(10, len(remaining) or 1)) as executor:
            futures = {executor.submit(_fetch_instrument_metadata, session, search_url, iid): iid for iid in remaining}
            for future in as_completed(futures):
                iid = futures[future]
                try:
                    meta = future.result()
                    if meta:
                        result[str(iid)] = meta
                except Exception as exc:
                    logger.debug("Instrument resolution future failed for %s: %s", iid, exc)

        if result:
            _save_instrument_cache(result)

        return result

    def get_users_by_cid(self, cids: List[str]) -> EToroUserLookupResult:
        """
        Resolve eToro usernames and account IDs from customer IDs.
    
        GET https://public-api.etoro.com/api/v1/user-info/people?cidList=...
    
        Args:
            cids: List of Customer IDs to resolve.
    
        Returns:
            EToroUserLookupResult mapping each requested CID string to an
            ``EToroUser`` with ``username``, ``gcid``, ``real_cid``, and
            ``demo_cid``. Missing users are omitted from ``by_cid``.
    
        Raises:
            EToroClientError: If the request fails or returns a non-2xx status.
        """
        if not cids:
            return EToroUserLookupResult(by_cid={}, requested=cids)
    
        session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)
        url = _ETORO_ENDPOINT_USER_INFO
        params: Dict[str, Any] = {"cidList": ",".join(str(c) for c in cids)}
    
        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)
    
        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET user lookup by CID failed: {exc}") from exc
    
        users = data.get("users", [])
        by_cid: Dict[str, EToroUser] = {}
        for user in users:
            etoro_user = EToroUser(
                username=user.get("username", ""),
                gcid=user.get("gcid"),
                real_cid=user.get("realCID"),
                demo_cid=user.get("demoCID"),
            )
            for cid_field in ("gcid", "realCID", "demoCID"):
                val = user.get(cid_field)
                if val is not None:
                    by_cid[str(val)] = etoro_user
    
        return EToroUserLookupResult(by_cid=by_cid, requested=[str(c) for c in cids])

    def get_user_info(self, usernames: str) -> Dict[str, Any]:
        url = _ETORO_ENDPOINT_USER_INFO
        params: Dict[str, Any] = {"usernames": usernames}

        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET user info failed: {exc}") from exc

    def get_daily_gain(self, username: str, params: Dict[str, Any]) -> Any:
        url = _ETORO_ENDPOINT_DAILY_GAIN.format(username=username)

        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET daily gain failed: {exc}") from exc

    def search_people(self, params: Dict[str, Any]) -> Dict[str, Any]:
        url = _ETORO_ENDPOINT_PEOPLE_SEARCH

        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET search people failed: {exc}") from exc

    def get_portfolio_rankings(self, username: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = _ETORO_ENDPOINT_PORTFOLIO_RANKINGS.format(username=username)

        def _session_factory():
            return public_api_session(self._api_key, get_random_private_key(), timeout=self._timeout)

        try:
            resp = _session_get_with_retry(_session_factory, url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except EToroClientError:
            raise
        except requests.RequestException as exc:
            raise EToroClientError(f"GET portfolio rankings failed: {exc}") from exc


def get_public_client_from_env(timeout: int = 30) -> ETPublicClient:
    api_key = os.getenv("ETORO_PUBLIC_KEY")
    user_key = get_random_private_key()
    logger.info(
        "EToro public client init: api_key=%s, user_key=%s",
        "present" if api_key else "missing",
        "present" if user_key else "missing",
    )
    if not api_key:
        raise EToroClientError(
            "ETORO_PUBLIC_KEY environment variable is required."
        )
    return ETPublicClient(api_key=api_key, user_key=user_key, timeout=timeout)


def _parse_date(value) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_time(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _safe_float(value, *, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
