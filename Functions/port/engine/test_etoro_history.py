"""
Diagnostic test script for eToro trade history integration.

Run from project root:
    source venv/bin/activate
    python3 Functions/port/engine/test_etoro_history.py
"""

import logging
import os
import sys
from pathlib import Path

# Load .env from project root
_dotenv_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _dotenv_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(_dotenv_path))
    except ImportError:
        with open(_dotenv_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
else:
    print("Warning: .env file not loaded; ETORO_PUBLIC_KEY/ETORO_PRIVATE_KEY may be missing.")

print(f"DEBUG: ETORO_PUBLIC_KEY set: {bool(os.getenv('ETORO_PUBLIC_KEY'))}")
print(f"DEBUG: ETORO_PRIVATE_KEY set: {bool(os.getenv('ETORO_PRIVATE_KEY'))}")

repo_root = str(Path(__file__).resolve().parent.parent.parent.parent)
functions_root = str(Path(__file__).resolve().parent.parent.parent)
port_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, repo_root)
sys.path.insert(0, functions_root)   # Functions/
sys.path.insert(0, port_root)         # Functions/port/

import pandas as pd

try:
    from Functions.data.loader import load_transactions_from_etoro
    _data_loader_import_ok = True
except Exception as _e:
    print("Functions.data.loader import FAILED:", _e)
    _data_loader_import_ok = False

try:
    from data.provider_factory import get_market_data_provider
except Exception as _e:
    print("data.provider_factory import FAILED:", _e)
    get_market_data_provider = None

try:
    from engine.analyzer import PortfolioAnalyzer
except Exception as _e:
    print("engine.analyzer import FAILED:", _e)
    PortfolioAnalyzer = None

try:
    from main import get_interactive_input
except Exception as _e:
    print("main import FAILED:", _e)
    get_interactive_input = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _print_failure_help():
    print()
    print("To fix this, either:")
    print("  1. export ETORO_PUBLIC_KEY=... ETORO_PRIVATE_KEY=...")
    print("  2. export ETORO_CID=<numeric-cid>")
    print()
    print("Then re-run: python3 Functions/port/engine/test_etoro_history.py")


def test_etoro_trade_history_endpoint():
    username = "jaynemesis"
    manual_cid = os.getenv("ETORO_CID", "").strip()

    print("=" * 60)
    print(f"TEST 1: Resolve CID for {username}")
    print("=" * 60)

    from Functions.etoro.client import ETPublicClient, EToroClientError, get_public_client_from_env

    client = None
    cid = None

    if manual_cid:
        print(f"Using manual ETORO_CID={manual_cid}")
        cid = manual_cid
    else:
        try:
            client = get_public_client_from_env(timeout=60)
            cid = client.resolve_cid(username)
            print(f"Auto-resolved CID={cid} for {username}")
        except EToroClientError as exc:
            cid = None

            if "404" in str(exc):
                print(f"CID resolution failed: eToro API returned 404 for username '{username}'.")
                print("This means the user-info endpoint could not find that username.")
                print("Possible causes: username is wrong, profile is private, or API permissions.")
            elif "401" in str(exc):
                print(f"CID resolution failed: eToro API returned 401 Unauthorized.")
                print("This means the public API key/user-key is missing or invalid.")
            else:
                print(f"CID resolution failed: {exc}")

            print()
            print("To fix this, either:")
            print("  1. Verify ETORO_PUBLIC_KEY and ETORO_PRIVATE_KEY env vars are correct")
            print("  2. Verify the eToro username is correct and the profile is public")
            print("  3. Export ETORO_CID directly: export ETORO_CID=<numeric-cid>")
            print()
            print("Then re-run: python3 Functions/port/engine/test_etoro_history.py")
            return False

    print()
    print("=" * 60)
    print(f"TEST 2: Direct eToro trade history fetch for {username}")
    print("=" * 60)

    try:
        if client is None:
            api_key = os.getenv("ETORO_PUBLIC_KEY", "")
            user_key = os.getenv("ETORO_PRIVATE_KEY", "")
            client = ETPublicClient(api_key=api_key, user_key=user_key, timeout=60)

        history = client.get_trade_history(username=username, explicit_cid=cid)

        print(f"Success. CID={history.cid}, records={history.total_items}, page={history.page}, per_page={history.items_per_page}")
        if history.records:
            sample = history.records[0]
            print(f"Sample record raw keys: {list(sample.raw.keys())[:10]}")
            print(f"Sample record raw: {sample.raw}")
        else:
            print("WARNING: API returned 0 records.")
            print("This may mean the user has no public trade history, or the CID is incorrect.")
            print("If you know the correct CID, set ETORO_CID=<numeric-cid> and re-run.")
    except Exception as exc:
        print(f"FAILED: {exc}")
        _print_failure_help()
        return False

    print()
    print("=" * 60)
    print(f"TEST 3: load_transactions_from_etoro('{username}')")
    print("=" * 60)

    if not _data_loader_import_ok or load_transactions_from_etoro is None:
        print("FAILED: load_transactions_from_etoro is not available.")
        return False

    df = load_transactions_from_etoro(username, cid=cid)
    if df.empty:
        print("DataFrame is empty after loading.")
        print("This is expected if the eToro API returned 0 trade history records.")
        print("To verify with non-empty data, set ETORO_CID to a user with public trade history.")
        return True

    print(f"Success. Loaded {len(df)} rows.")
    print(f"Columns: {df.columns.tolist()}")
    print(f"Date range: {df['Date'].min()} -> {df['Date'].max()}")
    print(f"Unique tickers: {df['Ticker'].unique().tolist()}")
    print(f"Side distribution:\n{df['Side'].value_counts()}")
    print()
    print("First 5 rows:")
    print(df.tail(5).to_string())

    print()
    print("=" * 60)
    print("TEST 4: Analyzer pipeline with eToro history")
    print("=" * 60)

    if get_interactive_input is None or PortfolioAnalyzer is None or get_market_data_provider is None:
        print("FAILED: Required imports for analyzer test are missing.")
        return False

    config = get_interactive_input(no_browser=True, etoro_username=username, etoro_cid=cid)
    analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())

    print(f"Analyzer etoro_username: {analyzer.etoro_username}")
    print(f"Analyzer etoro_cid: {analyzer.etoro_cid}")
    print(f"Analyzer transaction_mode before run: {analyzer.transaction_mode}")

    #analyzer.run_analysis()

    print(f"Analyzer transaction_mode after run: {analyzer.transaction_mode}")
    print(f"transactions_df shape: {analyzer.transactions_df.shape}")
    print(f"transactions_df empty: {analyzer.transactions_df.empty}")
    print(f"trades_table_html empty: {not getattr(analyzer, 'trades_table_html', '')}")

    charts = analyzer.charts
    has_trades_table = bool(charts.get("trades_table"))
    has_trades_metrics = bool(charts.get("trades_metrics_strip"))
    print(f"charts['trades_table'] present: {has_trades_table}")
    print(f"charts['trades_metrics_strip'] present: {has_trades_metrics}")

    if not has_trades_table:
        print("FAILED: trades_table chart not generated.")
        return False

    print("SUCCESS: All tests passed.")
    return True


if __name__ == "__main__":
    success = test_etoro_trade_history_endpoint()
    if not success:
        sys.exit(1)
