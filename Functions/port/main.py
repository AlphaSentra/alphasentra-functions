"""
Portfolio Function
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
import pickle
import gzip
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import argparse
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our modules
from engine.analyzer import PortfolioAnalyzer, PortfolioFunctionsError
from data.provider_factory import get_market_data_provider
from engine.output.html import generate_html_report, generate_ai_content_fragment
from Functions.db.cache import get_portfolio_cache_from_mongo, set_portfolio_cache_to_mongo
from Functions.port.config import CACHE_TTL_REPORT as _REPORT_TTL


def _analyzer_cache_key(etoro_username: str, benchmark_ticker: str, etoro_cid: str) -> str:
    suffix = f"_{(benchmark_ticker or '').strip().upper()}_{(etoro_cid or '').strip().lower()}" if benchmark_ticker or etoro_cid else ""
    return f"portfolio_report_{etoro_username.strip().lower()}{suffix}_analyzer"


def _serialize_analyzer_output(
    metrics: Dict[str, Dict],
    charts: Dict[str, str],
    start: Optional[datetime],
    holdings_df: pd.DataFrame,
    returns_series: Optional[pd.Series],
    benchmark_ticker: str,
    price_data: pd.DataFrame,
    risk_df: pd.DataFrame,
    sector_industry_df: pd.DataFrame,
    portfolio_df: pd.DataFrame,
    config: Dict[str, Any],
    trades_table_html: str,
    positions: pd.DataFrame,
) -> bytes:
    payload = {
        "metrics": metrics,
        "charts": charts,
        "start": start.isoformat() if start else None,
        "holdings_df": holdings_df.to_dict() if holdings_df is not None else None,
        "returns_series": returns_series.to_dict() if returns_series is not None else None,
        "benchmark_ticker": benchmark_ticker,
        "price_data": price_data.to_dict() if price_data is not None else None,
        "risk_df": risk_df.to_dict() if risk_df is not None else None,
        "sector_industry_df": sector_industry_df.to_dict() if sector_industry_df is not None else None,
        "portfolio_df": portfolio_df.to_dict() if portfolio_df is not None else None,
        "config": config,
        "trades_table_html": trades_table_html,
        "positions": positions.to_dict() if positions is not None else None,
    }
    return gzip.compress(pickle.dumps(payload))


def _deserialize_analyzer_output(data: bytes) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    payload = pickle.loads(gzip.decompress(data))
    return {
        "metrics": payload["metrics"],
        "charts": payload["charts"],
        "start": datetime.fromisoformat(payload["start"]) if payload["start"] else None,
        "holdings_df": pd.DataFrame(payload["holdings_df"]) if payload["holdings_df"] is not None else pd.DataFrame(),
        "returns_series": pd.Series(payload["returns_series"]) if payload["returns_series"] is not None else None,
        "benchmark_ticker": payload["benchmark_ticker"],
        "price_data": pd.DataFrame(payload["price_data"]) if payload["price_data"] is not None else pd.DataFrame(),
        "risk_df": pd.DataFrame(payload["risk_df"]) if payload["risk_df"] is not None else pd.DataFrame(),
        "sector_industry_df": pd.DataFrame(payload["sector_industry_df"]) if payload["sector_industry_df"] is not None else pd.DataFrame(),
        "portfolio_df": pd.DataFrame(payload["portfolio_df"]) if payload["portfolio_df"] is not None else pd.DataFrame(),
        "config": payload["config"],
        "trades_table_html": payload["trades_table_html"],
        "positions": pd.DataFrame(payload["positions"]) if payload["positions"] is not None else pd.DataFrame(),
    }


def _log_report_time(label: str, start_time: float):
    elapsed = time.perf_counter() - start_time
    logger.info(f"{label} completed in {elapsed:.2f}s")


def parse_flags() -> argparse.Namespace:
    """
    Parse command-line flags only (non-interactive options).

    Returns:
        argparse.Namespace with parsed flags.
    """
    parser = argparse.ArgumentParser(
        description="Portfolio Function",
        add_help=False  # We'll handle help manually after showing usage if needed
    )
    parser.add_argument(
        '--no-browser',
        action='store_true',
        default=False,
        help="Do not automatically open the report in a web browser."
    )
    parser.add_argument(
        '--help', '-h',
        action='store_true',
        default=False,
        help="Show this help message and exit."
    )
    # Parse only known args to ignore other inputs meant for interactive mode
    args, unknown = parser.parse_known_args()
    return args


def show_usage():
    """Display usage information."""
    print("""
