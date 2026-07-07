"""
Core portfolio functions engine.
"""


import logging
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import linregress

from data.loader import load_transactions_from_csv
from data.market import detect_relisted_stocks
from data.provider_factory import get_market_data_provider as _get_provider
from data.protocols import MarketDataProvider
from engine.modeling.timeseries import build_portfolio_timeseries, calculate_returns
from engine.modeling.metrics import calculate_performance_metrics
from engine.modeling.risk import (
    calculate_var_cvar,
    run_monte_carlo_simulation,
    calculate_risk_contribution,
    generate_shock_curve_chart,
    generate_shock_contribution_table
)
from config import BENCHMARK_CANDIDATES, ENABLED_MODULES, MARKET_SUFFIX_MAP, CRYPTO_PREFIXES, MARKET_DEFAULT_BENCHMARK

logger = logging.getLogger(__name__)


class PortfolioFunctionsError(Exception):
    """Custom exception for portfolio functions errors."""
    pass


class PortfolioAnalyzer:
    def __init__(self, config: Dict[str, Any], market_data_provider: Optional[MarketDataProvider] = None):
        self.config = config
        self.portfolio = pd.DataFrame()
        self.transactions_df = pd.DataFrame()
        self.prices = pd.DataFrame()
        self.ts = {}
        self.returns = {}
        self.benchmark = pd.Series(dtype='float64')
        self.benchmark_ticker = config.get('benchmark_ticker', BENCHMARK_CANDIDATES[0] if BENCHMARK_CANDIDATES else "^AXJO")
        self.include_yield = config['include_yield']
        self.transaction_mode = False
        self.initial_investment = config['initial_investment']
        self.start: Optional[datetime] = None
        self.end = datetime.now()
        self.metrics: Dict[str, Dict] = {}
        self.charts: Dict[str, str] = {}
        self.sector_industry_df = pd.DataFrame()
        self.risk_df = pd.DataFrame()
        self.layer_yields: Dict[str, float] = {}
        self.holdings_df = pd.DataFrame()
        self.positions = pd.DataFrame()
        self.market_data_provider = market_data_provider
        self._provider_instance = self.market_data_provider or _get_provider()
        self.etoro_username = config.get('etoro_username') or None
        self._etoro_returns_loaded = False
        self._etoro_portfolio_mode = False
        self._etoro_portfolio_raw = None

    # ----------------------------------------------------------------------
    # Input Handling & Data Loading
    # ----------------------------------------------------------------------

    def load_data(self) -> None:
        """Load transactions from CSV."""
        self.transaction_mode = True
        csv_path = Path(__file__).resolve().parent.parent / "transactions.csv"
        self.transactions_df = load_transactions_from_csv(str(csv_path))
        if self.transactions_df.empty:
            raise PortfolioFunctionsError("No transactions loaded from CSV.")
        logger.info(f"Loaded {len(self.transactions_df)} transactions.")
        logger.info("Portfolio/transactions loaded successfully.")

    def _load_etoro_portfolio_path(self) -> Tuple[bool, Optional[str]]:
        """
        Attempt to build the analysis from the live eToro portfolio API
        instead of running the full transaction-mode backtest.

        Returns:
            Tuple of (success, error_message). If success is True, error_message is None.
        """
        if not self.etoro_username:
            return False, "eToro username is not configured."

        try:
            from Functions.etoro.client import get_public_client_from_env
            client = get_public_client_from_env()
            portfolio = client.get_investor_portfolio(self.etoro_username)

            agg_positions = [
                pos for pos in portfolio.aggregated_positions
                if pos.symbol and pos.weight > 0.0001
            ]
            if not agg_positions:
                return False, "eToro portfolio returned no positions; falling back to transaction mode."

            self.transaction_mode = False
            self._etoro_portfolio_mode = True

            self.portfolio = pd.DataFrame([
                {
                    "ticker": pos.symbol,
                    "quantity": pos.weight,
                    "type": "L" if pos.trade_direction == "BUY" else "S" if pos.trade_direction == "SELL" else "MIXED",
                    "avg_price": pos.average_entry_price,
                }
                for pos in agg_positions
            ])

            self.start = self.parse_inception_date()
            effective_start = self.start or datetime(2000, 1, 1)

            tickers = self.portfolio['ticker'].tolist()
            tickers = self._prepare_tickers(tickers)

            provider = self.market_data_provider or _get_provider()
            self.prices_full = provider.download_price_data(tickers, effective_start, self.end)

            if isinstance(self.prices_full.columns, pd.MultiIndex):
                self.prices = self.prices_full["Close"]
            else:
                self.prices = self.prices_full[["Close"]]

            self._etoro_portfolio_raw = portfolio
            if 'benchmark_ticker' not in self.config:
                candidates = getattr(self, '_ordered_benchmark_candidates', BENCHMARK_CANDIDATES)
                candidates = [c for c in candidates if c in self.prices.columns]
                if candidates:
                    self.benchmark_ticker = candidates[0]
                    logger.info("Default benchmark set to %s based on eToro portfolio market exposure.", self.benchmark_ticker)
            logger.info("eToro live portfolio fast-path loaded successfully (%d positions).", len(agg_positions))
            return True, None

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            logger.warning("eToro portfolio fast-path failed (%s); falling back to transaction mode.", exc)
            return False, error_msg

    def parse_inception_date(self) -> Optional[datetime]:
        """Determine inception date. When eToro is active, defer to the API timeseries."""
        if self.etoro_username:
            logger.info("Deferring inception date to eToro timeseries.")
            return None

        if self.transaction_mode and not self.transactions_df.empty:
            start = self.transactions_df["Date"].min()
            logger.info(f"Using earliest transaction date {start.strftime('%Y-%m-%d')} as inception date.")
            return start

        start = datetime(2000, 1, 1)
        logger.info(f"Using default inception date: {start.strftime('%Y-%m-%d')}")
        return start

    def _get_tickers(self) -> list:
        """Extract unique tickers from transactions or live eToro portfolio."""
        if self._etoro_portfolio_mode and not self.portfolio.empty:
            return [t for t in self.portfolio['ticker'].astype(str).tolist() if t != "USD=X"]
        tickers = self.transactions_df["Ticker"].dropna().unique().astype(str).tolist()
        return tickers

    def _infer_primary_market(self, tickers: list) -> str:
        """Infer the portfolio's primary market from weights and suffix rules.

        Returns one of the keys from ``MARKET_SUFFIX_MAP`` values, ``CRYPTO``,
        or ``OTHER`` when no region dominates. The vote buckets are derived
        dynamically from ``MARKET_SUFFIX_MAP`` so adding new suffixes does
        not require code changes here.
        """
        weights: dict[str, float] = {}
        total_weight = 0.0

        if self._etoro_portfolio_mode and not self.portfolio.empty:
            for _, row in self.portfolio.iterrows():
                t = str(row.get('ticker', ''))
                w = float(row.get('weight', 0) or 0)
                if t in tickers:
                    weights[t] = weights.get(t, 0.0) + w
                    total_weight += w
        elif not self.transactions_df.empty:
            counts = self.transactions_df['Ticker'].value_counts()
            for t in tickers:
                w = float(counts.get(t, 1))
                weights[t] = weights.get(t, 0.0) + w
                total_weight += w

        if total_weight == 0:
            for t in tickers:
                weights[t] = 1.0
                total_weight += 1.0

        suffix_map = MARKET_SUFFIX_MAP
        crypto_prefixes = CRYPTO_PREFIXES

        vote_buckets = set(suffix_map.values()) | {"CRYPTO", "OTHER"}
        votes = {market: 0.0 for market in vote_buckets}
        for ticker, w in weights.items():
            upper = ticker.upper()
            market = "OTHER"
            for suffix, region in suffix_map.items():
                if upper.endswith(suffix):
                    market = region
                    break
            if any(upper.startswith(p) for p in crypto_prefixes):
                market = "CRYPTO"
            votes[market] += w / total_weight

        best_market = max(votes, key=votes.get)
        if votes[best_market] < 0.5:
            return "OTHER"
        return best_market

    # ----------------------------------------------------------------------
    # Market Data Processing
    # ----------------------------------------------------------------------

    def _prepare_tickers(self, tickers: list) -> list:
        """
        Normalize ticker format and add benchmarks.

        Reorders benchmark candidates based on the portfolio's actual market
        exposure so the default fallback is regionally appropriate rather than
        always ASX 200.

        Args:
            tickers: List of ticker symbols.

        Returns:
            Final ticker list including benchmarks.
        """
        tickers = [t.replace(".ASX", ".AX") if isinstance(t, str) and t.endswith(".ASX") else t for t in tickers]

        candidates = list(BENCHMARK_CANDIDATES)
        if candidates:
            primary_market = self._infer_primary_market(tickers)
            market_defaults = MARKET_DEFAULT_BENCHMARK
            default_candidate = market_defaults.get(primary_market, "^GSPC")
            candidates.sort(key=lambda c: (0 if c == default_candidate else 1, BENCHMARK_CANDIDATES.index(c)))
            logger.info("Portfolio primary market inferred as %s; default benchmark candidate=%s.", primary_market, default_candidate)

        self._ordered_benchmark_candidates = candidates

        for candidate in candidates:
            if candidate not in tickers:
                tickers.append(candidate)

        return tickers

    def download_and_process_prices(self) -> None:
        """Download price data and filter re-listed/crashed stocks."""
        tickers = self._get_tickers()
        tickers = self._prepare_tickers(tickers)

        provider = self.market_data_provider or _get_provider()

        effective_start = self.start
        if effective_start is None:
            logger.info("No inception date yet; fetching full available price history for benchmark/indices.")
            effective_start = self.end - timedelta(days=365 * 25)

        self.prices_full = provider.download_price_data(tickers, effective_start, self.end)

        # Extract closing prices for analysis
        if isinstance(self.prices_full.columns, pd.MultiIndex):
            self.prices = self.prices_full["Close"]
        else:
            self.prices = self.prices_full[["Close"]]

        if 'benchmark_ticker' not in self.config:
            candidates = getattr(self, '_ordered_benchmark_candidates', BENCHMARK_CANDIDATES)
            candidates = [c for c in candidates if c in self.prices.columns]
            if candidates:
                self.benchmark_ticker = candidates[0]
                logger.info("Default benchmark set to %s based on portfolio market exposure.", self.benchmark_ticker)

        relisted_tickers = detect_relisted_stocks(self.prices)
        if relisted_tickers:
            logger.info(f"Excluding re-listed/crashed stocks: {relisted_tickers}")
            self.prices = self.prices.drop(columns=relisted_tickers, errors='ignore')
            if self.transaction_mode and not self.transactions_df.empty:
                self.transactions_df = self.transactions_df[~self.transactions_df['Ticker'].isin(relisted_tickers)]
            elif self._etoro_portfolio_mode and not self.portfolio.empty:
                self.portfolio = self.portfolio.drop(index=relisted_tickers, errors='ignore')
            logger.info(f"Removed {len(relisted_tickers)} tickers from records.")

    def _select_benchmark(self) -> None:
        """
        Dynamically select the best benchmark from candidates based on average R²
        fit across portfolio holdings. Falls back to the first available candidate
        if R² computation is not possible.
        """
        if not hasattr(self, 'prices') or self.prices.empty:
            logger.warning("Benchmark auto-selection skipped: prices empty or missing.")
            return

        portfolio_tickers = [t for t in self._get_tickers() if t in self.prices.columns]
        if not portfolio_tickers:
            logger.warning("Benchmark auto-selection skipped: no portfolio tickers in price data.")
            return

        portfolio_returns = self.prices[portfolio_tickers].pct_change().dropna()
        if portfolio_returns.empty:
            logger.warning("Benchmark auto-selection skipped: portfolio returns empty after dropna.")
            return

        best_benchmark = None
        best_score = -1

        candidates = list(BENCHMARK_CANDIDATES)
        if self.benchmark_ticker not in candidates:
            candidates.append(self.benchmark_ticker)

        etoro_total_returns = None
        etoro_path = False
        if self._etoro_returns_loaded:
            etoro_total_returns = self.returns["total"]
            etoro_path = True
            logger.info(
                "Benchmark selection using eToro total-return series (%d points)",
                len(etoro_total_returns),
            )
        elif self.etoro_username:
            logger.info(
                "Benchmark selection: eToro username present but eToro returns failed; using per-stock R²"
            )

        benchmark_returns_lookup = {}
        for candidate in candidates:
            if candidate not in self.prices.columns:
                logger.info("Benchmark candidate %s skipped: not in price columns.", candidate)
                continue
            benchmark_returns_lookup[candidate] = self.prices[candidate].pct_change().dropna()

        MIN_ALIGN = 10

        if etoro_path and etoro_total_returns is not None:
            candidate_scores = []
            for candidate, benchmark_returns in benchmark_returns_lookup.items():
                if benchmark_returns.empty or benchmark_returns.std() == 0:
                    logger.info("Benchmark candidate %s skipped: empty or zero-std returns.", candidate)
                    continue
                aligned = pd.concat([etoro_total_returns, benchmark_returns], axis=1).dropna()
                if len(aligned) < MIN_ALIGN:
                    logger.info("Benchmark candidate %s skipped: only %d aligned rows (need %d).", candidate, len(aligned), MIN_ALIGN)
                    continue
                x = aligned.iloc[:, 1].values
                y = aligned.iloc[:, 0].values
                if np.std(x) == 0 or np.std(y) == 0:
                    logger.info("Benchmark candidate %s skipped: zero std in aligned series.", candidate)
                    continue
                corr = np.corrcoef(x, y)[0, 1]
                if np.isnan(corr):
                    logger.info("Benchmark candidate %s skipped: NaN correlation.", candidate)
                    continue
                score = corr ** 2
                weight = min(len(aligned) / 60.0, 1.0)
                candidate_scores.append((score, weight, candidate))
                logger.info("Benchmark candidate %s R² vs eToro total: %.4f (weight=%.2f)", candidate, score, weight)

            if candidate_scores:
                candidate_scores.sort(key=lambda t: t[0] * t[1], reverse=True)
                best_score, best_weight, best_benchmark = candidate_scores[0]
                logger.info("Selected benchmark %s via eToro path (weighted score=%.4f).", best_benchmark, best_score * best_weight)
        else:
            portfolio_tickers_in_prices = [t for t in portfolio_tickers if t in self.prices.columns]
            if portfolio_tickers_in_prices and not self.prices.empty:
                portfolio_returns = self.prices[portfolio_tickers_in_prices].pct_change().dropna()
                if not portfolio_returns.empty:
                    candidate_scores = []
                    for candidate in candidates:
                        if candidate not in self.prices.columns:
                            continue
                        benchmark_returns = self.prices[candidate].pct_change().dropna()
                        if benchmark_returns.empty or benchmark_returns.std() == 0:
                            logger.info("Benchmark candidate %s skipped: empty or zero-std returns.", candidate)
                            continue
                        r2_scores = []
                        weights = []
                        for ticker in portfolio_returns.columns:
                            aligned = pd.concat([portfolio_returns[ticker], benchmark_returns], axis=1).dropna()
                            if len(aligned) < MIN_ALIGN:
                                continue
                            x = aligned.iloc[:, 1].values
                            y = aligned.iloc[:, 0].values
                            if np.std(x) == 0 or np.std(y) == 0:
                                continue
                            corr = np.corrcoef(x, y)[0, 1]
                            if not np.isnan(corr):
                                r2 = corr ** 2
                                w = min(len(aligned) / 40.0, 1.0)
                                r2_scores.append(r2 * w)
                                weights.append(w)
                        if r2_scores:
                            score = float(sum(r2_scores) / sum(weights)) if sum(weights) > 0 else 0.0
                            candidate_scores.append((score, candidate))
                            logger.info("Benchmark candidate %s weighted R²: %.4f (from %d tickers).", candidate, score, len(r2_scores))
                        else:
                            logger.info("Benchmark candidate %s skipped: no tickers with sufficient aligned data.", candidate)

                    if candidate_scores:
                        candidate_scores.sort(key=lambda t: t[0], reverse=True)
                        best_score, best_benchmark = candidate_scores[0]
                        logger.info("Selected benchmark %s via per-stock weighted R² (score=%.3f).", best_benchmark, best_score)

        if best_benchmark:
            self.benchmark_ticker = best_benchmark
            logger.info(f"Selected benchmark {best_benchmark} (score={best_score:.3f})")
        else:
            selection_failure_reason = "no R² data available"
            if portfolio_tickers and not portfolio_returns.empty:
                combined_returns = portfolio_returns.mean(axis=1)
                for candidate in candidates:
                    if candidate not in self.prices.columns:
                        continue
                    benchmark_returns = self.prices[candidate].pct_change().dropna()
                    if benchmark_returns.empty or benchmark_returns.std() == 0:
                        continue
                    aligned = pd.concat([combined_returns, benchmark_returns], axis=1).dropna()
                    if len(aligned) < MIN_ALIGN:
                        continue
                    x = aligned.iloc[:, 1].values
                    y = aligned.iloc[:, 0].values
                    if np.std(x) == 0 or np.std(y) == 0:
                        continue
                    corr = np.corrcoef(x, y)[0, 1]
                    if not np.isnan(corr):
                        score = corr ** 2
                        logger.info(
                            "Selected benchmark %s via combined portfolio correlation (score=%.3f); per-stock R² insufficient.",
                            candidate, score,
                        )
                        self.benchmark_ticker = candidate
                        return

                selection_failure_reason = "combined portfolio correlation insufficient"

            for candidate in candidates:
                if candidate in self.prices.columns:
                    self.benchmark_ticker = candidate
                    logger.warning(
                        "Auto-selection failed (%s) Falling back to %s.",
                        selection_failure_reason, candidate,
                    )
                    break

    def _load_etoro_gain_timeseries(self) -> tuple[pd.Series, pd.Series]:
        """
        Fetch eToro daily gain timeseries and convert to daily returns.

        Returns:
            Tuple of (daily_returns, cumulative_value_series).

        Raises:
            PortfolioFunctionsError: If the eToro API returns no usable data.
        """
        from Functions.etoro.client import get_public_client_from_env, EToroClientError

        client = get_public_client_from_env()
        max_date = self.end.strftime("%Y-%m-%d") if self.end else None
        min_date = "2000-01-01"
        history = client.get_investor_gain_timeseries(
            self.etoro_username,
            granularity="daily",
            min_date=min_date,
            max_date=max_date,
        )

        if not history.gains:
            raise PortfolioFunctionsError(f"No gain data returned from eToro for {self.etoro_username}")

        logger.info(
            "eToro API returned %d raw gain points for %s (first=%s, last=%s)",
            len(history.gains),
            self.etoro_username,
            history.gains[0].date if history.gains else None,
            history.gains[-1].date if history.gains else None,
        )

        gains_df = pd.DataFrame([
            {"date": p.date, "gain": float(p.gain)}
            for p in history.gains
            if p.date is not None
        ])
        gains_df = gains_df.sort_values("date").drop_duplicates(subset=["date"]).set_index("date")

        if len(gains_df) < 2:
            raise PortfolioFunctionsError(f"Insufficient eToro gain data for {self.etoro_username}")

        if hasattr(self, "prices") and not self.prices.empty and isinstance(self.prices.index, pd.DatetimeIndex):
            mask = (self.prices.index >= gains_df.index.min()) & (self.prices.index <= gains_df.index.max())
            trading_index = self.prices.index[mask]
        else:
            trading_index = pd.bdate_range(start=gains_df.index.min(), end=gains_df.index.max())

        if trading_index.empty:
            trading_index = pd.bdate_range(start=gains_df.index.min(), end=gains_df.index.max())

        gains_df = gains_df.reindex(trading_index)
        gains_df["gain"] = gains_df["gain"].fillna(0).ffill()

        logger.info(
            "eToro gains after alignment: %d points, index %s to %s",
            len(gains_df),
            gains_df.index[0] if len(gains_df) else None,
            gains_df.index[-1] if len(gains_df) else None,
        )

        if len(gains_df) < 2:
            raise PortfolioFunctionsError(f"Insufficient eToro gain data for {self.etoro_username}")

        cumulative_values = self.initial_investment * (1 + gains_df["gain"] / 100).cumprod()
        cumulative_values = cumulative_values[cumulative_values > 0]

        if len(cumulative_values) < 2:
            raise PortfolioFunctionsError(f"Insufficient positive eToro cumulative values for {self.etoro_username}")

        cumulative_values = cumulative_values.reindex(gains_df.index).ffill().dropna()
        daily_returns = cumulative_values.pct_change().dropna()

        logger.info(
            "eToro cumulative values: first=%.4f, last=%.4f",
            cumulative_values.iloc[0],
            cumulative_values.iloc[-1],
        )

        return daily_returns, cumulative_values

    def _calculate_etoro_gain_error(self, error: Exception) -> tuple[pd.Series, pd.Series]:
        """
        Produce a zero-return fallback when the eToro gain API is unavailable.

        Args:
            error: The original exception raised by the eToro client.

        Returns:
            Tuple of (empty daily_returns, empty cumulative_value_series).
        """
        logger.warning("Falling back to empty eToro gain series after error: %s", error)
        empty = pd.Series(dtype="float64")
        return empty, empty

    # ----------------------------------------------------------------------
    # Timeseries & Returns
    # ----------------------------------------------------------------------

    def build_timeseries(self) -> None:
        """Build portfolio timeseries from transactions or live eToro portfolio."""
        if self._etoro_portfolio_mode and not self.portfolio.empty:
            etoro_total = self.ts.get("total")
            portfolio_for_ts = self.portfolio.copy()
            self.ts = build_portfolio_timeseries(
                self.prices,
                portfolio_df=portfolio_for_ts,
                transactions_df=None,
                total_investment=self.initial_investment,
            )
            if etoro_total is not None and not etoro_total.empty:
                self.ts["total"] = etoro_total
            self.holdings_df = self.portfolio.copy()
            self.holdings_df['quantity'] = self.portfolio['quantity']
            self.holdings_df['avg_price'] = self.portfolio.get('avg_price', pd.Series(dtype=float))
        else:
            self.ts = build_portfolio_timeseries(
                self.prices,
                portfolio_df=pd.DataFrame(),
                transactions_df=self.transactions_df,
                start_date=self.start,
                total_investment=self.initial_investment
            )
        self.positions = self.ts["positions"]
        if not hasattr(self, 'holdings_df') or self.holdings_df is None:
            self.holdings = self.ts["holdings"]

    def calculate_returns(self) -> None:
        """Calculate daily returns for portfolio and benchmark."""
        self._etoro_returns_loaded = False
        if self.etoro_username:
            try:
                self.returns["total"], self.ts["total"] = self._load_etoro_gain_timeseries()
                self._etoro_returns_loaded = True
                logger.info(
                    "Using eToro gain timeseries for portfolio returns (%d points)",
                    len(self.ts["total"]),
                )
                etoro_start = self.ts["total"].index[0]
                if self.start is None or etoro_start < self.start:
                    self.start = etoro_start
                    logger.info("Updated inception date to eToro start: %s", self.start.strftime("%Y-%m-%d"))
            except Exception as exc:
                logger.warning("eToro gain fetch failed (%s). Falling back to local transaction timeseries.", exc)
                self.returns = calculate_returns(self.ts)
        else:
            self.returns = calculate_returns(self.ts)

        self.benchmark = self.prices[self.benchmark_ticker].pct_change().dropna()

        if not self.benchmark.empty and not self.ts["total"].empty:
            portfolio_start = self.ts["total"].first_valid_index()
            if portfolio_start is not None:
                benchmark_for_chart = self.benchmark[self.benchmark.index >= portfolio_start]
                if not benchmark_for_chart.empty:
                    initial_reference = self.initial_investment
                    cumulative_benchmark_returns = (1 + benchmark_for_chart).cumprod()
                    self.ts["benchmark"] = cumulative_benchmark_returns * initial_reference
                else:
                    self.ts["benchmark"] = pd.Series(dtype='float64')
            else:
                self.ts["benchmark"] = pd.Series(dtype='float64')
        else:
            logger.warning("Benchmark series is empty. Benchmark not added.")
            self.ts["benchmark"] = pd.Series(dtype='float64')

    # ----------------------------------------------------------------------
    # Sector & Risk Data
    # ----------------------------------------------------------------------

    def load_sector_industry_data(self) -> None:
        """Fetch sector, industry, and dividend yield data."""
        if not self.transactions_df.empty and "Ticker" in self.transactions_df.columns:
            portfolio_tickers = self.transactions_df["Ticker"].dropna().unique().astype(str).tolist()
        elif not self.portfolio.empty and "ticker" in self.portfolio.columns:
            portfolio_tickers = self.portfolio['ticker'].astype(str).tolist()
        else:
            portfolio_tickers = []

        all_tickers = list(set(portfolio_tickers + [self.benchmark_ticker]))
        provider = self.market_data_provider or _get_provider()
        self.sector_industry_df = provider.get_sector_industry_data(all_tickers)
        self.sector_industry_df = self.sector_industry_df[~self.sector_industry_df.index.duplicated(keep='first')]

    def calculate_risk_contribution(self) -> None:
        """Calculate risk contribution for active holdings."""
        active_tickers_list = self._get_active_tickers()
        if not active_tickers_list:
            logger.warning("No active tickers found for risk calculation.")
            self.risk_df = pd.DataFrame()
            return

        asset_returns = self.prices[active_tickers_list].pct_change().dropna()
        self.risk_df = calculate_risk_contribution(
            self.ts["positions"][active_tickers_list],
            self.ts["total"],
            asset_returns=asset_returns
        )

        # Normalize weights to sum to 1 only in transaction mode (the computed backtest
        # weights are fractions). In eToro mode, risk_df is populated verbatim from
        # get_investor_portfolio which already sums to 100 — re-normalizing would change them.
        if not self._etoro_portfolio_mode:
            weight_sum = self.risk_df['Weight'].sum()
            if weight_sum > 0:
                self.risk_df['Weight'] = self.risk_df['Weight'] / weight_sum
                self.risk_df['Risk Contribution'] = self.risk_df['Risk Contribution'] / weight_sum
                self.risk_df['% Risk Contribution'] = self.risk_df['% Risk Contribution'] / weight_sum

    def _get_active_tickers(self) -> list:
        """Get tickers with non-trivial positions at end of period."""
        latest_pos_vals = self.ts["positions"].iloc[-1]
        latest_total_val = self.ts["total"].iloc[-1]

        if latest_total_val > 0:
            active_tickers_list = latest_pos_vals[latest_pos_vals / latest_total_val > 0.0001].index.tolist()
        else:
            active_tickers_list = []

        if not active_tickers_list:
            active_tickers_list = self.ts["positions"].columns.tolist()

        return active_tickers_list

    # ----------------------------------------------------------------------
    # Yield Calculation
    # ----------------------------------------------------------------------

    def calculate_yields(self) -> None:
        """Calculate dividend yields for portfolio layers and benchmark."""
        self.layer_yields = {"total": 0.0}
        self.benchmark_yield = 0.0  # default

        if not self.include_yield:
            return

        if self.risk_df.empty:
            logger.warning("Risk DataFrame empty; cannot calculate yields.")
            return

        # Total portfolio yield
        yield_analysis_df = self.risk_df[['Weight']].merge(
            self.sector_industry_df[['dividendYield']],
            left_index=True, right_index=True, how='left'
        )
        yield_analysis_df['dividendYield'] = yield_analysis_df['dividendYield'].fillna(0)
        total_yield = (yield_analysis_df['Weight'] * yield_analysis_df['dividendYield']).sum()
        self.layer_yields["total"] = total_yield

        # Benchmark yield
        benchmark_yield = self.sector_industry_df.loc[
            self.benchmark_ticker, 'dividendYield'
        ] if self.benchmark_ticker in self.sector_industry_df.index else 0.0
        self.benchmark_yield = 0.0 if pd.isna(benchmark_yield) else benchmark_yield

        # Layer-specific yields are handled separately in calculate_metrics()

    # ----------------------------------------------------------------------
    # Metrics Calculation
    # ----------------------------------------------------------------------

    def calculate_metrics(self) -> None:
        """
        Compute performance metrics for different time horizons based on calendar time.
        """
        # Define horizons using pandas DateOffset
        horizons = {
            "1W": pd.DateOffset(weeks=1),
            "1M": pd.DateOffset(months=1),
            "3M": pd.DateOffset(months=3),
            "1Y": pd.DateOffset(years=1),
            "5Y": pd.DateOffset(years=5),
            "All": None
        }
        
        # Calculate benchmark metrics per horizon
        for h, offset in horizons.items():
            if offset:
                start_date = self.end - offset
                b_slice = self.benchmark[self.benchmark.index >= start_date]
            else:
                b_slice = self.benchmark
            
            if len(b_slice) < 2:
                continue

            b_metrics = calculate_performance_metrics(b_slice, b_slice)
            
            # Add VaR/CVaR for benchmark
            b_var_cvar = calculate_var_cvar(b_slice)
            b_metrics["VaR (95%, 1-Year)"] = b_var_cvar["VaR"] * np.sqrt(252)
            b_metrics["CVaR (95%, 1-Year)"] = b_var_cvar["CVaR"] * np.sqrt(252)
            
            self.metrics[f"benchmark_{h}"] = b_metrics

        # Layer metrics
        for layer in ["total"]:
            layer_returns = self.returns[layer]
            
            for h, offset in horizons.items():
                if offset:
                    start_date = self.end - offset
                    l_slice = layer_returns[layer_returns.index >= start_date]
                    b_slice = self.benchmark[self.benchmark.index >= start_date]
                    # Align indices
                    common = l_slice.index.intersection(b_slice.index)
                    l_slice = l_slice.loc[common]
                    b_slice = b_slice.loc[common]
                else:
                    l_slice = layer_returns
                    b_slice = self.benchmark
                    common = l_slice.index.intersection(b_slice.index)
                    l_slice = l_slice.loc[common]
                    b_slice = b_slice.loc[common]

                if len(l_slice) < 2:
                    continue

                performance_metrics = calculate_performance_metrics(
                    l_slice, b_slice,
                    annual_yield=0,
                    benchmark_yield=0
                )
                
                # Daily yield
                daily_yield = (1 + self.layer_yields[layer]) ** (1/252) - 1
                adjusted_layer_returns = l_slice + daily_yield
                var_cvar = calculate_var_cvar(adjusted_layer_returns)
                performance_metrics["VaR (95%, 1-Year)"] = var_cvar["VaR"] * np.sqrt(252)
                performance_metrics["CVaR (95%, 1-Year)"] = var_cvar["CVaR"] * np.sqrt(252)
                performance_metrics["Estimated Yield"] = self.layer_yields[layer]
                
                self.metrics[h] = performance_metrics
                if f"benchmark_{h}" in self.metrics:
                    self.metrics[h]["benchmark"] = self.metrics[f"benchmark_{h}"]

    # ----------------------------------------------------------------------
    # Monte Carlo Simulation
    # ----------------------------------------------------------------------

    def run_monte_carlo(self) -> None:
        """Run Monte Carlo simulation and add metrics to self.metrics['total']."""
        logger.info("Running Monte Carlo Simulation (10,000 paths, 1-year forecast)...")
        initial_portfolio_value = self.ts["total"].iloc[-1]
        mc_simulations = run_monte_carlo_simulation(
            initial_portfolio_value,
            self.returns["total"],
            num_simulations=10000,
            forecast_days=252
        )
        
        # Calculate metrics from simulation paths
        final_mc_values = mc_simulations.iloc[-1]
        mc_returns_percentage = (mc_simulations.iloc[-1] / mc_simulations.iloc[0] - 1)

        # Forward Expected Drawdown (average of max drawdowns across paths)
        drawdowns = []
        for col in mc_simulations.columns:
            cumulative = mc_simulations[col]
            peak = cumulative.cummax()
            drawdown = (cumulative - peak) / peak  # Negative values
            drawdowns.append(drawdown.min())
        mc_expected_drawdown = np.mean(drawdowns)

        # Store Monte Carlo metrics in 'total' layer
        total_metrics = self.metrics.get("total", {})
        total_metrics["MC_Mean_Final_Return"] = mc_returns_percentage.mean()
        total_metrics["MC_Expected_Drawdown_Pct"] = mc_expected_drawdown
        total_metrics["MC_VaR_99_Pct"] = np.percentile(mc_returns_percentage, 1)
        total_metrics["MC_VaR_95_Pct"] = np.percentile(mc_returns_percentage, 5)
        total_metrics["MC_Expected_Upside_95_Pct"] = np.percentile(mc_returns_percentage, 95)
        self.metrics["total"] = total_metrics
        self.mc_simulations = mc_simulations  # Save for charts

    # ----------------------------------------------------------------------
    # Chart Generation
    # ----------------------------------------------------------------------

    def generate_charts(self) -> Dict[str, str]:
        """Generate all standard charts."""
        from engine.output.charts import generate_charts
        from engine.modules.breakdown.charts import (
            generate_zscore_scatter_plot,
            generate_breakdown_metrics_strip,
            generate_sector_sunburst_chart
        )
        from engine.modules.monte_carlo.charts import (
            generate_monte_carlo_chart,
            generate_monte_carlo_metrics_strip
        )
        from engine.modules.risks.charts import generate_var_es_analysis_charts
        from engine.modules.history.charts import generate_trades_metrics_strip
        from engine.modules.holdings.charts import generate_holdings_metrics_strip
        from engine.modules.overview.charts import generate_advances_declines_charts
        
        from engine.modules.breakdown.renderer import (
            generate_sector_industry_analysis,
            generate_sector_performance_table
        )
        from engine.modules.holdings.renderer import (
            generate_portfolio_holdings_analysis
        )
        from engine.modules.history.renderer import generate_trades_table

        charts = {}

        # Base charts (risk, correlation, etc.)
        active_tickers = self._get_active_tickers()
        asset_returns = self.prices[active_tickers].pct_change().dropna()

        direction_map = {}
        if self.holdings_df is not None and not self.holdings_df.empty and 'type' in self.holdings_df.columns:
            direction_map = self.holdings_df['type'].to_dict()

        direction_map = {t: ('L' if v == 'MIXED' else v) for t, v in direction_map.items()}

        holdings_tickers = set(self.holdings_df.index.tolist()) if self.holdings_df is not None and not self.holdings_df.empty else set()
        logger.info("Correlation holdings_df columns: %s", self.holdings_df.columns.tolist() if self.holdings_df is not None else None)
        logger.info("Correlation holdings_df types (normalized): %s", {t: direction_map.get(t) for t in active_tickers if t in direction_map or t in self.prices.columns})

        short_tickers = [t for t in active_tickers if direction_map.get(t) == 'S']
        logger.info("Correlation short tickers: %s", short_tickers)

        flipped = []
        for ticker in active_tickers:
            if ticker in asset_returns.columns and direction_map.get(ticker) == 'S':
                asset_returns[ticker] = -asset_returns[ticker]
                flipped.append(ticker)
        logger.info("Correlation flipped tickers: %s", flipped)

        corr = asset_returns.corr()
        corr = corr.mask(np.eye(len(corr), dtype=bool), -2.0)
        base_charts = generate_charts(
            self.ts, self.risk_df, corr, self.benchmark_ticker,
            annual_yield=self.layer_yields.get("total", 0.0),
            metrics=self.metrics
        )
        charts.update(base_charts)

        if ENABLED_MODULES.get("breakdown", True):
            # Sector analysis
            logger.info("Analyzing sector and industry weighting...")
            sector_analysis = generate_sector_industry_analysis(self.risk_df, self.sector_industry_df, include_yield=self.include_yield)
            charts["sector_table"] = sector_analysis["table_html"]
            charts["sector_pie"] = sector_analysis["pie_chart_html"]

            charts["sector_performance_table"] = generate_sector_performance_table(self.risk_df, self.sector_industry_df, self.prices, self.holdings_df)

            if ENABLED_MODULES.get("holdings", True) or ENABLED_MODULES.get("breakdown", True):
                logger.info("Generating portfolio holdings analysis...")
                self._generate_holdings_table()
                charts["holdings_table"] = self.holdings_table_html

            logger.info("Generating Z-Score scatter plot...")
            charts["zscore_scatter"] = generate_zscore_scatter_plot(self.holdings_df, self.risk_df)

            charts["breakdown_metrics_strip"] = generate_breakdown_metrics_strip(self.holdings_df, self.prices)
        elif ENABLED_MODULES.get("holdings", True):
            logger.info("Generating portfolio holdings analysis...")
            self._generate_holdings_table()
            charts["holdings_table"] = self.holdings_table_html

        if ENABLED_MODULES.get("holdings", True):
            charts["sector_sunburst"] = generate_sector_sunburst_chart(self.holdings_df)
            charts["holdings_metrics_strip"] = generate_holdings_metrics_strip(self.holdings_df)

        if ENABLED_MODULES.get("overview", True):
            charts["advances_declines"] = generate_advances_declines_charts(self.holdings_df)

        if ENABLED_MODULES.get("monte_carlo", True):
            charts["monte_carlo"] = generate_monte_carlo_chart(self.mc_simulations)
            charts["monte_carlo_metrics_strip"] = generate_monte_carlo_metrics_strip(self.metrics, self.mc_simulations)

        if ENABLED_MODULES.get("risks", True):
            # Shock analysis for multiple levels (20%, 30%, 50%)
            logger.info("Generating Shock Curve analysis...")
            asset_returns = self.prices[self._get_active_tickers()].pct_change().dropna()
            betas = None
            if not self.holdings_df.empty and 'beta' in self.holdings_df.columns:
                betas = self.holdings_df['beta']

            for level in [0.20, 0.30, 0.50]:
                level_key = int(level * 100)
                charts[f"shock_curve_{level_key}"] = generate_shock_curve_chart(
                    asset_returns, self.risk_df, shock_level=level, benchmark_returns=self.benchmark
                )
                charts[f"shock_contrib_{level_key}"] = generate_shock_contribution_table(
                    asset_returns, self.risk_df, shock_level=-level, benchmark_returns=self.benchmark, betas=betas,
                    holdings_df=self.holdings_df if not self.holdings_df.empty else None
                )

            # VaR/ES multi-horizon
            logger.info("Generating VaR/ES analysis charts...")
            var_es_html = generate_var_es_analysis_charts(self.returns["total"], "DAILY")
            weekly_returns = self.returns["total"].resample('W').apply(lambda x: (1 + x).prod() - 1).dropna()
            if len(weekly_returns) > 5:
                var_es_html += generate_var_es_analysis_charts(weekly_returns, "WEEKLY")
            monthly_returns = self.returns["total"].resample('ME').apply(lambda x: (1 + x).prod() - 1).dropna()
            if len(monthly_returns) > 5:
                var_es_html += generate_var_es_analysis_charts(monthly_returns, "MONTHLY")
            charts["var_es_analysis"] = var_es_html

        # Trades (transaction mode only)
        if ENABLED_MODULES.get("history", True) and self.transaction_mode and not self.transactions_df.empty:
            logger.info("Generating trades table...")
            charts["trades_table"] = generate_trades_table(self.transactions_df, self.sector_industry_df, self.prices)
            charts["trades_metrics_strip"] = generate_trades_metrics_strip(self.transactions_df)
            self.trades_table_html = charts["trades_table"]
        else:
            self.trades_table_html = ""

        if ENABLED_MODULES.get("intel", True):
            logger.info("Generating Intel analysis...")
            from engine.modules.intel.charts import generate_intel_metrics_strip, generate_intel_performance_chart, generate_intel_insights, generate_intel_commentary
            charts["intel_metrics_strip"] = generate_intel_metrics_strip(self.metrics, self.holdings_df)
            charts["intel_performance"] = generate_intel_performance_chart(self.metrics, self.ts, self.benchmark_ticker)
            charts["intel_insights"] = generate_intel_insights(self.metrics, self.holdings_df, self.risk_df)
            charts["intel_commentary"] = generate_intel_commentary(self.metrics, self.holdings_df)

        return charts

    def _calculate_average_costs(self) -> pd.Series:
        """Calculate average cost per ticker from transactions."""
        avg_costs = {}
        holdings = {}
        
        # Sort by date
        sorted_tx = self.transactions_df.sort_values(by="Date", ascending=True)
        
        for _, row in sorted_tx.iterrows():
            ticker = row["Ticker"]
            side = row["Side"]
            qty = row["Quantity"]
            price = row["Price"]
            
            if ticker not in holdings:
                holdings[ticker] = 0.0
                avg_costs[ticker] = 0.0
            
            if side == "BUY":
                total_cost = holdings[ticker] * avg_costs[ticker] + qty * price
                holdings[ticker] += qty
                if holdings[ticker] > 0:
                    avg_costs[ticker] = total_cost / holdings[ticker]
            elif side == "SELL":
                holdings[ticker] -= qty
                # Cost basis doesn't change on SELL
        
        return pd.Series(avg_costs)

    def _generate_holdings_table(self) -> None:
        """Generate the holdings table based on transaction mode or eToro live portfolio."""
        from engine.modules.holdings.renderer import generate_portfolio_holdings_analysis

        if self._etoro_portfolio_mode and not self.portfolio.empty:
            portfolio_snapshot = self.portfolio.copy()

            tickers_all = portfolio_snapshot['ticker'].tolist()
            tickers_with_prices = [t for t in tickers_all if t in self.prices.columns]

            # Use eToro weights verbatim from the API, but normalise from
            # %-points to fractions so all downstream consumers (shock beta,
            # sector breakdown, charts, etc.) see the same 0–1 scale.
            # e.g. 25.0 → 0.25
            raw_weights = portfolio_snapshot.set_index('ticker')['quantity']
            raw_weights = raw_weights.reindex(tickers_all).fillna(0.0)
            raw_weight_fractions = raw_weights / 100.0

            temp_risk = pd.DataFrame({
                "Weight": raw_weight_fractions,
                "Risk Contribution": 0.0,
                "% Risk Contribution": 0.0
            }, index=tickers_all)

            temp_portfolio_df = portfolio_snapshot.copy()

            self.holdings_table_html, self.holdings_df, self.chart_data_json = generate_portfolio_holdings_analysis(
                temp_risk, self.sector_industry_df, self.prices_full, temp_portfolio_df
            )
            self.charts['chart_data'] = self.chart_data_json
            # Authoritative source: override risk_df in eToro mode so all downstream
            # consumers (yield, metrics, pie chart, alerts, sector tables) use the
            # exact eToro-reported weights, not recomputed backtest weights.
            self.risk_df = temp_risk.copy()
            self._add_beta_to_holdings()
            return

        if self.ts.get("holdings") is not None:
            latest_holdings_qty = self.ts.get("holdings").iloc[-1]
        else:
            latest_holdings_qty = self.ts["positions"].iloc[-1]

        latest_holdings_qty = latest_holdings_qty[latest_holdings_qty > 1e-6]

        if not latest_holdings_qty.empty:
            temp_portfolio_df = pd.DataFrame({
                'ticker': latest_holdings_qty.index.astype(str),
                'quantity': latest_holdings_qty.values,
                'type': 'active'
            })

            avg_costs = self._calculate_average_costs()
            temp_portfolio_df['avg_price'] = temp_portfolio_df['ticker'].map(avg_costs)

            latest_pos_values = self.ts["positions"].iloc[-1]
            latest_total_val = self.ts["total"].iloc[-1]
            latest_weights = latest_pos_values / latest_total_val if latest_total_val > 0.01 else latest_pos_values * 0.0
            latest_weights = latest_weights[latest_weights.index.isin(latest_holdings_qty.index)]
            latest_weights = latest_weights[latest_weights > 0.0001]

            active_tickers_list = self._get_active_tickers()
            temp_risk = calculate_risk_contribution(
                self.ts["positions"][active_tickers_list],
                self.ts["total"],
                asset_returns=self.prices[active_tickers_list].pct_change().dropna()
            )
            weight_sum = latest_weights.sum()
            temp_risk['Weight'] = latest_weights / weight_sum
            valid_tickers = latest_weights.index.intersection(latest_holdings_qty.index)
            temp_risk = temp_risk.loc[valid_tickers]
            temp_portfolio_df = temp_portfolio_df[temp_portfolio_df['ticker'].isin(valid_tickers)]

            self.portfolio = temp_portfolio_df

            self.holdings_table_html, self.holdings_df, self.chart_data_json = generate_portfolio_holdings_analysis(
                temp_risk, self.sector_industry_df, self.prices_full, self.portfolio
            )
            self.charts['chart_data'] = self.chart_data_json
        else:
            logger.warning("No current holdings detected at end of backtest.")
            self.holdings_table_html = "<p>No current holdings detected.</p>"
            self.holdings_df = pd.DataFrame()

        self._add_beta_to_holdings()



    def _add_beta_to_holdings(self) -> None:
        """
        Compute each holding's beta relative to the benchmark and store in holdings_df['beta'].
        Uses aligned returns across all holdings for consistency with shock curve analysis.
        """
        if self.holdings_df.empty:
            return
        # Ensure benchmark returns are available
        if not hasattr(self, 'benchmark') or self.benchmark.empty:
            self.holdings_df['beta'] = np.nan
            return
        # Get tickers that exist in price data
        tickers = [t for t in self.holdings_df.index if t in self.prices.columns]
        if not tickers:
            self.holdings_df['beta'] = np.nan
            return
        # Build aligned asset returns matrix (drop any rows with missing data across any ticker)
        asset_returns = self.prices[tickers].pct_change().dropna()
        if asset_returns.empty:
            self.holdings_df['beta'] = np.nan
            return
        # Align benchmark to asset_returns index and drop rows where either is NaN
        market_proxy = self.benchmark.reindex(asset_returns.index)
        mask = market_proxy.notna()
        market_proxy = market_proxy[mask]
        asset_returns = asset_returns[mask]
        # Compute individual betas via regression
        betas = {}
        valid_obs = market_proxy.notna().sum()
        market_std = market_proxy.std()
        if valid_obs >= 2 and not np.isnan(market_std) and market_std > 0:
            for col in asset_returns.columns:
                y = asset_returns[col]
                if y.notna().sum() >= 2:
                    try:
                        slope, _, _, _, _ = linregress(market_proxy, y)
                        if not np.isnan(slope):
                            betas[col] = max(-5.0, min(5.0, slope))
                        else:
                            betas[col] = np.nan
                    except Exception:
                        betas[col] = np.nan
                else:
                    betas[col] = np.nan
        else:
            for col in asset_returns.columns:
                betas[col] = np.nan
        # Assign to holdings_df; tickers not in betas dict will get NaN
        self.holdings_df['beta'] = pd.Series(betas)

        # Compute weighted beta for the portfolio for shock analysis consistency
        if 'Weight' in self.holdings_df.columns:
            weighted_beta = (self.holdings_df['beta'] * self.holdings_df['Weight']).sum()
            self.metrics["total"]["Shock_Beta"] = weighted_beta

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------

    def run_analysis(self) -> Tuple[Dict[str, Dict], Dict[str, str], datetime]:
        """
        Execute the full analysis pipeline.

        When an eToro username is configured, the live portfolio API is used
        as the primary data source. The transaction-mode backtest is only
        used as a fallback if the eToro portfolio path fails or returns no
        positions.

        Returns:
            Tuple of (metrics dict, charts dict, start date).
        """
        # Step-by-step execution
        if self.etoro_username:
            portfolio_loaded, portfolio_error = self._load_etoro_portfolio_path()
            if not portfolio_loaded:
                raise PortfolioFunctionsError(
                    "eToro portfolio failed to load and transaction mode is disabled. "
                    "Check ETORO_PUBLIC_KEY/ETORO_PRIVATE_KEY env vars and the eToro username. "
                    f"Details: {portfolio_error}"
                )

            self.start = self.parse_inception_date()
        else:
            raise PortfolioFunctionsError(
                "eToro username is required. Transaction mode has been disabled."
            )

        logger.info("Starting portfolio functions...")
        if not self._etoro_portfolio_mode or self.prices.empty:
            self.download_and_process_prices()

        self.build_timeseries()
        self.calculate_returns()

        self._select_benchmark()

        # Validate benchmark availability after selection
        if self.benchmark_ticker not in self.prices.columns:
            fallback = "ES=F" if "ES=F" in self.prices.columns else None
            if fallback:
                logger.warning(f"Benchmark {self.benchmark_ticker} not found, using {fallback}.")
                self.benchmark_ticker = fallback
            else:
                raise PortfolioFunctionsError(
                    f"Benchmark {self.benchmark_ticker} not found. "
                    f"Available columns: {self.prices.columns.tolist()}"
                )

        self.load_sector_industry_data()
        self.calculate_risk_contribution()
        self.calculate_yields()
        self.calculate_metrics()

        self.run_monte_carlo()
        self.charts = self.generate_charts()

        logger.info("Analysis complete.")

        return self.metrics, self.charts, self.start
