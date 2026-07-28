"""Tests for ETPublicClient eToro API endpoints.

This module verifies the behavior of the eToro public API client, including
success paths, cache interactions, retry logic, and failure handling for each
endpoint wrapper. All network calls are mocked; no external requests are made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from requests import RequestException

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so that the `Functions` package can
# be imported regardless of how the test is invoked (pytest, direct run, etc.).
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from Functions.etoro.client import ETPublicClient, EToroClientError, _session_get_with_retry  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> ETPublicClient:
    """Create a fresh ETPublicClient with dummy credentials for testing."""
    return ETPublicClient(api_key="test-api-key", user_key="test-user-key", timeout=10)


def _mock_response(status_code: int = 200, json_data=None, text: str = ""):
    """Build a mock requests.Response with the given status and payload."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = text
    response.raise_for_status = MagicMock()
    if not (200 <= status_code < 300):
        from requests import HTTPError
        response.raise_for_status.side_effect = HTTPError(response=response)
    return response


def _mock_session(response):
    """Build a mock requests.Session that always returns the given response."""
    mock_session = MagicMock()
    mock_session.get.return_value = response
    return mock_session


# ---------------------------------------------------------------------------
# get_user_info
# ---------------------------------------------------------------------------


class TestGetUserInfo:
    """Tests for ETPublicClient.get_user_info."""

    def test_get_user_info(self):
        """Success path: returns raw user-info JSON and includes username in params."""
        client = _make_client()
        response = _mock_response(200, {"users": [{"username": "jdoe", "realCID": "123"}]})
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"):
            result = client.get_user_info("jdoe")
            assert result == {"users": [{"username": "jdoe", "realCID": "123"}]}
            mock_session.get.assert_called_once()
            called_url = mock_session.get.call_args[0][0]
            called_params = mock_session.get.call_args.kwargs.get("params", {})
            assert "/api/v1/user-info/people" in called_url
            assert called_params.get("usernames") == "jdoe"

    def test_get_user_info_request_exception(self):
        """When session.get raises, the client wraps it in EToroClientError after retries."""
        client = _make_client()
        mock_session = _mock_session(_mock_response(200, {}))
        mock_session.get.side_effect = RequestException("Network error")

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("time.sleep"):
            with pytest.raises(EToroClientError, match="failed after 5 attempts"):
                client.get_user_info("jdoe")


# ---------------------------------------------------------------------------
# get_users_by_cid
# ---------------------------------------------------------------------------


class TestGetUsersByCid:
    """Tests for ETPublicClient.get_users_by_cid."""

    def test_get_users_by_cid(self):
        """Success path: maps each CID field (gcid, realCID, demoCID) into by_cid."""
        client = _make_client()
        response = _mock_response(200, {
            "users": [
                {"username": "jdoe", "gcid": "100", "realCID": "101", "demoCID": "102"}
            ]
        })
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"):
            result = client.get_users_by_cid(["101"])
            # One user with 3 CID fields yields 3 entries in by_cid.
            assert len(result.by_cid) == 3
            assert "100" in result.by_cid
            assert "101" in result.by_cid
            assert "102" in result.by_cid
            assert result.by_cid["101"].username == "jdoe"

    def test_get_users_by_cid_empty(self):
        """Empty input returns an empty lookup result without making a request."""
        client = _make_client()
        result = client.get_users_by_cid([])
        assert result.by_cid == {}
        assert result.requested == []


# ---------------------------------------------------------------------------
# resolve_cid
# ---------------------------------------------------------------------------


class TestResolveCid:
    """Tests for ETPublicClient.resolve_cid."""

    def test_resolve_cid(self):
        """Success path: resolves username to realCID via the user-info API."""
        client = _make_client()
        response = _mock_response(200, {
            "users": [{"username": "jdoe", "realCID": "123"}]
        })
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            result = client.resolve_cid("jdoe")
            assert result == "123"

    def test_resolve_cid_cache_hit(self):
        """Cache hit skips the network call entirely."""
        client = _make_client()

        with patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value="cached-cid"), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo") as mock_cache_set:
            result = client.resolve_cid("jdoe")
            assert result == "cached-cid"
            mock_cache_set.assert_not_called()

    def test_resolve_cid_missing_cid(self):
        """When no CID fields are present, EToroClientError is raised."""
        client = _make_client()
        response = _mock_response(200, {"users": [{}]})
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            with pytest.raises(EToroClientError, match="Could not resolve CID"):
                client.resolve_cid("jdoe")


