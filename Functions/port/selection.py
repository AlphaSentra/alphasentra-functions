"""
Portfolio Pro Investor selection interface HTML template.
"""

import os
import resource
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from flask import request
from dotenv import load_dotenv

from Functions.port.cache import get as cache_get, set as cache_set, exists as cache_exists
from Functions.port.config import CACHE_TTL_ETORO_PI as _ETORO_PI_TTL, LOGIN_REDIRECT_URL
from Functions.etoro.client import EToroClientError, get_public_client_from_env

try:
    from Functions.helpers import DatabaseManager
except ImportError:
    DatabaseManager = None

from Functions.themes import (
    _TEXT_PRIMARY, _TEXT_HEADING, _BRAND_PRIMARY, _HOVER_SURFACE, _BORDER_DEFAULT,
    _BG_SUBTLE, _NEUTRAL_0, _BG_DEFAULT, _TEXT_MUTED, _GRID_LINE, BORDER_DIVIDER,
    _SEMANTIC_POSITIVE, _SEMANTIC_NEGATIVE, _SEMANTIC_WARNING, _SEMANTIC_NEUTRAL,
    _NEUTRAL_SURFACE,
    font as _font_module
)

FONT_FAMILY = _font_module.FONT_PRIMARY

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BASE_DIR, "..", "..", ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=False)

_AVATAR_CACHE: Dict[str, Optional[str]] = {}
_TREND_CACHE: Dict[str, List[float]] = {}
_COUNTRY_INFO_CACHE: Dict[str, Optional[Dict[str, str]]] = {}
_PERIOD_GAIN_CACHE: Dict[str, Dict[str, Optional[float]]] = {}
_COUNTRIES_API_BASE = "https://countries.dev"
_ETORO_COUNTRY_MAP: Dict[str, Dict[str, str]] = {}
_SEARCH_INDEX_CACHE: Optional[List[Dict[str, Any]]] = None
_SEARCH_QUERY_CACHE: Dict[str, tuple] = {}
_SEARCH_CACHE_TTL = 30


def _load_etoro_country_map() -> None:
    csv_path = os.path.join(_BASE_DIR, "..", "etoro", "countries.csv")
    if not os.path.isfile(csv_path):
        return
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            import csv
            reader = csv.DictReader(fh)
            for row in reader:
                etoro_id = (row.get("ETORO_COUNTRYID") or "").strip()
                iso_code = (row.get("ISO_CODE") or "").strip()
                iso_numeric = (row.get("ISO_COUNTRYID") or "").strip()
                if etoro_id and iso_code:
                    _ETORO_COUNTRY_MAP[etoro_id] = {
                        "isoCode": iso_code,
                        "isoNumeric": iso_numeric,
                    }
    except Exception:
        pass


_load_etoro_country_map()


def _get_etoro_client():
    try:
        return get_public_client_from_env()
    except Exception:
        return None


def _get_user_avatar(username: str) -> Optional[str]:
    if not username:
        return None
    if username in _AVATAR_CACHE:
        return _AVATAR_CACHE[username]

    client = _get_etoro_client()
    if client is None:
        _AVATAR_CACHE[username] = None
        return None

    try:
        data = client.get_user_info(username)
    except EToroClientError:
        _AVATAR_CACHE[username] = None
        return None
    if isinstance(data, dict):
        users = data.get("users", [])
        if users:
            avatars = users[0].get("avatars") or []
            for av in avatars:
                url = av.get("url")
                if url:
                    _AVATAR_CACHE[username] = url
                    return url
    _AVATAR_CACHE[username] = None
    return None


def _get_trend_data(username: str) -> List[float]:
    if not username:
        return []
    if username in _TREND_CACHE:
        return _TREND_CACHE[username]

    min_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    max_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    client = _get_etoro_client()
    if client is None:
        _TREND_CACHE[username] = []
        return []

    try:
        data = client.get_daily_gain(username, {"minDate": min_date, "maxDate": max_date, "type": "Daily"})
    except EToroClientError:
        _TREND_CACHE[username] = []
        return []
    if not isinstance(data, list):
        if isinstance(data, dict):
            data = data.get("dailyExample", data.get("daily", []))
        else:
            data = []
    points = []
    cumulative = 0.0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        gain = entry.get("gain")
        if gain is not None:
            cumulative += float(gain)
            points.append(cumulative)
    if points:
        _TREND_CACHE[username] = points
        return points
    _TREND_CACHE[username] = []
    return []


def _get_period_gain(username: str, period: str) -> Optional[float]:
    if not username:
        return None
    cache_key = f"{username}:{period}"
    if cache_key in _PERIOD_GAIN_CACHE:
        return _PERIOD_GAIN_CACHE[cache_key]

    client = _get_etoro_client()
    if client is None:
        _PERIOD_GAIN_CACHE[cache_key] = None
        return None

    try:
        data = client.get_daily_gain(username, {"type": "Period", "period": period})
    except EToroClientError as exc:
        if exc.status_code == 404:
            result = _get_period_gain_from_daily(username, period)
            _PERIOD_GAIN_CACHE[cache_key] = result
            return result
        _PERIOD_GAIN_CACHE[cache_key] = None
        return None
    result: Optional[float] = None
    if isinstance(data, dict):
        result = data.get("gain") or data.get("gainPercent")
    elif isinstance(data, list) and data:
        entry = data[0]
        result = entry.get("gain") or entry.get("gainPercent")
    _PERIOD_GAIN_CACHE[cache_key] = result
    return result


def _get_period_gain_from_daily(username: str, period: str) -> Optional[float]:
    period_days = {"1m": 30, "3m": 90, "1y": 365}
    days = period_days.get(period, 30)
    min_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    max_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    client = _get_etoro_client()
    if client is None:
        return None

    try:
        data = client.get_daily_gain(username, {"type": "Daily", "minDate": min_date, "maxDate": max_date})
    except EToroClientError:
        return None
    if not isinstance(data, list):
        return None
    total = 0.0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        gain = entry.get("gain")
        if gain is not None:
            total += float(gain)
    return total if total != 0 else None


def _trend_svg_from_points(points: List[float], width: int = 100, height: int = 28) -> str:
    if not points:
        return _trend_svg(positive=True)

    min_val = min(points)
    max_val = max(points)
    if max_val == min_val:
        normed = [height / 2 for _ in points]
    else:
        normed = [
            height - ((value - min_val) / (max_val - min_val)) * height
            for value in points
        ]

    step = width / (len(points) - 1) if len(points) > 1 else 0
    point_str = " ".join(
        f"{i * step:.2f},{value:.2f}" for i, value in enumerate(normed)
    )

    last = points[-1]
    color = _SEMANTIC_POSITIVE if last >= 0 else _SEMANTIC_NEGATIVE

    return (
        f"<svg class=\"trend-chart\" viewBox=\"0 0 {width} {height}\" preserveAspectRatio=\"none\">"
        f"<polyline fill=\"none\" stroke=\"{color}\" stroke-width=\"1.5\" points=\"{point_str}\"/></svg>"
    )


def _trend_svg_for_gains(week_gain: Optional[float], month_gain: Optional[float], year_gain: Optional[float]) -> str:
    if week_gain is None and month_gain is None and year_gain is None:
        return _trend_svg(positive=True)

    latest = week_gain if week_gain is not None else month_gain
    if latest is None:
        latest = year_gain

    return _trend_svg(positive=latest >= 0)


def _get_rankings(period: str = "CurrMonth", sort: Optional[str] = "-copiersGain", page_size: int = 20, page: int = 1, search_text: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "period": period,
        "sort": sort,
        "copiersMin": 10,
        "weeksSinceRegistrationMin": 52,
        "page": page,
    }
    if page_size is not None:
        params["pageSize"] = page_size
    if search_text:
        params["searchText"] = search_text

    client = _get_etoro_client()
    if client is None:
        return {"results": [], "pagination": {}, "error": "eToro client not initialized"}

    try:
        data = client.search_people(params)
        return {
            "results": data.get("items", []),
            "pagination": data.get("pagination", {}),
        }
    except EToroClientError as exc:
        return {"results": [], "pagination": {}, "error": str(exc)}


def _build_gain_map(items: List[Dict[str, Any]], gain_key: str) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for item in items:
        username = str(item.get("userName", item.get("cid", "")))
        if username:
            result[username] = item.get(gain_key)
    return result


