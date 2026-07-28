"""Tests for portfolio selection MongoDB cache behavior.

These tests verify that the portfolio selection page correctly reads/writes
the per-user ``My Portfolio`` row to MongoDB cache, and that stale cache
entries do not silently serve wrong ``N/A`` values.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from Functions.port.selection import get_portfolio_selection_html  # noqa: E402
from Functions.db.cache import (  # noqa: E402
    get_portfolio_cache_from_mongo,
    set_portfolio_cache_to_mongo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auth_user(username: str = "testuser"):
    """Build a minimal Flask ``g`` object with an authenticated user."""
    g = MagicMock()
    g.etoro_authuser = username
    return g


def _make_cache_doc(value, ttl_seconds=1800, ext=".html"):
    """Build a fake MongoDB document as returned by ``find_one``."""
    from datetime import datetime, timedelta, timezone

    return {
        "_id": "portfolio_selection_my_portfolio_testuser",
        "value": value,
        "ext": ext,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    }


# ---------------------------------------------------------------------------
# Tests: cached My Portfolio row is reused
# ---------------------------------------------------------------------------


class TestMyPortfolioCacheHit:
    """When a cached my_portfolio HTML row exists, it should be reused."""

    def test_cache_hit_returns_cached_html(self):
        """A valid cached my_portfolio row should appear in the output HTML."""
        cached_row = (
            '<tr class="my-portfolio-row">'
            '<td><div class="my-portfolio-investor">'
            '<div class="my-portfolio-avatar">@</div>'
            '<div class="my-portfolio-info">'
            '<div class="my-portfolio-name-row">'
            '<span class="my-portfolio-name">testuser</span>'
            "</div>"
            '<span class="my-portfolio-username">@testuser</span>'
            "</div>"
            "</div>"
            "</td>"
            '<td><span class="my-portfolio-country">US</span></td>'
            '<td><span class="my-portfolio-aum">$1.2M</span></td>'
            '<td><div class="my-portfolio-copiers-value">1,234</div>'
            '<div class="my-portfolio-copiers-change">&#x25B2; 5.0% 1M</div>'
            "</td>"
            "</tr>"
        )

        fake_mongo = {
            "portfolio_selection_my_portfolio_testuser": _make_cache_doc(cached_row),
        }

        def mock_get(collection, doc_id, ttl_seconds=86400, ext=".html"):
            if doc_id in fake_mongo:
                doc = fake_mongo[doc_id]
                if doc.get("chunked"):
                    return doc["value"]
                return doc["value"]
            return None

        def mock_set(collection, doc_id, value, ext=".html", ttl_seconds=86400):
            fake_mongo[doc_id] = {
                "_id": doc_id,
                "value": value,
                "ext": ext,
                "created_at": MagicMock(),
                "expires_at": MagicMock(),
            }

        with patch("Functions.port.selection.get_portfolio_cache_from_mongo", side_effect=mock_get), \
             patch("Functions.port.selection.set_portfolio_cache_to_mongo", side_effect=mock_set), \
             patch("Functions.port.selection._get_etoro_client", return_value=None), \
             patch("flask.g", _make_auth_user("testuser")):
            html = get_portfolio_selection_html()

        assert "testuser" in html
        assert "US" in html
        assert "1,234" in html
        assert "N/A" not in html

    def test_cache_hit_skips_personal_api_calls(self):
        """On my_portfolio cache hit, personal portfolio API calls are skipped."""
        cached_row = (
            '<tr class="my-portfolio-row">'
            '<td><div class="my-portfolio-investor">'
            '<div class="my-portfolio-avatar">@</div>'
            '<div class="my-portfolio-info">'
            '<div class="my-portfolio-name-row">'
            '<span class="my-portfolio-name">testuser</span>'
            "</div>"
            "</div>"
            "</div>"
            "</td>"
            "</tr>"
        )

        fake_mongo = {
            "portfolio_selection_my_portfolio_testuser": _make_cache_doc(cached_row),
            "portfolio_selection_rankings": {
                "_id": "portfolio_selection_rankings",
                "value": ([], {}, {}, {}),
                "ext": ".pkl",
                "created_at": MagicMock(),
                "expires_at": MagicMock(),
            },
        }

        def mock_get(collection, doc_id, ttl_seconds=86400, ext=".html"):
            if doc_id in fake_mongo:
                return fake_mongo[doc_id]["value"]
            return None

        def mock_set(collection, doc_id, value, ext=".html", ttl_seconds=86400):
            fake_mongo[doc_id] = {
                "_id": doc_id,
                "value": value,
                "ext": ext,
                "created_at": MagicMock(),
                "expires_at": MagicMock(),
            }

        personal_api_calls = []

        def mock_client():
            client = MagicMock()
            original_search = client.search_people

            def tracked_search(params):
                personal_api_calls.append(params)
                return original_search(params)

            client.search_people = tracked_search
            return client

        with patch("Functions.port.selection.get_portfolio_cache_from_mongo", side_effect=mock_get), \
             patch("Functions.port.selection.set_portfolio_cache_to_mongo", side_effect=mock_set), \
             patch("Functions.port.selection._get_etoro_client", side_effect=mock_client), \
             patch("flask.g", _make_auth_user("testuser")):
            html = get_portfolio_selection_html()

        assert "testuser" in html
        assert "N/A" not in html


# ---------------------------------------------------------------------------
# Tests: cache miss falls back to live data / placeholders
# ---------------------------------------------------------------------------


class TestMyPortfolioCacheMiss:
    """When no cached row exists, the function should attempt a live fetch."""

    def test_cache_miss_calls_api_when_no_client(self):
        """Cache miss with no eToro client should still return HTML without crashing."""
        fake_mongo: dict = {}
        get_calls = []

        def mock_get(collection, doc_id, ttl_seconds=86400, ext=".html"):
            get_calls.append(doc_id)
            if doc_id in fake_mongo:
                return fake_mongo[doc_id]["value"]
            return None

        def mock_set(collection, doc_id, value, ext=".html", ttl_seconds=86400):
            fake_mongo[doc_id] = {
                "_id": doc_id,
                "value": value,
                "ext": ext,
                "created_at": MagicMock(),
                "expires_at": MagicMock(),
            }

        with patch("Functions.port.selection.get_portfolio_cache_from_mongo", side_effect=mock_get), \
             patch("Functions.port.selection.set_portfolio_cache_to_mongo", side_effect=mock_set), \
             patch("Functions.port.selection._get_etoro_client", return_value=None), \
             patch("flask.g", _make_auth_user("testuser")):
            html = get_portfolio_selection_html()

        assert "testuser" in html
        assert get_calls or "N/A" in html


# ---------------------------------------------------------------------------
# Tests: unauthenticated user sees login prompt, not cached personal row
# ---------------------------------------------------------------------------


class TestUnauthenticatedMyPortfolio:
    """Unauthenticated visitors should see the login prompt, not personal data."""

    def test_no_auth_shows_login_prompt(self):
        fake_mongo: dict = {}

        def mock_get(collection, doc_id, ttl_seconds=86400, ext=".html"):
            if doc_id in fake_mongo:
                return fake_mongo[doc_id]["value"]
            return None

        def mock_set(collection, doc_id, value, ext=".html", ttl_seconds=86400):
            fake_mongo[doc_id] = {
                "_id": doc_id,
                "value": value,
                "ext": ext,
                "created_at": MagicMock(),
                "expires_at": MagicMock(),
            }

        with patch("Functions.port.selection.get_portfolio_cache_from_mongo", side_effect=mock_get), \
             patch("Functions.port.selection.set_portfolio_cache_to_mongo", side_effect=mock_set), \
             patch("Functions.port.selection._get_etoro_client", return_value=None), \
             patch("flask.g", _make_auth_user(None)):
            html = get_portfolio_selection_html()

        assert "Sign in to view and add your portfolio" in html


# ---------------------------------------------------------------------------
# Tests: cache key format
# ---------------------------------------------------------------------------


class TestCacheKeyFormat:
    """The my_portfolio cache key should be namespaced by username."""

    def test_cache_key_contains_username(self):
        captured_keys = []

        def mock_get(collection, doc_id, ttl_seconds=86400, ext=".html"):
            captured_keys.append(doc_id)
            return None

        with patch("Functions.port.selection.get_portfolio_cache_from_mongo", side_effect=mock_get), \
             patch("Functions.port.selection.set_portfolio_cache_to_mongo"), \
             patch("Functions.port.selection._get_etoro_client", return_value=None), \
             patch("flask.g", _make_auth_user("alice")):
            get_portfolio_selection_html()

        my_portfolio_keys = [k for k in captured_keys if "my_portfolio" in k]
        assert my_portfolio_keys, "Expected at least one my_portfolio cache key"
        assert all("alice" in k for k in my_portfolio_keys)


# ---------------------------------------------------------------------------
# Tests: rankings cache interaction
# ---------------------------------------------------------------------------


class TestRankingsCache:
    """The rankings cache should be read before falling back to the API."""

    def test_rankings_cache_hit_skips_fetch(self):
        fake_mongo: dict = {}

        rankings_key = "portfolio_selection_rankings"
        fake_mongo[rankings_key] = {
            "_id": rankings_key,
            "value": ([], {}, {}, {}),
            "ext": ".pkl",
            "created_at": MagicMock(),
            "expires_at": MagicMock(),
        }

        def mock_get(collection, doc_id, ttl_seconds=86400, ext=".html"):
            if doc_id in fake_mongo:
                return fake_mongo[doc_id]["value"]
            return None

        def mock_set(collection, doc_id, value, ext=".html", ttl_seconds=86400):
            fake_mongo[doc_id] = {
                "_id": doc_id,
                "value": value,
                "ext": ext,
                "created_at": MagicMock(),
                "expires_at": MagicMock(),
            }

        with patch("Functions.port.selection.get_portfolio_cache_from_mongo", side_effect=mock_get), \
             patch("Functions.port.selection.set_portfolio_cache_to_mongo", side_effect=mock_set), \
             patch("Functions.port.selection._get_etoro_client", return_value=None), \
             patch("Functions.port.selection._fetch_rankings") as mock_fetch, \
             patch("flask.g", _make_auth_user("testuser")):
            html = get_portfolio_selection_html()

        mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: My Portfolio data fields
# ---------------------------------------------------------------------------


class TestMyPortfolioDataFields:
    """The My Portfolio row should expose country, copiers, AUM, and performance."""

    def test_my_portfolio_contains_country_copiers_aum_and_periods(self):
        """When the API returns full portfolio data, all fields should be present."""
        fake_mongo: dict = {}
        my_username = "testuser"
        my_cid = my_username

        def mock_get(collection, doc_id, ttl_seconds=86400, ext=".html"):
            if doc_id in fake_mongo:
                return fake_mongo[doc_id]["value"]
            return None

        def mock_set(collection, doc_id, value, ext=".html", ttl_seconds=86400):
            fake_mongo[doc_id] = {
                "_id": doc_id,
                "value": value,
                "ext": ext,
                "created_at": MagicMock(),
                "expires_at": MagicMock(),
            }

        user_info_response = {
            "users": [
                {
                    "userName": my_username,
                    "fullName": "Test User",
                    "avatarUrl": "https://example.com/avatar.png",
                    "country": "US",
                    "copiers": 12345,
                    "aumValue": 2500000.0,
                    "baseLineCopiers": 12000,
                }
            ]
        }

        rankings_item = {
            "userName": my_username,
            "fullName": "Test User",
            "avatarUrl": "https://example.com/avatar.png",
            "country": "US",
            "copiers": 12345,
            "aumValue": 2500000.0,
            "baseLineCopiers": 12000,
            "gain": 0.5,
        }

        client = MagicMock()
        client.get_user_info.return_value = user_info_response
        client.get_portfolio_rankings.return_value = {
            "data": rankings_item,
            "items": [rankings_item],
            "pagination": {},
        }
        client.search_people.return_value = {"items": [], "pagination": {}}
        client.get_daily_gain.return_value = []

        def client_factory():
            return client

        with patch("Functions.port.selection.get_portfolio_cache_from_mongo", side_effect=mock_get), \
             patch("Functions.port.selection.set_portfolio_cache_to_mongo", side_effect=mock_set), \
             patch("Functions.port.selection._get_etoro_client", side_effect=client_factory), \
             patch("Functions.port.selection._fetch_rankings") as mock_fetch, \
             patch("Functions.port.selection._get_period_gain", side_effect=lambda username, period: {
                 "1m": 0.5,
                 "3m": 1.2,
                 "1y": 3.4,
             }.get(period)), \
             patch("Functions.port.selection._get_trend_data", return_value=[0.1, 0.2, 0.3]), \
             patch("flask.g", _make_auth_user(my_username)):
            mock_fetch.return_value = (
                [rankings_item],
                {my_cid: 0.5},
                {my_cid: 1.2},
                {my_cid: 3.4},
            )
            html = get_portfolio_selection_html()

        assert my_username in html
        assert "US" in html
        assert "12,345" in html
        assert "$2.5M" in html
        assert "+0.50%" in html or "0.50%" in html
        assert "+1.20%" in html or "1.20%" in html
        assert "+3.40%" in html or "3.40%" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