# ---------------------------------------------------------------------------
# get_investor_gain_timeseries
# ---------------------------------------------------------------------------


class TestGetInvestorGainTimeseries:
    """Tests for ETPublicClient.get_investor_gain_timeseries."""

    def test_gain_timeseries_daily(self):
        """Success path: parses Daily gain points and returns EToroGainHistory."""
        client = _make_client()
        response = _mock_response(200, [
            {"timestamp": "2024-01-01", "gain": 0.01},
            {"timestamp": "2024-01-02", "gain": 0.02},
        ])
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            result = client.get_investor_gain_timeseries("jdoe", "Daily")
            assert result.username == "jdoe"
            assert result.granularity == "Daily"
            assert len(result.gains) == 2
            assert result.gains[0].gain == 0.01

    def test_gain_timeseries_cache_hit(self):
        """Cache hit bypasses API and skips cache_set."""
        client = _make_client()
        cached = MagicMock()
        cached.username = "jdoe"

        with patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=cached), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo") as mock_cache_set:
            result = client.get_investor_gain_timeseries("jdoe", "Daily")
            assert result == cached
            mock_cache_set.assert_not_called()

    def test_gain_timeseries_invalid_granularity(self):
        """Invalid granularity raises ValueError before any network call."""
        client = _make_client()

        with pytest.raises(ValueError, match="granularity must be one of"):
            client.get_investor_gain_timeseries("jdoe", "Invalid")

    def test_gain_timeseries_non_list_response(self):
        """Non-list responses are normalized via the dailyExample fallback."""
        client = _make_client()
        response = _mock_response(200, {"dailyExample": [{"timestamp": "2024-01-01", "gain": 0.01}]})
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            result = client.get_investor_gain_timeseries("jdoe", "Daily")
            assert len(result.gains) == 1


# ---------------------------------------------------------------------------
# get_investor_portfolio
# ---------------------------------------------------------------------------


class TestGetInvestorPortfolio:
    """Tests for ETPublicClient.get_investor_portfolio."""

    def test_portfolio_success(self):
        """Success path resolves instrument metadata, maps DB tickers, and returns positions."""
        client = _make_client()
        response = _mock_response(200, {
            "positions": [
                {
                    "positionId": "pos1",
                    "instrumentId": "1",
                    "openTimestamp": "2024-01-01T00:00:00Z",
                    "openRate": 100.0,
                    "isBuy": True,
                    "leverage": 1.0,
                    "investmentPct": 50.0,
                    "netProfit": 10.0,
                }
            ]
        })
        mock_session = _mock_session(response)

        # Mock MongoDB lookup so instrumentId="1" maps to ticker "AAPL".
        mock_db = MagicMock()
        mock_tickers = MagicMock()
        mock_tickers.find.return_value = [
            {"ticker_etoro": "1", "ticker": "AAPL"}
        ]
        mock_db.__getitem__.return_value = {"tickers": mock_tickers}
        mock_db_manager = MagicMock()
        mock_db_manager.get_client.return_value = mock_db

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"), \
             patch("Functions.etoro.client.DatabaseManager", return_value=mock_db_manager), \
             patch.object(client, "resolve_instrument_metadata", return_value={"1": {"symbol": "TEST"}}):
            result = client.get_investor_portfolio("jdoe")
            assert result.username == "jdoe"
            assert len(result.positions) == 1
            assert result.positions[0].position_id == "pos1"
            # DB ticker mapping should override the resolved symbol.
            assert result.positions[0].symbol == "AAPL"

    def test_portfolio_empty_positions(self):
        """Empty positions list returns an empty portfolio result."""
        client = _make_client()
        response = _mock_response(200, {"positions": []})
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"), \
             patch("Functions.etoro.client.DatabaseManager", None):
            result = client.get_investor_portfolio("jdoe")
            assert len(result.positions) == 0

    def test_portfolio_stale_cache_fallback(self):
        """When the live API fails, the stale cache is returned if available."""
        client = _make_client()
        stale = MagicMock()
        stale.username = "jdoe"
        mock_session = _mock_session(_mock_response(500, {}))
        mock_session.get.side_effect = RequestException("API down")

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", side_effect=[None, stale]), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"), \
             patch("Functions.etoro.client.DatabaseManager", None):
            result = client.get_investor_portfolio("jdoe")
            assert result == stale


