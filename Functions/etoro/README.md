# eToro Public API Reference

This document describes every eToro public API endpoint used by the AlphaSentra Functions app, how they are called from the codebase, and the authentication requirements.

## Base URL

```
https://public-api.etoro.com/api/v1
https://www.etoro.com/sapi
```

The app talks to two distinct base URLs:
- `https://public-api.etoro.com/api/v1/...` — user-info and market-data endpoints
- `https://www.etoro.com/sapi/...` — trade history endpoint

## Authentication

All requests require two custom headers:

| Header | Value | Source |
|--------|-------|--------|
| `x-api-key` | eToro public API key | `ETORO_PUBLIC_KEY` env var |
| `x-user-key` | eToro private/user key | `ETORO_PRIVATE_KEY` env var |
| `User-Agent` | `Mozilla/5.0 (compatible; alphasentra-etoro-client)` | Hardcoded |
| `Accept` | `application/json` | Hardcoded |
| `x-request-id` | UUID v4 | Generated per request |

Session creation is handled centrally in `Functions/etoro/auth.py:public_api_session()`.

### Environment Variables

```env
ETORO_PUBLIC_KEY=<public_key>
# Provide a single key or a comma-separated list. When multiple keys are given,
# one is chosen at random for each request to distribute load.
ETORO_PRIVATE_KEY=<private_key1>,<private_key2>,<private_key3>
```

Client instantiation: `Functions/etoro/client.py:get_public_client_from_env()`

---

## Endpoints Used

### 1. Resolve username → CID

```
GET https://public-api.etoro.com/api/v1/user-info/people?usernames={username}
```

**Client method:** `ETPublicClient._resolve_cid_from_username()` in `client.py:464`

**Purpose:** Resolve an eToro username to a numeric customer ID (CID).

**Query params:**

| Param | Description |
|-------|-------------|
| `usernames` | eToro username (required) |

**Success response (200):**
```json
{
  "users": [
    {
      "username": "someuser",
      "gcid": 12345,
      "realCID": 12345,
      "demoCID": null,
      "avatars": [...],
      "country": "US",
      "countryId": 219,
      ...
    }
  ]
}
```

**Used by:**
- `PortfolioAnalyzer._load_etoro_portfolio_path()` → `client.resolve_cid()`
- `selection.py` does not call this directly; it uses `country` and `countryId` from the rankings/search endpoint instead.

---

### 2. Investor rankings / search

```
GET https://public-api.etoro.com/api/v1/user-info/people/search
```

**Client method:** Not wrapped in `ETPublicClient`; called directly from `selection.py:_get_rankings()`.

**Purpose:** Fetch the Top Pro Investor rankings used by the `/port` selection page.

**Query params:**

| Param | Description |
|-------|-------------|
| `period` | `OneMonthAgo`, `ThreeMonthsAgo`, `OneYearAgo`, `CurrMonth` |
| `sort` | `-copiersGain` (descending copier gain) |
| `copiersMin` | Minimum copiers filter (e.g. `10`) |
| `pageSize` | Number of results per page (e.g. `20`) |

**Request headers:**
Same as auth section above.

**Success response (200):**
```json
{
  "items": [
    {
      "userName": "someuser",
      "cid": 12345,
      "realCID": 12345,
      "gcid": 12345,
      "fullName": "Display Name",
      "avatarUrl": "https://...",
      "subType": "pi-elite-pro",
      "country": "US",
      "countryId": 219,
      "copiers": 32800,
      "aumValue": 14500000.0,
      "aumTierDesc": "$14.5M",
      "baseLineCopiers": 31850,
      "gain": 0.0042,
      ...
    }
  ],
  "pagination": { ... }
}
```

**Fields used by `selection.py`:**
- `userName` / `cid` / `realCID` / `gcid` → investor identity
- `fullName` / `displayName` → display name
- `avatarUrl` → profile image
- `subType` → badge classification (`pi-elite-pro`, `pi-elite`, `pi-champion`, `pi-certified`, `pi-rising-star`)
- `country` → ISO alpha-2 code
- `countryId` → eToro internal numeric country ID (mapped via `Functions/etoro/countries.csv`)
- `copiers` → current copier count
- `aumValue` / `aumTierDesc` → assets under management
- `baseLineCopiers` → previous period copier baseline
- `gain` → performance gain for the requested period

