import os
import sys
import uuid
from pathlib import Path

import requests

base = Path('/Users/daivieth/Documents/_G8I/Development/alphasentra-functions')
env_path = base / '.env'
env = {}
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

API_KEY = env.get('ETORO_PUBLIC_KEY', '')
USER_KEY = env.get('ETORO_PRIVATE_KEY', '')
BASE_URL = 'https://public-api.etoro.com/api/v1/user-info/people/search'


def _headers():
    return {
        'User-Agent': 'Mozilla/5.0 (compatible; alphasentra-etoro-client)',
        'Accept': 'application/json',
        'x-api-key': API_KEY,
        'x-user-key': USER_KEY,
        'x-request-id': str(uuid.uuid4()),
    }


def fetch_page(params):
    resp = requests.get(BASE_URL, params=params, headers=_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    items = data.get('items', [])
    total = data.get('totalItems')
    return items, total


def collect_all(default_page_size=200, delay_seconds=1.0):
    import time
    seen = {}
    query_variants = [
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'CurrMonth', 'sort': 'userName', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'CurrMonth', 'sort': '-userName', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'CurrYear', 'sort': 'userName', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'CurrYear', 'sort': '-userName', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'LastYear', 'sort': 'userName', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'LastYear', 'sort': '-userName', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 2},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 2},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 2},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 3},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 3},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 3},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 4},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 4},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 500, 'page': 4},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 200, 'page': 4},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 200, 'page': 4},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 200, 'page': 4},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 200, 'page': 5},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 200, 'page': 5},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 200, 'page': 5},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 6},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 6},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 6},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 7},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 7},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 7},
        {'period': 'CurrMonth', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 8},
        {'period': 'CurrYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 8},
        {'period': 'LastYear', 'sort': '-copiersGain', 'copiersMin': 10, 'weeksSinceRegistrationMin': 52, 'pageSize': 100, 'page': 8},
    ]

    global_total = None
    for idx, base_params in enumerate(query_variants, 1):
        page = int(base_params.pop('page', 1))
        page_size = int(base_params.pop('pageSize', default_page_size))
        variant_total = None
        while True:
            params = dict(base_params)
            params['pageSize'] = page_size
            params['page'] = page
            max_retries = 3
            retry_delays = [delay_seconds * 2, delay_seconds * 4, delay_seconds * 8]
            items = []
            total = None
            current_params = dict(params)
            for attempt in range(max_retries + 1):
                try:
                    items, total = fetch_page(current_params)
                    break
                except requests.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 404 and attempt < max_retries:
                        if attempt == max_retries - 1 and current_params.get('pageSize', 0) > 50:
                            reduced = max(50, current_params.get('pageSize', 200) // 2)
                            print(f"Variant {idx} page {page}: 404 persists, retrying with pageSize={reduced}")
                            current_params = dict(current_params)
                            current_params['pageSize'] = reduced
                        print(f"Variant {idx} page {page}: 404 (likely rate limit), retrying in {retry_delays[attempt]}s...")
                        time.sleep(retry_delays[attempt])
                    else:
                        print(f"Variant {idx} page {page}: error={exc}")
                        break
                except requests.RequestException as exc:
                    print(f"Variant {idx} page {page}: error={exc}")
                    break

            if variant_total is None:
                variant_total = total
            if global_total is None and total is not None:
                global_total = total

            if not items:
                print(f"Variant {idx}: no more items at page {page} (variant_total={variant_total})")
                break

            new = 0
            for item in items:
                uname = item.get('userName')
                if not uname:
                    continue
                if uname not in seen:
                    seen[uname] = item
                    new += 1

            print(f"Variant {idx} page {page}: got {len(items)}, new={new}, unique_total={len(seen)}, variant_total={variant_total}")
            if len(items) < page_size:
                break
            page += 1
            time.sleep(delay_seconds)

    return list(seen.values()), global_total


all_investors, global_total = collect_all()
print(f"\nTotal investors retrieved: {len(all_investors)}")
print(f"API global totalItems (best observed): {global_total}")
for item in all_investors:
    print(f"- {item.get('userName')} | {item.get('fullName')} | {item.get('avatarUrl')}")
print(f"\nSummary: collected {len(all_investors)} unique popular investors out of {global_total or 'unknown'} reported by eToro.")
