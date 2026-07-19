import os
import sys
import uuid
from pathlib import Path

import requests

base = Path('/Users/daivieth/Documents/_G8I/Development/alphasentra-functions')
_port_dir = base / 'Functions' / 'port'
if str(_port_dir) not in sys.path:
    sys.path.insert(0, str(_port_dir))
env_path = base / '.env'
env = {}
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from Functions.etoro.auth import get_random_private_key

API_KEY = env.get('ETORO_PUBLIC_KEY', '')
BASE_URL = 'https://public-api.etoro.com/api/v1/user-info/people/search'


def _headers():
    return {
        'User-Agent': 'Mozilla/5.0 (compatible; alphasentra-etoro-client)',
        'Accept': 'application/json',
        'x-api-key': API_KEY,
        'x-user-key': get_random_private_key(),
        'x-request-id': str(uuid.uuid4()),
    }


def fetch_page(params):
    resp = requests.get(BASE_URL, params=params, headers=_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    items = data.get('items', [])
    total = data.get('totalItems')
    return items, total


def collect_all(default_page_size=1000, delay_seconds=0.0):
    import time
    seen = {}
    variants = [
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'isPopularInvestor': 'true'},
        {'period': 'LastYear', 'sort': '-copiersGain', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': 'userName', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': 'userName', 'isPopularInvestor': 'true'},
        {'period': 'LastYear', 'sort': 'userName', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': '-gain', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': '-gain', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': '-aumValue', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': '-aumValue', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': '-copiers', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': '-copiers', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': 'displayName', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': 'displayName', 'isPopularInvestor': 'true'},
        {'period': 'CurrWeek', 'sort': '-copiersGain', 'isPopularInvestor': 'true'},
        {'period': 'CurrWeek', 'sort': 'userName', 'isPopularInvestor': 'true'},
        {'period': 'CurrWeek', 'sort': '-gain', 'isPopularInvestor': 'true'},
        {'period': 'ThreeMonthsAgo', 'sort': '-copiersGain', 'isPopularInvestor': 'true'},
        {'period': 'ThreeMonthsAgo', 'sort': 'userName', 'isPopularInvestor': 'true'},
        {'period': 'ThreeMonthsAgo', 'sort': '-gain', 'isPopularInvestor': 'true'},
        {'period': 'OneYearAgo', 'sort': '-copiersGain', 'isPopularInvestor': 'true'},
        {'period': 'OneYearAgo', 'sort': 'userName', 'isPopularInvestor': 'true'},
        {'period': 'OneYearAgo', 'sort': '-gain', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': '-weeklyGain', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': '-weeklyGain', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': 'riskScore', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': 'riskScore', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': '-riskScore', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': '-riskScore', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': 'username', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': 'username', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': 'fullName', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': 'fullName', 'isPopularInvestor': 'true'},
        {'period': 'CurrWeek', 'sort': '-copiers', 'isPopularInvestor': 'true'},
        {'period': 'CurrWeek', 'sort': '-aumValue', 'isPopularInvestor': 'true'},
        {'period': 'CurrWeek', 'sort': '-weeklyGain', 'isPopularInvestor': 'true'},
        {'period': 'ThreeMonthsAgo', 'sort': '-copiers', 'isPopularInvestor': 'true'},
        {'period': 'ThreeMonthsAgo', 'sort': '-aumValue', 'isPopularInvestor': 'true'},
        {'period': 'ThreeMonthsAgo', 'sort': '-weeklyGain', 'isPopularInvestor': 'true'},
        {'period': 'OneYearAgo', 'sort': '-copiers', 'isPopularInvestor': 'true'},
        {'period': 'OneYearAgo', 'sort': '-aumValue', 'isPopularInvestor': 'true'},
        {'period': 'OneYearAgo', 'sort': '-weeklyGain', 'isPopularInvestor': 'true'},
        {'period': 'CurrMonth', 'sort': '', 'isPopularInvestor': 'true'},
        {'period': 'CurrYear', 'sort': '', 'isPopularInvestor': 'true'},
    ]
    global_total = None

    def _fetch(variant, page):
        params = {**variant, 'page': page, 'pageSize': default_page_size}
        max_retries = 3
        retry_delays = [2, 4, 8]
        for attempt in range(max_retries + 1):
            try:
                items, total = fetch_page(params)
                return items, total
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response else None
                print(f"  _fetch variant={variant.get('period')}/{variant.get('sort')} page={page} attempt={attempt+1} HTTP {status}: {exc}")
                if status == 404 and attempt < max_retries:
                    time.sleep(retry_delays[attempt])
                else:
                    return [], status
            except requests.RequestException as exc:
                print(f"  _fetch variant={variant.get('period')}/{variant.get('sort')} page={page} attempt={attempt+1} error={type(exc).__name__}: {exc}")
                if attempt < max_retries:
                    time.sleep(retry_delays[attempt])
                else:
                    return [], str(exc)
        return [], 'max_retries'

    for idx, variant in enumerate(variants, 1):
        page = 1
        while True:
            items, total = _fetch(variant, page)
            if isinstance(total, (str, int)) and global_total is None:
                global_total = total if isinstance(total, int) else None
            if not items:
                print(f"Variant {idx} ({variant.get('period')}/{variant.get('sort')}) stopped at page {page}: empty/failed (reason={total!r})")
                break
            new = 0
            for item in items:
                uname = item.get('userName')
                if not uname or uname in seen:
                    continue
                seen[uname] = item
                new += 1
            print(f"Variant {idx} page {page}: got {len(items)}, new={new}, unique_total={len(seen)}, total={total}")
            if len(items) < default_page_size:
                break
            page += 1

    return list(seen.values()), global_total


all_investors, global_total = collect_all()
print(f"\nTotal investors retrieved: {len(all_investors)}")
print(f"API global totalItems (best observed): {global_total}")
for item in all_investors:
    print(f"- {item.get('userName')} | {item.get('fullName')} | {item.get('avatarUrl')}")
print(f"\nSummary: collected {len(all_investors)} unique popular investors out of {global_total or 'unknown'} reported by eToro.")
