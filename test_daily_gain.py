import os
import sys
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = _BASE_DIR / ".env"
load_dotenv(dotenv_path=str(_ENV_PATH), override=False)

API_KEY = os.getenv("ETORO_PUBLIC_KEY", "")
USER_KEY = os.getenv("ETORO_PRIVATE_KEY", "")

_RANKINGS_URL = "https://public-api.etoro.com/api/v1/user-info/people/search"
_USER_INFO_URL = "https://public-api.etoro.com/api/v1/user-info/people"
_TREND_URL = "https://public-api.etoro.com/api/v1/user-info/people/{username}/daily-gain"

if not API_KEY or not USER_KEY:
    print("Missing ETORO_PUBLIC_KEY or ETORO_PRIVATE_KEY in .env")
    sys.exit(1)


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; alphasentra-etoro-client)",
        "Accept": "application/json",
        "x-api-key": API_KEY,
        "x-user-key": USER_KEY,
        "x-request-id": str(uuid.uuid4()),
    })
    return session


def _print_separator(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f" {title}")
    print(f"{'=' * 70}")


def test_rankings() -> None:
    _print_separator("TEST: rankings search")
    session = _new_session()
    resp = session.get(
        _RANKINGS_URL,
        params={"period": "CurrMonth", "sort": "-copiersGain", "copiersMin": 10, "pageSize": 20},
        timeout=30,
    )
    print(f"status: {resp.status_code}")
    try:
        data = resp.json()
        items = data.get("items", [])
        print(f"items count: {len(items)}")
        if items:
            print(f"first username: {items[0].get('userName')}")
            print(f"first hasAvatar: {items[0].get('hasAvatar')}")
    except Exception as exc:
        print(f"json error: {exc}")
    print(f"x-request-id: {session.headers.get('x-request-id')}")


def test_user_lookup() -> None:
    _print_separator("TEST: user lookup by username")
    session = _new_session()
    resp = session.get(
        _USER_INFO_URL,
        params={"usernames": "Positive_Vector"},
        timeout=30,
    )
    print(f"status: {resp.status_code}")
    try:
        data = resp.json()
        users = data.get("users", [])
        print(f"users count: {len(users)}")
        if users:
            print(f"first user keys: {list(users[0].keys())}")
            print(f"avatars: {users[0].get('avatars')}")
    except Exception as exc:
        print(f"json error: {exc}")
    print(f"x-request-id: {session.headers.get('x-request-id')}")


def test_daily_gain(username: str, label: str) -> None:
    _print_separator(f"TEST: {label}")
    session = _new_session()
    min_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    max_date = datetime.now().strftime("%Y-%m-%d")
    url = _TREND_URL.format(username=username)

    cases = [
        {"type": "Daily", "minDate": min_date, "maxDate": max_date},
        {"type": "Daily", "minDate": min_date},
        {"type": "Daily"},
        {"minDate": min_date, "maxDate": max_date},
        {},
    ]
    for idx, params in enumerate(cases, 1):
        resp = session.get(url, params=params, timeout=20)
        print(f"  case {idx}: params={params} -> status={resp.status_code}")
        print(f"    url: {resp.url}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, list):
                    print(f"    list length: {len(data)}")
                    if data:
                        print(f"    first: {data[0]}")
                elif isinstance(data, dict):
                    print(f"    dict keys: {list(data.keys())}")
                    for key in ("dailyExample", "daily", "items", "gains"):
                        if key in data:
                            value = data[key]
                            print(f"    {key}: {value if not isinstance(value, list) else f'list[{len(value)}]'}")
            except Exception as exc:
                print(f"    json error: {exc}")
        else:
            print(f"    body: {resp.text[:200]}")
        print(f"    x-request-id: {session.headers.get('x-request-id')}")


def test_alternative_username(username: str) -> None:
    _print_separator(f"TEST: daily-gain with username={username}")
    session = _new_session()
    min_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    max_date = datetime.now().strftime("%Y-%m-%d")
    url = _TREND_URL.format(username=username)
    resp = session.get(url, params={"type": "Daily", "minDate": min_date, "maxDate": max_date}, timeout=20)
    print(f"status: {resp.status_code}")
    print(f"url: {resp.url}")
    print(f"body: {resp.text[:500]}")
    print(f"x-request-id: {session.headers.get('x-request-id')}")


def main() -> None:
    print(f"API_KEY present: {bool(API_KEY)}")
    print(f"USER_KEY present: {bool(USER_KEY)}")
    print(f"Current time: {datetime.now().isoformat()}")

    test_rankings()
    test_user_lookup()
    test_daily_gain("Positive_Vector", "daily-gain Positive_Vector")
    test_alternative_username("AlphaMatriX2-LS")
    test_alternative_username("Tankianek")


if __name__ == "__main__":
    main()
