<p align="center">
  <img src="img/banner.png" alt="Banner"/>
</p>

# AlphaSentra Functions App

This is the **Functions App** for the **AlphaSentra Project** — a Flask backend that serves and renders the outputs of various analytical functions. It acts as a unified gateway for portfolio analytics and AI-powered screening tools, with most modules rendering live HTML reports or redirecting to the AlphaSentra web application.

- **PORT (Portfolio & Risk Analytics)** — Connects to eToro accounts and delivers deep portfolio analytics via the eToro API. Runs a full `PortfolioAnalyzer` pipeline that computes performance metrics, generates charts, evaluates risk, analyzes sector/industry exposure, and produces a rendered HTML report. Supports AI commentary generation powered by Google Gemini.
- **EQS (Stocks AI Screener)** — Redirects to the AlphaSentra stock screener (`/screener?asset_class=EQ`) for AI-powered equity screening.
- **WCR (Forex AI Screener)** — Redirects to the AlphaSentra forex screener (`/screener?asset_class=FX`) for AI-powered currency screening.
- **CRYP (Cryptocurrency AI Screener)** — Redirects to the AlphaSentra crypto screener (`/screener?asset_class=CR`) for AI-powered digital asset screening.
- **ANA (Analyse)** — Redirects to the AlphaSentra analysis search page for general asset analysis.

The app uses a **route registry** pattern where each function module is loaded dynamically from the `Functions/` directory via `importlib.util`, allowing modules to remain gitignored while still being discoverable and documented at runtime. Supporting utilities include MongoDB-backed data lookups (ticker resolution, settings), Gemini AI integration with usage tracking, Fernet-based encryption for sensitive strings, and structured file/console logging with unique error codes.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# MongoDB Connection
USE_MONGODB_SRV=true
MONGODB_SRV=mongodb_srv_connection_string
MONGODB_HOST=mongodb_host
MONGODB_PORT=mongodb_port
MONGODB_DATABASE=database_name
MONGODB_USERNAME=mongodb_username
MONGODB_PASSWORD=mongodb_password
MONGODB_AUTH_SOURCE=auth_source

# Gemini AI
GEMINI_API_KEY=gemini_api_key
GEMINI_DEFAULT=default_gemini_model
GEMINI_FLASH_MODEL=flash_model_name
GEMINI_FLASH_LITE_MODEL=flash_lite_model_name
GEMINI_PRO_MODEL=pro_model_name

# Security
ENCRYPTION_SECRET=encryption_secret

# eToro API credentials (required for /etopi)
ETORO_PUBLIC_KEY=public_key
# ETORO_PRIVATE_KEY can be a single key or a comma-separated list.
# When multiple keys are provided, one is chosen at random per request.
ETORO_PRIVATE_KEY=private_key1,private_key2,private_key3

# Optional: Override default market data provider (default: yfinance)
# MARKET_DATA_PROVIDER=yfinance
```

| Variable | Required | Description |
|----------|----------|-------------|
| `USE_MONGODB_SRV` | No | Set to `true` to use MongoDB SRV connection string format |
| `MONGODB_SRV` | Yes* | Full MongoDB SRV connection string (used when `USE_MONGODB_SRV=true`) |
| `MONGODB_HOST` | Yes* | MongoDB server hostname (used when `USE_MONGODB_SRV=false`) |
| `MONGODB_PORT` | Yes* | MongoDB server port (used when `USE_MONGODB_SRV=false`) |
| `MONGODB_DATABASE` | Yes | MongoDB database name |
| `MONGODB_USERNAME` | Yes | MongoDB authentication username |
| `MONGODB_PASSWORD` | Yes | MongoDB authentication password |
| `MONGODB_AUTH_SOURCE` | Yes | MongoDB authentication database (usually `admin`) |
| `GEMINI_API_KEY` | Yes | Google Gemini AI API key for AI-powered analysis |
| `GEMINI_DEFAULT` | No | Default Gemini model to use |
| `GEMINI_FLASH_MODEL` | No | Gemini Flash model identifier |
| `GEMINI_FLASH_LITE_MODEL` | No | Gemini Flash Lite model identifier |
| `GEMINI_PRO_MODEL` | No | Gemini Pro model identifier |
| `ENCRYPTION_SECRET` | Yes | Secret key used for data encryption |
| `ETORO_PUBLIC_KEY` | Yes | eToro public API key |
| `ETORO_PRIVATE_KEY` | Yes | eToro private API key. Accepts a single key or a comma-separated list; one key is selected at random per request |
| `MARKET_DATA_PROVIDER` | No | Market data provider (`yfinance` is default) |

\* Either `MONGODB_SRV` (when `USE_MONGODB_SRV=true`) or `MONGODB_HOST` + `MONGODB_PORT` (when `USE_MONGODB_SRV=false`) is required.

**Note**: The `/etopi` endpoint requires valid eToro API credentials. Without them, the portfolio analysis will fail with a `PortfolioFunctionsError`.

## Running the App

```bash
python app.py
```

The app will start on `http://localhost:8888`.

## Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Function Index — auto-generated list of all registered routes |
| `/etopi` | GET/POST | Portfolio & Risk Analytics (rendered live). **Auth required**, but cached reports bypass auth (TTL 20h). |
| `/port` | GET | Portfolio Investor Selection — Pro Investor ranking table with country resolution. **Auth required**, but cached page bypasses auth (TTL 24h). |
| `/eqs` | GET | Stocks AI Screener (rendered live) |
| `/wcr` | GET | Forex AI Screener (rendered live) |
| `/cryp` | GET | Cryptocurrency AI Screener (rendered live) |

## How It Works

The Flask app uses a **route registry** pattern to manage all available endpoints:

1. `Functions/routes.py` defines a global `ROUTES` list and a `register_route(app, path, description, handler)` function.
2. Each call to `register_route()` appends `(path, description)` to `ROUTES` and applies the standard Flask `app.route(path)(handler)` decorator.
3. The `/` (root) route renders an auto-generated Function Index page by reading `Functions/index/index.html` and passing the `ROUTES` list to it.
4. All function modules live under `Functions/`. They are loaded by filesystem path using `importlib.util`, which allows the `Functions/` directory to remain gitignored.

    This makes it trivial to discover and document endpoints as the project grows.

    ```mermaid
    flowchart TD
        B[Flask App<br>app.py]
        C[Route Registry<br>Functions/routes.py]
        D[ROUTES list]
        E[Function Modules<br>Functions/*/main.py]
        F[HTML string]
        G[index page /]
        B --> C
        C -->|stores| D
        C -->|loads| E
        E -->|returns| F
        F -->|rendered by| B
        D -->|displayed on| G
        G -->|served by| B
    ```

    ## Adding a New Function

To add a new analytical function (e.g., `Functions/myfunction/`):

### Step 1: Create the function module

Create a new directory under `Functions/` (e.g., `Functions/myfunction/`) with a `main.py` that exposes a function returning an HTML string:

```python
# Functions/myfunction/main.py
def generate_myfunction_html() -> str:
    """
    Run the analysis and return the HTML report as a string.
    """
    # ... your analysis logic ...
    return html_string
```

### Step 2: Import and register the route in `app.py`

Import your function's handler in `app.py` and register it using `register_route()`:

```python
from flask import Flask
from Functions.routes import index, port, register_route

app = Flask(__name__)

register_route(app, '/', 'Function Index', index)
register_route(app, '/etopi', 'Portfolio & Risk Analytics', port)
register_route(app, '/myfunction', 'My analysis report', myfunction_handler)
```

Where `myfunction_handler` is a function defined in `app.py` that imports and calls your module:

```python
def myfunction_handler():
    from Functions.myfunction.main import generate_myfunction_html
    return generate_myfunction_html()
```

### Step 3: Visit `/` to confirm

Start the app and go to `http://localhost:8888/` to see your new route listed in the Function Index.

## Adding an API Route to an Existing Function

If you want to add a non-HTML endpoint (e.g., a JSON API) to an existing function, use the same `register_route()` function in `app.py`:

```python
def portfolio_metrics():
    from Functions.port.main import get_metrics_json
    return get_metrics_json()

register_route(app, '/etopi/api/metrics', 'Portfolio metrics as JSON', portfolio_metrics)
```

## Notes

- `ROUTES` is a plain Python list populated at import time, so every route registered in `app.py` is automatically reflected on the Function Index.
- No `@register_route` decorator syntax is used — all routes are explicitly registered via the function call.
- The `Functions/` directory is gitignored; it is loaded at runtime from the filesystem using `importlib.util`, so there is no need to add function directories to `sys.path` manually.

## Deployment

### Gunicorn (Production)

A `Procfile` is included for running the app with Gunicorn in production:

```
web: gunicorn -w 2 -k gevent --worker-connections 25 --max-requests 500 --preload -b 0.0.0.0:$PORT app:app
```

This starts the app using the **gevent** worker class with 2 workers and 25 concurrent connections per worker.

### Render.com

A `render.yaml` configuration is included for deploying to [Render.com](https://render.com):

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

#### Environment Variables

Set all required environment variables in the Render dashboard. To share variables between the `web` and `cron` services, use **Render Environment Groups**:

1. In the Render dashboard, go to **Environment** → **Environment Groups**.
2. Create an environment group and add all shared variables (MongoDB, eToro, etc.).
3. Attach the environment group to both the `ago-functions` web service and the `ago-batch-cache` cron service.

This avoids duplicating secrets and keeps them in sync across services.

Key production dependencies:
- `gunicorn` — WSGI HTTP server
- `gevent` — async worker class for Gunicorn
