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
| `/` | GET | Health check — returns `{"message": "Hello, World!"}` |
