import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = _BASE_DIR / ".env"
load_dotenv(dotenv_path=str(_ENV_PATH), override=False)

API_KEY = os.getenv("ETORO_PUBLIC_KEY", "")
USER_KEY = os.getenv("ETORO_PRIVATE_KEY", "")
URL = "https://public-api.etoro.com/api/v1/user-info/people/search"
USER_URL = "https://public-api.etoro.com/api/v1/user-info/people"
TREND_URL = "https://public-api.etoro.com/api/v1/user-info/people/{username}/daily-gain"

if not API_KEY or not USER_KEY:
    print("Missing ETORO_PUBLIC_KEY or ETORO_PRIVATE_KEY in .env")
    sys.exit(1)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; alphasentra-etoro-client)",
    "Accept": "application/json",
    "x-api-key": API_KEY,
    "x-user-key": USER_KEY,
    "x-request-id": str(__import__("uuid").uuid4()),
})

params = {
    "period": "CurrMonth",
    "sort": "-copiersGain",
    "copiersMin": 10,
    "pageSize": 20,
}

periods = ["OneMonthAgo", "ThreeMonthsAgo", "OneYearAgo"]
for period in periods:
    test_params = dict(params)
    test_params["period"] = period
    resp = session.get(URL, params=test_params, timeout=30)
    print(f"{period}: {resp.status_code}")
    try:
        data = resp.json()
        items = data.get("items", [])
        print(f"  totalItems={data.get('totalItems')} items={len(items)}")
        if items:
            print(f"  first={items[0].get('userName')} gain={items[0].get('gain')} thisWeekGain={items[0].get('thisWeekGain')}")
    except Exception as exc:
        print(f"  json error={exc}")
    print()

print(f"URL: {URL}")
print(f"Params: {params}")
print(f"API_KEY present: {bool(API_KEY)}")
print(f"USER_KEY present: {bool(USER_KEY)}")
print(f"x-request-id: {session.headers['x-request-id']}")
print(f"Request time: {datetime.now(timezone.utc).isoformat()}")
print("-" * 60)

try:
    resp = session.get(URL, params=params, timeout=30)
    print(f"Status: {resp.status_code}")
    print(f"Headers: {dict(resp.headers)}")
    body = resp.text
    print(f"Body: {body[:4000]}")
    try:
        data = resp.json()
        items = data.get("items", data.get("users", data.get("results", [])))
        print(f"results/users count: {len(items)}")
        print(f"pagination: {data.get('pagination')}")
        print(f"keys: {list(data.keys())}")
        if items:
            print(f"first item keys: {list(items[0].keys())}")
            print(f"first item: {items[0]}")
            username = items[0].get("userName") or items[0].get("username", "")
            has_avatar = items[0].get("hasAvatar")
            print(f"first username: {username}")
            print(f"hasAvatar: {has_avatar}")
            if username and has_avatar:
                user_resp = session.get(USER_URL, params={"usernames": username}, timeout=20)
                print(f"avatar endpoint status: {user_resp.status_code}")
                if user_resp.status_code == 200:
                    user_data = user_resp.json()
                    print(f"avatar keys: {list(user_data.keys())}")
                    users = user_data.get("users", [])
                    if users:
                        print(f"user keys: {list(users[0].keys())}")
                        print(f"avatars: {users[0].get('avatars')}")
            trend_resp = session.get(TREND_URL.format(username=username), params={"type": "Daily", "minDate": "2026-06-01"}, timeout=20)
            print(f"trend endpoint status: {trend_resp.status_code}")
            if trend_resp.status_code == 200:
                trend_data = trend_resp.json()
                print(f"trend type: {type(trend_data)}")
                if isinstance(trend_data, list):
                    print(f"trend items: {len(trend_data)}")
                    if trend_data:
                        print(f"first trend: {trend_data[0]}")
                elif isinstance(trend_data, dict):
                    print(f"trend keys: {list(trend_data.keys())}")
    except Exception as exc:
        print(f"JSON decode failed: {exc}")
except requests.RequestException as exc:
    print(f"Request failed: {exc}")
