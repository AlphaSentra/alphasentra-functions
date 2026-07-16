"""
Portfolio Pro Investor selection interface HTML template.
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from Functions.port.cache import get as cache_get, set as cache_set, exists as cache_exists, _ETORO_PI_TTL

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

_ETORO_API_KEY = os.getenv("ETORO_PUBLIC_KEY", "")
_ETORO_USER_KEY = os.getenv("ETORO_PRIVATE_KEY", "")
_RANKINGS_URL = "https://public-api.etoro.com/api/v1/user-info/people/search"
_USER_INFO_URL = "https://public-api.etoro.com/api/v1/user-info/people"
_AVATAR_CACHE: Dict[str, Optional[str]] = {}
_TREND_CACHE: Dict[str, List[float]] = {}


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; alphasentra-etoro-client)",
        "Accept": "application/json",
        "x-api-key": _ETORO_API_KEY,
        "x-user-key": _ETORO_USER_KEY,
        "x-request-id": str(uuid.uuid4()),
    })
    return session


def _get_trend_session() -> requests.Session:
    return _get_session()


def _get_user_avatar(username: str) -> Optional[str]:
    if not username:
        return None
    if username in _AVATAR_CACHE:
        return _AVATAR_CACHE[username]

    session = _get_session()
    try:
        resp = session.get(_USER_INFO_URL, params={"usernames": username}, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            users = data.get("users", [])
            if users:
                avatars = users[0].get("avatars") or []
                for av in avatars:
                    url = av.get("url")
                    if url:
                        _AVATAR_CACHE[username] = url
                        return url
    except requests.RequestException:
        pass
    _AVATAR_CACHE[username] = None
    return None


def _get_trend_data(username: str) -> List[float]:
    if not username:
        return []
    if username in _TREND_CACHE:
        return _TREND_CACHE[username]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; alphasentra-etoro-client)",
        "Accept": "application/json",
        "x-api-key": _ETORO_API_KEY,
        "x-user-key": _ETORO_USER_KEY,
        "x-request-id": str(uuid.uuid4()),
    })
    min_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    max_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://public-api.etoro.com/api/v1/user-info/people/{username}/daily-gain"
    try:
        resp = session.get(
            url,
            params={"minDate": min_date, "maxDate": max_date, "type": "Daily"},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
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
    except requests.RequestException:
        pass
    _TREND_CACHE[username] = []
    return []


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


def _get_rankings(period: str = "CurrMonth", sort: Optional[str] = "-copiersGain", page_size: int = 20) -> Dict[str, Any]:
    session = _get_session()
    params: Dict[str, Any] = {
        "period": period,
        "sort": sort,
        "copiersMin": 10,
    }
    if page_size is not None:
        params["pageSize"] = page_size

    try:
        resp = session.get(_RANKINGS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return {"results": [], "pagination": {}, "error": str(exc)}

    return {
        "results": data.get("items", []),
        "pagination": data.get("pagination", {}),
    }


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


def _avatar_html(avatar_url: Optional[str], name: str) -> str:
    if avatar_url:
        return (
            f"<img class=\"investor-avatar\" src=\"{avatar_url}\" alt=\"avatar\" "
            f"onerror=\"this.style.display='none'\">"
        )
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    return f"<div class=\"investor-avatar\" style=\"background-color:{_SEMANTIC_POSITIVE};color:{_NEUTRAL_0};display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:18px;flex-shrink:0;\">{initials}</div>"


def _country_html(country: Optional[str]) -> str:
    if not country:
        return "<span class=\"country-badge\">N/A</span>"
    flag_map = {
        "US": "&#x1F1FA&#x1F1F8;",
        "GB": "&#x1F1EC&#x1F1E7;",
        "AU": "&#x1F1E6&#x1F1FA;",
        "DE": "&#x1F1E9&#x1F1EA;",
        "FR": "&#x1F1EB&#x1F1F7;",
        "ES": "&#x1F1EA&#x1F1F8;",
        "SE": "&#x1F1F8&#x1F1EA;",
        "NO": "&#x1F1F3&#x1F1F4;",
        "DK": "&#x1F1E9&#x1F1F0;",
        "JP": "&#x1F1EF&#x1F1F5;",
        "IN": "&#x1F1EE&#x1F1F3;",
        "SG": "&#x1F1F8&#x1F1EC;",
        "BR": "&#x1F1E7&#x1F1F7;",
    }
    flag = flag_map.get(country.upper(), "")
    return f"<span class=\"country-badge\"><span class=\"country-flag\">{flag}</span>{country.upper()}</span>"


def _render_row(item: Dict[str, Any], week_map: Dict[str, float], month_map: Dict[str, float], year_map: Dict[str, float]) -> str:
    cid = str(item.get("userName", item.get("cid", item.get("realCID", item.get("gcid", "")))))
    username = item.get("userName", item.get("username", ""))
    full_name = item.get("fullName") or item.get("displayName") or username
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
        country = str(country_id)

    aum_display = aum_tier_desc if aum_tier_desc else _safe_aum(aum_value)

    trend_points = _get_trend_data(username)
    if trend_points:
        trend_svg = _trend_svg_from_points(trend_points)
    else:
        trend_svg = _trend_svg_for_gains(week_gain, month_gain, year_gain)

    search_text = (
        f"{full_name} @{username} {country or ''}".lower()
    )

    return (
        f"<tr data-search=\"{search_text}\">"
        f"<td>"
        f"<div class=\"investor-info\">"
        f"{_avatar_html(avatar_url, full_name)}"
        f"<div class=\"investor-details\">"
        f"<div class=\"investor-name-row\">"
        f"<span class=\"investor-name\">{full_name}</span>"
        f"{_badge_for_subtype(subtype)}"
        f"</div>"
        f"<span class=\"investor-username\">@{username}</span>"
        f"</div>"
        f"</div>"
        f"</td>"
        f"<td>{_country_html(country)}</td>"
        f"<td><span class=\"aum-value\">{_safe_aum(aum_display)}</span></td>"
        f"<td>"
        f"<div class=\"copiers-value\">{_safe_int(copiers)}</div>"
        f"<div class=\"copiers-change\">{_copiers_change(copiers, base_line_copiers)}</div>"
        f"</td>"
        f"<td>{_safe_gain(week_gain)}</td>"
        f"<td>{_safe_gain(month_gain)}</td>"
        f"<td>{_safe_gain(year_gain)}</td>"
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
    if not base_results and base_data.get("error"):
        raise RuntimeError(base_data["error"])

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
        usernames = [str(item.get("userName", "")) for item in merged if item.get("userName")]
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_avatars = {executor.submit(_get_user_avatar, u): u for u in usernames}
            future_trends = {executor.submit(_get_trend_data, u): u for u in usernames}
            for future in as_completed(future_avatars):
                future.result()
            for future in as_completed(future_trends):
                future.result()

    return merged, week_map, month_map, year_map


_FALLBACK_INVESTORS = [
    {"cid": "1", "username": "CompoundValue", "fullName": "Sarah Miller", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "US", "copiers": 32800, "aumValue": 14500000.0, "baseLineCopiers": 31850, "gain": 0.0042},
    {"cid": "2", "username": "GreenMacro_Vance", "fullName": "Helena Vance", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "GB", "copiers": 24100, "aumValue": 12200000.0, "baseLineCopiers": 22900, "gain": 0.0072},
    {"cid": "3", "username": "TechBull_Sanchez", "fullName": "Ruben Sanchez", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "ES", "copiers": 18450, "aumValue": 8400000.0, "baseLineCopiers": 16080, "gain": 0.0284},
    {"cid": "4", "username": "NordicCap_Nielsen", "fullName": "Line Nielsen", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "DK", "copiers": 14200, "aumValue": 7900000.0, "baseLineCopiers": 13020, "gain": 0.0165},
    {"cid": "5", "username": "CryptoQuantum", "fullName": "Yuki Sato", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-champion", "country": "JP", "copiers": 11350, "aumValue": 4100000.0, "baseLineCopiers": 8820, "gain": -0.0432},
    {"cid": "6", "username": "ShenzhenVanguard", "fullName": "Lin Wong", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "SG", "copiers": 10800, "aumValue": 6700000.0, "baseLineCopiers": 9130, "gain": 0.0342},
    {"cid": "7", "username": "AlphaDividends", "fullName": "Maximilian Weber", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "DE", "copiers": 9200, "aumValue": 5800000.0, "baseLineCopiers": 8480, "gain": 0.0115},
    {"cid": "8", "username": "TrendRider_Chloe", "fullName": "Chloe Laurent", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "FR", "copiers": 8700, "aumValue": 6200000.0, "baseLineCopiers": 7820, "gain": 0.0214},
    {"cid": "9", "username": "QuantumEdge", "fullName": "Marcus Chen", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "AU", "copiers": 21500, "aumValue": 9300000.0, "baseLineCopiers": 20150, "gain": 0.0128},
    {"cid": "10", "username": "NordicGrowth", "fullName": "Sofia Andersson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "SE", "copiers": 16800, "aumValue": 7600000.0, "baseLineCopiers": 15360, "gain": 0.0095},
    {"cid": "11", "username": "QuantumAlpha", "fullName": "James Wilson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "GB", "copiers": 28300, "aumValue": 11800000.0, "baseLineCopiers": 27080, "gain": 0.0115},
    {"cid": "12", "username": "EmergingMarkets", "fullName": "Aisha Patel", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "IN", "copiers": 12100, "aumValue": 5400000.0, "baseLineCopiers": 11220, "gain": 0.0188},
    {"cid": "13", "username": "AsiaTech_Kim", "fullName": "David Kim", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "KR", "copiers": 19700, "aumValue": 8900000.0, "baseLineCopiers": 18600, "gain": 0.0205},
    {"cid": "14", "username": "GreenBond_Emma", "fullName": "Emma Thompson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "GB", "copiers": 14500, "aumValue": 6300000.0, "baseLineCopiers": 13650, "gain": 0.0065},
    {"cid": "15", "username": "LatamGrowth", "fullName": "Lucas Silva", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-champion", "country": "BR", "copiers": 9800, "aumValue": 4700000.0, "baseLineCopiers": 8710, "gain": -0.0125},
    {"cid": "16", "username": "EuroValue_Nina", "fullName": "Nina Kowalski", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "DE", "copiers": 15600, "aumValue": 7100000.0, "baseLineCopiers": 14780, "gain": 0.0088},
    {"cid": "17", "username": "DeepSea_Oliver", "fullName": "Oliver Brown", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite-pro", "country": "AU", "copiers": 22400, "aumValue": 9600000.0, "baseLineCopiers": 20910, "gain": 0.0155},
    {"cid": "18", "username": "IndiaRising", "fullName": "Priya Sharma", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "IN", "copiers": 8200, "aumValue": 3900000.0, "baseLineCopiers": 7420, "gain": 0.0235},
    {"cid": "19", "username": "NordicBond_Thomas", "fullName": "Thomas Anderson", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-elite", "country": "NO", "copiers": 13100, "aumValue": 5800000.0, "baseLineCopiers": 12570, "gain": 0.0055},
    {"cid": "20", "username": "JapanNext", "fullName": "Yuki Tanaka", "avatarUrl": "https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850", "subType": "pi-champion", "country": "JP", "copiers": 16900, "aumValue": 6900000.0, "baseLineCopiers": 15540, "gain": -0.0075},
]

_WEEK_MAP = {str(item["cid"]): item["gain"] for item in _FALLBACK_INVESTORS}
_MONTH_MAP = {
    "1": 0.0185, "2": 0.0245, "3": 0.0812, "4": 0.0524, "5": 0.145,
    "6": 0.0955, "7": 0.041, "8": 0.068, "9": 0.039, "10": 0.042,
    "11": 0.054, "12": 0.068, "13": 0.062, "14": 0.029, "15": -0.0125,
    "16": 0.0325, "17": 0.0475, "18": 0.082, "19": 0.021, "20": 0.051,
}
_YEAR_MAP = {
    "1": 0.142, "2": 0.1685, "3": 0.4265, "4": 0.284, "5": 0.892,
    "6": 0.328, "7": 0.194, "8": 0.269, "9": 0.185, "10": 0.213,
    "11": 0.198, "12": 0.241, "13": 0.312, "14": 0.157, "15": 0.453,
    "16": 0.179, "17": 0.224, "18": 0.385, "19": 0.138, "20": 0.276,
}


def get_portfolio_selection_html() -> str:
    cache_key = ("portfolio_selection",)
    cached_html = cache_get(cache_key, _ETORO_PI_TTL, ext=".html")
    if cached_html is not None:
        return cached_html

    try:
        merged, week_map, month_map, year_map = _fetch_rankings()
    except Exception as exc:
        print(f"Failed to fetch eToro rankings: {exc}")
        merged, week_map, month_map, year_map = [], {}, {}, {}

    if not merged:
        merged = _FALLBACK_INVESTORS
        week_map = _WEEK_MAP
        month_map = _MONTH_MAP
        year_map = _YEAR_MAP

    rows_html = "\n".join(_render_row(item, week_map, month_map, year_map) for item in merged)

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

        .my-portfolio-badge {{
            display: inline-flex;
            align-items: center;
            padding: 1px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            line-height: 1.4;
            background-color: rgba(64, 224, 208, 0.15);
            color: {_BRAND_PRIMARY};
            border: 1px solid rgba(64, 224, 208, 0.3);
            flex-shrink: 0;
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
                        <tbody>
                            <tr class="my-portfolio-row">
                                <td>
                                    <div class="my-portfolio-investor">
                                        <div class="my-portfolio-avatar">&#x1F4B0;</div>
                                        <div class="my-portfolio-info">
                                            <div class="my-portfolio-name-row">
                                                <span class="my-portfolio-name">My Portfolio</span>
                                                <span class="my-portfolio-badge">CURRENT</span>
                                            </div>
                                            <span class="my-portfolio-username">@MyPortfolio</span>
                                        </div>
                                    </div>
                                </td>
                                <td>
                                    <span class="my-portfolio-country">
                                        <span class="my-portfolio-country-flag">&#x1F1FA&#x1F1F8;</span>
                                        US
                                    </span>
                                </td>
                                <td><span class="my-portfolio-aum">$14.5M</span></td>
                                <td>
                                    <div>
                                        <div class="my-portfolio-copiers-value">32,800</div>
                                        <div class="my-portfolio-copiers-change">&#x25B2; 3.1% 1M</div>
                                    </div>
                                </td>
                                <td><span class="perf-pill perf-pill-pos">▲ +0.42%</span></td>
                                <td><span class="perf-pill perf-pill-pos">▲ +1.85%</span></td>
                                <td><span class="perf-pill perf-pill-pos">▲ +14.20%</span></td>
                                <td>
                                    <svg class="my-portfolio-trend" viewBox="0 0 100 28" preserveAspectRatio="none">
                                        <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,20 12,18 24,19 36,16 48,15 60,14 72,10 84,8 100,4"/>
                                    </svg>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <div class=\"selection-container\">
                    <div class=\"selection-header\">
                        <h2 class=\"selection-title\">
                            Top 20 Pro Investors Trending This Week
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
            const tableBody = document.getElementById('investor-table-body');
            const noResults = document.getElementById('no-results');
            const rows = Array.from(tableBody.querySelectorAll('tr'));

            function filterRows(query) {{
                const q = query.toLowerCase().trim();
                let visibleCount = 0;

                rows.forEach(function(row) {{
                    const searchText = row.getAttribute('data-search') || '';
                    const cells = row.querySelectorAll('td');
                    let rowText = searchText;
                    cells.forEach(function(cell) {{
                        rowText += ' ' + cell.textContent.toLowerCase();
                    }});

                    if (!q || rowText.includes(q)) {{
                        row.classList.remove('hidden');
                        visibleCount++;
                    }} else {{
                        row.classList.add('hidden');
                    }}
                }});

                if (visibleCount === 0) {{
                    noResults.classList.remove('hidden');
                }} else {{
                    noResults.classList.add('hidden');
                }}
            }}

            searchInput.addEventListener('input', function() {{
                filterRows(this.value);
            }});

            tableBody.addEventListener('click', function(e) {{
                const row = e.target.closest('tr');
                if (!row) return;

                const nameCell = row.querySelector('.investor-name');
                if (!nameCell) return;

                const investorName = nameCell.textContent.trim();
                const usernameCell = row.querySelector('.investor-username');
                const username = usernameCell ? usernameCell.textContent.trim() : '';

                if (investorName) {{
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = '/port';

                    const usernameInput = document.createElement('input');
                    usernameInput.type = 'hidden';
                    usernameInput.name = 'etoro_username';
                    usernameInput.value = username.replace('@', '');
                    form.appendChild(usernameInput);

                    document.body.appendChild(form);
                    form.submit();
                }}
            }});
        }})();
    </script>

    <script>
        (function() {{
            const overlay = document.getElementById('loading-overlay');
            if (!overlay) return;

            function hideOverlay() {{
                overlay.classList.add('hidden');
            }}

            if (document.readyState === 'complete') {{
                setTimeout(hideOverlay, 400);
            }} else {{
                window.addEventListener('load', function() {{
                    setTimeout(hideOverlay, 400);
                }});
            }}
        }})();
    </script>
</body>
</html>
"""

    cache_set(cache_key, html, ext=".html")
    return html
