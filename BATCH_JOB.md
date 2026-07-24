# Batch Job Documentation

## Overview

The batch job (`Functions/batch/job.py`) is a scheduled cache-warming pipeline that runs a sequence of Python scripts to pre-generate and store HTML and data artifacts. It is designed to be deployed as a **Render Cron Job**.

## Scripts

The runner executes three scripts in order. Each script depends on the state left by the previous one.

| Order | Script | Purpose |
|-------|--------|---------|
| 1 | `port_clear_cache.py` | Deletes the `/.cache/` directory to ensure a clean state before warming. |
| 2 | `index_function_cache.py` | Generates the landing-page index HTML and stores it in cache. |
| 3 | `port_selection_cache.py` | Generates portfolio selection HTML, caches the top-investor usernames list, and pre-generates per-investor portfolio reports. |

## How It Works

`job.py` resolves the project root (`_ROOT`) and invokes each script sequentially using `sys.executable` (the same Python interpreter). Each script is given a wall-clock timeout of **3 hours** (`SCRIPT_TIMEOUT_SECONDS = 10800`). After all scripts finish, a summary report is printed showing pass/fail status and duration.

A non-zero exit code is emitted if any script fails or times out.

## Local Execution

```bash
python Functions/batch/job.py
```

## Required Environment Variables

The batch scripts touch MongoDB, eToro auth, and optional AI services. The following variables must be set in the execution environment.

### MongoDB (required for `index_function_cache.py` and `port_selection_cache.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MONGODB_SRV` | `false` | Set to `true` when using a MongoDB SRV connection string. |
| `MONGODB_SRV` | — | Required if `USE_MONGODB_SRV=true`. The full SRV URI (e.g., `mongodb+srv://cluster.mongodb.net`). |
| `MONGODB_HOST` | `localhost` | Hostname when not using SRV. |
| `MONGODB_PORT` | `27017` | Port when not using SRV. |
| `MONGODB_DATABASE` | `alphasentra-core` | Target database name. |
| `MONGODB_USERNAME` | — | Auth username (omit for unauthenticated local clusters). |
| `MONGODB_PASSWORD` | — | Auth password. |
| `MONGODB_AUTH_SOURCE` | `admin` | Authentication database. |

### eToro (required for `port_selection_cache.py`)

| Variable | Description |
|----------|-------------|
| `ETORO_PRIVATE_KEY` | One or more private keys, comma-separated. One key is selected at random per run. |

### AI / Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google GenAI key (only needed if AI commentary features are exercised). |
| `GEMINI_DEFAULT` | `gemini-2.5-flash-lite` | Default model override. |
| `ENCRYPTION_SECRET` | — | Required by `Functions/crypt.py` if encryption utilities are touched during imports. |

## Deploying on Render

### 1. Update `render.yaml`

Add a `cron` service alongside the existing `web` service.

```yaml
services:
  - type: web
    name: ago-functions
    env: python
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn -w 2 -k gevent --worker-connections 25 --max-requests 500 --preload -b 0.0.0.0:$PORT app:app
    healthCheckPath: /

  - type: cron
    name: ago-batch-cache
    env: python
    plan: starter
    schedule: "0 0 * * *"
    buildCommand: pip install -r requirements.txt
    startCommand: python Functions/batch/job.py
    autoDeploy: true
```

### 2. Share Environment Variables with Environment Groups (Recommended)

To avoid duplicating environment variables across the `web` and `cron` services, use **Render Environment Groups**:

1. In the Render dashboard, go to **Environment** → **Environment Groups**.
2. Create a new group (e.g., `ago-functions-env`) and add all shared variables there:
   - `USE_MONGODB_SRV`
   - `MONGODB_SRV` (if applicable)
   - `MONGODB_DATABASE`
   - `MONGODB_USERNAME`
   - `MONGODB_PASSWORD`
   - `MONGODB_AUTH_SOURCE`
   - `ETORO_PRIVATE_KEY`
   - Any other shared secrets
3. Attach the environment group to **both** the `ago-functions` web service and the `ago-batch-cache` cron service.

This ensures both services always use the same values, and you only need to update them in one place.

### 3. Verify Working Directory

Render sets the working directory to the repo root by default. The batch scripts compute the project root dynamically from `__file__`, so no extra configuration is needed.

### 4. Schedule

The default schedule `"0 0 * * *"` runs daily at **00:00 UTC**. Adjust the cron expression in `render.yaml` to change frequency:

- Every 6 hours: `"0 */6 * * *"`
- Twice daily (00:00 and 12:00): `"0 0,12 * * *"`

### 5. Timeout Considerations

Each script has an internal timeout of 3 hours. Render Cron Jobs on the **Starter** plan allow up to **15 minutes** of runtime by default. If the batch job regularly exceeds 15 minutes, upgrade the cron job plan or optimize the underlying scripts.

## Logs

Logs are written to `Functions/log/` with daily rotating filenames (`YYYY-MM-DD.log`). On Render, inspect cron job logs from the dashboard or via the Render CLI:

```bash
render logs -s ago-batch-cache
```

## Failure Handling

- If any script fails or times out, `job.py` exits with code `1`.
- Failed scripts are marked explicitly in the summary report.
- Render will retry failed cron runs on the next scheduled execution.
