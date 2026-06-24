# AlphaSentra Functions App

This is the **Functions App** for the **AlphaSentra Project** — a Flask backend that serves and renders the outputs of various analytical functions.

- **PORT (Portfolio Report)** — Currently the primary function, focused on connecting eToro users and delivering portfolio analytics.
- Additional investment analytics functions will be added over time as the project evolves.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the App

```bash
python app.py
```

The app will start on `http://localhost:8888`.

## Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Function Index — auto-generated list of all registered routes |
| `/port` | GET | Portfolio Function (rendered live) |

## How It Works

The Flask app uses a **route registry** pattern to manage all available endpoints:

1. `Functions/routes.py` defines a global `ROUTES` list and a `register_route(app, path, description, handler)` function.
2. Each call to `register_route()` appends `(path, description)` to `ROUTES` and applies the standard Flask `app.route(path)(handler)` decorator.
3. The `/` (root) route renders an auto-generated Function Index page by reading `Functions/index/index.html` and passing the `ROUTES` list to it.
4. All function modules live under `Functions/`. They are loaded by filesystem path using `importlib.util`, which allows the `Functions/` directory to remain gitignored.

This makes it trivial to discover and document endpoints as the project grows.

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
from Functions.routes import index, portfolio, register_route

app = Flask(__name__)

register_route(app, '/', 'Function Index', index)
register_route(app, '/port', 'Portfolio Function', portfolio)
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

register_route(app, '/port/api/metrics', 'Portfolio metrics as JSON', portfolio_metrics)
```

## Notes

- `ROUTES` is a plain Python list populated at import time, so every route registered in `app.py` is automatically reflected on the Function Index.
- No `@register_route` decorator syntax is used — all routes are explicitly registered via the function call.
- The `Functions/` directory is gitignored; it is loaded at runtime from the filesystem using `importlib.util`, so there is no need to add function directories to `sys.path` manually.