Portfolio Function

Usage: python3 main.py [options]

Options:
    --no-browser    Do not automatically open the report in a web browser.
    --help, -h      Show this help message and exit.

The program will then prompt you interactively for:
  - Inception date (auto-detected from transaction history in eToro mode)
  - Benchmark ticker
  - Yield inclusion
  - Maximum position size
  - Maximum sector size
  - Minimum position size

No command-line arguments are required; all main inputs are collected via prompts.
    """.strip())


def get_interactive_input(no_browser: bool, etoro_username: str = "", benchmark_ticker: str = "", etoro_cid: str = "") -> dict:
    """
    Collect all inputs interactively from the user.

    Args:
        no_browser: Whether to suppress browser opening.
        etoro_username: Optional eToro username for report title customization.
        benchmark_ticker: Optional benchmark ticker to override auto-selection.
        etoro_cid: Optional eToro customer ID to avoid username resolution.

    Returns:
        Dictionary containing all configuration options.
    """
    print("=" * 60)
    print(f"PROCESSING PORTFOLIO: {etoro_username}")
    print("=" * 60)

    report_title = f"{etoro_username}" if etoro_username else "PORT"

    include_yield = True


    max_position_size = 20.0

    max_sector_size = 30.0

    min_position_size = 0.5

    # Optimization lookback period
    opt_lookback = '1y'

    # Initial investment (for transaction mode)
    initial_investment = 100000.0

    config = {
        'title': report_title,
        'include_yield': include_yield,
        'max_position_size': max_position_size,
        'max_sector_size': max_sector_size,
        'min_position_size': min_position_size,
        'opt_lookback': opt_lookback,
        'initial_investment': initial_investment,
        'no_browser': no_browser,
        'etoro_username': etoro_username,
        'etoro_cid': etoro_cid or None,
    }

    if benchmark_ticker:
        config['benchmark_ticker'] = benchmark_ticker

    return config


_ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Function - Error</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <style>
        @keyframes fade-in {{ 0%, 100% {{ opacity: 0; }} 50% {{ opacity: 1; }} }}
        @keyframes fade-out {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0; }} }}
        .animated-gradient-background {{
          position: absolute; top: 0; left: 0; width: 100%; height: 100%;
          background-color: #000; z-index: 0;
        }}
        .animated-gradient-background::before,
        .animated-gradient-background::after {{
          content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
          background-size: 100% 100%; background-repeat: no-repeat;
        }}
        .animated-gradient-background::before {{
          background-image: radial-gradient(ellipse 80% 50% at 50% 120%, rgba(180, 50, 50, 0.4), transparent);
          animation: fade-out 10s infinite;
        }}
        .animated-gradient-background::after {{
          background-image: radial-gradient(ellipse 80% 50% at 50% 120%, rgba(255, 100, 50, 0.3), transparent);
          animation: fade-in 10s infinite;
        }}
        body {{ margin: 0; padding: 0; font-family: 'Inter', system-ui, -apple-system, sans-serif; background-color: #000; color: #e0e0e0; }}
        .form-background-wrapper {{ position: relative; min-height: 100vh; overflow: hidden; background-color: #000; }}
        .form-foreground {{ position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 2rem; box-sizing: border-box; }}
        .error-card {{
          background: #1a1a1a; border: 1px solid #3a2020; border-radius: 12px;
          max-width: 600px; width: 100%; padding: 2.5rem; box-shadow: 0 0 40px rgba(255, 60, 60, 0.08);
        }}
        .error-icon {{ font-size: 2.5rem; margin-bottom: 1rem; }}
        .error-title {{ font-size: 1.4rem; font-weight: 700; color: #ff6b6b; margin-bottom: 0.75rem; letter-spacing: 0.02em; }}
        .error-message {{ font-size: 0.95rem; color: #b0b0b0; line-height: 1.6; margin-bottom: 1.25rem; }}
        .error-details {{ font-size: 0.8rem; color: #777; background: #111; padding: 0.75rem 1rem; border-radius: 6px; border: 1px solid #2a2a2a; word-break: break-word; white-space: pre-wrap; font-family: 'Courier New', monospace; }}
        .back-link {{ display: inline-block; margin-top: 1.5rem; color: #5ce0d8; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: color 0.2s; }}
        .back-link:hover {{ color: #7fecf5; }}

        /* Navigation loading overlay */
        .nav-loading-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 99999;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
        }}

        .nav-loading-overlay.active {{
            opacity: 1;
            pointer-events: auto;
        }}

        .nav-loading-spinner {{
            width: 48px;
            height: 48px;
            border: 4px solid rgba(255, 255, 255, 0.2);
            border-top-color: #fff;
            border-radius: 50%;
            animation: nav-spin 0.8s linear infinite;
        }}

        .nav-loading-text {{
            margin-top: 16px;
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            letter-spacing: 0.05em;
        }}

        @keyframes nav-spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="nav-loading-overlay" id="nav-loading-overlay">
        <div class="nav-loading-spinner"></div>
        <div class="nav-loading-text">Loading...</div>
    </div>
    <div class="animated-gradient-background"></div>
    <div class="form-background-wrapper">
        <div class="form-foreground">
            <div class="error-card">
                <div class="error-icon">&#9888;</div>
                <div class="error-title">Portfolio Report Failed to Generate</div>
                <div class="error-message">
                    The eToro portfolio for username <strong>{username}</strong> could not be loaded.
                    This is usually caused by an invalid or non-existent eToro username, or a temporary issue with the eToro API.
                    Please verify the username and try again.
                </div>
                <div class="error-details">{detail}</div>
                <a class="back-link" href="/port">Back to portfolio selection</a>
            </div>
        </div>
    </div>
    <script>
        (function() {{
            const overlay = document.getElementById('nav-loading-overlay');
            if (!overlay) return;

            function showOverlay() {{
                overlay.classList.add('active');
            }}

            document.addEventListener('click', function(e) {{
                const link = e.target.closest('a');
                if (link && link.href && !link.href.startsWith('javascript:') && !link.target && !link.hasAttribute('download')) {{
                    showOverlay();
                    return;
                }}

                const el = e.target.closest('[onclick]');
                if (el) {{
                    const onclick = (el.getAttribute('onclick') || '');
                    if (onclick.includes('window.location') || onclick.includes('window.top.location')) {{
                        showOverlay();
                        return;
                    }}
                }}

                const btn = e.target.closest('button[type="submit"]');
                if (btn && btn.closest('form')) {{
                    showOverlay();
                }}
            }});
        }})();
    </script>
</body>
</html>"""