---

### 3. User info lookup by username

```
GET https://public-api.etoro.com/api/v1/user-info/people?usernames={username}
```

**Client method:** Not directly wrapped; the pattern is the same as endpoint #1 above.

**Purpose:** Resolve avatar URL for a given username when `avatarUrl` is not already present in rankings data.

**Called from:** `selection.py:_get_user_avatar()` → `_USER_INFO_URL`

**Query params:**

| Param | Description |
|-------|-------------|
| `usernames` | eToro username |

**Response:** Same shape as endpoint #1.

---

### 4. Daily gain time-series

```
GET https://public-api.etoro.com/api/v1/user-info/people/{username}/daily-gain
```

**Client method:** `ETPublicClient.get_investor_gain_timeseries()` in `client.py:104`

**Purpose:** Fetch historical daily gain data for an investor to render the sparkline trend chart.

**Query params:**

| Param | Description |
|-------|-------------|
| `type` | `Daily` or `Period` |
| `minDate` | Inclusive start date (`YYYY-MM-DD`) |
| `maxDate` | Inclusive end date (`YYYY-MM-DD`) |

**Success response — `type=Daily` (list):**
```json
[
  {"timestamp": "2024-01-15", "gain": 0.0012},
  {"timestamp": "2024-01-16", "gain": -0.0008},
  ...
]
```

**Success response — `type=Period` (dict):**
```json
{
  "dailyExample": [...]
}
```

**Called from:**
- `client.py:get_investor_gain_timeseries()` — used by `PortfolioAnalyzer._load_etoro_gain_timeseries()` in `engine/analyzer.py:289`
- `selection.py:_get_trend_data()` — 30-day daily gain for sparkline rendering

---

### 5. Live portfolio positions

```
GET https://public-api.etoro.com/api/v1/user-info/people/{username}/portfolio/live
```

**Client method:** `ETPublicClient.get_investor_portfolio()` in `client.py:192`

**Purpose:** Fetch current open portfolio positions for a Popular Investor, resolve instrument symbols, and build an enriched portfolio representation.

**Success response (200):**
```json
{
  "positions": [
    {
      "positionId": "12345",
      "instrumentId": "1010001",
      "openRate": 175.43,
      "isBuy": true,
      "leverage": 1.0,
      "netProfit": 1234.56,
      "openTimestamp": "2024-01-15T10:30:00Z",
      "takeProfitRate": 200.0,
      "stopLossRate": 150.0,
      "investmentPct": 25.0
    }
  ]
}
```

**Post-processing:**
- Instrument IDs are resolved to canonical tickers via `resolve_instrument_metadata()` → eToro search API
- Symbol mapping is cross-checked against the MongoDB `tickers` collection (`ticker_etoro` → `ticker`)
- Positions are aggregated by symbol; weights are computed as `abs(investmentPct)` and summed
- A residual `USD=X` cash position is added for any unallocated remainder

**Called from:** `engine/analyzer.py:_load_etoro_portfolio_path()`

---

### 6. User lookup by CID list

```
GET https://public-api.etoro.com/api/v1/user-info/people?cidList={cid1},{cid2},...
```

**Client method:** `ETPublicClient.get_users_by_cid()` in `client.py:549`

**Purpose:** Resolve multiple eToro customer IDs to usernames and account types.

**Query params:**

| Param | Description |
|-------|-------------|
| `cidList` | Comma-separated list of customer IDs |

**Success response (200):**
```json
{
  "users": [
    {
      "username": "someuser",
      "gcid": 12345,
      "realCID": 12345,
      "demoCID": null
    }
  ]
}
```

**Returned model:** `EToroUserLookupResult` — maps each requested CID string to an `EToroUser` dataclass.

---

### 7. Market data search (instrument metadata)

