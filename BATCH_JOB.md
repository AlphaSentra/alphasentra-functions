# Batch Jobs Documentation

## Overview

The project uses three batch job runners executed via **GitHub Actions** workflows:

| Runner | Script | Purpose |
|--------|--------|---------|
| `cache_job.py` | Clears and warms portfolio cache | Clears stale cache, generates index HTML, pre-caches portfolio selection and reports |
| `feed_job.py` | Collects eToro feed data | Fetches trending PIs, instruments, and their posts from the eToro public API |
| `logs_rm_duplicated.py` | Deduplicates logs database | Removes duplicate documents from `etoro_unmapped_instruments` collection |

Additionally, `port_user_report_cache.py` is a long-lived worker that continuously pre-caches portfolio reports for active users.

## Runners

### 1. `Functions/batch/cache_job.py`

Clears the cache and warms the function index and portfolio selection pages.

**Scripts executed in order:**

| Order | Script | Purpose |
|-------|--------|---------|
| 1 | `clear_cache.py` | Drops all known cache collections (`portfolio_selection_cache`, `portfolio_report_cache`, `yfinance_cache`, `etoro_cache`, `function_index_cache`) to ensure a clean state. |
| 2 | `index_function_cache.py` | Generates the landing-page index HTML and stores it in cache. |
| 3 | `port_selection_cache.py` | Generates portfolio selection HTML, caches the top-investor usernames list, and pre-generates per-investor portfolio reports. |

**Timeout:** 5 hours per script (`SCRIPT_TIMEOUT_SECONDS = 18000`).

### 2. `Functions/batch/feed_job.py`

Collects eToro feed data (trending PIs, instruments, and posts) and stores it in the feed MongoDB database.

**Scripts executed in order:**

| Order | Script | Purpose |
|-------|--------|---------|
| 1 | `clear_feed.py` | Drops `etoro_trending_instruments` and `etoro_trending_pi` collections; removes `etoro_posts` older than 60 days. |
| 2 | `feed_get_pi.py` | Fetches current-year top-copier Popular Investor rankings and upserts into `etoro_trending_pi`. |
| 3 | `feed_get_instruments.py` | Fetches top 100 instruments by 7-day viewer popularity and trader change, upserts into `etoro_trending_instruments`. |
| 4 | `feed_get_posts_from_pi.py` | Reads `etoro_trending_pi`, fetches each PI's public feed posts (last 30 days), stores in `etoro_posts`. |
| 5 | `feed_get_posts_from_instruments.py` | Reads `etoro_trending_instruments`, fetches each instrument's public market feed posts (last 30 days), stores in `etoro_posts`. |

**Timeout:** 3 hours per script (`SCRIPT_TIMEOUT_SECONDS = 10800`).

### 3. `Functions/batch/logs_rm_duplicated.py`

Removes duplicate documents from the `etoro_unmapped_instruments` collection in the logs database.

**Logic:**
- Groups documents by `(username, instrument_id)`.
- Retains the document with the most recent `detected_at` timestamp.
- When timestamps are equal, retains the document with the highest `_id` (insertion order tie-break).
- Deletes all other documents in the same group in batches of 1000.

**Output:** Logs the number of scanned groups and deleted documents.

### 4. `Functions/batch/port_user_report_cache.py` (Long-lived Worker)

Continuously polls the `users` collection for accounts with a valid `etoro_username` and non-expired `expiry_subscription`, then pre-generates and caches:
- Full portfolio HTML reports (and AI/static variants) in `portfolio_report_cache`.
- Authenticated `/port` selection pages in `portfolio_selection_cache`.

**Polling interval:** 10 seconds by default (`POLL_INTERVAL_SECONDS` env var).

Gracefully handles `SIGINT` and `SIGTERM` for clean shutdown.

## How It Works

Each runner executes its scripts sequentially using `subprocess.run()` with the current Python interpreter. After all scripts finish, a summary report is printed showing pass/fail status and duration. A non-zero exit code is emitted if any script fails or times out.

## Local Execution

```bash
# Cache job
python Functions/batch/cache_job.py

# Feed collection job
python Functions/batch/feed_job.py

# Logs deduplication
python Functions/batch/logs_rm_duplicated.py

# Portfolio report cache worker (long-lived)
python Functions/batch/port_user_report_cache.py
```

## Required Environment Variables

The batch scripts touch multiple MongoDB databases, eToro auth, AI services, and email. The following variables must be set in the execution environment.

### MongoDB Core (required for `cache_job.py` and `port_user_report_cache.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MONGODB_SRV` | `false` | Set to `true` when using a MongoDB SRV connection string. |
| `MONGODB_SRV` | — | Required if `USE_MONGODB_SRV=true`. The full SRV URI. |
| `MONGODB_HOST` | `localhost` | Hostname when not using SRV. |
| `MONGODB_PORT` | `27017` | Port when not using SRV. |
| `MONGODB_DATABASE` | `alphasentra-core` | Core database name. |
| `MONGODB_USERNAME` | — | Auth username (omit for unauthenticated local clusters). |
| `MONGODB_PASSWORD` | — | Auth password. |
| `MONGODB_AUTH_SOURCE` | `admin` | Authentication database. |

