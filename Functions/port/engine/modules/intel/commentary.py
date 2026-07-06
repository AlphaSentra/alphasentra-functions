import re
import pandas as pd
import numpy as np

from config import (
    ATTENTION_TABLE_CELL_BORDER,
    ATTENTION_TABLE_HEADER_BG,
    ATTENTION_TABLE_HEADER_BORDER,
    ATTENTION_TABLE_HEADER_ROW_BORDER,
    BG_BUTTON_PRIMARY,
    BG_ROW_HEADER_ALT,
    BORDER_THEME,
    BUTTON_TEXT,
    DANGER_INDICATOR,
    EFFICIENCY_COMPOSITE_BAD,
    EFFICIENCY_COMPOSITE_GOOD,
    GAUGE_TRACK_BG,
    HOLDINGS_COMMENTARY_ALERT_ATTENTION,
    HOLDINGS_COMMENTARY_ALERT_CAUTION,
    HOLDINGS_COMMENTARY_ALERT_MONITOR,
    HOLDINGS_ZONE_DEPRESSED_LIGHT,
    HOLDINGS_ZONE_OVERBOUGHT,
    HOLDINGS_ZONE_OVERSOLD_LIGHT,
    HOLDINGS_ZONE_SLIGHTLY_ELEVATED,
    LIGHT_ELEMENT,
    NEGATIVE_RETURN_CARD,
    NEGATIVE_RETURN_CELL_BG,
    NEUTRAL_GRAY,
    NONZERO_RETURN_CELL_TEXT,
    POSITIVE_RETURN_CARD,
    POSITIVE_RETURN_CELL_BG,
    SUCCESS_INDICATOR,
    ZERO_RETURN_CELL_BG,
    ZERO_RETURN_CELL_TEXT,
)

from Functions.port.engine.modeling.metrics import calculate_performance_metrics, _ratio_metrics_1y


# ---------------------------------------------------------------------------
# Overview commentary
# ---------------------------------------------------------------------------
def _fmt_pct(v):
    """Format a decimal metric value as a human-readable percentage string."""
    try:
        return f"{v * 100:+.2f}%"
    except Exception:
        return str(v)


def _fmt_num(v, decimals=2):
    """Format a metric value as a plain number string."""
    try:
        return f"{v:+.{decimals}f}"
    except Exception:
        return str(v)


# ---------------------------------------------------------------------------
# Individual metric explanation builders
# ---------------------------------------------------------------------------

def _explain_annualized_return(v, bench_ann=None):
    if pd.isna(v):
        return "neutral", "Annualized Return is not available."
    sign = "positive" if v > 0 else "negative"
    bench_context = ""
    if bench_ann is not None and not pd.isna(bench_ann) and abs(bench_ann) > 0.001:
        diff = v, bench_ann
        sign_diff = "outperforming" if diff > 0 else "underperforming"
        bench_context = f" The portfolio is {sign_diff} the benchmark by <b>{_fmt_pct(diff)}</b>."
    desc = (
        f"<b>Annualized Return of {_fmt_pct(v)}.</b> "
        "The geometric average yearly growth rate over the past year, enabling direct comparison across portfolios and benchmarks. "
        f"{bench_context}"
    )
    return sign, desc


def _explain_cumulative_return(v, bench_cum=None):
    if pd.isna(v):
        return "neutral", "Cumulative Return is not available."
    sign = "positive" if v > 0 else "negative"
    bench_context = ""
    if bench_cum is not None and not pd.isna(bench_cum):
        diff = v, bench_cum
        diff_dir = "outperformance" if diff > 0 else "underperformance"
        bench_context = (
            f" Relative to the benchmark's {_fmt_pct(bench_cum)}, "
            f"this represents a {diff_dir} of <b>{_fmt_pct(diff)}</b>."
        )
    desc = (
        f"<b>Cumulative Return of {_fmt_pct(v)}.</b>{bench_context} "
        "Total aggregate growth (or loss) over the past year, combining price appreciation and distributions."
    )
    return sign, desc


def _explain_volatility(v):
    if pd.isna(v):
        return "neutral", "Volatility is not available."
    sign = "positive" if v <= 0.15 else "negative" if v >= 0.30 else "neutral"
    qualifier = (
        "Low ,  the portfolio is relatively stable."
        if v <= 0.15 else
        "High ,  the portfolio is subject to substantial daily price movement."
        if v >= 0.30 else
        "Moderate ,  daily price variation is within a mid-range band."
    )
    desc = (
        f"<b>Volatility of {_fmt_pct(v)}.</b> "
        "Annualised standard deviation of returns, measuring the magnitude of price swings irrespective of direction. "
        f"{qualifier} "
        "Elevated volatility heightens drawdown risk during adverse market conditions and increases the likelihood of emotionally driven decision-making."
    )
    return sign, desc


def _explain_sharpe(v):
    if pd.isna(v):
        return "neutral", "Sharpe Ratio is not available."
    sign = "positive"
    if v >= 2.0:
        label = "excellent"
    elif v >= 1.0:
        label = "good"
    elif v >= 0.5:
        label = "moderate"
    elif v > 0:
        label = "weak"
    else:
        label = "poor"
        sign = "negative"
    desc = (
        f"<b>Sharpe Ratio of {_fmt_num(v)} ,  {label}.</b> "
        "Excess return per unit of total volatility. "
        f"A ratio above 1.0 exceeds a risk-free asset on a risk-adjusted basis; "
        f"below 0.0, the portfolio is underperforming cash after risk. "
        "This 1-year window is the most responsive indicator of current portfolio health."
    )
    return sign, desc


def _explain_sortino(v):
    if pd.isna(v):
        return "neutral", "Sortino Ratio is not available."
    sign = "positive" if v > 0 else "negative"
    qualifier = (
        "excellent" if v >= 2.0 else
        "good" if v >= 1.0 else
        "moderate" if v >= 0.5 else
        "weak" if v > 0 else
        "negative"
    )
    desc = (
        f"<b>Sortino Ratio of {_fmt_num(v)} ,  {qualifier}.</b> "
        "Like Sharpe but only penalizes downside volatility ,  more consistent with how actual losses are experienced. "
        "A materially higher Sortino than Sharpe indicates smooth, accretive returns."
    )
    return sign, desc


def _explain_max_drawdown(v):
    if pd.isna(v):
        return "neutral", "Max Drawdown is not available."
    sign = "positive" if v > -0.15 else "negative" if v < -0.25 else "neutral"
    qualifier = (
        "relatively mild"
        if v > -0.15 else
        "significant"
        if v < -0.25 else
        "moderate"
    )
    desc = (
        f"<b>Max Drawdown of {_fmt_pct(v)} ,  {qualifier}.</b> "
        "The deepest peak-to-trough loss the portfolio has experienced across the observation period. "
        "It represents the worst-case drawdown a buy-and-hold position would have encountered. "
        "Within −15% suggests resilience during adverse periods; "
        "exceeding −25% signals substantial vulnerability under prolonged stress."
    )
    return sign, desc


def _explain_var(v):
    if pd.isna(v):
        return "neutral", "VaR (95%, 1-Year) is not available."
    sign = "positive" if v > -0.10 else "negative" if v < -0.20 else "neutral"
    desc = (
        f"<b>VaR (95%, 1-Year) of {_fmt_pct(v)}.</b> "
        "The maximum expected loss in an ordinary year, with 95% confidence. "
        "There is a 1-in-20 chance that annual losses exceed this threshold. "
        "This sets the floor for expected downside, though tail risk lies beyond it."
    )
    return sign, desc


def _explain_cvar(v):
    if pd.isna(v):
        return "neutral", "CVaR (95%, 1-Year) is not available."
    sign = "positive" if v > -0.15 else "negative" if v < -0.30 else "neutral"
    desc = (
        f"<b>CVaR (95%, 1-Year) of {_fmt_pct(v)}.</b> "
        "Expected loss conditional on a tail event ,  the average drawdown when the portfolio falls within the worst 5% of outcomes. "
        "CVaR always exceeds VaR and is the more meaningful measure of irrecoverable downside. "
        "Elevated CVaR warrants stress-testing and the potential use of hedging overlays."
    )
    return sign, desc


def _explain_yield(v):
    if pd.isna(v):
        return "neutral", "Estimated Yield is not available."
    sign = "positive" if v > 0.03 else "negative" if v < 0.01 else "neutral"
    qualifier = (
        "strong"
        if v >= 0.05 else
        "meaningful"
        if v >= 0.03 else
        "constrained"
        if v < 0.01 else
        "moderate"
    )
    desc = (
        f"<b>Estimated Yield of {_fmt_pct(v)} ,  {qualifier}.</b> "
        "Income from interest, dividends, and distributions as a proportion of market value. "
        "Provides return resilience independent of price appreciation and acts as a stabiliser during stagnation or correction. "
        "A robust yield acts independently of equity market cycles."
    )
    return sign, desc


def _explain_market_exposure(v, beta):
    if pd.isna(v):
        return "neutral", "Market Exposure Effect is not available."
    sign = "positive" if v > 0 else "negative"
    direction = (
        "amplifying market returns" if (not pd.isna(beta) and beta > 1.0) else
        "dampening market returns" if (not pd.isna(beta) and beta < 1.0) else
        "tracking market returns"
    )
    desc = (
        f"<b>Market Exposure Effect of {_fmt_pct(v)}.</b> "
        f"The return attributable purely to the portfolio's passive sensitivity to the benchmark's trajectory, given a Beta of {beta:.2f}. "
        f"{sign.capitalize()} value indicates market-driven returns across {direction}. "
        "It decomposes whether portfolio returns are primarily systematic (benchmark-driven) or arise from security selection."
    )
    return sign, desc


def _explain_alpha_annual(v, beta, bench_ann):
    if pd.isna(v):
        return "neutral", "Alpha (Risk-Adj) Annualized is not available."
    sign = "positive" if v > 0 else "negative" if v < 0 else "neutral"
    bench_phrase = (" vs benchmark annualized return of " + _fmt_pct(bench_ann)) if not pd.isna(bench_ann) else ""
    desc = (
        f"<b>Alpha (Risk-Adj) Annualized of {_fmt_pct(v)}</b>{bench_phrase}. "
        f"The annualised return in excess of the CAPM-implied return, stripping reward for market risk at Beta {beta:.2f}. "
        "Positive value indicates consistent extraction of benchmark-independent return from security selection. "
        "Negative value signals holdings underperform what their market exposure should earn."
    )
    return sign, desc


def _explain_alpha_cum(v):
    if pd.isna(v):
        return "neutral", "Alpha (Risk-Adj) Cumulative is not available."
    sign = "positive" if v > 0 else "negative" if v < 0 else "neutral"
    desc = (
        f"<b>Alpha (Risk-Adj) Cumulative of {_fmt_pct(v)}.</b> "
        "The realised annualised alpha over the observation period. "
        "It measures the contribution from security selection versus market timing or factor tilts. "
        "A sustained positive alpha is consistent with benchmark-uncorrelated returns."
    )
    return sign, desc


