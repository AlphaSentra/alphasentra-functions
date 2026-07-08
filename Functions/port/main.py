"""
Portfolio Function
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import logging
import pandas as pd
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our modules
from engine.analyzer import PortfolioAnalyzer, PortfolioFunctionsError
from data.provider_factory import get_market_data_provider
from engine.output.html import generate_html_report


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
    print("PORTFOLIO FUNCTION")
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


def generate_portfolio_html(etoro_username: str = "", benchmark_ticker: str = "", etoro_cid: str = "") -> str:
    """
    Generate portfolio HTML report and return it as a string.
    This function is used by the Flask web application.

    Args:
        etoro_username: Optional eToro username for report title customization.
        benchmark_ticker: Optional benchmark ticker to override auto-selection.
        etoro_cid: Optional eToro customer ID to avoid username resolution.

    Returns:
        HTML string of the portfolio report.
    """
    config = get_interactive_input(no_browser=True, etoro_username=etoro_username, benchmark_ticker=benchmark_ticker, etoro_cid=etoro_cid)

    analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())

    logger.info("Starting portfolio function...")
    metrics, charts, start = analyzer.run_analysis()

    trades_table = getattr(analyzer, 'trades_table_html', '')
    transactions_df = getattr(analyzer, 'transactions_df', pd.DataFrame())
    holdings_df = getattr(analyzer, 'holdings_df', pd.DataFrame())
    positions = getattr(analyzer, 'positions', pd.DataFrame())
    prices = analyzer.prices

    logger.info("Generating HTML report...")
    html = generate_html_report(
        metrics,
        charts,
        config['title'],
        start,
        transactions_df=transactions_df,
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

    return html


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
        # Collect input from user (interactive)
        config = get_interactive_input(flags.no_browser)

        # Create analyzer and run
        analyzer = PortfolioAnalyzer(config, market_data_provider=get_market_data_provider())

        logger.info("Starting portfolio function...")
        metrics, charts, start = analyzer.run_analysis()

        # Extract data for report
        trades_table = getattr(analyzer, 'trades_table_html', '')
        transactions_df = getattr(analyzer, 'transactions_df', pd.DataFrame())
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
            transactions_df=transactions_df,
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