def generate_portfolio_html(etoro_username: str = "", benchmark_ticker: str = "", etoro_cid: str = "", cached_ai_content=None, return_ai_content: bool = False, skip_ai: bool = False):
    """
    Generate portfolio HTML report and return it as a string.
    This function is used by the Flask web application.

    Args:
        etoro_username: Optional eToro username for report title customization.
        benchmark_ticker: Optional benchmark ticker to override auto-selection.
        etoro_cid: Optional eToro customer ID to avoid username resolution.
        cached_ai_content: Optional dict with pre-generated AI commentary text.
        return_ai_content: If True, return a tuple of (html, ai_content_dict).
        skip_ai: If True, generate HTML without AI content and without LLM calls.

    Returns:
        HTML string of the portfolio report, or tuple if return_ai_content is True.
    """
    report_start = time.perf_counter()
    config = get_interactive_input(no_browser=True, etoro_username=etoro_username, benchmark_ticker=benchmark_ticker, etoro_cid=etoro_cid)

    analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())

    logger.info("Starting portfolio function...")
    analyzer_cache_key = _analyzer_cache_key(etoro_username, benchmark_ticker, etoro_cid)
    cached_analyzer_bytes = get_portfolio_cache_from_mongo("portfolio_report_cache", analyzer_cache_key, ttl_seconds=_REPORT_TTL, ext=".pkl")
    if cached_analyzer_bytes is not None:
        logger.info("Analyzer cache hit for %s", etoro_username)
        cached = _deserialize_analyzer_output(cached_analyzer_bytes)
        if cached:
            analyzer.metrics = cached["metrics"]
            analyzer.charts = cached["charts"]
            analyzer.start = cached["start"]
            analyzer.holdings_df = cached["holdings_df"]
            analyzer.returns = {"total": cached["returns_series"]} if cached["returns_series"] is not None else {}
            analyzer.benchmark_ticker = cached["benchmark_ticker"]
            analyzer.prices = cached["price_data"]
            analyzer.risk_df = cached["risk_df"]
            analyzer.sector_industry_df = cached["sector_industry_df"]
            analyzer.portfolio = cached["portfolio_df"]
            analyzer.trades_table_html = cached["trades_table_html"]
            analyzer.positions = cached["positions"]
            metrics, charts, start = analyzer.metrics, analyzer.charts, analyzer.start
        else:
            cached_analyzer_bytes = None

    if cached_analyzer_bytes is None:
        try:
            metrics, charts, start = analyzer.run_analysis()
        except PortfolioFunctionsError as exc:
            logger.error("PortfolioFunctionsError for username=%s: %s", etoro_username, exc)
            error_html = _ERROR_HTML.format(
                username=etoro_username or "portfolio",
                detail=str(exc).replace("{", "{{").replace("}", "}}"),
            )
            if return_ai_content:
                return error_html, {}
            return error_html

        trades_table = getattr(analyzer, 'trades_table_html', '')
        holdings_df = getattr(analyzer, 'holdings_df', pd.DataFrame())
        positions = getattr(analyzer, 'positions', pd.DataFrame())
        prices = analyzer.prices

        serialized = _serialize_analyzer_output(
            metrics=metrics,
            charts=charts,
            start=start,
            holdings_df=holdings_df,
            returns_series=analyzer.returns.get('total'),
            benchmark_ticker=analyzer.benchmark_ticker,
            price_data=prices,
            risk_df=analyzer.risk_df,
            sector_industry_df=analyzer.sector_industry_df,
            portfolio_df=analyzer.portfolio,
            config=config,
            trades_table_html=trades_table,
            positions=positions,
        )
        set_portfolio_cache_to_mongo("portfolio_report_cache", analyzer_cache_key, serialized, ext=".pkl", ttl_seconds=_REPORT_TTL)

    trades_table = getattr(analyzer, 'trades_table_html', '')
    holdings_df = getattr(analyzer, 'holdings_df', pd.DataFrame())
    positions = getattr(analyzer, 'positions', pd.DataFrame())
    prices = analyzer.prices

    logger.info("Generating HTML report...")
    effective_cached_ai = cached_ai_content
    ai_content = None
    if skip_ai and effective_cached_ai is None:
        effective_cached_ai = {"intel_commentary_text": "", "overview_ai_interpretation": ""}
    elif return_ai_content and not skip_ai and cached_ai_content is None:
        ai_content = generate_ai_content_fragment(
            metrics, charts, config['title'], start,
            holdings_df=holdings_df,
            returns_series=analyzer.returns.get('total'),
            benchmark_ticker=analyzer.benchmark_ticker,
            price_data=prices,
        )
        effective_cached_ai = ai_content

    html = generate_html_report(
        metrics,
        charts,
        config['title'],
        start,
        include_yield=config['include_yield'],
        trades_table=trades_table,
        holdings_df=holdings_df,
        position_values=positions,
        price_data=prices,
        risk_df=analyzer.risk_df,
        sector_industry_df=analyzer.sector_industry_df,
        portfolio_df=analyzer.portfolio,
        config=config,
        returns_series=analyzer.returns.get('total'),
        benchmark_ticker=analyzer.benchmark_ticker,
        cached_ai_content=effective_cached_ai,
    )

    _log_report_time("Portfolio HTML report", report_start)

    if return_ai_content:
        if ai_content is not None:
            return html, ai_content
        if cached_ai_content is not None:
            return html, cached_ai_content
        ai_content = generate_ai_content_fragment(
            metrics, charts, config['title'], start,
            holdings_df=holdings_df,
            returns_series=analyzer.returns.get('total'),
            benchmark_ticker=analyzer.benchmark_ticker,
            price_data=prices,
        )
        return html, ai_content

    return html


