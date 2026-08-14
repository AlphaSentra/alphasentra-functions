"""Tests for the eToro post comments API and batch fetcher.

Covers:
- Unit tests for ``_fetch_post_comments`` with mocked HTTP responses.
- Unit tests for ``_prepare_comment_documents`` normalization.
- Optional integration/smoke test against the live eToro API when
  ``ETORO_TEST_POST_ID`` is set.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from Functions.batch.feed_get_posts_from_pi import (
    _fetch_post_comments,
    _prepare_comment_documents,
    _build_comments_url,
)
from Functions.etoro.client import _ETORO_ENDPOINT_POST_COMMENTS  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    session = MagicMock()
    session.headers = {}
    return session


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestFetchPostComments:
    """Unit tests for ``_fetch_post_comments``."""

    def test_returns_empty_list_when_no_items(self):
        session = _make_session()
        session.get.return_value = _mock_response({"items": [], "paging": {}})

        comments = _fetch_post_comments(lambda: session, "post-123", take=20, order="Desc")

        assert comments == []
        session.get.assert_called_once()
        url = session.get.call_args[0][0]
        assert url == "https://public-api.etoro.com/api/v1/posts/post-123/comments?take=20&order=Desc"

    def test_parses_comments_from_items(self):
        session = _make_session()
        payload = {
            "items": [
                {"id": "c1", "text": "Nice post", "author": {"username": "alice"}},
                {"id": "c2", "text": "Thanks", "author": {"username": "bob"}},
            ],
            "paging": {},
        }
        session.get.return_value = _mock_response(payload)

        comments = _fetch_post_comments(lambda: session, "post-abc", take=10, order="Asc")

        assert len(comments) == 2
        assert comments[0]["comment_id"] == "c1"
        assert comments[0]["post_id"] == "post-abc"
        assert comments[0]["raw"]["text"] == "Nice post"
        assert comments[1]["comment_id"] == "c2"

    def test_parses_entity_wrapped_comments(self):
        session = _make_session()
        payload = {
            "reactionPaging": {"totalCount": 1},
            "comments": [
                {
                    "entity": {
                        "id": "ent-c1",
                        "message": {"text": "Great post", "languageCode": "en-gb"},
                        "attachments": [],
                        "isSpam": False,
                        "editStatus": "None",
                    }
                }
            ],
        }
        session.get.return_value = _mock_response(payload)

        comments = _fetch_post_comments(lambda: session, "post-entity", take=10, order="Desc")

        assert len(comments) == 1
        assert comments[0]["comment_id"] == "ent-c1"
        assert comments[0]["post_id"] == "post-entity"
        assert comments[0]["raw"]["entity"]["message"]["text"] == "Great post"

    def test_falls_back_to_commentId_field(self):
        session = _make_session()
        payload = {
            "items": [{"commentId": "c99", "text": "hello"}],
            "paging": {},
        }
        session.get.return_value = _mock_response(payload)

        comments = _fetch_post_comments(lambda: session, "post-xyz")

        assert len(comments) == 1
        assert comments[0]["comment_id"] == "c99"

    def test_falls_back_to_comments_key(self):
        session = _make_session()
        payload = {
            "comments": [{"id": "c1", "text": "hello"}],
            "paging": {},
        }
        session.get.return_value = _mock_response(payload)

        comments = _fetch_post_comments(lambda: session, "post-xyz")

        assert len(comments) == 1
        assert comments[0]["comment_id"] == "c1"

    def test_paginates_using_offsetEntityId(self):
        session = _make_session()
        page1 = {
            "items": [{"id": "c1", "text": "first"}],
            "paging": {"offsetEntityId": "cursor-1"},
        }
        page2 = {
            "items": [{"id": "c2", "text": "second"}],
            "paging": {},
        }
        session.get.side_effect = [
            _mock_response(page1),
            _mock_response(page2),
        ]

        comments = _fetch_post_comments(lambda: session, "post-page", take=50, order="Desc")

        assert len(comments) == 2
        assert comments[0]["comment_id"] == "c1"
        assert comments[1]["comment_id"] == "c2"
        assert session.get.call_count == 2

        second_url = session.get.call_args_list[1][0][0]
        assert "offsetEntityId=cursor-1" in second_url
        assert "take=50" in second_url

    def test_paginates_using_next_as_fallback(self):
        session = _make_session()
        page1 = {
            "items": [{"id": "c1"}],
            "paging": {"next": "next-cursor"},
        }
        page2 = {
            "items": [{"id": "c2"}],
            "paging": {},
        }
        session.get.side_effect = [
            _mock_response(page1),
            _mock_response(page2),
        ]

        comments = _fetch_post_comments(lambda: session, "post-page")

        assert len(comments) == 2
        second_url = session.get.call_args_list[1][0][0]
        assert "offsetEntityId=next-cursor" in second_url

    def test_rate_limit_delay_between_pages(self):
        session = _make_session()
        page1 = {
            "items": [{"id": "c1"}],
            "paging": {"offsetEntityId": "cursor-1"},
        }
        page2 = {
            "items": [{"id": "c2"}],
            "paging": {},
        }
        session.get.side_effect = [
            _mock_response(page1),
            _mock_response(page2),
        ]

        with patch("Functions.batch.feed_get_posts_from_pi.time.sleep") as mock_sleep:
            comments = _fetch_post_comments(lambda: session, "post-slow", take=100)

        assert len(comments) == 2
        assert session.get.call_count == 2
        assert mock_sleep.call_count >= 1

    def test_retries_on_server_error(self):
        session = _make_session()
        error_resp = _mock_response({"message": "Internal Server Error"}, status_code=500)
        ok_resp = _mock_response({"items": [{"id": "c1"}], "paging": {}})
        session.get.side_effect = [error_resp, ok_resp]

        with patch("Functions.batch.feed_get_posts_from_pi.time.sleep"):
            comments = _fetch_post_comments(lambda: session, "post-retry")

        assert len(comments) == 1
        assert comments[0]["comment_id"] == "c1"
        assert session.get.call_count == 2

    def test_rotates_session_on_401(self):
        session1 = _make_session()
        session2 = _make_session()
        factory_calls = [0]

        def factory():
            factory_calls[0] += 1
            return session1 if factory_calls[0] == 1 else session2

        unauthorized = _mock_response({"message": "Unauthorized"}, status_code=401)
        ok = _mock_response({"items": [{"id": "c1"}], "paging": {}})
        session1.get.return_value = unauthorized
        session2.get.return_value = ok

        with patch("Functions.batch.feed_get_posts_from_pi.time.sleep"):
            comments = _fetch_post_comments(factory, "post-401")

        assert len(comments) == 1
        assert comments[0]["comment_id"] == "c1"
        assert session1.get.call_count == 1
        assert session2.get.call_count == 1

    def test_raises_after_max_retries(self):
        session = _make_session()
        error_resp = _mock_response({"message": "Internal Server Error"}, status_code=500)
        session.get.return_value = error_resp

        with patch("Functions.batch.feed_get_posts_from_pi.time.sleep"):
            with pytest.raises(RuntimeError, match="failed after 5 attempts"):
                _fetch_post_comments(lambda: session, "post-fail")

    def test_take_clamped_to_valid_range(self):
        session = _make_session()
        session.get.return_value = _mock_response({"items": [], "paging": {}})

        _fetch_post_comments(lambda: session, "post-clamp", take=200, order="Desc")
        url = session.get.call_args[0][0]
        assert "take=100" in url

        _fetch_post_comments(lambda: session, "post-clamp2", take=0, order="Desc")
        url = session.get.call_args[0][0]
        assert "take=1" in url

    def test_endpoint_url_format(self):
        assert _ETORO_ENDPOINT_POST_COMMENTS.endswith("/posts/{post_id}/comments")
        expected = (
            "https://public-api.etoro.com/api/v1/posts/{post_id}/comments"
        )
        assert _ETORO_ENDPOINT_POST_COMMENTS == expected


class TestPrepareCommentDocuments:
    """Unit tests for ``_prepare_comment_documents``."""

    def test_normalizes_entity_wrapped_comment(self):
        raw_item = {
            "entity": {
                "id": "comment-1",
                "message": {"text": "Hello world", "languageCode": "en-gb"},
                "isSpam": False,
                "editStatus": "None",
                "created": "2026-08-01T10:00:00.000Z",
                "owner": {
                    "id": "user-1",
                    "username": "testuser",
                },
            },
            "repliesCount": 3,
            "emotionsData": {
                "like": {"paging": {"totalCount": 5}}
            },
        }
        comments = [
            {
                "comment_id": "comment-1",
                "post_id": "post-1",
                "raw": raw_item,
            }
        ]

        documents = _prepare_comment_documents(comments)

        assert len(documents) == 1
        doc = documents[0]
        assert doc["comment_id"] == "comment-1"
        assert doc["post_id"] == "post-1"
        assert doc["text"] == "Hello world"
        assert doc["language_code"] == "en-gb"
        assert doc["username"] == "testuser"
        assert doc["owner_id"] == "user-1"
        assert doc["is_spam"] is False
        assert doc["edit_status"] == "None"
        assert doc["replies_count"] == 3
        assert doc["likes"] == 5
        assert doc["raw"] == raw_item
        assert doc["created"] is not None

    def test_handles_missing_optional_fields(self):
        raw_item = {
            "entity": {
                "id": "comment-2",
                "message": {},
                "owner": {},
            },
            "repliesCount": 0,
            "emotionsData": {},
        }
        comments = [
            {
                "comment_id": "comment-2",
                "post_id": "post-2",
                "raw": raw_item,
            }
        ]

        documents = _prepare_comment_documents(comments)

        assert len(documents) == 1
        doc = documents[0]
        assert doc["text"] is None
        assert doc["language_code"] is None
        assert doc["username"] is None
        assert doc["owner_id"] is None
        assert doc["is_spam"] is None
        assert doc["edit_status"] is None
        assert doc["replies_count"] == 0
        assert doc["likes"] == 0
        assert doc["created"] is None


# ---------------------------------------------------------------------------
# Optional integration / smoke test
# ---------------------------------------------------------------------------


class TestLiveCommentsApi:
    """Smoke tests against the live eToro comments API.

    These tests require:
      - ETORO_PUBLIC_KEY
      - ETORO_PRIVATE_KEY
      - ETORO_TEST_POST_ID (a real post UUID from etoro_posts)
    """

    def test_live_comments_endpoint_returns_200(self):
        post_id = os.getenv("ETORO_TEST_POST_ID", "")
        if not post_id:
            pytest.skip("ETORO_TEST_POST_ID is required for live comments test")

        from Functions.etoro.auth import public_api_session, get_random_private_key
        api_key = os.getenv("ETORO_PUBLIC_KEY", "")
        factory = lambda: public_api_session(api_key, get_random_private_key(), timeout=30)

        comments = _fetch_post_comments(factory, post_id, take=10, order="Desc")

        assert isinstance(comments, list)
        if comments:
            assert "comment_id" in comments[0]
            assert "post_id" in comments[0]
            assert comments[0]["post_id"] == post_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
