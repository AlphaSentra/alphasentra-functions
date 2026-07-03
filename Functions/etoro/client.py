import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

_current_dir = Path(__file__).resolve().parent
_parent_dir = _current_dir.parent
if str(_parent_dir) not in sys.path:
    sys.path.append(str(_parent_dir))

try:
    from helpers import DatabaseManager
except ImportError:
    DatabaseManager = None

from .auth import public_api_session
from .models import (
    EToroGainHistory,
    EToroGainPoint,
    EToroInvestorPortfolio,
    EToroPortfolioPosition,
    EToroTradeHistory,
    EToroTradeRecord,
    EToroUser,
    EToroUserLookupResult,
)

logger = logging.getLogger(__name__)


class EToroClientError(Exception):
    pass


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
        granularity = granularity.capitalize()
        if granularity not in {"Daily", "Period"}:
            raise ValueError("granularity must be one of: Daily, Period")

        session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)
        url = f"https://public-api.etoro.com/api/v1/user-info/people/{username}/daily-gain"

        params: Dict[str, Any] = {"type": granularity}
        if min_date:
            params["minDate"] = min_date
        if max_date:
            params["maxDate"] = max_date

        req = requests.Request("GET", url, params=params)
        prepared = session.prepare_request(req)
        logger.info("EToro request URL: %s", prepared.url)

        try:
            resp = session.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
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

        return EToroGainHistory(
            username=username,
            granularity=granularity,
            total_gain=total_gain,
            gains=gains,
        )

    def get_investor_portfolio(self, username: str) -> EToroInvestorPortfolio:
        """
        Fetch live open portfolio positions for a Popular Investor and match symbols.
        """
        # --- 1. Fetch live portfolio positions ---
        url = f"https://public-api.etoro.com/api/v1/user-info/people/{username}/portfolio/live"
        session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)

        try:
            resp = session.get(url, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise EToroClientError(f"GET investor portfolio failed: {exc}") from exc

        raw_positions = data.get("positions", [])
        if not raw_positions:
            return EToroInvestorPortfolio(username=username, positions=[])

        # Extract unique instrument IDs
        instrument_ids = list({str(item["instrumentId"]) for item in raw_positions if item.get("instrumentId")})

        # --- 2. Identify symbols directly from eToro search API ---
        etoro_symbol_map: Dict[str, str] = {}
        try:
            search_url = "https://public-api.etoro.com/api/v1/market-data/search"
            for iid in instrument_ids:
                inst_resp = session.get(search_url, params={"instrumentId": iid}, timeout=self._timeout)
                inst_resp.raise_for_status()
                for item in inst_resp.json().get("items", []):
                    sid = str(item.get("internalInstrumentId", ""))
                    symbol = item.get("internalSymbolFull")
                    if sid and symbol:
                        etoro_symbol_map[sid] = str(symbol)
        except Exception as exc:
            logger.warning("Failed to resolve live symbols from eToro search API: %s", exc)

        # --- 2b. Verify symbols by reverse lookup (internalSymbolFull -> ID) ---
        try:
            search_url = "https://public-api.etoro.com/api/v1/market-data/search"
            for iid, symbol in list(etoro_symbol_map.items()):
                inst_resp = session.get(search_url, params={"internalSymbolFull": symbol}, timeout=self._timeout)
                inst_resp.raise_for_status()
                for item in inst_resp.json().get("items", []):
                    sid = str(item.get("internalInstrumentId", ""))
                    if sid and sid != iid:
                        logger.info(
                            f"Symbol ambiguity detected for '{symbol}': "
                            f"expected ID {iid} but search returned ID {sid}."
                        )
        except Exception as exc:
            logger.warning("Failed to verify symbols via eToro search API: %s", exc)

        # --- 3. Pull from MongoDB and compare fields ---
        db_symbol_map: Dict[str, str] = {}
        if DatabaseManager is not None and instrument_ids:
            try:
                db = DatabaseManager().get_client()
                db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
                tickers_collection = db[db_name]["tickers"]

                cursor = tickers_collection.find(
                    {"ticker_etoro": {"$in": instrument_ids}},
                    {"ticker_etoro": 1, "ticker": 1},
                )
                for doc in cursor:
                    iid = str(doc.get("ticker_etoro", ""))
                    db_ticker = doc.get("ticker")
                    if iid and db_ticker is not None:
                        db_symbol_map[iid] = str(db_ticker)

                        api_symbol = etoro_symbol_map.get(iid)
                        if api_symbol and api_symbol != str(db_ticker):
                            logger.warning(
                                f"Symbol mismatch detected for ID {iid}: "
                                f"eToro API says '{api_symbol}', DB mapping says '{db_ticker}'."
                            )
            except Exception as exc:
                logger.warning("Failed to lookup eToro instrument symbols from DB: %s", exc)

        # --- 4. Build positions list with a progressive fallback chain ---
        positions = []
        for item in raw_positions:
            iid = str(item.get("instrumentId", ""))
            
            # Fallback hierarchy logic:
            # 1. Prefer MongoDB symbol mapping if available
            # 2. Fall back to the real-time API mapped symbol if DB skipped/missing 
            # 3. Fall back to None if both failed
            resolved_symbol = db_symbol_map.get(iid) or etoro_symbol_map.get(iid)
    
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
            
        return EToroInvestorPortfolio(username=username, positions=positions)
    
    def get_trade_history(
        self,
        *,
        username: str,
        page: int = 1,
        items_per_page: int = 9999999,
    ) -> EToroTradeHistory:
        """
        Fetch flat public credit/trade history for a user by username.
    
        The client resolves the username to a customer ID via the public
        user-info API before fetching trade history. History is automatically
        fetched from 10 years back from the current UTC date.
    
        GET https://www.etoro.com/sapi/trade-data-real/history/public/credit/flat
    
        Args:
            username: eToro username to resolve and query.
            page: 1-based page number.
            items_per_page: Number of records per page.
    
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
        resolved_cid = self._resolve_cid_from_username(username)
    
        session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)
        url = "https://www.etoro.com/sapi/trade-data-real/history/public/credit/flat"
    
        params: Dict[str, Any] = {
            "cid": resolved_cid,
            "startTime": start_time,
            "pageNumber": page,
            "itemsPerPage": items_per_page,
        }
    
        try:
            resp = session.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise EToroClientError(f"GET trade history failed: {exc}") from exc
    
        raw_items = data.get("items", data if isinstance(data, list) else [])
        records = [EToroTradeRecord(raw=item) for item in raw_items]
    
        return EToroTradeHistory(
            cid=str(resolved_cid),
            records=records,
            page=data.get("pageNumber", page),
            items_per_page=data.get("itemsPerPage", items_per_page),
            total_items=data.get("totalItems", len(records)),
        )
    
    
    def _resolve_cid_from_username(self, username: str) -> str:
        session = public_api_session(self._api_key, self._user_key, timeout=self._timeout)
        url = f"https://public-api.etoro.com/api/v1/user-info/people/{username}"
    
        try:
            resp = session.get(url, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise EToroClientError(f"GET user by username failed: {exc}") from exc
    
        user = data.get("user", data) if isinstance(data, dict) else {}
        cid = user.get("gcid") or user.get("realCID") or user.get("demoCID")
        if not cid:
            raise EToroClientError(f"Could not resolve CID for username={username}")
        return str(cid)
    
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
        url = "https://public-api.etoro.com/api/v1/user-info/people"
        params: Dict[str, Any] = {"cidList": ",".join(str(c) for c in cids)}
    
        try:
            resp = session.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
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


def get_public_client_from_env(timeout: int = 30) -> ETPublicClient:
    api_key = os.getenv("ETORO_PUBLIC_KEY")
    user_key = os.getenv("ETORO_PRIVATE_KEY")
    logger.info(
        "EToro public client init: api_key=%s, user_key=%s",
        "present" if api_key else "missing",
        "present" if user_key else "missing",
    )
    if not api_key or not user_key:
        raise EToroClientError(
            "ETORO_PUBLIC_KEY and ETORO_PRIVATE_KEY environment variables are required."
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