```
GET https://public-api.etoro.com/api/v1/market-data/search?instrumentId={id}
```

**Client method:** `ETPublicClient.resolve_instrument_metadata()` in `client.py:508`, internally calls `_fetch_instrument_metadata()`.

**Purpose:** Resolve an eToro `instrumentId` to its canonical symbol and display name.

**Query params:**

| Param | Description |
|-------|-------------|
| `instrumentId` | eToro internal instrument ID |

**Success response (200):**
```json
{
  "items": [
    {
      "internalSymbolFull": "AAPL",
      "internalSymbol": "AAPL",
      "symbol": "AAPL",
      "displayname": "Apple Inc.",
      "displayName": "Apple Inc.",
      "instrumentDisplayName": "Apple Inc.",
      "name": "Apple Inc.",
      "instrumentName": "Apple Inc.",
      "title": "Apple Inc."
    }
  ]
}
```

**Field fallback chain for symbol:**
`internalSymbolFull` → `internalSymbol` → `symbol`

**Field fallback chain for name:**
`internalInstrumentDisplayName` → `displayname` → `displayName` → `instrumentDisplayName` → `name` → `instrumentName` → `title`

**Caching:** Results are persisted to `.etoro_instrument_cache.json` at the project root with a 24-hour TTL.

**Called from:**
- `client.py:get_investor_portfolio()` — to resolve live portfolio instruments
- `Functions/data/loader.py:load_transactions_from_etoro()` — to resolve trade history instruments

**DB Fallback:** When the live search API returns no data for an instrument, `resolve_instrument_metadata()` falls back to the `etoro_instruments` MongoDB collection via `Functions/db/repositories.py:lookup_etoro_instruments_from_db()`. This provides a secondary resolution path for instruments not found in the eToro search API.

---

### 8. Trade history (credit/flat)

```
GET https://www.etoro.com/sapi/trade-data-real/history/public/credit/flat
```

**Client method:** `ETPublicClient.get_trade_history()` in `client.py:388`

**Purpose:** Fetch the full flat trade/credit history for a user, going back 10 years by default.

**Query params:**

| Param | Description |
|-------|-------------|
| `cid` | Customer ID (numeric string) |
| `startTime` | ISO 8601 UTC timestamp, auto-set to 10 years ago |
| `pageNumber` | 1-based page number |
| `itemsPerPage` | Records per page (default `9999999`) |

**Success response (200):**
```json
{
  "PublicHistoryPositions": [
    {
      "OpenDate": "2023-06-15T14:30:00Z",
      "Exit Date": "2023-06-20T09:15:00Z",
      "Ticker": "AAPL",
      "Name": "Apple Inc.",
      "Side": "buy",
      "EntryPrice": 175.5,
      "ExitPrice": 180.2,
      "netProfit": 482.5,
      "instrumentId": "1010001",
      "leverage": 1.0,
      ...
    }
  ],
  "pageNumber": 1,
  "itemsPerPage": 20,
  "totalPages": 1
}
```

**Called from:** `Functions/data/loader.py:load_transactions_from_etoro()`

**Data mapping:** Each raw item becomes an `EToroTradeRecord`, then a DataFrame row with columns:
- `Date` (Exit Date)
- `Ticker` (resolved via instrument metadata)
- `Name` (resolved via instrument metadata)
- `Side` (buy/sell)
- `EntryPrice`
- `ExitPrice`
- `PnL`

---

## Data Models

Defined in `Functions/etoro/models.py`:

| Model | Description |
|-------|-------------|
| `EToroPortfolioPosition` | Single open position: `position_id`, `instrument_id`, `symbol`, `open_rate`, `is_buy`, `leverage`, `net_profit`, ... |
| `EToroAggregatedPosition` | Aggregated position by symbol: `symbol`, `weight`, `trade_direction`, `average_entry_price`, `position_count` |
| `EToroInvestorPortfolio` | Full portfolio for a user: `username`, `positions`, `aggregated_positions` |
| `EToroGainPoint` | Single gain data point: `date`, `gain` (decimal fraction) |
| `EToroGainHistory` | Gain time-series: `username`, `granularity`, `total_gain`, `gains` |
| `EToroTradeRecord` | Wrapper around raw trade history JSON dict |
| `EToroTradeHistory` | Full trade history: `cid`, `records`, pagination info |
| `EToroUser` | Resolved user: `username`, `gcid`, `real_cid`, `demo_cid` |
| `EToroUserLookupResult` | Batch CID resolution: `by_cid` dict + `requested` list |