def merge_static_html_with_ai(static_html: str, ai_content: dict, etoro_username: str = "", benchmark_ticker: str = "", etoro_cid: str = "") -> str:
    """
    Merge a previously generated static HTML report with AI content.
    Re-runs analysis but skips LLM calls by injecting cached AI.
    """
    if not ai_content:
        return static_html
    return generate_portfolio_html(
        etoro_username=etoro_username,
        benchmark_ticker=benchmark_ticker,
        etoro_cid=etoro_cid,
        cached_ai_content=ai_content,
    )


def generate_ai_commentary_text(etoro_username: str = "", benchmark_ticker: str = "", etoro_cid: str = "") -> str:
    """
    Generate combined plain-text commentary from overview, holdings and efficiency modules.

    Args:
        etoro_username: Optional eToro username for report title customization.
        benchmark_ticker: Optional benchmark ticker to override auto-selection.
        etoro_cid: Optional eToro customer ID to avoid username resolution.

    Returns:
        str: Combined commentary text suitable for sending to an AI prompt.
    """
    report_start = time.perf_counter()
    config = get_interactive_input(no_browser=True, etoro_username=etoro_username, benchmark_ticker=benchmark_ticker, etoro_cid=etoro_cid)

    analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())

    logger.info("Starting portfolio function...")
    metrics, charts, start = analyzer.run_analysis()

    holdings_df = getattr(analyzer, 'holdings_df', pd.DataFrame())
    prices = analyzer.prices

    logger.info("Generating AI commentary...")
    from engine.output.html import generate_portfolio_ai_commentary
    commentary = generate_portfolio_ai_commentary(
        metrics,
        charts,
        config['title'],
        start,
        holdings_df=holdings_df,
        price_data=prices,
        returns_series=analyzer.returns.get('total'),
        benchmark_ticker=analyzer.benchmark_ticker,
    )

    _log_report_time("Portfolio AI commentary", report_start)

    return commentary


