import os
import sys
import time
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

ETORO_PUBLIC_KEY = env.get('ETORO_PUBLIC_KEY', '')
ETORO_PRIVATE_KEY = env.get('ETORO_PRIVATE_KEY', '')
TARGET_USERNAME = env.get('ETORO_TEST_USERNAME', 'VIXGold')
_api_url = 'https://public-api.etoro.com/api/v1'


def _load_auth():
    from Functions.etoro.auth import get_random_private_key
    return get_random_private_key


def _headers(user_key: str):
    return {
        'User-Agent': 'Mozilla/5.0 (compatible; alphasentra-etoro-client)',
        'Accept': 'application/json',
        'x-api-key': ETORO_PUBLIC_KEY,
        'x-user-key': user_key,
        'x-request-id': str(__import__('uuid').uuid4()),
    }


def _get_with_retry(url, params=None, timeout=30, user_key=None):
    max_retries = 3
    retry_delays = [5, 10, 20]
    last_exception = None
    key_provider = _load_auth()
    for attempt in range(max_retries + 1):
        try:
            actual_key = user_key or key_provider()
            resp = requests.get(url, params=params, headers=_headers(actual_key), timeout=timeout)
            if resp.status_code != 401:
                return resp
            print(f"  Attempt {attempt + 1}: HTTP 401 Unauthorized")
        except requests.RequestException as exc:
            last_exception = exc
            print(f"  Attempt {attempt + 1}: {type(exc).__name__}: {exc}")
        except Exception as exc:
            last_exception = exc
            print(f"  Attempt {attempt + 1}: {type(exc).__name__}: {exc}")
        if attempt < max_retries:
            print(f"  Retrying in {retry_delays[attempt]}s...")
            time.sleep(retry_delays[attempt])
    return None if last_exception is None else last_exception


def check_env_vars():
    print("=" * 70)
    print("STEP 1: CHECK ENVIRONMENT VARIABLES")
    print("=" * 70)
    if not ETORO_PUBLIC_KEY:
        print("FAIL: ETORO_PUBLIC_KEY is not set.")
        return False
    print(f"PASS: ETORO_PUBLIC_KEY is set ({len(ETORO_PUBLIC_KEY)} chars).")

    if not ETORO_PRIVATE_KEY:
        print("FAIL: ETORO_PRIVATE_KEY is not set.")
        return False
    keys = [k.strip() for k in ETORO_PRIVATE_KEY.split(',') if k.strip()]
    print(f"PASS: ETORO_PRIVATE_KEY is set ({len(keys)} key(s) available).")
    return True


def check_username_resolution():
    print("\n" + "=" * 70)
    print("STEP 2: CHECK USERNAME RESOLUTION (public-api.etoro.com)")
    print("=" * 70)
    url = f"{_api_url}/user-info/people"
    params = {"usernames": TARGET_USERNAME}
    resp = _get_with_retry(url, params=params, timeout=30)

    if resp is None:
        print("FAIL: No response after retries to user-info/people endpoint.")
        return False, "No response"
    if isinstance(resp, Exception):
        print(f"FAIL: Exception occurred: {resp}")
        return False, str(resp)

    status = resp.status_code
    print(f"HTTP Status: {status}")
    if status == 404:
        print(f"FAIL: Username '{TARGET_USERNAME}' returned HTTP 404.")
        return False, f"HTTP 404 for username '{TARGET_USERNAME}'"
    if status != 200:
        body_preview = resp.text[:300] if resp.text else ''
        print(f"FAIL: Unexpected HTTP {status}. Body: {body_preview!r}")
        return False, f"HTTP {status}: {body_preview[:200]}"

    try:
        data = resp.json()
    except Exception as exc:
        print(f"FAIL: Could not parse JSON response: {exc}")
        body = resp.text[:300]
        print(f"Body preview: {body!r}")
        return False, f"JSON parse error: {exc}"

    users = data.get("users", [])
    if not users and isinstance(data, dict):
        users = [data]
    user = users[0] if users else {}
    resolved_username = user.get("username")
    full_name = user.get("fullName")
    cid_fields = {
        "gcid": user.get("gcid"),
        "realCID": user.get("realCID"),
        "demoCID": user.get("demoCID"),
    }
    print(f"Resolved username : {resolved_username}")
    print(f"Full name         : {full_name}")
    print(f"CID fields        : {cid_fields}")

    any_cid = next((v for v in cid_fields.values() if v is not None), None)
    if not any_cid:
        print("FAIL: Username exists but no CID fields were returned.")
        return False, "No CID fields in response"

    print(f"PASS: Username resolved. CID={any_cid}")
    return True, f"cid={any_cid}"