def _explain_outperformance_annual(v, bench_ann):
    if pd.isna(v):
        return "neutral", "Outperformance Annualized is not available."
    sign = "positive" if v > 0 else "negative" if v < 0 else "neutral"
    if not pd.isna(bench_ann) and abs(bench_ann) > 0.001:
        pct_of_bench = (v / bench_ann) * 100
        pct_phrase = (
            f" A margin of <b>{pct_of_bench:+.1f}%</b> against the benchmark's annual return."
        )
    else:
        pct_phrase = ""
    desc = (
        f"<b>Annualised Outperformance of {_fmt_pct(v)}</b>{pct_phrase} "
        "The direct, unadjusted year-on-year return differential from the benchmark. "
        "Does not account for risk differentials ,  outperformance achieved through materially higher leverage is not equivalent to alpha."
    )
    return sign, desc


def _explain_outperformance_cum(v):
    if pd.isna(v):
        return "neutral", "Outperformance Cumulative is not available."
    sign = "positive" if v > 0 else "negative" if v < 0 else "neutral"
    desc = (
        f"<b>Cumulative Outperformance of {_fmt_pct(v)}.</b> "
        "Total excess return relative to the benchmark, accumulated since inception. "
        "Even a marginal recurring annual outperformance compounds into a material wealth divergence over a sufficiently extended period."
    )
    return sign, desc


def _explain_beta(v):
    if pd.isna(v):
        return "neutral", "Beta is not available."
    sign = "neutral"
    if v < 0.8:
        label = "conservative"
        qualifier = (
            "moves at a lower multiple of benchmark swings, limiting drawdown participation in broad sell-offs."
        )
    elif v < 1.0:
        label = "conservative"
        qualifier = (
            "absorbs slightly less market risk than the benchmark, affording partial resilience in adverse regimes."
        )
    elif v < 1.2:
        label = "market-neutral"
        qualifier = (
            "tracks benchmark movements closely, neither amplifying nor dampening systematic risk."
        )
    elif v < 1.6:
        label = "cyclical"
        qualifier = (
            "magnifies benchmark volatility, benefiting strongly in bull markets but exacerbating losses in bear markets."
        )
    else:
        label = "leveraged"
        qualifier = (
            "carries a high systematic leverage profile, where market directionality dominates security-specific return."
        )
        sign = "negative"
    desc = (
        f"<b>Beta of {v:.2f} ,  {label}.</b> "
        "Sensitivity of portfolio returns to benchmark movements. "
        "Beta of 1.00 represents unit-for-unit co-movement with the benchmark. "
        f"At {v:.2f}, {qualifier} "
        "Consequently, Beta is a primary determinant of both upside potential in favourable environments and downside exposure in adverse ones."
    )
    return sign, desc


def _explain_information_ratio(v):
    if pd.isna(v):
        return "neutral", "Information Ratio is not available."
    sign = "positive" if v > 0 else "negative" if v < 0 else "neutral"
    qualifier = (
        "excellent"
        if v >= 1.0 else
        "strong"
        if v >= 0.5 else
        "moderate"
        if v >= 0.2 else
        "low" if v > 0 else
        "negative"
    )
    desc = (
        f"<b>Information Ratio of {_fmt_num(v)} ,  {qualifier}.</b> "
        "Mean active return relative to tracking error. "
        "A high reading indicates not only consistent benchmark outperformance, but a high ratio of hits to misses. "
        "A negative reading signals persistent underperformance warranting review of the selection process."
    )
    return sign, desc


# ---------------------------------------------------------------------------
# Per-metric dispatch dictionary
# ---------------------------------------------------------------------------

_METRIC_BUILDERS = {
    "Annualized Return": _explain_annualized_return,
    "Cumulative Return": _explain_cumulative_return,
    "Volatility": _explain_volatility,
    "Sharpe Ratio": _explain_sharpe,
    "Sortino Ratio": _explain_sortino,
    "Max Drawdown": _explain_max_drawdown,
    "VaR (95%, 1-Year)": _explain_var,
    "CVaR (95%, 1-Year)": _explain_cvar,
    "Estimated Yield": _explain_yield,
    "Market Exposure Effect (Cum.)": _explain_market_exposure,
    "Alpha (Risk-Adj) Annualized": _explain_alpha_annual,
    "Alpha (Risk-Adj) Cumulative": _explain_alpha_cum,
    "Outperformance Annualized": _explain_outperformance_annual,
    "Outperformance Cumulative": _explain_outperformance_cum,
    "Beta": _explain_beta,
    "Information Ratio": _explain_information_ratio,
}

_VALID_METRIC_KEYS = set(_METRIC_BUILDERS.keys())


_COLUMN_DISPLAY_NAMES = {
    "ret_1w": "1W",
    "ret_1m": "1M",
    "ret_3m": "3M",
}

def _build_overview_underperforming_table(holdings_df):
    if holdings_df is None:
        return ""

    df = holdings_df.copy()
    col_map = {c.lower().strip(): c for c in df.columns}

    def _pick(*alts):
        for a in alts:
            if a in col_map:
                return col_map[a]
        return None

    name_col = _pick("name", "security_name", "security")
    ticker_col = _pick("ticker", "symbol", "t")
    ret_1w_col = _pick("ret_1w", "return_1w", "1w_return", "weekly")
    ret_1m_col = _pick("ret_1m", "return_1m", "1m_return", "monthly")
    ret_3m_col = _pick("ret_3m", "return_3m", "3m_return", "quarterly")

    if name_col is None and ticker_col is None:
        return ""
    if ret_1w_col is None and ret_1m_col is None and ret_3m_col is None:
        return ""
    for c in (ret_1w_col, ret_1m_col, ret_3m_col):
        if c is not None and c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    weights = {}
    if ret_1w_col is not None and ret_1w_col in df.columns:
        weights[ret_1w_col] = 0.50
    if ret_1m_col is not None and ret_1m_col in df.columns:
        weights[ret_1m_col] = 0.30
    if ret_3m_col is not None and ret_3m_col in df.columns:
        weights[ret_3m_col] = 0.20

    if weights:
        df["worst"] = sum(df[col] * w for col, w in weights.items()) / sum(weights.values())
    else:
        df["worst"] = 0
    df = df.sort_values(by="worst").head(5)

    period_cols = [ret_1w_col, ret_1m_col, ret_3m_col]
    period_labels = [_COLUMN_DISPLAY_NAMES.get(c, c) for c in period_cols if c is not None]

    if name_col is None:
        name_col = ticker_col

    header = "".join(
        f"<th style=\'padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};\'>{lb}</th>"
        for lb in period_labels
    )
    rows = []
    for _, row in df.iterrows():
        name = row.get(name_col) if name_col and name_col in row else row.get(ticker_col, row.name)
        ticker = row.get(ticker_col, row.name)
        ticker_str = str(ticker) if ticker is not None else ""
        if ticker_str and not ticker_str.endswith(")") and name:
            ticker_full = f"{name} ({ticker_str})"
        else:
            ticker_full = name if ticker_str in (None, "") else ticker_str

        cells = []
        for p_col in period_cols:
            if p_col is None or p_col not in row:
                cells.append(f"<td style=\'padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};\'>N/A</td>")
                continue
            val = row[p_col]
            if pd.isna(val):
                cells.append(f"<td style=\'padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};\'>N/A</td>")
                continue
            pct = f"{val * 100:+.2f}%"
            bg = NEGATIVE_RETURN_CELL_BG if val < 0 else POSITIVE_RETURN_CELL_BG if val > 0 else ZERO_RETURN_CELL_BG
            fg = NONZERO_RETURN_CELL_TEXT if val != 0 else ZERO_RETURN_CELL_TEXT
            cells.append(f"<td style=\'padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};background:{bg};color:{fg};white-space:nowrap;\'>{pct}</td>")
        rows.append(f"<tr><td style=\'padding:3px 6px;border:1px solid {ATTENTION_TABLE_CELL_BORDER};\'>{ticker_full}</td>{''.join(cells)}</tr>")

    header_col = (
        f"<tr style=\'background:{ATTENTION_TABLE_HEADER_BG};border-bottom:2px solid {ATTENTION_TABLE_HEADER_ROW_BORDER};\'>"
        f"<th style=\'padding:3px 6px;border:1px solid {ATTENTION_TABLE_CELL_BORDER};text-align:left;\'>Security</th>"
        f"{header}</tr>"
    )

    table_html = (
        f"<p style='margin:0 0 0.5em 0;'><b><u>Need Attention Today</u></b></p>"
        f"<p style='margin:0 0 0.5em 0;'>The table below highlights the securities currently weighing on portfolio returns and efficiency, which need to be reviewed.</p>"
        f"<div style='overflow-x:auto;'><table style='border-collapse:collapse;font-size:0.75em;width:100%;max-width:100%;'>{header_col}"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"<div style='margin-top:0.75em;'>"
        f"<span style='font-size: 0.85em; margin-right:10px;'>Positions to review: </span>"
        f"<button onclick='exportTableToExcel(this, \"overview_attention_table\")' style='background-color: {BG_BUTTON_PRIMARY}; color: {BUTTON_TEXT}; border: none; padding: 6px 12px; cursor: pointer; border-radius: 4px; font-weight: bold; font-size: 0.8em;'>Save Excel</button>"
        f"</div><br>"
    )
    return table_html