def _safe_gain(value: Optional[float]) -> str:
    if value is None:
        return ""
    is_pos = value > 0
    css_class = "perf-pill-pos" if is_pos else "perf-pill-neg" if value < 0 else "perf-pill-na"
    arrow = "▲" if is_pos else "▼" if value < 0 else ""
    sign = "+" if value >= 0 else ""
    return f'<span class="perf-pill {css_class}">{arrow} {sign}{value:.2f}%</span>'


def _safe_aum(value: Optional[Any]) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"${value / 1_000:.1f}K"
        return f"${value:.0f}"
    return str(value)


def _safe_int(value: Optional[int]) -> str:
    if value is None:
        return "N/A"
    return f"{value:,}"


def _copiers_change(copiers: Optional[int], base: Optional[int]) -> str:
    if copiers is None or base is None or base == 0:
        return ""
    change_pct = ((copiers - base) / base) * 100
    sign = "+" if change_pct >= 0 else ""
    arrow = "&#x25B2;" if change_pct >= 0 else "&#x25BC;"
    return f"{arrow} {sign}{change_pct:.1f}% 1M"


def _badge_for_subtype(subtype: Optional[str]) -> str:
    if not subtype:
        return ""
    normalized = subtype.lower()
    if normalized == "pi-elite-pro":
        label = "ELITE PRO"
        css = "badge-elite-pro"
    elif normalized == "pi-elite":
        label = "ELITE"
        css = "badge-elite"
    elif normalized == "pi-champion":
        label = "CHAMPION"
        css = "badge-champion"
    elif normalized == "pi-rising-star":
        label = "RISING STAR"
        css = "badge-elite"
    elif normalized == "pi-certified":
        label = "CERTIFIED"
        css = "badge-elite"
    else:
        return ""
    return f"<span class=\"badge {css}\">{label}</span>"


def _trend_svg(positive: bool = True) -> str:
    color = _SEMANTIC_POSITIVE if positive else _SEMANTIC_NEGATIVE
    points = "0,20 12,18 24,19 36,16 48,15 60,14 72,10 84,8 100,4"
    return (
        f"<svg class=\"trend-chart\" viewBox=\"0 0 100 28\" preserveAspectRatio=\"none\">"
        f"<polyline fill=\"none\" stroke=\"{color}\" stroke-width=\"1.5\" points=\"{points}\"/></svg>"
    )


def _avatar_html(avatar_url: Optional[str], name: str, avatar_class: str = "investor-avatar") -> str:
    if avatar_url:
        return (
            f"<img class=\"{avatar_class}\" src=\"{avatar_url}\" alt=\"avatar\" "
            f"onerror=\"this.style.display='none'\">"
        )
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    return f"<div class=\"{avatar_class}\" style=\"background-color:{_SEMANTIC_POSITIVE};color:{_NEUTRAL_0};display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:18px;flex-shrink:0;\">{initials}</div>"


def _render_login_prompt_row() -> str:
    login_url = LOGIN_REDIRECT_URL
    return (
        f'<tr class="my-portfolio-row my-portfolio-login-prompt">'
        f'<td colspan="8">'
        f'<div class="my-portfolio-investor">'
        f'<div class="my-portfolio-avatar my-portfolio-login-avatar">'
        f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        f' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
        f' style="color:{_TEXT_MUTED};flex-shrink:0;">'
        f'<rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>'
        f'<path d="M7 11V7a5 5 0 0 1 10 0v4"></path>'
        f'</svg>'
        f'</div>'
        f'<div class="my-portfolio-info my-portfolio-login-info">'
        f'<div class="my-portfolio-name-row my-portfolio-login-name-row">'
        f'<span class="my-portfolio-name my-portfolio-login-name">My Portfolio</span>'
        f'</div>'
        f'<span class="my-portfolio-username my-portfolio-login-subtitle">'
        f'Sign in to view and add your portfolio'
        f'</span>'
        f'<a href="{login_url}" class="my-portfolio-login-btn"'
        f' onclick="window.top.location.href=\'{login_url}\'; event.stopPropagation(); event.preventDefault(); return false;">'
        f'Login &rarr;'
        f'</a>'
        f'</div>'
        f'</div>'
        f'</td>'
        f'</tr>'
    )


def _get_country_info(code: str) -> Optional[Dict[str, str]]:
    if not code:
        return None
    code = str(code)
    if code in _COUNTRY_INFO_CACHE:
        return _COUNTRY_INFO_CACHE[code]

    is_numeric = code.isdigit()
    endpoint = "numericcode" if is_numeric else "alpha"
    url = f"{_COUNTRIES_API_BASE}/{endpoint}/{code}"

    try:
        resp = requests.get(url, params={"fields": "name,alpha2Code,flag"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = {
                "flag": data.get("flag", ""),
                "alpha2": data.get("alpha2Code", ""),
            }
            _COUNTRY_INFO_CACHE[code] = result
            return result
    except requests.RequestException:
        pass

    _COUNTRY_INFO_CACHE[code] = None
    return None


def _prefetch_country_data(items: List[Dict[str, Any]]) -> None:
    codes: set = set()
    for item in items:
        country = item.get("country")
        if country:
            codes.add(str(country))
        country_id = item.get("countryId")
        if country_id is not None:
            mapped = _ETORO_COUNTRY_MAP.get(str(country_id))
            if mapped:
                codes.add(mapped["isoCode"])
            else:
                codes.add(str(country_id))

    if not codes:
        return

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_get_country_info, code): code for code in codes}
        for future in as_completed(futures):
            future.result()


def _country_html(country: Optional[str]) -> str:
    if not country:
        return "<span class=\"country-badge\">N/A</span>"
    country = str(country)

    mapped = _ETORO_COUNTRY_MAP.get(country)
    if mapped:
        country = mapped["isoCode"]

    info = _get_country_info(country)
    if info:
        flag = info.get("flag", "")
        alpha2 = info.get("alpha2", country.upper() if not country.isdigit() else "")
        display = alpha2 or country.upper()
        return f"<span class=\"country-badge\"><span class=\"country-flag\">{flag}</span>{display}</span>"

    return f"<span class=\"country-badge\">{country.upper()}</span>"


_MP_CLASSES = {
    "tr": "my-portfolio-row",
    "avatar": "my-portfolio-avatar",
    "investor": "my-portfolio-investor",
    "info": "my-portfolio-info",
    "name_row": "my-portfolio-name-row",
    "name": "my-portfolio-name",
    "username": "my-portfolio-username",
    "country": "my-portfolio-country",
    "aum": "my-portfolio-aum",
    "copiers_value": "my-portfolio-copiers-value",
    "copiers_change": "my-portfolio-copiers-change",
    "week_perf": "my-portfolio-performance",
    "month_perf": "my-portfolio-performance",
    "year_perf": "my-portfolio-performance",
    "trend": "my-portfolio-trend",
}

_PI_CLASSES = {
    "tr": "",
    "avatar": "investor-avatar",
    "investor": "investor-info",
    "info": "investor-details",
    "name_row": "investor-name-row",
    "name": "investor-name",
    "badge": "badge",
    "username": "investor-username",
    "country": "country-badge",
    "aum": "aum-value",
    "copiers_value": "copiers-value",
    "copiers_change": "copiers-change",
    "week_perf": "",
    "month_perf": "",
    "year_perf": "",
    "trend": "trend-chart",
}