---

## Caching

All eToro client responses are cached using `Functions/port/cache.py` with key prefixes:

| Cache Key Prefix | TTL | Used For |
|------------------|-----|----------|
| `("gains", username, ...)` | `_ETORO_TTL` | Daily gain time-series |
| `("portfolio", username)` | `_ETORO_TTL` | Live portfolio positions |
| `("history", username, cid, page, per_page)` | `_ETORO_TTL` | Trade history |
| `("cid", username)` | `_ETORO_TTL` | Username → CID resolution |
| Instrument metadata | 24h on disk | `data/.etoro_instrument_cache.json` |

Instrument metadata cache is separate from the pickled API cache and uses a JSON file with a `_ts` timestamp field per entry.

---

## Error Handling

All public client methods raise `EToroClientError` on failure. Callers typically catch this and fall back to:
- Empty portfolio / trade history DataFrames
- Hardcoded fallback investor data in `selection.py`
- Local price-derived returns in `engine/analyzer.py`

Network errors, non-2xx status codes, and JSON parsing failures are all wrapped in `EToroClientError` with descriptive messages.

## Unmapped Instruments Logging

When the eToro portfolio API returns positions with instrument IDs that cannot be resolved to canonical tickers, the system records these in the `etoro_unmapped_instruments` collection in the logs MongoDB database.

### `_record_unmapped_instruments()`

`Functions/etoro/client.py:_record_unmapped_instruments()` writes a document for each unresolved instrument containing:

| Field | Description |
|-------|-------------|
| `username` | eToro username |
| `instrument_id` | Unresolved eToro instrument ID |
| `symbol_full` | Any symbol available from the eToro symbol map |
| `raw_symbol` | Raw symbol from the API response |
| `display_name` | Display name from the API response |
| `open_rate` | Open rate from the API response |
| `investment_pct` | Investment percentage from the API response |
| `position_id` | Position ID from the API response |
| `is_buy` | Trade direction from the API response |
| `leverage` | Leverage from the API response |
| `detected_at` | UTC timestamp when the instrument was detected as unmapped |

### Stale Cache Refusal

If a cached portfolio report contains unmapped instruments (`unmapped_instrument_ids` is non-empty), the system refuses to serve the stale cache and forces a fresh API fetch instead. This prevents serving incomplete portfolio snapshots.

**Code:** `client.py:get_investor_portfolio()` — when `live_portfolio_api_failed` and `stale.unmapped_instrument_ids` is truthy, the stale cache is bypassed and the exception is re-raised.

### Deduplication

Run `Functions/batch/logs_rm_duplicated.py` to deduplicate the `etoro_unmapped_instruments` collection. The script retains the most recent document per `(username, instrument_id)` group and deletes all others.

### Required Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI_LOGS` | — | **Required.** MongoDB connection URI for the logs database. |
| `MONGODB_DATABASE_LOGS` | `alphasentra-logs` | Logs database name. |

---

## Related Files

| File | Role |
|------|------|
| `Functions/etoro/client.py` | Main `ETPublicClient` implementation |
| `Functions/etoro/auth.py` | Session factory with API key headers |
| `Functions/etoro/models.py` | Data classes for all eToro response types |
| `Functions/etoro/countries.csv` | eToro `countryId` → ISO alpha-2 mapping |
| `Functions/port/selection.py` | `/port` endpoint — rankings + country resolution |
| `Functions/port/engine/analyzer.py` | Portfolio analysis orchestration |
| `Functions/data/loader.py` | Trade history loader |
| `Functions/port/cache.py` | Pickled response cache with TTL |