# Metrics excluded from the table ,  not covered in this section
_TABLE_EXCLUDED = {
    "MC_Mean_Final_Return", "MC_Expected_Drawdown_Pct",
    "MC_VaR_99_Pct", "MC_VaR_95_Pct", "MC_Expected_Upside_95_Pct",
    "Shock_Beta", "Max Drawdown 1M", "Max Drawdown 1Y", "Max Drawdown 5Y",
}


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def generate_overview_commentary(metrics, holdings_df=None):
    """
    Generates compact, metric-by-metric commentary for the Overview tab.
    """
    # Prefer '1Y' horizon, fallback to any available that isn't a benchmark
    m = None
    if "1Y" in metrics and "Annualized Return" in metrics["1Y"]:
        m = metrics["1Y"]
    else:
        for k, v in metrics.items():
            if not k.startswith("benchmark") and isinstance(v, dict) and "Annualized Return" in v:
                m = v
                break
    
    if m is None:
        return "Performance data currently being analyzed."

    benchmark_m = m.get("benchmark", metrics.get("benchmark_1Y", {}))

    # Convenience introspection for metric keys with (1-Yr) suffix in the
    # table display but stored under bare names in the dict.
    def _get(key):
        return m.get(key)
    def _bench(key):
        return benchmark_m.get(key)

    # ── Section 1: Portfolio Functions Overview ─────────────────────────
    ann_ret   = _get("Annualized Return")
    cum_ret   = _get("Cumulative Return")
    vol       = _get("Volatility")
    max_dd    = _get("Max Drawdown")
    sharpe    = _get("Sharpe Ratio")
    sortino   = _get("Sortino Ratio")
    beta      = _get("Beta")
    alpha_ann = _get("Alpha (Risk-Adj) Annualized")
    ir        = _get("Information Ratio")
    yield_val = _get("Estimated Yield")

    def _fmt_or_na(v, default="N/A", fmt="pct"):
        if pd.isna(v):
            return default
        return _fmt_pct(v) if fmt == "pct" else _fmt_num(v)

    def _gt_zero(v):
        return not pd.isna(v) and v is not None and v > 0

    # ── Plain-language portfolio health check ──────────────────────────────
    income_profile = False
    income_tag = ""
    if yield_val is not None and not pd.isna(yield_val):
        if yield_val >= 0.045:
            income_profile = True
            income_tag = " This portfolio takes income seriously - dividends and distributions are a meaningful part of the story here."
        elif yield_val >= 0.03:
            income_profile = True
            income_tag = " There's also a decent income layer to this portfolio - dividends do contribute to performance."
        else:
            income_tag = " Returns here rely mostly on price appreciation rather than income."

    opening = ""
    if ann_ret is not None and not pd.isna(ann_ret) and not pd.isna(sharpe) and not pd.isna(max_dd):
        if ann_ret > 0.10 and sharpe >= 1.0 and max_dd > -0.10:
            opening = (
                "The portfolio is in good shape. "
                "It delivered solid growth for the level of risk taken, "
                "and when markets got rough, the biggest dips were relatively mild. "
                "Broadly speaking, this has been a rewarding and steady portfolio to hold."
            )
            if income_profile:
                opening += " And here's the nice part - the dividend yield adds a reliable income stream on top of that growth, so you're getting paid both ways."
            else:
                opening += " Returns are driven mainly by price appreciation."
        elif ann_ret > 0 and sharpe >= 0.5 and max_dd > -0.20:
            if income_profile:
                opening = (
                    "The portfolio is in reasonable shape overall. "
                    "It's built to deliver income first, with price growth on top. "
                    f"The dividend yield of <b>{_fmt_pct(yield_val)}</b> is meaningful, and downside has been within a manageable range. "
                    "For investors who value regular income, this portfolio delivers."
                )
            else:
                opening = (
                    "The portfolio is in reasonable shape overall. "
                    "It delivered positive returns for the risk taken, "
                    "though the ride had some rougher moments. "
                    "Overall, it strikes a sensible balance between growing capital and protecting it."
                )
        elif ann_ret <= 0 or sharpe < 0.5:
            if income_profile:
                opening = (
                    "The portfolio leans on income as its main strength. "
                    f"With a dividend yield of <b>{_fmt_pct(yield_val)}</b>, it continues to deliver meaningful cash flow "
                    "even while price movements have been modest or negative. "
                    "The portfolio is more resilient than headline returns alone suggest."
                )
            else:
                opening = (
                    "Honestly, the portfolio is underperforming for the risk level. "
                    "Returns haven't compensated investors for the volatility experienced."
                )
        else:
            if income_profile:
                opening = (
                    "The portfolio presents a mixed picture. "
                    "Some aspects work in its favor, and the dividend yield does provide a stabilising anchor for overall returns."
                )
            else:
                opening = (
                    "The portfolio presents a mixed picture. "
                    "Some aspects look favorable while others need watching - "
                    "worth digging into the details below to get the full story."
                )
    else:
        opening = "The portfolio's profile is still being assessed from available data."

    opening = f"Based on a 1-year time horizon, {opening[0].lower() + opening[1:]}"

    performance_story = ""
    if ann_ret is not None and not pd.isna(ann_ret):
        if ann_ret > 0.10:
            performance_story = (
                f"Annualised return is <b>{_fmt_pct(ann_ret)}</b>, "
                f"so 100 invested would be worth about {int(100 * (1 + ann_ret))} in a year."
            )
        elif ann_ret > 0:
            performance_story = (
                f"Annualised return is a positive <b>{_fmt_pct(ann_ret)}</b>, "
                "meaning the portfolio grew, albeit slowly."
            )
        else:
            performance_story = (
                f"Annualised return is <b>{_fmt_pct(ann_ret)}</b>, "
                "meaning the portfolio lost value."
            )
    else:
        performance_story = "Performance data is not yet available."

    risk_story = ""

    quality_verdict = ""
    if sharpe is not None and not pd.isna(sharpe) and sortino is not None and not pd.isna(sortino):
        if sharpe >= 1.0 and sortino >= 1.0:
            quality_verdict = (
                f"Return compensated for the risk taken, with Sharpe <b>{_fmt_num(sharpe)}</b> and Sortino <b>{_fmt_num(sortino)}</b>."
            )
        elif sharpe >= 1.0:
            quality_verdict = (
                f"Returns compensated for risk, with Sharpe <b>{_fmt_num(sharpe)}</b>. "
                f"Sortino (<b>{_fmt_num(sortino)}</b>) focuses on the downside."
            )
        elif sortino > sharpe:
            quality_verdict = (
                f"Downside-adjusted returns (Sortino <b>{_fmt_num(sortino)}</b>) look better than the headline (Sharpe <b>{_fmt_num(sharpe)}</b>), "
                "meaning most volatility was on the upside."
            )
        else:
            quality_verdict = (
                f"Return-for-volatility was <b>{'better than' if sharpe >= 0.5 else 'weaker than'} typical</b>, "
                f"with Sharpe <b>{_fmt_num(sharpe)}</b> and Sortino <b>{_fmt_num(sortino)}</b>."
            )
    elif sharpe is not None and not pd.isna(sharpe):
        quality_verdict = f"Sharpe ratio was <b>{_fmt_num(sharpe)}</b>."

    alpha_cmp = ""
    if not pd.isna(alpha_ann) and alpha_ann != 0:
        alpha_phrase = _fmt_pct(alpha_ann)
        alpha_cmp = (
            f"Security-picking skill (alpha) added <b>{alpha_phrase}</b> "
            f"{'positively' if alpha_ann > 0 else 'with limited impact'} versus the benchmark."
        )

    beta_cmp = ""
    if not pd.isna(beta):
        if beta < 0.8:
            beta_cmp = (
                f"Beta is <b>{beta:.2f}</b>, meaning the portfolio is less volatile than the market. "
                "It takes on less risk, which protects on the downside, but also means lower returns when markets rally strongly."
            )
        elif beta < 1.0:
            beta_cmp = (
                f"Beta is <b>{beta:.2f}</b>, meaning slightly lower volatility than the market. "
                "A modest cushion on the downside, but also reduced participation in strong rallies."
            )
        elif beta < 1.2:
            beta_cmp = (
                f"Beta is <b>{beta:.2f}</b>, meaning the portfolio's volatility and risk level are broadly in line with the market. "
                "Profitability moves with market direction, neither amplified nor dampened."
            )
        elif beta < 1.6:
            beta_cmp = (
                f"Beta is <b>{beta:.2f}</b>, meaning the portfolio is more volatile than the market. "
                "It takes on elevated risk relative to the benchmark, leading to larger swings in profitability in both directions."
            )
        else:
            beta_cmp = (
                f"Beta is <b>{beta:.2f}</b>, meaning highly elevated volatility and risk. "
                "The portfolio's profitability swings dramatically with market direction, so risk is significantly amplified."
            )

    yield_note = ""
    if not pd.isna(yield_val) and not income_profile:
        if yield_val >= 0.045:
            yield_note = f" The dividend yield of <b>{_fmt_pct(yield_val)}</b> adds a steady income stream on top of growth."
        elif yield_val >= 0.03:
            yield_note = f" A dividend yield of <b>{_fmt_pct(yield_val)}</b> contributes to performance."
        elif yield_val >= 0.01:
            yield_note = f" Dividend yield is <b>{_fmt_pct(yield_val)}</b>, providing some income offset."
        else:
            yield_note = f" Dividend yield is minimal at <b>{_fmt_pct(yield_val)}</b>, so returns depend mostly on price changes."

    ss_qualifier = ""
    if _gt_zero(sharpe) and _gt_zero(sortino):
        if sortino > sharpe:
            ss_qualifier = " Most movement was on the upside, with losing periods relatively contained."
        else:
            ss_qualifier = " The portfolio saw both gains and setbacks as markets move."

    joined = " ".join(filter(None, [
        opening,
        performance_story,
        risk_story,
        f"Return quality, {quality_verdict}{ss_qualifier}{alpha_cmp}{beta_cmp}{yield_note}".strip(),
    ]))
    joined = re.sub(r'\.(?=[A-Z])', '. ', joined)
    return_section = [joined]


    # ── Section 2: Volatility & Stability ───────────────────────────────
    vol_section = []
    for key in ["Volatility", "Max Drawdown", "VaR (95%, 1-Year)", "CVaR (95%, 1-Year)"]:
        builder = _METRIC_BUILDERS.get(key)
        if builder:
            sign, html = builder(_get(key))
            # colour the first word bold
            vol_section.append(html)

    # ── Section 3: Risk-Adjusted Performance ────────────────────────────
    ratio_section = []
    for key in ["Sharpe Ratio", "Sortino Ratio", "Information Ratio"]:
        builder = _METRIC_BUILDERS.get(key)
        if builder:
            sign, html = builder(_get(key))
            ratio_section.append(html)

    # ── Section 4: Benchmark-Relative Performance ────────────────────────
    beta_val   = _get("Beta")
    alpha_ann  = _get("Alpha (Risk-Adj) Annualized")
    alpha_cum  = _get("Alpha (Risk-Adj) Cumulative")
    out_ann    = _get("Outperformance Annualized")
    out_cum    = _get("Outperformance Cumulative")
    out_bench  = _bench("Annualized Return")

    relative_section = []
    for key, extra_args in [
        ("Beta",                                 (beta_val,)),
        ("Alpha (Risk-Adj) Annualized",          (alpha_ann, beta_val, out_bench)),
        ("Alpha (Risk-Adj) Cumulative",          (alpha_cum,)),
        ("Outperformance Annualized",            (out_ann, out_bench)),
        ("Outperformance Cumulative",            (out_cum,)),
    ]:
        builder = _METRIC_BUILDERS.get(key)
        if builder:
            sign, html = builder(*extra_args)
            relative_section.append(html)

    # ── Section 5: Income ────────────────────────────────────────────────
    yield_val = _get("Estimated Yield")
    if yield_val is not None:
        yield_section = []
        builder = _METRIC_BUILDERS["Estimated Yield"]
        sign, html = builder(yield_val)
        yield_section.append(html)
    else:
        yield_section = None

    # ── Assemble ─────────────────────────────────────────────────────────
    parts = []

    if return_section:
        intro = return_section[0]
        parts.append(f"<p style=\"margin: 0 0 0.5em 0;\"><u><strong>Rating</strong></u></p><p style=\"margin: 0 0 1em 0;\">{intro}</p>")

    if holdings_df is not None:
        table_html = _build_overview_underperforming_table(holdings_df)
        if table_html:
            parts.append(table_html)

    return "<br>".join(parts) if parts else "Metrics are still being processed."

# ---------------------------------------------------------------------------
# Holdings commentary
# ---------------------------------------------------------------------------