def _render_row(
    item: Dict[str, Any],
    week_map: Dict[str, float],
    month_map: Dict[str, float],
    year_map: Dict[str, float],
    classes: Optional[Dict[str, str]] = None,
    badge_text: Optional[str] = None,
    country_html_override: Optional[str] = None,
    aum_override: Optional[str] = None,
    copiers_value_override: Optional[str] = None,
    copiers_change_override: Optional[str] = None,
    week_gain_html_override: Optional[str] = None,
    month_gain_html_override: Optional[str] = None,
    year_gain_html_override: Optional[str] = None,
    error_message: Optional[str] = None,
    include_badge: bool = True,
) -> str:
    cls = classes if classes else _PI_CLASSES
    cid = str(item.get("userName", item.get("username", item.get("cid", item.get("realCID", item.get("gcid", ""))))))
    username = item.get("userName", item.get("username", ""))
    full_name = item.get("fullName") or item.get("displayName") or username

    if error_message:
        display_name = full_name or item.get("userName", username)
        return (
            f"<tr class=\"{cls['tr']}\">"
            f"<td colspan=\"8\">"
            f"<div class=\"my-portfolio-investor\">"
            f"{_avatar_html(None, display_name, cls['avatar'])}"
            f"<div class=\"{cls['info']}\">"
            f"<div class=\"{cls['name_row']}\">"
            f"<span class=\"{cls['name']}\">{display_name}</span>"
            f"</div>"
            f"<span class=\"{cls['username']}\" style=\"color:{_SEMANTIC_NEGATIVE};\">{error_message}</span>"
            f"</div>"
            f"</div>"
            f"</td>"
            f"</tr>"
        )
    avatar_url = item.get("avatarUrl")
    if not avatar_url:
        avatar_url = _get_user_avatar(username)
    subtype = item.get("subType")
    country = item.get("country")
    country_id = item.get("countryId")
    copiers = item.get("copiers")
    aum_value = item.get("aumValue")
    aum_tier_desc = item.get("aumTierDesc")
    base_line_copiers = item.get("baseLineCopiers")

    week_gain = week_map.get(cid)
    month_gain = month_map.get(cid)
    year_gain = year_map.get(cid)

    if not country and country_id is not None:
        mapped = _ETORO_COUNTRY_MAP.get(str(country_id))
        if mapped:
            country = mapped["isoCode"]
        else:
            country = str(country_id)

    aum_display = aum_tier_desc if aum_tier_desc else _safe_aum(aum_value)

    trend_points = _get_trend_data(username)
    if trend_points:
        trend_svg = _trend_svg_from_points(trend_points)
    else:
        trend_svg = _trend_svg_for_gains(week_gain, month_gain, year_gain)

    if include_badge:
        if badge_text:
            badge_html = f"<span class=\"{cls['badge']}\">{badge_text}</span>"
        else:
            badge_html = _badge_for_subtype(subtype)
    else:
        badge_html = ""

    search_text = (
        f"{full_name} @{username} {country or ''}".lower()
    )

    country_td = country_html_override if country_html_override is not None else _country_html(country)
    aum_td = aum_override if aum_override is not None else _safe_aum(aum_display)
    copiers_val_td = copiers_value_override if copiers_value_override is not None else _safe_int(copiers)
    copiers_chg_td = copiers_change_override if copiers_change_override is not None else _copiers_change(copiers, base_line_copiers)
    week_td = week_gain_html_override if week_gain_html_override is not None else _safe_gain(week_gain)
    month_td = month_gain_html_override if month_gain_html_override is not None else _safe_gain(month_gain)
    year_td = year_gain_html_override if year_gain_html_override is not None else _safe_gain(year_gain)

    return (
        f"<tr class=\"{cls['tr']}\" data-search=\"{search_text}\">"
        f"<td>"
        f"<div class=\"{cls['investor']}\">"
        f"{_avatar_html(avatar_url, full_name, cls['avatar'])}"
        f"<div class=\"{cls['info']}\">"
        f"<div class=\"{cls['name_row']}\">"
        f"<span class=\"{cls['name']}\">{full_name}</span>"
        f"{badge_html}"
        f"</div>"
        f"<span class=\"{cls['username']}\">@{username}</span>"
        f"</div>"
        f"</div>"
        f"</td>"
        f"<td>{country_td}</td>"
        f"<td><span class=\"{cls['aum']}\">{aum_td}</span></td>"
        f"<td>"
        f"<div class=\"{cls['copiers_value']}\">{copiers_val_td}</div>"
        f"<div class=\"{cls['copiers_change']}\">{copiers_chg_td}</div>"
        f"</td>"
        f"<td class=\"{cls['week_perf']}\">{week_td}</td>"
        f"<td class=\"{cls['month_perf']}\">{month_td}</td>"
        f"<td class=\"{cls['year_perf']}\">{year_td}</td>"
        f"<td>{trend_svg}</td>"
        f"</tr>"
    )