### MongoDB Cache (optional for `cache_job.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI_CACHE` | Main MongoDB URI | Separate connection URI for cache database. |
| `MONGODB_DATABASE_CACHE` | `MONGODB_DATABASE` | Cache database name. |

### MongoDB Feed (required for `feed_job.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI_FEED` | Main MongoDB URI | Separate connection URI for feed database. |
| `MONGODB_DATABASE_FEED` | `alphasentra-feed` | Feed database name. |

### MongoDB Logs (required for `logs_rm_duplicated.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI_LOGS` | — | **Required.** MongoDB connection URI for logs database. |
| `MONGODB_DATABASE_LOGS` | `alphasentra-logs` | Logs database name. |

### eToro (required for `feed_job.py`, `port_selection_cache.py`, `port_user_report_cache.py`)

| Variable | Description |
|----------|-------------|
| `ETORO_PRIVATE_KEY` | One or more private keys, comma-separated. One key is selected at random per run. |
| `ETORO_PUBLIC_KEY` | eToro public API key. |

### AI / Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google GenAI key (only needed if AI commentary features are exercised). |
| `GEMINI_DEFAULT` | `gemini-2.5-flash-lite` | Default model override. |
| `ENCRYPTION_SECRET` | — | Required by `Functions/crypt.py` if encryption utilities are touched during imports. |

### Email (optional)

| Variable | Description |
|----------|-------------|
| `BREVO_API_KEY` | Brevo API key for sending email notifications. |
| `BREVO_SENDER_EMAIL` | Sender email address for Brevo notifications. |

## Deploying on GitHub Actions

### Batch Functions Cache Job

Runs daily at 22:00 UTC and on manual dispatch. Clears cache and warms index + portfolio selection pages.

**Workflow file:** `.github/workflows/batch-job.yml`

**Triggers:**
- Schedule: `0 22 * * *` (daily at 22:00 UTC)
- `workflow_dispatch` (manual)

### Batch Portfolio Report Cache Job

Runs every 4 hours, on push to `main`, and on manual dispatch. Pre-generates portfolio reports for active users.

**Workflow file:** `.github/workflows/batch-report-job.yml`

**Triggers:**
- Push to `main`
- Schedule: `0 */4 * * *` (every 4 hours)
- `workflow_dispatch` (manual)

### Batch Feed Collection Job

Runs daily at 03:00 UTC and on manual dispatch. Collects eToro feed data.

**Workflow file:** `.github/workflows/feed-job.yml`

**Triggers:**
- Schedule: `0 3 * * *` (daily at 03:00 UTC)
- `workflow_dispatch` (manual)

### Required GitHub Secrets

All workflows share a common set of secrets configured in the repository settings:

| Secret | Required For |
|--------|-------------|
| `USE_MONGODB_SRV` | All jobs |
| `MONGODB_SRV` | All jobs (when `USE_MONGODB_SRV=true`) |
| `MONGODB_HOST` | All jobs (when `USE_MONGODB_SRV=false`) |
| `MONGODB_PORT` | All jobs (when `USE_MONGODB_SRV=false`) |
| `MONGODB_DATABASE` | All jobs |
| `MONGODB_USERNAME` | All jobs |
| `MONGODB_PASSWORD` | All jobs |
| `MONGODB_AUTH_SOURCE` | All jobs |
| `MONGODB_URI_CACHE` | `batch-job.yml`, `batch-report-job.yml` |
| `MONGODB_DATABASE_CACHE` | `batch-job.yml`, `batch-report-job.yml` |
| `MONGODB_URI_FEED` | `feed-job.yml`, `batch-job.yml`, `batch-report-job.yml` |
| `MONGODB_DATABASE_FEED` | `feed-job.yml`, `batch-job.yml`, `batch-report-job.yml` |
| `MONGODB_URI_LOGS` | `batch-job.yml`, `batch-report-job.yml`, `feed-job.yml` |
| `MONGODB_DATABASE_LOGS` | `batch-job.yml`, `batch-report-job.yml`, `feed-job.yml` |
| `ETORO_PRIVATE_KEY` | `batch-job.yml`, `batch-report-job.yml`, `feed-job.yml` |
| `ETORO_PUBLIC_KEY` | `batch-job.yml`, `batch-report-job.yml`, `feed-job.yml` |
| `GEMINI_API_KEY` | All jobs (optional) |
| `GEMINI_DEFAULT` | All jobs (optional) |
| `GEMINI_FLASH_MODEL` | All jobs (optional) |
| `GEMINI_FLASH_LITE_MODEL` | All jobs (optional) |
| `GEMINI_PRO_MODEL` | All jobs (optional) |
| `ENCRYPTION_SECRET` | All jobs |
| `BREVO_API_KEY` | All jobs (optional) |
| `BREVO_SENDER_EMAIL` | All jobs (optional) |

## Logs

Logs are written to `Functions/log/` with daily rotating filenames (`YYYY-MM-DD.log`). For GitHub Actions workflows, inspect logs from the Actions tab in the GitHub repository.

## Failure Handling

- If any script fails or times out, the runner exits with code `1`.
- Failed scripts are marked explicitly in the summary report.
- GitHub Actions will retry failed runs according to the workflow schedule.