def _find_col(df, candidates):
    """Return the first column name from *candidates* that exists in *df* (case-insensitive)."""
    for cand in candidates:
        for col in df.columns:
            if col.lower() == cand.lower():
                return col
    return None


def _label(ticker, name):
    """Return a human-readable label combining ticker and name."""
    if name and str(name).strip().lower() != str(ticker).lower():
        return f"{ticker} ({name})"
    return str(ticker)


def _zscore_zone(z):
    try:
        z = float(z)
    except Exception:
        return "undetermined", NEUTRAL_GRAY, ""
    if z > 2.0:
        return "extreme overbought", DANGER_INDICATOR, f"<b>{_fmt_pct(z)}</b> above its 1-year mean — statistically elevated"
    elif z > 1.0:
        return "overbought", HOLDINGS_ZONE_OVERBOUGHT, f"<b>{_fmt_pct(z)}</b> above its 1-year mean"
    elif z > 0.3:
        return "slightly elevated", HOLDINGS_ZONE_SLIGHTLY_ELEVATED, f"<b>{_fmt_pct(z)}</b> above its 1-year mean — mild positive deviation"
    elif z < -2.0:
        return "deeply oversold", SUCCESS_INDICATOR, f"<b>{_fmt_pct(z)}</b> below its 1-year mean — statistically depressed"
    elif z < -1.0:
        return "oversold", HOLDINGS_ZONE_OVERSOLD_LIGHT, f"<b>{_fmt_pct(z)}</b> below its 1-year mean"
    elif z < -0.3:
        return "slightly depressed", HOLDINGS_ZONE_DEPRESSED_LIGHT, f"<b>{_fmt_pct(z)}</b> below its 1-year mean — mild negative deviation"
    return "near average", NEUTRAL_GRAY, f"near its 1-year average at <b>{_fmt_pct(z)}</b>"


def _section_head(title):
    """An underlined, bold heading with exactly 12 px of bottom margin."""
    return f"<b><u style='font-size:1.02em;margin:0 0 12px 0;display:block;'>{title}</u></b>"


def _section(title, items, fallback=""):
    """Wrap a list of HTML strings into a titled bullet-list block.

    Uses clean 38 px left margin for the <ul> so bullet and text have
    generous separation without any negative-text-indent tricks.
    """
    if not items:
        hdr = _section_head(title)
        return f"{hdr}<p class='cm-hold'>{fallback}</p><br>"

    hdr = _section_head(title)
    bullet_str = "".join(
        f"<li style='margin:2px 0 6px 0;'>{t}</li>\n"
        for t in items
    )
    return (
        f"{hdr}"
        f"<ul style='margin:0 0 0 38px;padding-left:0;'>"
        f"{bullet_str}</ul>"
        f"<br>"
    )


def _build_top_performers_table(holdings_df):
    if holdings_df is None:
        return ""

    df = holdings_df.copy()
    col_map = {c.lower().strip(): c for c in df.columns}

    def _pick(*alts):
        for a in alts:
            if a in col_map:
                return col_map[a]
        return None

    name_col = _pick("name", "security_name", "security")
    ticker_col = _pick("ticker", "symbol", "t")
    ret_1w_col = _pick("ret_1w", "return_1w", "1w_return", "weekly")
    ret_1m_col = _pick("ret_1m", "return_1m", "1m_return", "monthly")
    ret_3m_col = _pick("ret_3m", "return_3m", "3m_return", "quarterly")

    if name_col is None and ticker_col is None:
        return ""
    if ret_1w_col is None and ret_1m_col is None and ret_3m_col is None:
        return ""
    for c in (ret_1w_col, ret_1m_col, ret_3m_col):
        if c is not None and c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    weights = {}
    if ret_1w_col is not None and ret_1w_col in df.columns:
        weights[ret_1w_col] = 0.50
    if ret_1m_col is not None and ret_1m_col in df.columns:
        weights[ret_1m_col] = 0.30
    if ret_3m_col is not None and ret_3m_col in df.columns:
        weights[ret_3m_col] = 0.20

    if weights:
        df["score"] = sum(df[col] * w for col, w in weights.items()) / sum(weights.values())
    else:
        df["score"] = 0
    df = df.sort_values(by="score", ascending=False).head(5)

    period_cols = [ret_1w_col, ret_1m_col, ret_3m_col]
    _alias_map = {"ret_1w": "1W", "ret_1m": "1M", "ret_3m": "3M"}
    period_labels = [_alias_map.get(_col, _col) if _col in _alias_map else _col for _col in period_cols]

    if name_col is None:
        name_col = ticker_col

    header = "".join(
        f"<th style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>{lb}</th>"
        for lb in period_labels if lb
    )
    rows = []
    for _, row in df.iterrows():
        name = row.get(name_col) if name_col and name_col in row else row.get(ticker_col, row.name)
        ticker = row.get(ticker_col, row.name)
        ticker_str = str(ticker) if ticker is not None else ""
        if ticker_str and not ticker_str.endswith(")") and name:
            ticker_full = f"{name} ({ticker_str})"
        else:
            ticker_full = name if ticker_str in (None, "") else ticker_str

        cells = []
        for p_col in period_cols:
            if p_col is None or p_col not in row:
                cells.append(f"<td style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>N/A</td>")
                continue
            val = row[p_col]
            if pd.isna(val):
                cells.append(f"<td style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>N/A</td>")
                continue
            pct = f"{val * 100:+.2f}%"
            bg = NEGATIVE_RETURN_CARD if val < 0 else POSITIVE_RETURN_CARD if val > 0 else ZERO_RETURN_CELL_BG
            fg = BUTTON_TEXT if val != 0 else ZERO_RETURN_CELL_TEXT
            cells.append(f"<td style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};background:{bg};color:{fg};white-space:nowrap;'>{pct}</td>")
        rows.append(f"<tr><td style='padding:3px 6px;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>{ticker_full}</td>{''.join(cells)}</tr>")

    header_col = (
        f"<tr style='background:{ATTENTION_TABLE_HEADER_BG};border-bottom:2px solid {ATTENTION_TABLE_HEADER_BORDER};'>"
        f"<th style='padding:3px 6px;text-align:left;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>Security</th>"
        f"{header}</tr>"
    )

    table_html = (
        f"<p style='margin:0 0 0.5em 0;'><b><u>Top Performers</u></b></p>"
        f"<div style='overflow-x:auto;'><table style='border-collapse:collapse;font-size:0.75em;width:100%;max-width:100%;'>{header_col}"
        f"<tbody>{''.join(rows)}</tbody></table></div><br>"
    )
    return table_html


def _build_holdings_underperforming_table(holdings_df):
    if holdings_df is None:
        return ""

    df = holdings_df.copy()
    col_map = {c.lower().strip(): c for c in df.columns}

    def _pick(*alts):
        for a in alts:
            if a in col_map:
                return col_map[a]
        return None

    name_col = _pick("name", "security_name", "security")
    ticker_col = _pick("ticker", "symbol", "t")
    ret_1w_col = _pick("ret_1w", "return_1w", "1w_return", "weekly")
    ret_1m_col = _pick("ret_1m", "return_1m", "1m_return", "monthly")
    ret_3m_col = _pick("ret_3m", "return_3m", "3m_return", "quarterly")

    if name_col is None and ticker_col is None:
        return ""
    if ret_1w_col is None and ret_1m_col is None and ret_3m_col is None:
        return ""
    for c in (ret_1w_col, ret_1m_col, ret_3m_col):
        if c is not None and c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    weights = {}
    if ret_1w_col is not None and ret_1w_col in df.columns:
        weights[ret_1w_col] = 0.50
    if ret_1m_col is not None and ret_1m_col in df.columns:
        weights[ret_1m_col] = 0.30
    if ret_3m_col is not None and ret_3m_col in df.columns:
        weights[ret_3m_col] = 0.20

    if weights:
        df["worst"] = sum(df[col] * w for col, w in weights.items()) / sum(weights.values())
    else:
        df["worst"] = 0
    df = df.sort_values(by="worst").head(5)

    period_cols = [ret_1w_col, ret_1m_col, ret_3m_col]
    _alias_map = {"ret_1w": "1W", "ret_1m": "1M", "ret_3m": "3M"}
    period_labels = [_alias_map.get(_col, _col) if _col in _alias_map else _col for _col in period_cols]

    if name_col is None:
        name_col = ticker_col

    header = "".join(
        f"<th style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>{lb}</th>"
        for lb in period_labels if lb
    )
    rows = []
    for _, row in df.iterrows():
        name = row.get(name_col) if name_col and name_col in row else row.get(ticker_col, row.name)
        ticker = row.get(ticker_col, row.name)
        ticker_str = str(ticker) if ticker is not None else ""
        if ticker_str and not ticker_str.endswith(")") and name:
            ticker_full = f"{name} ({ticker_str})"
        else:
            ticker_full = name if ticker_str in (None, "") else ticker_str

        cells = []
        for p_col in period_cols:
            if p_col is None or p_col not in row:
                cells.append(f"<td style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>N/A</td>")
                continue
            val = row[p_col]
            if pd.isna(val):
                cells.append(f"<td style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>N/A</td>")
                continue
            pct = f"{val * 100:+.2f}%"
            bg = NEGATIVE_RETURN_CARD if val < 0 else POSITIVE_RETURN_CARD if val > 0 else ZERO_RETURN_CELL_BG
            fg = BUTTON_TEXT if val != 0 else ZERO_RETURN_CELL_TEXT
            cells.append(f"<td style='padding:3px 6px;text-align:right;border:1px solid {ATTENTION_TABLE_CELL_BORDER};background:{bg};color:{fg};white-space:nowrap;'>{pct}</td>")
        rows.append(f"<tr><td style='padding:3px 6px;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>{ticker_full}</td>{''.join(cells)}</tr>")

    header_col = (
        f"<tr style='background:{ATTENTION_TABLE_HEADER_BG};border-bottom:2px solid {ATTENTION_TABLE_HEADER_BORDER};'>"
        f"<th style='padding:3px 6px;text-align:left;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>Security</th>"
        f"{header}</tr>"
    )

    table_html = (
        f"<p style='margin:0 0 0.5em 0;'><b><u>Lagging Positions</u></b></p>"
        f"<div style='overflow-x:auto;'><table style='border-collapse:collapse;font-size:0.75em;width:100%;max-width:100%;'>{header_col}"
        f"<tbody>{''.join(rows)}</tbody></table></div><br>"
    )
    return table_html