def _fetch_rankings() -> List[Dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_base = executor.submit(_get_rankings, "OneMonthAgo", "-copiersGain", 20)
        future_month = executor.submit(_get_rankings, "ThreeMonthsAgo", "-copiersGain", 20)
        future_year = executor.submit(_get_rankings, "OneYearAgo", "-copiersGain", 20)

        base_data = future_base.result()
        month_data = future_month.result()
        year_data = future_year.result()

    base_results = base_data.get("results", [])
    month_results = month_data.get("results", [])
    year_results = year_data.get("results", [])

    if not base_results and not month_results and not year_results:
        base_error = base_data.get("error") or month_data.get("error") or year_data.get("error")
        if base_error:
            raise RuntimeError(base_error)

    if not base_results:
        base_results = month_results or year_results

    merged: List[Dict[str, Any]] = []
    seen = set()
    for item in base_results:
        if item.get("copiers", 0) <= 10:
            continue
        cid = str(item.get("userName", item.get("cid", "")))
        if cid and cid not in seen:
            seen.add(cid)
            merged.append(item)

    week_map: Dict[str, float] = {}
    month_map: Dict[str, float] = {}
    year_map: Dict[str, float] = {}

    for item in merged:
        cid = str(item.get("userName", item.get("cid", "")))
        if cid:
            week_map[cid] = item.get("gain")

    month_map = _build_gain_map(month_data.get("results", []), "gain")
    year_map = _build_gain_map(year_data.get("results", []), "gain")

    if merged:
        _prefetch_country_data(merged)

    return merged, week_map, month_map, year_map


def _search_user_full(username: str) -> Optional[Dict[str, Any]]:
    if not username or username == "My Portfolio":
        return None

    client = _get_etoro_client()
    if client is None:
        return None

    try:
        data = client.get_portfolio_rankings(username, {"period": "CurrMonth"})
        item = data.get("data")
        if item and isinstance(item, dict):
            if str(item.get("userName", item.get("username", ""))).lower() == username.lower():
                if not item.get("country") and not item.get("countryId"):
                    try:
                        user_data = client.get_user_info(username)
                        users = user_data.get("users", [])
                        if users:
                            country_val = users[0].get("country")
                            if country_val is not None:
                                item["country"] = country_val
                    except EToroClientError:
                        pass
                return item
        return None
    except EToroClientError:
        return None


def _ensure_etoro_pi_indexes(db_name: str, coll) -> None:
    try:
        existing = set(idx["key"] for idx in coll.list_indexes())
        target = {("userName", 1), ("fullName", 1), ("username", 1), ("isPi", 1)}
        if not target.issubset(existing):
            for field in ("userName", "fullName", "username"):
                try:
                    coll.create_index([(field, 1)], background=True)
                except Exception:
                    pass
            try:
                coll.create_index([("userName", 1), ("fullName", 1), ("username", 1)], background=True)
            except Exception:
                pass
    except Exception:
        pass


def _search_etoro_pi_db(query: str, limit: int = 20) -> Dict[str, Any]:
    if DatabaseManager is None:
        return {"results": [], "error": "MongoDB client not available"}

    q = query.strip().lower()
    if not q:
        return {"results": []}

    try:
        db = DatabaseManager().get_client()
        db_name = os.getenv("MONGODB_DATABASE", "alphasentra-core")
        coll = db[db_name]["etoro_pi"]
        _ensure_etoro_pi_indexes(db_name, coll)

        prefix = {"$regex": f"^{q}", "$options": "i"}
        cursor = coll.find(
            {
                "$or": [
                    {"userName": prefix},
                    {"fullName": prefix},
                    {"username": prefix},
                ]
            },
            {
                "userName": 1,
                "fullName": 1,
                "username": 1,
                "country": 1,
                "gain": 1,
                "copiers": 1,
                "baseLineCopiers": 1,
                "aumTierDesc": 1,
                "avatars": 1,
                "countryId": 1,
                "subType": 1,
            },
        ).limit(limit)

        results = []
        seen = set()
        for doc in cursor:
            username = str(doc.get("userName") or doc.get("username") or "").strip()
            if not username or username.lower() in seen:
                continue
            seen.add(username.lower())

            full_name = str(doc.get("fullName") or "").strip() or None
            avatar_url = None
            avatars = doc.get("avatars") or []
            if isinstance(avatars, list) and avatars:
                avatar_url = avatars[0].get("url") if isinstance(avatars[0], dict) else None

            results.append(
                {
                    "userName": username,
                    "username": username,
                    "fullName": full_name,
                    "displayName": full_name,
                    "avatarUrl": avatar_url,
                    "country": doc.get("country"),
                    "countryId": doc.get("countryId"),
                    "copiers": doc.get("copiers"),
                    "baseLineCopiers": doc.get("baseLineCopiers"),
                    "gain": doc.get("gain"),
                    "aumTierDesc": doc.get("aumTierDesc"),
                    "aumValue": None,
                    "subType": doc.get("subType") or "",
                    "isPi": doc.get("isPi", True),
                }
            )

        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


def search_investors_api(query: str) -> Dict[str, Any]:
    if not query or not query.strip():
        return {"results": []}

    q = query.strip().lower()
    now = time.time()

    for prefix_len in range(len(q), 0, -1):
        prefix = q[:prefix_len]
        entry = _SEARCH_QUERY_CACHE.get(prefix)
        if entry is None:
            continue
        ts, cached_results = entry
        if now - ts > _SEARCH_CACHE_TTL:
            del _SEARCH_QUERY_CACHE[prefix]
            continue
        if cached_results.get("results") and prefix == q:
            _SEARCH_QUERY_CACHE[q] = (now, cached_results)
            return cached_results
        if cached_results.get("results"):
            filtered = _filter_results_by_suffix(cached_results["results"], q[prefix_len:])
            result = {"results": filtered}
            _SEARCH_QUERY_CACHE[q] = (now, result)
            return result

    db_result = _search_etoro_pi_db(query, limit=20)
    _cleanup_expired_cache_entries(now)
    _SEARCH_QUERY_CACHE[q] = (now, db_result)
    return db_result


def _filter_results_by_suffix(results: List[Dict[str, Any]], suffix: str) -> List[Dict[str, Any]]:
    if not suffix:
        return results
    suffix_lower = suffix.lower()
    filtered = []
    for item in results:
        searchable = " ".join([
            str(item.get("userName", "")),
            str(item.get("fullName", "")),
            str(item.get("username", "")),
        ]).lower()
        if suffix_lower in searchable:
            filtered.append(item)
    return filtered[:20]


def _cleanup_expired_cache_entries(now: float) -> None:
    expired = [k for k, (ts, _) in _SEARCH_QUERY_CACHE.items() if now - ts > _SEARCH_CACHE_TTL]
    for k in expired:
        del _SEARCH_QUERY_CACHE[k]


_FALLBACK_INVESTORS = [
    {"cid": "1", "username": "CompoundValue", "fullName": "Sarah Miller", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "US", "copiers": 32800, "aumValue": 14500000.0, "baseLineCopiers": 31850, "gain": 0.42},
    {"cid": "2", "username": "GreenMacro_Vance", "fullName": "Helena Vance", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "GB", "copiers": 24100, "aumValue": 12200000.0, "baseLineCopiers": 22900, "gain": 0.72},
    {"cid": "3", "username": "TechBull_Sanchez", "fullName": "Ruben Sanchez", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "ES", "copiers": 18450, "aumValue": 8400000.0, "baseLineCopiers": 16080, "gain": 2.84},
    {"cid": "4", "username": "NordicCap_Nielsen", "fullName": "Line Nielsen", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "DK", "copiers": 14200, "aumValue": 7900000.0, "baseLineCopiers": 13020, "gain": 1.65},
    {"cid": "5", "username": "CryptoQuantum", "fullName": "Yuki Sato", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-champion", "country": "JP", "copiers": 11350, "aumValue": 4100000.0, "baseLineCopiers": 8820, "gain": -4.32},
    {"cid": "6", "username": "ShenzhenVanguard", "fullName": "Lin Wong", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "SG", "copiers": 10800, "aumValue": 6700000.0, "baseLineCopiers": 9130, "gain": 3.42},
    {"cid": "7", "username": "AlphaDividends", "fullName": "Maximilian Weber", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "DE", "copiers": 9200, "aumValue": 5800000.0, "baseLineCopiers": 8480, "gain": 1.15},
    {"cid": "8", "username": "TrendRider_Chloe", "fullName": "Chloe Laurent", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "FR", "copiers": 8700, "aumValue": 6200000.0, "baseLineCopiers": 7820, "gain": 2.14},
    {"cid": "9", "username": "QuantumEdge", "fullName": "Marcus Chen", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "AU", "copiers": 21500, "aumValue": 9300000.0, "baseLineCopiers": 20150, "gain": 1.28},
    {"cid": "10", "username": "NordicGrowth", "fullName": "Sofia Andersson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "SE", "copiers": 16800, "aumValue": 7600000.0, "baseLineCopiers": 15360, "gain": 0.95},
    {"cid": "11", "username": "QuantumAlpha", "fullName": "James Wilson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "GB", "copiers": 28300, "aumValue": 11800000.0, "baseLineCopiers": 27080, "gain": 1.15},
    {"cid": "12", "username": "EmergingMarkets", "fullName": "Aisha Patel", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "IN", "copiers": 12100, "aumValue": 5400000.0, "baseLineCopiers": 11220, "gain": 1.88},
    {"cid": "13", "username": "AsiaTech_Kim", "fullName": "David Kim", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "KR", "copiers": 19700, "aumValue": 8900000.0, "baseLineCopiers": 18600, "gain": 2.05},
    {"cid": "14", "username": "GreenBond_Emma", "fullName": "Emma Thompson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "GB", "copiers": 14500, "aumValue": 6300000.0, "baseLineCopiers": 13650, "gain": 0.65},
    {"cid": "15", "username": "LatamGrowth", "fullName": "Lucas Silva", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-champion", "country": "BR", "copiers": 9800, "aumValue": 4700000.0, "baseLineCopiers": 8710, "gain": -1.25},
    {"cid": "16", "username": "EuroValue_Nina", "fullName": "Nina Kowalski", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "DE", "copiers": 15600, "aumValue": 7100000.0, "baseLineCopiers": 14780, "gain": 0.88},
    {"cid": "17", "username": "DeepSea_Oliver", "fullName": "Oliver Brown", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "AU", "copiers": 22400, "aumValue": 9600000.0, "baseLineCopiers": 20910, "gain": 1.55},
    {"cid": "18", "username": "IndiaRising", "fullName": "Priya Sharma", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "IN", "copiers": 8200, "aumValue": 3900000.0, "baseLineCopiers": 7420, "gain": 2.35},
    {"cid": "19", "username": "NordicBond_Thomas", "fullName": "Thomas Anderson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "NO", "copiers": 13100, "aumValue": 5800000.0, "baseLineCopiers": 12570, "gain": 0.55},
    {"cid": "20", "username": "JapanNext", "fullName": "Yuki Tanaka", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-champion", "country": "JP", "copiers": 16900, "aumValue": 6900000.0, "baseLineCopiers": 15540, "gain": -0.75},
]

_WEEK_MAP = {str(item["cid"]): item["gain"] * 100 for item in _FALLBACK_INVESTORS}
_MONTH_MAP = {
    "1": 1.85, "2": 2.45, "3": 8.12, "4": 5.24, "5": 14.5,
    "6": 9.55, "7": 4.1, "8": 6.8, "9": 3.9, "10": 4.2,
    "11": 5.4, "12": 6.8, "13": 6.2, "14": 2.9, "15": -1.25,
    "16": 3.25, "17": 4.75, "18": 8.2, "19": 2.1, "20": 5.1,
}
_YEAR_MAP = {
    "1": 14.2, "2": 16.85, "3": 42.65, "4": 28.4, "5": 89.2,
    "6": 32.8, "7": 19.4, "8": 26.9, "9": 18.5, "10": 21.3,
    "11": 19.8, "12": 24.1, "13": 31.2, "14": 15.7, "15": 45.3,
    "16": 17.9, "17": 22.4, "18": 38.5, "19": 13.8, "20": 27.6,
}


def get_portfolio_selection_html() -> str:
    from flask import g
    try:
        start_usage = resource.getrusage(resource.RUSAGE_SELF)
        start_rss = start_usage.ru_maxrss
        if sys.platform.startswith("linux"):
            start_mem_mb = start_rss / 1024
        else:
            start_mem_mb = start_rss / (1024 * 1024)
    except Exception:
        start_mem_mb = None
    etoro_authuser = getattr(g, 'etoro_authuser', None)
    is_authenticated = etoro_authuser is not None
    if is_authenticated:
        username_from_cookie = etoro_authuser
        username_display = etoro_authuser
        username_at_display = f"@{etoro_authuser}"
    else:
        username_from_cookie = 'My Portfolio'
        username_display = 'My Portfolio'
        username_at_display = "@MyPortfolio"

    # Try to get cached my_portfolio row for this user
    my_portfolio_cache_key = ("portfolio_selection_my_portfolio", username_from_cookie)
    my_portfolio_html_row = cache_get(my_portfolio_cache_key, _ETORO_PI_TTL, ext=".html")

    # Fetch rankings data (cache the raw result to avoid repeated API calls)
    rankings_cache_key = ("portfolio_selection_rankings",)
    cached_rankings = cache_get(rankings_cache_key, _ETORO_PI_TTL, ext=".pkl")
    
    if cached_rankings is not None:
        merged, week_map, month_map, year_map = cached_rankings
    else:
        try:
            merged, week_map, month_map, year_map = _fetch_rankings()
            cache_set(rankings_cache_key, (merged, week_map, month_map, year_map), ext=".pkl")
        except Exception as exc:
            print(f"Failed to fetch eToro rankings: {exc}")
            merged, week_map, month_map, year_map = [], {}, {}, {}

    if not merged:
        merged = _FALLBACK_INVESTORS
        week_map = _WEEK_MAP
        month_map = _MONTH_MAP
        year_map = _YEAR_MAP

    if merged:
        _prefetch_country_data(merged)

    # Cache the common rows HTML (shared across all users)
    common_rows_cache_key = ("portfolio_selection_common_rows",)
    rows_html = cache_get(common_rows_cache_key, _ETORO_PI_TTL, ext=".html")
    if rows_html is None:
        rows_html = "\n".join(_render_row(item, week_map, month_map, year_map) for item in merged)
        cache_set(common_rows_cache_key, rows_html, ext=".html")

    _FALLBACK_AUM = "$14.5M"
    _FALLBACK_COPIERS = "32,800"
    _FALLBACK_COPIERS_CHANGE = "&#x25B2; 3.1% 1M"
    _FALLBACK_WEEK = "<span class=\"perf-pill perf-pill-pos\">▲ +0.42%</span>"
    _FALLBACK_MONTH = "<span class=\"perf-pill perf-pill-pos\">▲ +1.85%</span>"
    _FALLBACK_YEAR = "<span class=\"perf-pill perf-pill-pos\">▲ +14.20%</span>"
    _FALLBACK_TREND = f"<svg class=\"my-portfolio-trend\" viewBox=\"0 0 100 28\" preserveAspectRatio=\"none\"><polyline fill=\"none\" stroke=\"{_SEMANTIC_POSITIVE}\" stroke-width=\"1.5\" points=\"0,20 12,18 24,19 36,16 48,15 60,14 72,10 84,8 100,4\"/></svg>"

    # Default values for "My Portfolio" — start as N/A; only replaced by placeholders
    # if the API call completely fails (network error / non-200 / empty users).
    my_avatar_html = f"<div class=\"my-portfolio-avatar\">&#x1F4B0;</div>"
    my_country_html_val = "<span class=\"my-portfolio-country\">N/A</span>"
    my_aum_display = "N/A"
    my_copiers_value = "N/A"
    my_copiers_change_val = ""
    my_week_gain_html = ""
    my_month_gain_html = ""
    my_year_gain_html = ""
    my_trend_svg_val = _trend_svg(positive=True)

    my_portfolio_item: Optional[Dict[str, Any]] = None
    my_portfolio_invalid = False
    my_portfolio_error = ""
    my_portfolio_api_failed = False
    my_portfolio_from_rankings = False

    for item in merged:
        if str(item.get("userName", item.get("username", ""))).lower() == username_from_cookie.lower():
            my_portfolio_item = item
            break

    if not my_portfolio_item and username_from_cookie != "My Portfolio":
        my_portfolio_item = _search_user_full(username_from_cookie)
        if my_portfolio_item:
            my_portfolio_from_rankings = True
            _prefetch_country_data([my_portfolio_item])

    if not my_portfolio_item and username_from_cookie != "My Portfolio":
        client = _get_etoro_client()
        if client is not None:
            try:
                data = client.get_user_info(username_from_cookie)
                users = data.get("users", [])
                if users:
                    my_portfolio_item = users[0]
                    _prefetch_country_data([my_portfolio_item])
                else:
                    my_portfolio_invalid = True
                    my_portfolio_error = f"@{username_from_cookie} portfolio does not exist"
            except EToroClientError:
                my_portfolio_api_failed = True
        else:
            my_portfolio_api_failed = True

    if my_portfolio_api_failed and username_from_cookie != "My Portfolio":
        my_aum_display = _FALLBACK_AUM
        my_copiers_value = _FALLBACK_COPIERS
        my_copiers_change_val = _FALLBACK_COPIERS_CHANGE
        my_week_gain_html = _FALLBACK_WEEK
        my_month_gain_html = _FALLBACK_MONTH
        my_year_gain_html = _FALLBACK_YEAR
        my_trend_svg_val = _FALLBACK_TREND

    if my_portfolio_item:
        cid = str(my_portfolio_item.get("userName", my_portfolio_item.get("cid", my_portfolio_item.get("realCID", my_portfolio_item.get("gcid", "")))))
        if my_portfolio_from_rankings and cid:
            week_map[cid] = my_portfolio_item.get("gain")

        my_avatar_url = my_portfolio_item.get("avatarUrl")
        if not my_avatar_url:
            my_avatar_url = _get_user_avatar(username_from_cookie)
        my_avatar_html = _avatar_html(my_avatar_url, username_display)

        my_country_val = my_portfolio_item.get("country")
        if my_country_val is not None:
            mapped = _ETORO_COUNTRY_MAP.get(str(my_country_val))
            if mapped:
                my_country_val = mapped["isoCode"]
            else:
                my_country_val = str(my_country_val)
        else:
            country_id = my_portfolio_item.get("countryId")
            if country_id is not None:
                mapped = _ETORO_COUNTRY_MAP.get(str(country_id))
                if mapped:
                    my_country_val = mapped["isoCode"]
                else:
                    my_country_val = str(country_id)
        if my_country_val is not None:
            my_country_val = str(my_country_val)
            _prefetch_country_data([{"country": my_country_val}])
            my_country_html_val = _country_html(my_country_val)

        my_aum_value = my_portfolio_item.get("aumValue")
        my_aum_tier_desc = my_portfolio_item.get("aumTierDesc")
        if my_aum_tier_desc is not None or my_aum_value is not None:
            my_aum_display = my_aum_tier_desc if my_aum_tier_desc else _safe_aum(my_aum_value)

        my_copiers = my_portfolio_item.get("copiers")
        my_base_line_copiers = my_portfolio_item.get("baseLineCopiers")
        if my_copiers is not None or my_base_line_copiers is not None:
            my_copiers_value = _safe_int(my_copiers)
            my_copiers_change_val = _copiers_change(my_copiers, my_base_line_copiers)

        my_week_gain = week_map.get(cid)
        my_month_gain = month_map.get(cid)
        my_year_gain = year_map.get(cid)

        if my_week_gain is None and username_from_cookie != "My Portfolio":
            my_week_gain = _get_period_gain(username_from_cookie, "1m")
        if my_month_gain is None and username_from_cookie != "My Portfolio":
            my_month_gain = _get_period_gain(username_from_cookie, "3m")
        if my_year_gain is None and username_from_cookie != "My Portfolio":
            my_year_gain = _get_period_gain(username_from_cookie, "1y")

        if my_week_gain is not None or my_month_gain is not None or my_year_gain is not None:
            my_week_gain_html = _safe_gain(my_week_gain)
            my_month_gain_html = _safe_gain(my_month_gain)
            my_year_gain_html = _safe_gain(my_year_gain)

            my_trend_points = _get_trend_data(username_from_cookie)
            if my_trend_points:
                my_trend_svg_val = _trend_svg_from_points(my_trend_points)
            else:
                my_trend_svg_val = _trend_svg_for_gains(my_week_gain, my_month_gain, my_year_gain)

    if not my_portfolio_item or my_portfolio_invalid:
        if not is_authenticated:
            my_portfolio_html_row = _render_login_prompt_row()
        else:
            my_portfolio_html_row = _render_row(
                {
                    "userName": username_from_cookie,
                    "fullName": username_display,
                    "avatarUrl": None,
                    "subType": None,
                    "country": my_portfolio_item.get("country") if my_portfolio_item else None,
                    "copiers": my_portfolio_item.get("copiers") if my_portfolio_item else 32800,
                    "aumValue": my_portfolio_item.get("aumValue") if my_portfolio_item else 14500000.0,
                    "aumTierDesc": my_portfolio_item.get("aumTierDesc") if my_portfolio_item else None,
                    "baseLineCopiers": my_portfolio_item.get("baseLineCopiers") if my_portfolio_item else 31850,
                },
                week_map,
                month_map,
                year_map,
                classes=_MP_CLASSES,
                country_html_override=my_country_html_val,
                aum_override=my_aum_display,
                copiers_value_override=my_copiers_value,
                copiers_change_override=my_copiers_change_val,
                week_gain_html_override=my_week_gain_html,
                month_gain_html_override=my_month_gain_html,
                year_gain_html_override=my_year_gain_html,
                error_message=my_portfolio_error if my_portfolio_invalid else None,
                include_badge=False,
            )
    else:
        my_portfolio_html_row = _render_row(
            my_portfolio_item,
            week_map,
            month_map,
            year_map,
            classes=_MP_CLASSES,
            country_html_override=my_country_html_val,
            aum_override=my_aum_display,
            copiers_value_override=my_copiers_value,
            copiers_change_override=my_copiers_change_val,
            week_gain_html_override=my_week_gain_html,
            month_gain_html_override=my_month_gain_html,
            year_gain_html_override=my_year_gain_html,
            error_message=my_portfolio_error if my_portfolio_invalid else None,
            include_badge=False,
        )

    cache_set(my_portfolio_cache_key, my_portfolio_html_row, ext=".html")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Function - Select Investor</title>
    <meta http-equiv=\"Cache-Control\" content=\"no-cache, no-store, must-revalidate\">
    <meta http-equiv=\"Pragma\" content=\"no-cache\">
    <meta http-equiv=\"Expires\" content=\"0\">
    <style>
        :root {{
            --brand-primary: {_BRAND_PRIMARY};
            --neutral-0: {_NEUTRAL_0};
            --text-primary: {_TEXT_PRIMARY};
            --semantic-positive: {_SEMANTIC_POSITIVE};
            --semantic-warning: {_SEMANTIC_WARNING};
            --text-muted: {_TEXT_MUTED};
            --border-default: {_BORDER_DEFAULT};
            --bg-subtle: {_BG_SUBTLE};
            --text-heading: {_TEXT_HEADING};
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: {FONT_FAMILY};
            background: var(--neutral-0);
            color: var(--text-primary);
            min-height: 100vh;
            margin: 20px auto;
            padding: 0;
            max-width: 1380px;
        }}

        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-subtle); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border-default); }}

        .selection-background-wrapper {{
          position: relative;
          background-color: {_NEUTRAL_0};
        }}

        .selection-foreground {{
          position: relative;
          z-index: 1;
        }}

        .search-container {{
            font-family: {FONT_FAMILY};
            padding: 20px;
            position: relative;
        }}

        .search-input {{
            width: 100%;
            padding: 8px;
            box-sizing: border-box;
            background-color: {_BG_SUBTLE};
            border: 1px solid {_BORDER_DEFAULT};
            color: {_BRAND_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 16px;
            line-height: 24px;
            outline: none;
            caret-color: {_BRAND_PRIMARY};
            caret-shape: block;
            text-transform: uppercase;
        }}

        .search-input:focus {{
            border-color: {_BRAND_PRIMARY};
        }}

        .search-input::placeholder {{
            color: {_TEXT_MUTED};
        }}

        .search-dropdown {{
            position: absolute;
            top: 100%;
            left: 20px;
            right: 20px;
            background-color: var(--brand-primary);
            border: 1px solid {_BORDER_DEFAULT};
            border-top: none;
            max-height: 320px;
            overflow-y: auto;
            z-index: 1000;
            display: none;
        }}

        .search-dropdown.active {{
            display: block;
        }}

        .search-dropdown-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 12px;
            cursor: pointer;
            border-bottom: 1px solid {BORDER_DIVIDER};
            transition: background-color 0.15s ease;
        }}

        .search-dropdown-item:hover, .search-dropdown-item.selected {{
            background-color: rgba(21, 184, 166);
        }}

        .search-dropdown-item:last-child {{
            border-bottom: none;
        }}

        .search-dropdown-avatar {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
            background-color: {_SEMANTIC_POSITIVE};
            display: flex;
            align-items: center;
            justify-content: center;
            color: {_NEUTRAL_0};
            font-weight: bold;
            font-size: 14px;
        }}

        .search-dropdown-avatar img {{
            width: 100%;
            height: 100%;
            border-radius: 50%;
            object-fit: cover;
        }}

        .search-dropdown-details {{
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
        }}

        .search-dropdown-name {{
            font-weight: bold;
            color: #1a1a1a;
            font-size: 14px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .search-dropdown-username {{
            color: #3a3a3a;
            font-size: 12px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .search-dropdown-empty {{
            padding: 16px;
            text-align: center;
            color: #3a3a3a;
            font-size: 14px;
        }}

        .my-portfolio-container {{
            padding: 20px;
        }}

        .selection-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}

        .my-portfolio-row {{
            cursor: pointer;
            text-decoration: none;
            color: inherit;
        }}

        .my-portfolio-investor {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .my-portfolio-avatar {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background-color: {_SEMANTIC_POSITIVE};
            display: flex;
            align-items: center;
            justify-content: center;
            color: {_NEUTRAL_0};
            font-weight: bold;
            font-size: 18px;
            flex-shrink: 0;
        }}

        .my-portfolio-info {{
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 160px;
        }}

        .my-portfolio-name-row {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .my-portfolio-name {{
            font-weight: bold;
            color: {_TEXT_HEADING};
            font-size: 14px;
        }}

        .my-portfolio-username {{
            color: {_TEXT_MUTED};
            font-size: 12px;
        }}

        .my-portfolio-country {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 4px;
            background-color: {_NEUTRAL_SURFACE};
            border: 1px solid {_BORDER_DEFAULT};
            font-size: 12px;
            color: {_TEXT_PRIMARY};
            flex-shrink: 0;
        }}

        .my-portfolio-country-flag {{
            font-size: 14px;
            line-height: 1;
        }}

        .my-portfolio-aum {{
            font-weight: bold;
            color: {_TEXT_PRIMARY};
            font-size: 14px;
            min-width: 60px;
        }}

        .my-portfolio-copiers-value {{
            color: {_TEXT_PRIMARY};
            font-size: 13px;
        }}

        .my-portfolio-copiers-change {{
            font-size: 11px;
            color: {_TEXT_MUTED};
        }}

        .my-portfolio-performance {{
            font-size: 13px;
            min-width: 50px;
        }}

        .my-portfolio-performance-positive {{
            color: {_SEMANTIC_POSITIVE};
        }}

        .my-portfolio-performance-negative {{
            color: {_SEMANTIC_NEGATIVE};
        }}

        .my-portfolio-trend {{
            width: 100px;
            height: 28px;
            flex-shrink: 0;
        }}

        .my-portfolio-login-prompt {{
            cursor: default;
        }}

        .my-portfolio-login-avatar {{
            background-color: {_BG_SUBTLE} !important;
            border: 1.5px dashed {_BORDER_DEFAULT};
        }}

        .my-portfolio-login-name {{
            color: {_TEXT_MUTED};
            font-weight: 600;
        }}

        .my-portfolio-login-subtitle {{
            color: {_TEXT_MUTED};
            font-size: 12px;
            font-style: italic;
        }}

        .my-portfolio-login-btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            margin-top: 10px;
            padding: 7px 16px;
            border-radius: 6px;
            background-color: {_BRAND_PRIMARY};
            color: {_NEUTRAL_0};
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            transition: opacity 0.15s ease;
            letter-spacing: 0.02em;
            align-self: flex-start;
        }}

        .my-portfolio-login-btn:hover {{
            opacity: 0.88;
            color: {_NEUTRAL_0};
        }}

        .selection-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }}

        .selection-title {{
            font-size: 20px;
            font-weight: bold;
            color: {_TEXT_HEADING};
            margin: 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .investor-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            table-layout: fixed;
        }}

        .investor-table col:nth-child(1) {{
            width: 35%;
        }}

        .investor-table col:nth-child(2) {{
            width: 10%;
        }}

        .investor-table col:nth-child(3) {{
            width: 10%;
        }}

        .investor-table col:nth-child(4) {{
            width: 13%;
        }}

        .investor-table col:nth-child(5) {{
            width: 7%;
        }}

        .investor-table col:nth-child(6) {{
            width: 7%;
        }}

        .investor-table col:nth-child(7) {{
            width: 8%;
        }}

        .investor-table col:nth-child(8) {{
            width: 10%;
        }}

        .selection-container {{
            font-family: {FONT_FAMILY};
            padding: 20px;
            color: {_TEXT_PRIMARY};
        }}

        .investor-table thead th {{
            text-align: left;
            padding: 10px 12px;
            color: {_TEXT_MUTED};
            font-weight: normal;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid {BORDER_DIVIDER};
            white-space: nowrap;
        }}

        .investor-table tbody tr {{
            border-bottom: 1px solid {BORDER_DIVIDER};
            transition: background-color 0.15s ease;
            cursor: pointer;
        }}

        .investor-table tbody tr:hover {{
            background-color: {_HOVER_SURFACE};
        }}

        .investor-table tbody td {{
            padding: 14px 12px;
            vertical-align: middle;
            white-space: nowrap;
        }}

        .investor-info {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .investor-avatar {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
            background-color: {_BG_SUBTLE};
        }}

        .investor-details {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .investor-name-row {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .investor-name {{
            font-weight: bold;
            color: {_TEXT_HEADING};
            font-size: 14px;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            line-height: 1.4;
        }}

        .badge-elite-pro {{
            background-color: rgba(64, 224, 208, 0.15);
            color: {_BRAND_PRIMARY};
            border: 1px solid rgba(64, 224, 208, 0.3);
        }}

        .badge-elite {{
            background-color: rgba(64, 224, 208, 0.1);
            color: {_BRAND_PRIMARY};
            border: 1px solid rgba(64, 224, 208, 0.25);
        }}

        .badge-champion {{
            background-color: rgba(251, 191, 36, 0.15);
            color: {_SEMANTIC_WARNING};
            border: 1px solid rgba(251, 191, 36, 0.3);
        }}

        .investor-username {{
            color: {_TEXT_MUTED};
            font-size: 12px;
        }}

        .country-badge {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px 8px;
            border-radius: 4px;
            background-color: {_NEUTRAL_SURFACE};
            border: 1px solid {_BORDER_DEFAULT};
            font-size: 12px;
            color: {_TEXT_PRIMARY};
        }}

        .country-flag {{
            font-size: 14px;
            line-height: 1;
        }}

        .aum-value {{
            font-weight: bold;
            color: {_TEXT_PRIMARY};
            font-size: 14px;
        }}

        .copiers-value {{
            color: {_TEXT_PRIMARY};
            font-size: 13px;
        }}

        .copiers-change {{
            font-size: 11px;
            color: {_TEXT_MUTED};
        }}

        .perf-pill {{
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 13px;
            display: inline-block;
            color: {_NEUTRAL_0};
        }}

        .perf-pill-pos {{
            background-color: {_SEMANTIC_POSITIVE};
        }}

        .perf-pill-neg {{
            background-color: {_SEMANTIC_NEGATIVE};
        }}

        .perf-pill-na {{
            background-color: {_TEXT_MUTED};
        }}

        .my-portfolio-performance {{
            font-size: 13px;
            min-width: 50px;
        }}

        .my-portfolio-performance-positive {{
            background-color: {_SEMANTIC_POSITIVE};
            color: {_NEUTRAL_0};
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
        }}

        .my-portfolio-performance-negative {{
            background-color: {_SEMANTIC_NEGATIVE};
            color: {_NEUTRAL_0};
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
        }}

        .trend-chart {{
            width: 100px;
            height: 28px;
        }}

        .no-results {{
            text-align: center;
            padding: 48px 16px;
            color: {_TEXT_MUTED};
            font-size: 14px;
        }}

        .hidden {{
            display: none !important;
        }}

        .frozen-top {{
            position: sticky;
            top: 0;
            z-index: 10;
            background: var(--neutral-0);
        }}

        .loading-overlay {{
            position: fixed;
            inset: 0;
            background: {_NEUTRAL_0};
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            transition: opacity 0.2s ease;
        }}

        .loading-overlay.hidden {{
            opacity: 0;
            pointer-events: none;
        }}

        .loading-spinner {{
            width: 40px;
            height: 40px;
            border: 3px solid {_BORDER_DEFAULT};
            border-top-color: {_BRAND_PRIMARY};
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}

        .loading-text {{
            margin-top: 12px;
            font-size: 14px;
            color: {_TEXT_MUTED};
            letter-spacing: 0.05em;
        }}

        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="loading-overlay" id="loading-overlay">
        <div class="loading-spinner"></div>
        <div class="loading-text">Loading...</div>
    </div>
    <div class="selection-background-wrapper">
        <div class="selection-foreground">
            <div class="frozen-top">
                <div class="search-container">
                    <input
                        type="text"
                        class="search-input"
                        id="investor-search"
                        placeholder="Search Pro Investors..."
                        autocomplete="off"
                        autofocus
                    >
                    <div class="search-dropdown" id="investor-search-dropdown"></div>
                </div>
                <div class="my-portfolio-container">
                    <table class="investor-table">
                        <colgroup>
                            <col style="width: 35%">
                            <col style="width: 10%">
                            <col style="width: 10%">
                            <col style="width: 13%">
                            <col style="width: 7%">
                            <col style="width: 7%">
                            <col style="width: 8%">
                            <col style="width: 10%">
                        </colgroup>
                        <thead>
                            <tr>
                                <th>My Portfolio</th>
                                <th>Country</th>
                                <th>AUM</th>
                                <th>Copiers</th>
                                <th>1M</th>
                                <th>3M</th>
                                <th>1Y</th>
                                <th>1M Trend</th>
                            </tr>
                        </thead>
                        <tbody id="my-portfolio-table-body">
{my_portfolio_html_row}
                        </tbody>
                    </table>
                </div>
                <div class=\"selection-container\">
                    <div class=\"selection-header\">
                        <h2 class=\"selection-title\">
                            Top Pro Investors Trending This Week
                        </h2>
                    </div>
                    <table class=\"investor-table\">
                        <colgroup>
                            <col style=\"width: 35%\">
                            <col style=\"width: 10%\">
                            <col style=\"width: 10%\">
                            <col style=\"width: 13%\">
                            <col style=\"width: 7%\">
                            <col style=\"width: 7%\">
                            <col style=\"width: 8%\">
                            <col style=\"width: 10%\">
                        </colgroup>
                        <thead>
                            <tr>
                                <th>Pro Investor</th>
                                <th>Country</th>
                                <th>AUM</th>
                                <th>Copiers</th>
                                <th>1M</th>
                                <th>3M</th>
                                <th>1Y</th>
                                <th>1M Trend</th>
                            </tr>
                        </thead>
                    </table>
                </div>
            </div>
            <div class=\"selection-container\">
                <table class=\"investor-table\">
                    <colgroup>
                        <col style=\"width: 35%\">
                        <col style=\"width: 10%\">
                        <col style=\"width: 10%\">
                        <col style=\"width: 13%\">
                        <col style=\"width: 7%\">
                        <col style=\"width: 7%\">
                        <col style=\"width: 8%\">
                        <col style=\"width: 10%\">
                    </colgroup>
                    <tbody id=\"investor-table-body\">
                        {rows_html}
                    </tbody>
                </table>
                <div class=\"no-results hidden\" id=\"no-results\">No investors match your search.</div>
            </div>
        </div>
    </div>
    <script>
        (function() {{
            const searchInput = document.getElementById('investor-search');
            const dropdown = document.getElementById('investor-search-dropdown');
            let debounceTimer = null;
            let selectedIndex = -1;

            function getInitials(name) {{
                if (!name) return '?';
                const parts = name.trim().split(/\s+/);
                return parts.slice(0, 2).map(p => p[0]).join('').toUpperCase();
            }}

            function clearSelection() {{
                const items = dropdown.querySelectorAll('.search-dropdown-item');
                items.forEach(function(el) {{ el.classList.remove('selected'); }});
                selectedIndex = -1;
            }}

            function setSelectedIndex(index) {{
                const items = dropdown.querySelectorAll('.search-dropdown-item');
                if (!items.length) return;
                if (index < 0) index = 0;
                if (index >= items.length) index = items.length - 1;
                clearSelection();
                selectedIndex = index;
                items[selectedIndex].classList.add('selected');
                items[selectedIndex].scrollIntoView({{ block: 'nearest' }});
            }}

            function selectCurrent() {{
                const items = dropdown.querySelectorAll('.search-dropdown-item');
                if (selectedIndex < 0 || selectedIndex >= items.length) return;
                const row = items[selectedIndex];
                const username = row.getAttribute('data-username') || '';
                const fullName = row.getAttribute('data-fullname') || '';
                if (username) {{
                    window.location.href = '/etopi?etoro_username=' + encodeURIComponent(username);
                }}
                dropdown.classList.remove('active');
                searchInput.value = fullName || username;
            }}

            function renderDropdown(results, error) {{
                dropdown.innerHTML = '';
                clearSelection();
                if (error) {{
                    dropdown.innerHTML = '<div class=\"search-dropdown-empty\">' + error + '</div>';
                    dropdown.classList.add('active');
                    return;
                }}
                if (!results.length) {{
                    dropdown.innerHTML = '<div class=\"search-dropdown-empty\">No investors found.</div>';
                    dropdown.classList.add('active');
                    return;
                }}

                results.forEach(function(item) {{
                    const avatarUrl = item.avatarUrl || '';
                    const username = item.username || '';
                    const fullName = item.fullName || '';

                    const row = document.createElement('div');
                    row.className = 'search-dropdown-item';

                    let avatarHtml;
                    if (avatarUrl) {{
                        avatarHtml = '<div class=\"search-dropdown-avatar\"><img src=\"' + avatarUrl + '\" alt=\"avatar\" onerror=\"this.style.display=\\'none\\'\"></div>';
                    }} else {{
                        const initials = getInitials(fullName || username);
                        avatarHtml = '<div class=\"search-dropdown-avatar\" style=\"background-color:{_SEMANTIC_POSITIVE};color:{_NEUTRAL_0};display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:14px;\">' + initials + '</div>';
                    }}

                    const nameDisplay = fullName || username;
                    const nameHtml = '<div class=\"search-dropdown-details\">' +
                        '<div class=\"search-dropdown-name\">' + nameDisplay + '</div>' +
                        (fullName ? '<div class=\"search-dropdown-username\">@' + username + '</div>' : '') +
                        '</div>';

                    row.setAttribute('data-username', username);
                    row.setAttribute('data-fullname', fullName);
                    row.innerHTML = avatarHtml + nameHtml;

                    row.addEventListener('mouseenter', function() {{
                        const items = dropdown.querySelectorAll('.search-dropdown-item');
                        const arr = Array.prototype.slice.call(items);
                        const idx = arr.indexOf(row);
                        if (idx >= 0) setSelectedIndex(idx);
                    }});

                    row.addEventListener('click', function() {{
                        if (username) {{
                            window.location.href = '/etopi?etoro_username=' + encodeURIComponent(username);
                        }}
                        dropdown.classList.remove('active');
                        searchInput.value = fullName || username;
                    }});

                    dropdown.appendChild(row);
                }});

                dropdown.classList.add('active');
            }}

            searchInput.addEventListener('input', function() {{
                const query = this.value.trim();

                clearTimeout(debounceTimer);
                if (!query) {{
                    dropdown.classList.remove('active');
                    return;
                }}

                debounceTimer = setTimeout(function() {{
                    fetch('/port/search_investors?query=' + encodeURIComponent(query))
                        .then(function(res) {{ return res.json(); }})
                        .then(function(data) {{
                            renderDropdown(data.results || [], data.error);
                        }})
                        .catch(function() {{
                            dropdown.classList.remove('active');
                        }});
                }}, 120);
            }});

            searchInput.addEventListener('focus', function() {{
                const query = this.value.trim();
                if (query && dropdown.children.length > 0) {{
                    dropdown.classList.add('active');
                }}
            }});

            searchInput.addEventListener('keydown', function(e) {{
                if (!dropdown.classList.contains('active')) {{
                    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {{
                        const query = searchInput.value.trim();
                        if (query) {{
                            searchInput.dispatchEvent(new Event('input'));
                        }}
                    }}
                    return;
                }}
                if (e.key === 'ArrowDown') {{
                    e.preventDefault();
                    const items = dropdown.querySelectorAll('.search-dropdown-item');
                    if (!items.length) return;
                    const next = selectedIndex + 1;
                    setSelectedIndex(next);
                }} else if (e.key === 'ArrowUp') {{
                    e.preventDefault();
                    const items = dropdown.querySelectorAll('.search-dropdown-item');
                    if (!items.length) return;
                    const prev = selectedIndex - 1;
                    setSelectedIndex(prev);
                }} else if (e.key === 'Enter') {{
                    e.preventDefault();
                    selectCurrent();
                }} else if (e.key === 'Escape') {{
                    dropdown.classList.remove('active');
                }}
            }});

            document.addEventListener('click', function(e) {{
                if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {{
                    dropdown.classList.remove('active');
                }}
            }});

            const tableBody = document.getElementById('investor-table-body');
            const myPortfolioTableBody = document.getElementById('my-portfolio-table-body');

            function handleTableRowClick(e) {{
                const row = e.target.closest('tr');
                if (!row) return;

                const nameCell = row.querySelector('.investor-name, .my-portfolio-name');
                if (!nameCell) return;

                const investorName = nameCell.textContent.trim();
                const usernameCell = row.querySelector('.investor-username, .my-portfolio-username');
                const username = usernameCell ? usernameCell.textContent.trim() : '';

                if (investorName) {{
                    window.location.href = `/etopi?etoro_username=${{encodeURIComponent(username.replace('@', ''))}}`;
                }}
            }}

            if (tableBody) {{
                tableBody.addEventListener('click', handleTableRowClick);
            }}
            if (myPortfolioTableBody) {{
                myPortfolioTableBody.addEventListener('click', handleTableRowClick);
            }}
        }})();
    </script>

    <script>
        (function() {{
            const overlay = document.getElementById('loading-overlay');
            if (!overlay) return;

            let submitted = false;

            function hideOverlay() {{
                if (submitted) return;
                overlay.classList.add('hidden');
            }}

            if (document.readyState === 'complete') {{
                setTimeout(hideOverlay, 400);
            }} else {{
                window.addEventListener('load', function() {{
                    setTimeout(hideOverlay, 400);
                }});
            }}

            window.addEventListener('beforeunload', function() {{
                submitted = true;
            }});
        }})();
    </script>
</body>
</html>
"""

    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        if sys.platform.startswith("linux"):
            end_mem_mb = rss / 1024
        else:
            end_mem_mb = rss / (1024 * 1024)
        if start_mem_mb is not None:
            delta_mb = end_mem_mb - start_mem_mb
            print(f"[selection.py] start_mem={start_mem_mb:.2f} MB, peak_mem={end_mem_mb:.2f} MB, delta={delta_mb:+.2f} MB")
        else:
            print(f"[selection.py] peak_mem={end_mem_mb:.2f} MB")
    except Exception:
        pass
    return html


def cached_portfolio_selection_html() -> str:
    cache_key = ("portfolio_selection",)
    cached = cache_get(cache_key, _ETORO_PI_TTL, ext=".html")
    if cached is not None:
        return cached
    html = get_portfolio_selection_html()
    cache_set(cache_key, html, ext=".html")
    return html