# ---------------------------------------------------------------------------
# get_trade_history
# ---------------------------------------------------------------------------


class TestGetTradeHistory:
    """Tests for ETPublicClient.get_trade_history."""

    def test_trade_history(self):
        """Success path: resolves CID if needed and returns parsed trade records."""
        client = _make_client()
        response = _mock_response(200, {
            "PublicHistoryPositions": [
                {"positionId": "trade1", "cid": "123"}
            ],
            "pageNumber": 1,
            "itemsPerPage": 10,
        })
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"), \
             patch.object(client, "resolve_cid", return_value="123"):
            result = client.get_trade_history(username="jdoe")
            assert result.cid == "123"
            assert len(result.records) == 1
            assert result.records[0].raw["positionId"] == "trade1"

    def test_trade_history_with_explicit_cid(self):
        """When explicit_cid is provided, CID resolution is skipped."""
        client = _make_client()
        response = _mock_response(200, {
            "PublicHistoryPositions": [],
            "pageNumber": 1,
            "itemsPerPage": 10,
        })
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            result = client.get_trade_history(username="jdoe", explicit_cid="999")
            assert result.cid == "999"


# ---------------------------------------------------------------------------
# search_people
# ---------------------------------------------------------------------------


class TestSearchPeople:
    """Tests for ETPublicClient.search_people."""

    def test_search_people(self):
        """Success path: returns raw search result JSON."""
        client = _make_client()
        response = _mock_response(200, {
            "items": [
                {"internalSymbolFull": "AAPL", "displayname": "Apple Inc."}
            ]
        })
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            result = client.search_people({"query": "AAPL"})
            assert result == {"items": [{"internalSymbolFull": "AAPL", "displayname": "Apple Inc."}]}

    def test_search_people_request_exception(self):
        """Request exceptions are wrapped in EToroClientError after retries."""
        client = _make_client()
        mock_session = _mock_session(_mock_response(200, {}))
        mock_session.get.side_effect = RequestException("Network error")

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("time.sleep"):
            with pytest.raises(EToroClientError, match="failed after 5 attempts"):
                client.search_people({"query": "AAPL"})


# ---------------------------------------------------------------------------
# get_portfolio_rankings
# ---------------------------------------------------------------------------


class TestGetPortfolioRankings:
    """Tests for ETPublicClient.get_portfolio_rankings."""

    def test_portfolio_rankings(self):
        """Success path: returns raw rankings JSON."""
        client = _make_client()
        response = _mock_response(200, {
            "rankings": [
                {"userName": "top_investor", "gain": 100.0}
            ]
        })
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            result = client.get_portfolio_rankings("jdoe", {"period": "1y"})
            assert result == {"rankings": [{"userName": "top_investor", "gain": 100.0}]}

    def test_portfolio_rankings_request_exception(self):
        """Request exceptions are wrapped in EToroClientError after retries."""
        client = _make_client()
        mock_session = _mock_session(_mock_response(200, {}))
        mock_session.get.side_effect = RequestException("Network error")

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("time.sleep"):
            with pytest.raises(EToroClientError, match="failed after 5 attempts"):
                client.get_portfolio_rankings("jdoe", {"period": "1y"})


# ---------------------------------------------------------------------------
# get_daily_gain
# ---------------------------------------------------------------------------


class TestGetDailyGain:
    """Tests for ETPublicClient.get_daily_gain."""

    def test_daily_gain(self):
        """Success path: returns raw JSON list from the daily-gain endpoint."""
        client = _make_client()
        response = _mock_response(200, [
            {"timestamp": "2024-01-01", "gain": 0.01}
        ])
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"):
            result = client.get_daily_gain("jdoe", {"type": "Daily"})
            assert isinstance(result, list)
            assert len(result) == 1

    def test_daily_gain_request_exception(self):
        """Request exceptions are wrapped in EToroClientError after retries."""
        client = _make_client()
        mock_session = _mock_session(_mock_response(200, {}))
        mock_session.get.side_effect = RequestException("Network error")

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("time.sleep"):
            with pytest.raises(EToroClientError, match="failed after 5 attempts"):
                client.get_daily_gain("jdoe", {"type": "Daily"})