def _build_alert_table(holdings_df):
    if holdings_df is None:
        return ""

    df = holdings_df.copy()
    col_map = {c.lower().strip(): c for c in df.columns}

    def _pick(*alts):
        for a in alts:
            if a in col_map:
                return col_map[a]
        return None

    name_col = _pick("name", "security_name", "security")
    alert_col = _pick("alert")

    if alert_col is None or alert_col not in df.columns:
        return ""

    flagged_df = df[df[alert_col].isin(["Caution", "Attention", "Monitor"])].copy()
    if flagged_df.empty:
        return ""

    alert_colors = {"Caution": HOLDINGS_COMMENTARY_ALERT_CAUTION,
                    "Attention": HOLDINGS_COMMENTARY_ALERT_ATTENTION,
                    "Monitor": HOLDINGS_COMMENTARY_ALERT_MONITOR}
    rows = []
    for _, row in flagged_df.iterrows():
        nm = str(row[name_col]) if name_col and name_col in row and pd.notna(row.get(name_col)) else ""
        tk = str(row.name) if row.name is not None else ""
        if nm and nm.lower() != tk.lower():
            label = f"{nm} ({tk})"
        else:
            label = nm or tk
        alert = str(row[alert_col])
        color = alert_colors.get(alert, NEUTRAL_GRAY)
        rows.append(
            f"<tr>"
            f"<td style='padding:3px 6px;'>{label}</td>"
            f"<td style='padding:3px 6px;color:{color};font-weight:bold;'>{alert}</td>"
            f"</tr>"
        )

    table_html = (
        f"<p style='margin:0 0 0.5em 0;'><b><u>Action Alerts</u></b></p>"
        f"<p style='margin:0 0 6px 0;'>The securities listed below need to be reviewed as they are at critical price levels requiring attention or action.</p>"
        f"<div style='overflow-x:auto;'><table id='action-alerts-table' style='border-collapse:collapse;font-size:0.75em;width:100%;max-width:100%;'>"
        f"<tr style='background:{ATTENTION_TABLE_HEADER_BG};border-bottom:2px solid {ATTENTION_TABLE_HEADER_BORDER};'>"
        f"<th style='padding:3px 6px;text-align:left;border:1px solid {ATTENTION_TABLE_CELL_BORDER};'>Security</th>"
        f"<th style='padding:3px 6px;text-align:left;'>Action alert</th>"
        f"</tr>"
        f"{''.join(rows)}"
        f"</table></div>"
    )
    return table_html


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def _build_structure_section(holdings_df):
    """S1 — portfolio structure and sector breakdown."""
    items = []

    n = len(holdings_df)
    sector_col = _find_col(holdings_df, ["sector"])

    # Sector concentration snapshot
    if sector_col is not None and "Weight" in holdings_df.columns:
        n_sectors = holdings_df[sector_col].nunique()
        top_sectors = holdings_df.groupby(sector_col)["Weight"].sum().sort_values(ascending=False)
        top3_text, top3_wt = "", top_sectors.head(3).sum() * 100
        for sec, wt in top_sectors.head(3).items():
            top3_text += f"<b>{sec}</b> ({wt * 100:.1f}%), "

        if top3_wt > 65:
            items.append(
                f"<b>Concentrated sector exposure</b>: the top three sectors — "
                f"{top3_text.rstrip(', ')} — account for {top3_wt:.1f}% of total portfolio weight. "
                "A broad sector shock would disproportionately affect this portfolio."
            )
        elif n_sectors <= 4:
            items.append(
                f"<b>Narrow sector footprint</b>: only {n_sectors} distinct sectors are held. "
                "A concentrated sector list weakens the diversification benefit at the sector level."
            )
        elif top3_wt > 45:
            items.append(
                f"<b>Moderate sector concentration</b>: top three sectors represent {top3_wt:.1f}% of the portfolio."
            )
        else:
            items.append(
                f"<b>Broad sector coverage</b> across {n_sectors} sectors with the top three accounting for {top3_wt:.1f}% of weight — "
                "a well-diversified sector footprint."
            )

    return items


def _build_concentration_section(holdings_df):
    """S2 — position size distribution, HHI, short-side risk."""
    items = []
    if "Weight" not in holdings_df.columns:
        return items

    sorted_df = holdings_df.sort_values("Weight", ascending=False)
    top1 = sorted_df.iloc[0] if len(sorted_df) > 0 else None
    top3_wt = sorted_df.head(3)["Weight"].sum() * 100
    top5_wt = sorted_df.head(5)["Weight"].sum() * 100
    n = len(sorted_df)

    name_col = _find_col(holdings_df, ["name"])
    w_vec = sorted_df["Weight"].values.astype(float)
    hhi = float((w_vec ** 2).sum())

    def _lbl(row):
        nm = str(row[name_col]) if name_col and pd.notna(row.get(name_col)) else ""
        return _label(str(row.name), nm)

    if top1 is not None:
        max_w = float(top1["Weight"]) * 100
        if max_w > 20:
            items.append(
                f"<b>Dominant single position</b>: {_label(str(top1.name), str(top1[name_col]) if name_col else '')}"
                f" holds {max_w:.1f}% of the portfolio. This is an outsized position — "
                f"a material adverse move here will dominate portfolio-level losses regardless of other holdings."
            )
        elif max_w > 10:
            items.append(
                f"<b>Material single-asset exposure</b>: {_lbl(top1)} at {max_w:.1f}%. "
                "At this weight, idiosyncratic moves in this position meaningfully affect portfolio-level risk."
            )

    if hhi > 0.30:
        items.append(
            f"<b>Extreme concentration (HHI: {hhi:.3f})</b>: top-3 hold {top3_wt:.1f}%, top-5 hold {top5_wt:.1f}%. "
            "The concentration profile is consistent with a thesis-driven portfolio rather than a broad-diversification benchmark."
        )
    elif hhi > 0.12:
        items.append(
            f"<b>Moderate concentration (HHI: {hhi:.3f})</b>: top-5 positions hold {top5_wt:.1f}% of the portfolio. "
            "Within normal bounds for a targeted portfolio, but worth monitoring as positions scale."
        )
    elif hhi < 0.04 and n > 10:
        items.append(
            f"<b>Well-diversified (HHI: {hhi:.3f})</b>: holdings are distributed broadly with no individual position dominating."
        )

    # Short side
    qty_col = _find_col(holdings_df, ["quantity"])
    if qty_col is not None:
        shorts = sorted_df[sorted_df[qty_col] < 0] if "Weight" in sorted_df.columns else pd.DataFrame()
        if not shorts.empty:
            shorts_sorted = shorts.sort_values("Weight")
            largest_short = shorts_sorted.iloc[0]
            sw_abs = abs(shorts["Weight"].sum()) * 100
            items.append(
                f"<b>Short exposure</b>: {len(shorts)} short positions across {sw_abs:.1f}% absolute portfolio weight. "
                f"Largest short is {_lbl(largest_short)} at {abs(float(largest_short['Weight'])) * 100:.1f}% absolute weight."
            )

    return items


def _build_opening_narrative(holdings_df):
    """S0 — high-level opening narrative: Z-score, momentum spread, position count."""
    n = len(holdings_df)
    sentences = []

    sector_col = _find_col(holdings_df, ["sector"])
    z_col      = _find_col(holdings_df, ["z_score"])
    spread_col = _find_col(holdings_df, ["momentum_spread"])

    n_sectors = holdings_df[sector_col].nunique() if sector_col else n

    # --- Portfolio weighted-average Z-score ---
    w_col = "Weight"
    if z_col and w_col in holdings_df.columns:
        valid = holdings_df[[z_col, w_col]].dropna()
        if not valid.empty and valid[w_col].sum() != 0:
            avg_z = (valid[z_col] * valid[w_col]).sum() / valid[w_col].sum()
            zone, _, _ = _zscore_zone(avg_z)
            direction = "above" if avg_z > 0.3 else "below" if avg_z < -0.3 else "near"
            if abs(avg_z) > 0.3:
                sentences.append(
                    f"the portfolio's weighted-average Z-score of <b>{avg_z:+.2f}</b> sits {direction} the 1-year mean, "
                    f"classifying the overall technical posture as <b>{zone}</b>"
                )
            else:
                sentences.append(
                    f"the weighted-average Z-score of <b>{avg_z:+.2f}</b> is {direction} neutral, "
                    f"indicating the portfolio is broadly balanced around its one-year return baseline"
                )

    # --- Portfolio weighted-average momentum spread ---
    if spread_col and w_col in holdings_df.columns:
        valid = holdings_df[[spread_col, w_col]].dropna()
        if not valid.empty and valid[w_col].sum() != 0:
            avg_spread = (valid[spread_col] * valid[w_col]).sum() / valid[w_col].sum()
            spread_pct = avg_spread * 100
            if spread_pct > 3:
                sentences.append(
                    f"the portfolio trades <b>{spread_pct:+.1f}%</b> above its collective 200-day SMA on a weighted basis, "
                    f"reflecting broad bullish momentum in the majority of holdings"
                )
            elif spread_pct < -3:
                sentences.append(
                    f"the portfolio trades <b>{spread_pct:+.1f}%</b> below its collective 200-day SMA on a weighted basis, "
                    f"indicating sustained downward pressure across a meaningful share of positions"
                )
            elif spread_pct > 0:
                sentences.append(
                    f"on aggregate the portfolio holds a slight positive bias relative to 200-day SMAs "
                    f"(<b>{spread_pct:+.1f}%</b>)"
                )
            else:
                sentences.append(
                    f"on aggregate the portfolio carries a slight negative bias relative to 200-day SMAs "
                    f"(<b>{spread_pct:+.1f}%</b>)"
                )

    sentences.append(
        f"the portfolio holds <b>{n} positions across {n_sectors} sectors</b>"
    )

    return " ".join(sentences)


def _build_pnl_section(holdings_df):
    """S3 — PnL picture: winners, losers, average trade quality."""
    items = []
    pnl_col = _find_col(holdings_df, ["pnl_pct"])
    if pnl_col is None:
        return items

    name_col = _find_col(holdings_df, ["name"])

    winners = holdings_df[holdings_df[pnl_col] > 0].sort_values(pnl_col, ascending=False)
    losers  = holdings_df[holdings_df[pnl_col] < 0].sort_values(pnl_col)
    flt     = holdings_df[holdings_df[pnl_col].between(-0.5, 0.5, inclusive="neither")]

    n_win, n_loss = len(winners), len(losers)
    n_flat = len(flt)
    n_total = n_win + n_loss + n_flat
    avg_win   = winners[pnl_col].mean() if n_win > 0 else np.nan
    avg_loss  = losers[pnl_col].mean()  if n_loss > 0 else np.nan

    if n_total == 0:
        return items

    def _wt(row):
        nm = str(row[name_col]) if name_col and pd.notna(row.get(name_col)) else ""
        return _label(str(row.name), nm)

    if n_win > n_loss and pd.notna(avg_win) and avg_win > avg_loss:
        items.append(
            f"<b>Positive skew across positions</b>: {n_win} winning positions "
            f"(avg {avg_win:.1f}%) vs {n_loss} losing positions "
            f"(avg {avg_loss:.1f}%). Winners outnumber losers and the average win exceeds the average loss."
        )
    elif n_loss > 0 and pd.notna(avg_loss) and avg_loss < -5:
        items.append(
            f"<b>Elevated loss count</b>: {n_loss} of {n_total} positions are underwater "
            f"with an average loss of {avg_loss:.1f}%, "
            f"adding a significant drag on the portfolio's unrealised P&L."
        )

    return items