def main() -> int:
    """
    Main entry point for the portfolio function.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    # Parse flags first
    flags = parse_flags()

    # Show usage and exit if --help
    if flags.help:
        show_usage()
        return 0

    try:
        report_start = time.perf_counter()
        # Collect input from user (interactive)
        config = get_interactive_input(flags.no_browser)

        # Create analyzer and run
        analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())

        logger.info("Starting portfolio function...")
        metrics, charts, start = analyzer.run_analysis()

        # Extract data for report
        trades_table = getattr(analyzer, 'trades_table_html', '')
        holdings_df = getattr(analyzer, 'holdings_df', pd.DataFrame())
        positions = getattr(analyzer, 'positions', pd.DataFrame())
        prices = analyzer.prices

        # Generate HTML report
        logger.info("Generating HTML report...")
        html = generate_html_report(
            metrics,
            charts,
            config['title'],
            start,
            include_yield=config['include_yield'],
            trades_table=trades_table,
            holdings_df=holdings_df,
            position_values=positions,
            price_data=prices,
            risk_df=analyzer.risk_df,
            sector_industry_df=analyzer.sector_industry_df,
            portfolio_df=analyzer.portfolio,
            config=config,
            returns_series=analyzer.returns.get('total'),
            benchmark_ticker=analyzer.benchmark_ticker,
        )

        logger.info("Analysis complete.")
        _log_report_time("Portfolio report (CLI)", report_start)
        print("\nAnalysis complete.")

        return 0

    except PortfolioFunctionsError as e:
        logger.error(f"Portfolio function failed: {e}")
        print(f"Error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\nAnalysis cancelled by user.")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