# ---------------------------------------------------------------------------
# resolve_instrument_metadata
# ---------------------------------------------------------------------------


class TestResolveInstrumentMetadata:
    """Tests for ETPublicClient.resolve_instrument_metadata."""

    def test_resolve_instrument_metadata(self):
        """Success path: fetches missing instruments from the search API and caches them."""
        client = _make_client()
        response = _mock_response(200, {
            "items": [
                {"internalSymbolFull": "AAPL", "displayname": "Apple Inc."}
            ]
        })
        mock_session = _mock_session(response)

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("Functions.etoro.client._load_instrument_cache", return_value={}), \
             patch("Functions.etoro.client._save_instrument_cache"), \
             patch("Functions.etoro.client.get_portfolio_cache_from_mongo", return_value=None), \
             patch("Functions.etoro.client.set_portfolio_cache_to_mongo"):
            result = client.resolve_instrument_metadata(["1"])
            assert "1" in result
            assert result["1"]["symbol"] == "AAPL"

    def test_resolve_instrument_metadata_empty_input(self):
        """Empty input returns an empty dict without calling the API."""
        client = _make_client()
        result = client.resolve_instrument_metadata([])
        assert result == {}

    def test_resolve_instrument_metadata_cache_hit(self):
        """Cached entries are returned immediately; internal metadata is stripped of timestamps."""
        client = _make_client()

        with patch("Functions.etoro.client._load_instrument_cache", return_value={
            "1": {"_ts": 1000, "symbol": "AAPL", "name": "Apple"}
        }):
            result = client.resolve_instrument_metadata(["1"])
            assert result["1"]["symbol"] == "AAPL"
            assert "_ts" not in result["1"]

    def test_resolve_instrument_metadata_rth_suffix(self):
        """The .RTH suffix is stripped from cached symbol values."""
        client = _make_client()

        with patch("Functions.etoro.client._load_instrument_cache", return_value={
            "1": {"_ts": 1000, "symbol": "AAPL.RTH", "name": "Apple"}
        }):
            result = client.resolve_instrument_metadata(["1"])
            assert result["1"]["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# _session_get_with_retry
# ---------------------------------------------------------------------------


class TestSessionGetWithRetry:
    """Tests for the module-level _session_get_with_retry helper."""

    def test_success_first_attempt(self):
        """A successful response on the first attempt is returned immediately."""
        client = _make_client()
        response = _mock_response(200, {"data": "ok"})
        mock_session = _mock_session(response)

        def session_factory():
            return mock_session

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"):
            result = _session_get_with_retry(session_factory, "https://example.com")
            assert result.status_code == 200
            assert mock_session.get.call_count == 1

    def test_retry_on_failure(self):
        """A 500 on the first attempt is retried, and the second attempt succeeds."""
        client = _make_client()
        fail_response = _mock_response(500, {"error": "server error"})
        success_response = _mock_response(200, {"data": "ok"})
        mock_session = _mock_session(fail_response)
        mock_session.get.side_effect = [fail_response, success_response]

        def session_factory():
            return mock_session

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("time.sleep"):
            result = _session_get_with_retry(session_factory, "https://example.com")
            assert result.status_code == 200
            assert mock_session.get.call_count == 2

    def test_retry_exhausted(self):
        """After 5 consecutive failures, EToroClientError is raised."""
        client = _make_client()
        fail_response = _mock_response(500, {"error": "server error"})
        mock_session = _mock_session(fail_response)

        def session_factory():
            return mock_session

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("time.sleep"):
            with pytest.raises(EToroClientError, match="failed after 5 attempts"):
                _session_get_with_retry(session_factory, "https://example.com")
            assert mock_session.get.call_count == 5

    def test_request_exception_retry(self):
        """A network exception on the first attempt is retried, and the second succeeds."""
        client = _make_client()
        success_response = _mock_response(200, {"data": "ok"})
        mock_session = _mock_session(_mock_response(200, {}))
        mock_session.get.side_effect = [RequestException("connection error"), success_response]

        def session_factory():
            return mock_session

        with patch("Functions.etoro.client.public_api_session", return_value=mock_session), \
             patch("Functions.etoro.client.get_random_private_key", return_value="random-key"), \
             patch("time.sleep"):
            result = _session_get_with_retry(session_factory, "https://example.com")
            assert result.status_code == 200
            assert mock_session.get.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