def generate_holdings_commentary(holdings_df):
    """
    Generates rich, multi-dimensional commentary for the Holdings tab.

    Covers:
      0. Opening paragraph
      1. Portfolio structure (sectors)
      2. Concentration & idiosyncratic risk
      3. P&L picture (winners, losers, average trade quality)
      4. Entry positioning (avg cost vs current)
      5. Action alerts (Caution, Attention, Monitor)
    """
    if holdings_df is None or holdings_df.empty:
        return "Holdings data currently unavailable for detailed analysis."

    # ---- Sections ----
    intro = _build_opening_narrative(holdings_df)
    structure_items      = _build_structure_section(holdings_df)
    concentration_items  = _build_concentration_section(holdings_df)
    pnl_items            = _build_pnl_section(holdings_df)

    # ---- Assemble ----
    parts = []

    intro_text = (
        f"{_section_head('Holdings Overview')}"
        f"<p class='cm-hold' style='margin:0 0 12px 0;'>{intro}.</p>"
        f"<br>"
    )
    parts.append(intro_text)

    part = _section("Portfolio Structure", structure_items,
                    fallback="Portfolio structure is within expected bounds given current holdings.")
    parts.append(part)

    part = _section("Concentration &amp; Idiosyncratic Risk", concentration_items,
                    fallback="No critical concentration risks identified.")
    parts.append(part)

    part = _section("P&amp;L Distribution", pnl_items,
                    fallback="P&amp;L distribution across positions is currently neutral.")
    parts.append(part)

    top_table = _build_top_performers_table(holdings_df)
    if top_table:
        parts.append(top_table)

    underperforming_table = _build_holdings_underperforming_table(holdings_df)
    if underperforming_table:
        parts.append(underperforming_table)

    alert_table = _build_alert_table(holdings_df)
    if alert_table:
        parts.append(alert_table)

    return "".join(parts)

# ---------------------------------------------------------------------------
# Efficiency commentary
# ---------------------------------------------------------------------------

def _efficiency_label(ratio_name, value):
    if pd.isna(value):
        return "not available"
    if ratio_name == "Sharpe Ratio":
        if value >= 2.0:
            return "excellent"
        if value >= 1.0:
            return "strong"
        if value >= 0.5:
            return "moderate"
        if value > 0:
            return "weak"
        return "poor"
    if ratio_name == "Sortino Ratio":
        if value >= 2.0:
            return "excellent"
        if value >= 1.0:
            return "strong"
        if value >= 0.5:
            return "moderate"
        if value > 0:
            return "weak"
        return "negative"
    if ratio_name == "Information Ratio":
        if value >= 1.0:
            return "excellent"
        if value >= 0.5:
            return "strong"
        if value >= 0.2:
            return "moderate"
        if value > 0:
            return "low"
        if value == 0:
            return "neutral"
        return "negative"
    if ratio_name == "Alpha":
        if value > 0.02:
            return "strong positive"
        if value > 0:
            return "positive"
        if value == 0:
            return "neutral"
        if value > -0.02:
            return "negative"
        return "strong negative"
    return ""


def _rolling_trend(series):
    if series is None or series.empty or series.dropna().empty:
        return "insufficient data"
    clean = series.dropna()
    mid = len(clean) // 2
    first_half = clean.iloc[:mid].mean() if mid > 0 else clean.iloc[0]
    second_half = clean.iloc[mid:].mean() if len(clean) > mid else clean.iloc[-1]
    if first_half == second_half:
        return "flat"
    if second_half > first_half * 1.05:
        return "improving"
    if second_half < first_half * 0.95:
        return "deteriorating"
    return "mixed / stable"


def _get_comp_color(comp_val):
    if pd.isna(comp_val):
        return ZERO_RETURN_CELL_TEXT
    if comp_val >= 60:
        return EFFICIENCY_COMPOSITE_GOOD
    elif comp_val >= 40:
        t = (comp_val - 40) / 20.0
        r = int(168 - 23 * t)
        g = int(148 + 22 * t)
        b = int(148 + 7  * t)
        return f"rgb({r}, {g}, {b})"
    else:
        return EFFICIENCY_COMPOSITE_BAD


def _security_composite_flags(holdings_df, prices, returns_series, risk_free_rate=0.02, window=252):
    flags = {
        "attn": [],
    }
    if holdings_df is None or holdings_df.empty or prices is None or prices.empty or returns_series is None or returns_series.empty:
        return flags

    port_rets_1y = returns_series.tail(window)
    col_map = {c.lower().strip(): c for c in holdings_df.columns}
    def _pick(*alts):
        for a in alts:
            if a in col_map:
                return col_map[a]
        return None
    name_col = _pick("name", "security_name", "security")
    ticker_col = _pick("ticker", "symbol", "t")
    weight_col = _pick("weight", "wt", "portfolio_weight")

    for ticker in holdings_df.index:
        if ticker not in prices.columns:
            continue
        series = prices[ticker].dropna()
        if len(series) < 20:
            continue
        rets = series.pct_change().dropna()
        rets_1y = rets.tail(window)
        if len(rets_1y) < 20:
            continue
        w1, w2, w3, w4 = 0.5, 0.3, 0.2, 0.2
        days_252 = min(len(series) - 1, 252)
        days_63 = min(len(series) - 1, 63)
        days_200 = min(len(series), 200)
        ret_12m = series.iloc[-1] / series.iloc[-days_252] - 1 if days_252 >= 1 else np.nan
        ret_3m = series.iloc[-1] / series.iloc[-days_63] - 1 if days_63 >= 1 else np.nan
        ma_200 = series.rolling(days_200).mean().iloc[-1] if days_200 >= 1 else np.nan
        mean_reversion = -(series.iloc[-1] / ma_200 - 1) if pd.notna(ma_200) and ma_200 != 0 else np.nan
        arima_contrib = np.nan
        if len(series.dropna()) >= 10:
            try:
                from statsmodels.tsa.arima.model import ARIMA
                model = ARIMA(series.dropna(), order=(1, 1, 1))
                fitted = model.fit()
                forecast = fitted.forecast(steps=1).iloc[0]
                arima_contrib = forecast / series.iloc[-1] - 1
            except Exception:
                pass
        expected_ret = w1 * ret_12m + w2 * ret_3m + w3 * mean_reversion + w4 * arima_contrib
        direction = holdings_df.loc[ticker, 'type'] if 'type' in holdings_df.columns else 'active'
        if direction == 'S':
            expected_ret = -expected_ret
        std_ret = rets_1y.std()
        vol = std_ret * np.sqrt(252) if std_ret > 0 else np.nan
        common_idx = rets_1y.index.intersection(port_rets_1y.index)
        corr = rets_1y.loc[common_idx].corr(port_rets_1y.loc[common_idx]) if len(common_idx) > 20 else np.nan
        if pd.isna(expected_ret) or pd.isna(vol) or pd.isna(corr):
            continue
        e_score = min(max(expected_ret / 0.20, 0.0), 1.0) if expected_ret > 0 else 0.0
        v_score = min(max((0.40 - vol) / (0.40 - 0.05), 0.0), 1.0)
        c_score = min(max((0.80 - corr) / 0.80, 0.0), 1.0)
        composite = (e_score * 0.4 + v_score * 0.3 + c_score * 0.3) * 100

        row_flags = []
        if expected_ret <= 0:
            row_flags.append("Non-positive ER")
        if vol >= 0.40:
            row_flags.append("High vol")
        if corr >= 0.80:
            row_flags.append("High corr")
        if composite < 40:
            row_flags.append("Low composite")
        if row_flags:
            name = holdings_df.loc[ticker, name_col] if name_col and name_col in holdings_df.columns else None
            weight = holdings_df.loc[ticker, weight_col] if weight_col and weight_col in holdings_df.columns else None
            flags["attn"].append({
                "ticker": ticker,
                "name": name,
                "weight": weight,
                "expected_return": expected_ret,
                "composite": composite,
                "flags": ", ".join(row_flags),
            })
    flags["attn"].sort(key=lambda x: x["composite"])
    return flags


def _build_securities_attention_table(holdings_df, prices, returns_series, risk_free_rate=0.02):
    if holdings_df is None or prices is None or returns_series is None:
        return ""
    security_flags = _security_composite_flags(holdings_df, prices, returns_series, risk_free_rate=risk_free_rate)
    if not security_flags["attn"]:
        return ""

    table_rows = []
    for row in security_flags["attn"]:
        if row["composite"] >= 40:
            continue
        ticker = row["ticker"]
        name = row["name"]
        w = row["weight"]
        er = row["expected_return"]
        comp = row["composite"]
        ticker_full = f"{name} ({ticker})" if name and not str(name).endswith(")") else (name or ticker)
        weight_str = f"{w * 100:.2f}%" if pd.notna(w) else "-"
        weight_cell = f"<span style='font-family:\"Courier New\",monospace;font-weight:bold;'>{weight_str}</span>"
        if pd.notna(er):
            er_val = er * 100
            er_color = POSITIVE_RETURN_CARD if er_val > 0 else NEGATIVE_RETURN_CARD if er_val < 0 else ZERO_RETURN_CELL_TEXT
            er_arrow = '▲' if er_val > 0 else '▼' if er_val < 0 else ''
            er_cell = f"<span style='background-color:{er_color};color:{LIGHT_ELEMENT};padding:2px 6px;border-radius:3px;font-weight:bold;font-size:0.85em;white-space:nowrap;'>{er_arrow} {er_val:.2f}%</span>"
        else:
            er_cell = f"<span style='background-color:{ZERO_RETURN_CELL_TEXT};color:{LIGHT_ELEMENT};padding:2px 6px;border-radius:3px;font-weight:bold;font-size:0.85em;'>N/A</span>"
        if pd.notna(comp):
            comp_color = EFFICIENCY_COMPOSITE_GOOD if comp >= 60 else EFFICIENCY_COMPOSITE_BAD if comp < 40 else GAUGE_TRACK_BG
            comp_cell = (
                f"<div style='display:flex;align-items:center;gap:4px;'>"
                f"<span style='font-weight:bold;font-family:\"Courier New\",monospace;min-width:22px;color:{comp_color};font-size:0.85em;'>{comp:.0f}</span>"
                f"<div style='flex-grow:1;height:4px;background-color:{GAUGE_TRACK_BG};border-radius:2px;overflow:hidden;width:36px;'>"
                f"<div style='width:{comp:.0f}%;height:100%;background-color:{comp_color};border-radius:2px;'></div></div></div>"
            )
        else:
            comp_cell = "<div style='font-family:\"Courier New\",monospace;'>-</div>"
        table_rows.append(
            f"<tr>"
            f"<td style='padding:3px 6px;border:1px solid {BORDER_THEME};'>{ticker_full}</td>"
            f"<td style='padding:3px 6px;text-align:right;border:1px solid {BORDER_THEME};'>{weight_cell}</td>"
            f"<td style='padding:3px 6px;text-align:right;border:1px solid {BORDER_THEME};'>{er_cell}</td>"
            f"<td style='padding:3px 6px;text-align:right;border:1px solid {BORDER_THEME};'>{comp_cell}</td>"
            f"</tr>"
        )

    table_html = (
        f"<div style='margin-top:0.75em;'><div style='margin:0 0 0.5em 0;'><b><u>Securities Requiring Attention</u></b></div>"
        f"<table style='border-collapse:collapse;font-size:0.75em;width:100%;'>"
        f"<tr style='background:{BG_ROW_HEADER_ALT};border-bottom:2px solid {BORDER_THEME};'>"
        f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:left;'>Security</th>"
        f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:right;white-space:nowrap;'>Weight<br>(%)</th>"
        f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:right;white-space:nowrap;'>ER (1Y)</th>"
        f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:right;white-space:nowrap;'>Composite<br>Score</th>"
        f"</tr>"
        + "".join(table_rows)
        + "</table></div><br>"
    )
    return table_html