def check_portfolio_api():
    print("\n" + "=" * 70)
    print("STEP 3: CHECK PORTFOLIO API (public-api.etoro.com)")
    print("=" * 70)
    username = TARGET_USERNAME.lower().strip()
    url = f"{_api_url}/user-info/people/{username}/portfolio/live"
    resp = _get_with_retry(url, timeout=30)

    if resp is None:
        print("FAIL: EToroClientError: GET investor portfolio failed after retries: no response")
        return False, "No response after retries"
    if isinstance(resp, Exception):
        print(f"FAIL: Exception occurred: {resp}")
        return False, str(resp)

    status = resp.status_code
    print(f"HTTP Status: {status}")
    if status == 404:
        print(f"FAIL: Portfolio endpoint returned HTTP 404 for username '{TARGET_USERNAME}'.")
        return False, f"HTTP 404 for portfolio of '{TARGET_USERNAME}'"
    if status != 200:
        body_preview = resp.text[:300] if resp.text else ''
        print(f"FAIL: Unexpected HTTP {status}. Body: {body_preview!r}")
        return False, f"HTTP {status}: {body_preview[:200]}"

    try:
        data = resp.json()
    except Exception as exc:
        print(f"FAIL: Could not parse JSON response: {exc}")
        body = resp.text[:300]
        print(f"Body preview: {body!r}")
        return False, f"JSON parse error: {exc}"

    raw_positions = data.get("positions", [])
    print(f"PASS: Portfolio API returned {len(raw_positions)} position(s).")
    if raw_positions:
        sample = raw_positions[:3]
        print("Sample positions:")
        for item in sample:
            print(f"  - instrumentId={item.get('instrumentId')} openRate={item.get('openRate')} netProfit={item.get('netProfit')}")
    return True, f"{len(raw_positions)} positions"


def check_etoro_client_direct():
    print("\n" + "=" * 70)
    print("STEP 4: CHECK EToroClient.get_investor_portfolio() directly")
    print("=" * 70)

    try:
        from Functions.etoro.client import ETPublicClient, get_public_client_from_env
        print("PASS: Imported ETPublicClient and get_public_client_from_env successfully.")
    except Exception as exc:
        print(f"FAIL: Could not import eToro client: {exc}")
        return False, str(exc)

    try:
        client = get_public_client_from_env()
        print("PASS: get_public_client_from_env() instantiated.")
    except Exception as exc:
        print(f"FAIL: get_public_client_from_env() failed: {exc}")
        return False, str(exc)

    try:
        portfolio = client.get_investor_portfolio(TARGET_USERNAME)
        count = len(getattr(portfolio, 'aggregated_positions', []) or [])
        print(f"PASS: get_investor_portfolio succeeded with {count} aggregated position(s).")
        return True, f"{count} aggregated positions"
    except Exception as exc:
        print(f"FAIL: EToroClient returned error:")
        print(f"  {type(exc).__name__}: {exc}")
        tb = __import__('traceback').format_exc()
        print(tb)
        return False, f"{type(exc).__name__}: {exc}"


def check_all_private_keys():
    print("\n" + "=" * 70)
    print("STEP 5: CHECK EACH PRIVATE KEY INDIVIDUALLY")
    print("=" * 70)

    from Functions.etoro.client import ETPublicClient
    keys = [k.strip() for k in ETORO_PRIVATE_KEY.split(',') if k.strip()]
    if not keys:
        print("SKIP: No private keys to test.")
        return True, "No keys"

    passing = 0
    failing = 0
    bad_keys = []
    for i, key in enumerate(keys, 1):
        masked = key[:4] + '...' + key[-4:] if len(key) >= 8 else '****'
        try:
            client = ETPublicClient(api_key=ETORO_PUBLIC_KEY, user_key=key, timeout=15)
            portfolio = client.get_investor_portfolio(TARGET_USERNAME)
            count = len(getattr(portfolio, 'aggregated_positions', []) or [])
            print(f"  Key {i} ({masked})... PASS ({count} aggregated positions)")
            passing += 1
        except Exception as exc:
            print(f"  Key {i} ({masked})... FAIL: {type(exc).__name__}: {exc}")
            failing += 1
            bad_keys.append(masked)

    detail = f"{passing} pass, {failing} fail"
    if failing > 0:
        print(f"WARNING: {failing} key(s) failed: {', '.join(bad_keys)}")
        print("If the app randomly picks one of the failing keys, it will hit 'no response' errors.")
    else:
        print("All keys passed.")
    return True, detail


def main():
    print("=" * 70)
    print(f"eToro portfolio connectivity test")
    print(f"Project  : {base}")
    print(f"Username : {TARGET_USERNAME}")
    print("=" * 70)

    results = {
        "env_vars": check_env_vars(),
        "username_resolution": None,
        "portfolio_api": None,
        "etoro_client": None,
        "all_private_keys": None,
    }

    if not results["env_vars"]:
        print("\nABORTING: Cannot continue without required environment variables.")
        return

    results["username_resolution"] = check_username_resolution()
    if results["username_resolution"] is not False:
        results["portfolio_api"] = check_portfolio_api()
        results["etoro_client"] = check_etoro_client_direct()
        results["all_private_keys"] = check_all_private_keys()

    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)
    step_names = {
        "env_vars": "Environment variables",
        "username_resolution": "Username resolution",
        "portfolio_api": "Portfolio API",
        "etoro_client": "EToroClient direct",
        "all_private_keys": "All private keys",
    }
    all_passed = True
    for key in ("env_vars", "username_resolution", "portfolio_api", "etoro_client", "all_private_keys"):
        result = results[key]
        name = step_names[key]
        if result is None:
            print(f"  {name}: SKIPPED")
            continue
        if key == "env_vars":
            ok = result
            detail = "OK" if result else "FAIL"
        else:
            ok, detail = result
        if ok:
            print(f"  PASS: {name} ({detail})")
        else:
            print(f"  FAIL: {name} ({detail})")
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("RESULT: All connectivity checks passed. This only validates API access.")
        print("        It does NOT generate the full portfolio report.")
    else:
        print("RESULT: One or more checks failed. Review the details above.")
    print("=" * 70)


if __name__ == "__main__":
    main()