def generate_efficiency_commentary(returns_series, benchmark_returns, holdings_df=None, prices=None, risk_free_rate=0.02):
    if returns_series is None or returns_series.empty or benchmark_returns is None or benchmark_returns.empty:
        return "Efficiency metrics are still being processed. Please ensure full return data is available."

    port_metrics = calculate_performance_metrics(returns_series, benchmark_returns, risk_free_rate=risk_free_rate)
    ratios_1y = _ratio_metrics_1y(returns_series, benchmark_returns, risk_free_rate=risk_free_rate)

    sharpe_1y = ratios_1y.get("Sharpe Ratio", np.nan)
    sortino_1y = ratios_1y.get("Sortino Ratio", np.nan)
    ir_1y = ratios_1y.get("Information Ratio", np.nan)
    alpha_ann = port_metrics.get("Alpha (Risk-Adj) Annualized", np.nan)
    beta_full = port_metrics.get("Beta", np.nan)

    window = 252
    common_idx = returns_series.index.intersection(benchmark_returns.index)
    port = returns_series.loc[common_idx]
    bench = benchmark_returns.loc[common_idx]
    daily_rf = (1 + risk_free_rate) ** (1/252) - 1
    port_rolling_mean = port.rolling(window=window).mean()
    port_rolling_std = port.rolling(window=window).std()
    sharpe_rolling = ((port_rolling_mean - daily_rf) / port_rolling_std) * np.sqrt(252)
    def sortino_rolling_fn(w):
        downside = w[w < 0]
        downside_std = downside.std()
        if pd.isna(downside_std) or downside_std == 0:
            return np.nan
        ann_ret = (1 + w).prod() - 1
        return (ann_ret - risk_free_rate) / (downside_std * np.sqrt(252))
    sortino_rolling = port.rolling(window=window).apply(sortino_rolling_fn, raw=False)
    excess = port - bench
    rolling_excess_mean = excess.rolling(window=window).mean()
    rolling_excess_std = excess.rolling(window=window).std()
    ir_rolling = (rolling_excess_mean / rolling_excess_std) * np.sqrt(252)
    cov_pb = port.rolling(window=window).cov(bench)
    var_b = bench.rolling(window=window).var()
    beta_rolling = cov_pb / var_b
    def ann_ret_rolling_fn(w):
        return (1 + w).prod() - 1
    port_ann_rolling = port.rolling(window=window).apply(ann_ret_rolling_fn, raw=False)
    bench_ann_rolling = bench.rolling(window=window).apply(ann_ret_rolling_fn, raw=False)
    alpha_rolling = (port_ann_rolling - (risk_free_rate + beta_rolling * (bench_ann_rolling - risk_free_rate))) * 100

    main_insights = []
    trend_items = []
    risks = []
    suggestions = []
    suggestion_parts = []

    benchmarks = {
        "Sharpe Ratio": {"ideal": 1.0, "label": "1.0"},
        "Sortino Ratio": {"ideal": 1.0, "label": "1.0"},
        "Information Ratio": {"ideal": 0.5, "label": "0.5"},
    }

    ratio_checks = {
        "Sharpe Ratio": sharpe_1y,
        "Sortino Ratio": sortino_1y,
        "Information Ratio": ir_1y,
    }

    for ratio_name, value in ratio_checks.items():
        lbl = _efficiency_label(ratio_name, value)
        bm = benchmarks[ratio_name]
        if pd.isna(value):
            main_insights.append(f"<b>{ratio_name}:</b> Not available for the current observation window.")
            continue
        if ratio_name == "Sharpe Ratio":
            main_insights.append(
                f"<b>Sharpe Ratio of {_fmt_num(value)} — {lbl}.</b> "
                "Excess return per unit of total volatility. "
                f"A portfolio with an ideal Sharpe of {bm['label']} earns {bm['label']} units of excess return for each unit of total risk. "
                f"At {_fmt_num(value)}, this portfolio {'exceeds' if value >= bm['ideal'] else 'falls below'} that {bm['label']} benchmark — "
                "meaning risk-adjusted efficiency is sensitive to any further increase in total volatility."
            )
            if value < bm["ideal"]:
                risks.append(
                    f"<b>Sharpe Ratio ({_fmt_num(value)}) is below the {bm['label']} benchmark.</b> "
                    "Return is not sufficiently compensating for the aggregate volatility assumed. "
                    "This warrants scrutiny of high-volatility positions that may be diluting risk-adjusted efficiency."
                )
        elif ratio_name == "Sortino Ratio":
            main_insights.append(
                f"<b>Sortino Ratio of {_fmt_num(value)} — {lbl}.</b> "
                "Excess return per unit of downside volatility only, filtering out upside drift. "
                f"An ideal Sortino of {bm['label']} implies clean, accretive returns with limited tail events. "
                "Compared to Sharpe, Sortino isolates the portion of volatility that actually harms the investor. "
                f"At {_fmt_num(value)}, this portfolio {'meets the' if value >= bm['ideal'] else 'is below the'} {bm['label']} threshold, "
                f"suggesting that drawdown control is {'strong' if value >= bm['ideal'] else 'a drag on overall risk-adjusted quality'}."
            )
            if sortino_1y > sharpe_1y and not (pd.isna(sharpe_1y) or pd.isna(sortino_1y)):
                main_insights.append(
                    "<b>Sortino exceeds Sharpe</b>, confirming that a meaningful share of observed volatility manifests as upside rather than drawdown — "
                    "a hallmark of asymmetric, accretive return construction."
                )
            elif sortino_1y < sharpe_1y and not (pd.isna(sharpe_1y) or pd.isna(sortino_1y)):
                risks.append(
                    "<b>Sharpe exceeds Sortino</b>, signalling that a large fraction of the portfolio’s volatility is concentrated in downside events. "
                    "This pattern is typical of carry, short-option, or momentum-biased portfolios."
                )
            if value < bm["ideal"]:
                suggestions.append(
                    "Improve Sortino by trimming positions with high downside semivariance — "
                    "review holdings in the Security Efficiency table for negative skew or high drawdown frequency."
                )
        elif ratio_name == "Information Ratio":
            main_insights.append(
                f"<b>Information Ratio of {_fmt_num(value)} — {lbl}.</b> "
                "Mean active return relative to tracking error, measuring the consistency of benchmark outperformance. "
                f"An IR above {bm['label']} signals a sustainable active process with a high hit-rate. "
                f"At {_fmt_num(value)}, the portfolio's active-management skill is "
                f"{'commensurate with the risk taken versus a benchmark if above' if value >= bm['ideal'] else 'below the ' + bm['label'] + ' benchmark; active bets are not sufficiently rewarded relative to tracking error introduced'}."
            )
            if value < bm["ideal"] and not pd.isna(value):
                risks.append(
                    f"<b>Information Ratio ({_fmt_num(value)}) is below the {bm['label']} threshold.</b> "
                    "The portfolio's active positions are introducing tracking error without commensurate excess return. "
                    "Review the Security Efficiency table for holdings with high benchmark correlation yet low expected return."
                )

    alpha_section = []
    if not pd.isna(alpha_ann):
        bench_ann = port_metrics.get("benchmark_ann", np.nan)
        bench_phrase = (" vs benchmark annualized return of " + _fmt_pct(bench_ann)) if not pd.isna(bench_ann) else ""
        if alpha_ann > 0.02:
            lbl = "strong positive"
        elif alpha_ann > 0:
            lbl = "positive"
        elif alpha_ann == 0:
            lbl = "neutral"
        elif alpha_ann > -0.02:
            lbl = "negative"
        else:
            lbl = "strong negative"
        alpha_section.append(
            f"<b>Alpha (Risk-Adj) Annualized of {_fmt_pct(alpha_ann)} — {lbl}.</b>{bench_phrase} "
            f"At a Beta of {beta_full:.2f}, the portfolio is exposed to {beta_full:.2f}x the benchmark's amplitude. "
            "Alpha strips out this systematic reward, isolating manager skill. "
            f"A {'positive' if alpha_ann > 0 else 'negative'} alpha indicates the portfolio is {'extracting' if alpha_ann > 0 else 'failing to capture'} benchmark-independent returns through security selection. "
            "Potential causes of negative alpha include: overconcentration in high-beta names with insufficient return premium, or poor sector/industry allocation within factor exposures."
        )
    else:
        alpha_section.append("<b>Alpha:</b> Insufficient data for meaningful inference on risk-adjusted excess return.")

    beta_section = []
    if not pd.isna(beta_full):
        if beta_full < 0.8:
            beta_section.append(
                f"<b>Beta of {beta_full:.2f} — low-volatility.</b> The portfolio dampens benchmark swings, "
                "which reduces participation in broad market sell-offs but also capping upside. "
                "A low-volatility Beta can depress alpha if security selection does not sufficiently compensate via idiosyncratic return."
            )
        elif beta_full < 1.0:
            beta_section.append(
                f"<b>Beta of {beta_full:.2f} — conservative.</b> Slightly below-market sensitivity. "
                "This positioning affords partial resilience during adverse regimes while still capturing modest benchmark participation."
            )
        elif beta_full < 1.2:
            beta_section.append(
                f"<b>Beta of {beta_full:.2f} — near market-neutral.</b> Tracks benchmark movements closely, "
                "making alpha the primary differentiator of performance. At this sensitivity, alpha volatility, not beta, drives deviation from benchmark returns."
            )
        elif beta_full < 1.6:
            beta_section.append(
                f"<b>Beta of {beta_full:.2f} — cyclical.</b> Magnifies benchmark volatility. "
                "Elevated systemic exposure means that even marginal benchmark weakness is amplified into portfolio losses — this is the most common source of deteriorating Sharpe and Sortino."
            )
        else:
            beta_section.append(
                f"<b>Beta of {beta_full:.2f} — leveraged.</b> A high systematic leverage profile. "
                "Market directionality dominates security-specific return. Any deterioration in benchmark performance is transmitted disproportionately into portfolio drawdowns — the primary risk factor for Sharpe and Sortino compression."
            )

    security_flags = _security_composite_flags(holdings_df, prices, returns_series, risk_free_rate=risk_free_rate)

    attention_securities = []
    table_rows = []
    if security_flags["attn"]:
        for row in security_flags["attn"]:
            if row["composite"] >= 40:
                continue
            ticker = row["ticker"]
            name = row["name"]
            w = row["weight"]
            er = row["expected_return"]
            comp = row["composite"]
            flags = row["flags"]
            ticker_full = f"{name} ({ticker})" if name and not str(name).endswith(")") else (name or ticker)
            weight_str = f"{w * 100:.2f}%" if pd.notna(w) else "-"
            weight_cell = f"<span style='font-family:\"Courier New\",monospace;font-weight:bold;'>{weight_str}</span>"
            if pd.notna(er):
                er_val = er * 100
                er_color = POSITIVE_RETURN_CARD if er_val > 0 else NEGATIVE_RETURN_CARD if er_val < 0 else ZERO_RETURN_CELL_TEXT
                er_arrow = '▲' if er_val > 0 else '▼' if er_val < 0 else ''
                er_cell = f"<span style='background-color:{er_color};color:{LIGHT_ELEMENT};padding:2px 6px;border-radius:3px;font-weight:bold;font-size:0.85em;white-space:nowrap;'>{er_arrow} {er_val:.2f}%</span>"
            else:
                er_cell = f"<span style='background-color:{ZERO_RETURN_CELL_TEXT};color:{LIGHT_ELEMENT};padding:2px 6px;border-radius:3px;font-weight:bold;font-size:0.85em;'>N/A</span>"
            if pd.notna(comp):
                comp_color = _get_comp_color(comp)
                comp_cell = (
                    f"<div style='display:flex;align-items:center;gap:4px;'>"
                    f"<span style='font-weight:bold;font-family:\"Courier New\",monospace;min-width:22px;color:{comp_color};font-size:0.85em;'>{comp:.0f}</span>"
                    f"<div style='flex-grow:1;height:4px;background-color:{GAUGE_TRACK_BG};border-radius:2px;overflow:hidden;width:36px;'>"
                    f"<div style='width:{comp:.0f}%;height:100%;background-color:{comp_color};border-radius:2px;'></div></div></div>"
                )
            else:
                comp_cell = "<div style='font-family:\"Courier New\",monospace;'>-</div>"
            table_rows.append(
                f"<tr>"
                f"<td style='padding:3px 6px;border:1px solid {BORDER_THEME};'>{ticker_full}</td>"
                f"<td style='padding:3px 6px;text-align:right;border:1px solid {BORDER_THEME};'>{weight_cell}</td>"
                f"<td style='padding:3px 6px;text-align:right;border:1px solid {BORDER_THEME};'>{er_cell}</td>"
                f"<td style='padding:3px 6px;text-align:right;border:1px solid {BORDER_THEME};'>{comp_cell}</td>"
                f"</tr>"
            )

    if security_flags["attn"]:
        names = ", ".join(r["ticker"] for r in security_flags["attn"] if r["composite"] < 40)[:5]
        suggestion_parts.append(
            "Review positions listed above in the table <b>Securities requiring attention</b> carefully as they weigh on portfolio efficiency, potentially dragging Sharpe, Sortino, and Information Ratio. "
            "Determine whether to trim or replace each with securities offering higher expected return, lower volatility, and reduced correlation to the portfolio. "
            "This targeted review will help concentrate risk where it is best rewarded and improve overall portfolio efficiency."
        )
    if ir_1y < 0.5 and not pd.isna(ir_1y):
        suggestion_parts.append(
            f"<b>Information Ratio improvement plan (current IR: {_fmt_num(ir_1y)}):</b> "
            "The portfolio is generating active return but not consistently enough relative to tracking error. "
            "Specific actions: identify the top weighted positions with high correlation to the benchmark and trim them; "
            "instead, concentrate active bets on 5-8 securities with the highest expected return and lowest correlation — "
            "this concentrates active risk where it is most rewarded, raising the Information Ratio."
        )
    if sortino_1y < sharpe_1y and not (pd.isna(sharpe_1y) or pd.isna(sortino_1y)):
        suggestion_parts.append(
            "<b>Sortino repair:</b> Because Sortino lags Sharpe, a meaningful portion of volatility is concentrated in downside events. "
            "Specific actions: scan the flagged securities for high downside semivariance (negative skew); "
            "reduce or hedge long-only positions that carry hidden tail-risk, such as small-cap growth, crypto-exposed names, or options structures with negative convexity. "
            "Replacing these with low-beta, positive-carry positions will lift Sortino above Sharpe."
        )
    if not pd.isna(beta_full) and beta_full > 1.2:
        suggestion_parts.append(
            f"<b>Beta de-risking (current Beta: {beta_full:.2f}):</b> "
            "A portfolio Beta above 1.2 means benchmark weakness is amplified into portfolio losses — this is the most common mechanical driver of Sharpe and Sortino compression. "
            "Specific actions: reduce the overall portfolio Beta by adding low-beta or zero-beta instruments (e.g., government bonds, gold, cash, or low-beta ETFs). "
            "Target a portfolio Beta of 1.0 or below; this alone, without changing security selection, will reduce portfolio volatility and improve Sharpe and Sortino."
        )
    if suggestion_parts:
        suggestions.extend(suggestion_parts)

    alpha_trend = _rolling_trend(alpha_rolling)
    beta_trend = _rolling_trend(beta_rolling)
    sharpe_trend = _rolling_trend(sharpe_rolling)
    sortino_trend = _rolling_trend(sortino_rolling)
    ir_trend = _rolling_trend(ir_rolling)

    trend_lines = []

    def _trend_desc(metric_key, t):
        direction = {
            "improving": "trending <b>improving</b>",
            "deteriorating": "trending <b>deteriorating</b>",
            "mixed / stable": "mixed or broadly stable",
            "flat": "broadly unchanged",
        }.get(t, t)
        if metric_key == "Sharpe Ratio":
            detail = (
                "Excess return per unit of total risk has risen — volatility is easing or return generation is strengthening."
                if t == "improving"
                else "The portfolio’s compensation for total volatility has fallen — check whether upside is fading or volatility is expanding."
                if t == "deteriorating"
                else "Estimation window offers no clear signal on total risk-adjusted efficiency."
            )
        elif metric_key == "Sortino Ratio":
            detail = (
                "Downside risk-adjusted return is strengthening — drawdowns are becoming less frequent or less severe."
                if t == "improving"
                else "Downside-adjusted return is worsening — drawdown-contributing positions or tail-event frequency may be rising."
                if t == "deteriorating"
                else "No consistent change in downside-adjusted efficiency is observable."
            )
        elif metric_key == "Information Ratio":
            detail = (
                "Active return consistency is rising — the portfolio’s benchmark-relative positions are generating higher repeated excess return per unit of tracking error."
                if t == "improving"
                else "Active-return consistency is declining — active bets are generating less consistent outperformance relative to the benchmark."
                if t == "deteriorating"
                else "Active-return consistency shows no strong directional drift."
            )
        elif metric_key == "Alpha (Risk-Adj)":
            detail = (
                "Risk-adjusted excess return over the benchmark is increasing, suggesting manager skill or security-selection quality is improving."
                if t == "improving"
                else "Risk-adjusted excess return is declining, suggesting that returns are being captured via market exposure rather than selection alpha."
                if t == "deteriorating"
                else "Alpha generation shows no discernible directional drift."
            )
        elif metric_key == "Beta":
            detail = (
                "Market sensitivity is easing — the portfolio is becoming less responsive to benchmark swings."
                if t == "improving"
                else "Market sensitivity is rising — the portfolio is becoming more exposed to benchmark directionality."
                if t == "deteriorating"
                else "Systematic market sensitivity is holding steady."
            )
        else:
            detail = ""
        return f"{direction} — {detail}" if detail else direction

    trend_map = {
        "Sharpe Ratio": sharpe_trend,
        "Sortino Ratio": sortino_trend,
        "Information Ratio": ir_trend,
        "Alpha (Risk-Adj)": alpha_trend,
        "Beta": beta_trend,
    }
    for name, t in trend_map.items():
        if t == "insufficient data":
            continue
        desc = _trend_desc(name, t)
        trend_lines.append(f"<b>{name}:</b> {desc}")

    closing = ""
    any_weakness = any(
        v is not None and not pd.isna(v) and v < bm["ideal"]
        for v, bm in zip([sharpe_1y, sortino_1y, ir_1y], benchmarks.values())
    )
    any_strength = any(
        v is not None and not pd.isna(v) and v >= bm["ideal"]
        for v, bm in zip([sharpe_1y, sortino_1y, ir_1y], benchmarks.values())
    )
    has_negative_alpha = not pd.isna(alpha_ann) and alpha_ann < 0
    has_high_beta = not pd.isna(beta_full) and beta_full > 1.2

    if any_weakness and any_strength:
        closing = (
            "The portfolio exhibits a mixed efficiency profile: some metrics are supportive while others lag. "
            "Focus on the securities flagged above and the trend analysis to pinpoint whether volatility, correlation, or return generation is the primary drag."
        )
    elif any_weakness:
        closing = ""
    elif any_strength and not has_negative_alpha and not has_high_beta:
        closing = (
            "The portfolio's efficiency metrics are supportive. "
            "Maintain current allocation discipline and continue monitoring the trend trajectories in the Rolling Metrics History."
        )
    else:
        closing = "Efficiency metrics are being tracked. Continue monitoring for shifts in the rolling trend data."

    parts = []

    main_insight_items = main_insights + alpha_section + beta_section

    if main_insight_items:
        parts.append(
            "<b><u>Efficiency Insights</u></b><br><ul><li>"
            + "</li><li>".join(main_insight_items)
            + f"</li></ul>{closing}"
        )

    if table_rows:
        parts.append(
            f"<div style='margin-top:0.75em;'><div style='margin:0 0 0.5em 0;'><b><u>Securities Requiring Attention</u></b></div>"
            f"<table style='border-collapse:collapse;font-size:0.75em;width:100%;'>"
            f"<tr style='background:{BG_ROW_HEADER_ALT};border-bottom:2px solid {BORDER_THEME};'>"
            f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:left;'>Security</th>"
            f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:right;white-space:nowrap;'>Weight<br>(%)</th>"
            f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:right;white-space:nowrap;'>ER (1Y)</th>"
            f"<th style='padding:3px 6px;border:1px solid {BORDER_THEME};text-align:right;white-space:nowrap;'>Composite<br>Score</th>"
            f"</tr>"
            + "".join(table_rows)
            + "</table></div><br>"
        )

    if trend_lines:
        parts.append(
            "<b><u>Rolling Metrics History — Trend Analysis</u></b><br><ul><li>"
            + "</li><li>".join(trend_lines)
            + "</li></ul>"
        )

    if risks:
        parts.append("<b><u>Efficiency Risks</u></b><br><ul><li>" + "</li><li>".join(risks) + "</li></ul>")
    if suggestions:
        parts.append("<b><u>Efficiency Recommendations</u></b><br><ul><li>" + "</li><li>".join(suggestions) + "</li></ul>")

    return "<br>".join(parts) if parts else "Efficiency indicators are currently within expected ranges."
