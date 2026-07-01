import importlib.util
from pathlib import Path
from flask import render_template_string, request, jsonify

base_path = Path(__file__).resolve().parent.parent

theme_path = base_path / "Functions" / "themes" / "theme.py"
theme_spec = importlib.util.spec_from_file_location("theme", theme_path)
theme = importlib.util.module_from_spec(theme_spec)
theme_spec.loader.exec_module(theme)

font_path = base_path / "Functions" / "themes" / "font.py"
font_spec = importlib.util.spec_from_file_location("font", font_path)
font = importlib.util.module_from_spec(font_spec)
font_spec.loader.exec_module(font)

main_path = base_path / "Functions" / "port" / "main.py"
main_spec = importlib.util.spec_from_file_location("main", main_path)
main = importlib.util.module_from_spec(main_spec)
main_spec.loader.exec_module(main)

ROUTES = []

index_template_path = base_path / "Functions" / "index" / "index.html"
with open(index_template_path, 'r') as f:
    _INDEX_HTML = f.read()



from Functions.port.input import handle_portfolio_input


def index():
    return render_template_string(_INDEX_HTML, routes=ROUTES, theme=theme, font=font)


def port():
    return handle_portfolio_input()


def etoro_gain():
    username = request.args.get("username", "").strip()
    granularity = request.args.get("granularity", "monthly").strip().lower()
    if not username:
        return jsonify({"error": "username parameter is required"}), 400
    if granularity not in {"daily", "monthly", "yearly"}:
        return jsonify({"error": "granularity must be daily, monthly, or yearly"}), 400

    try:
        from Functions.etoro import get_public_client_from_env
        client = get_public_client_from_env()
        history = client.get_investor_gain_timeseries(username, granularity=granularity)
        return jsonify({
            "username": history.username,
            "granularity": history.granularity,
            "totalGain": history.total_gain,
            "gains": [
                {"date": point.date.isoformat() if point.date else None, "gain": point.gain}
                for point in history.gains
            ],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def etoro_portfolio():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"error": "username parameter is required"}), 400

    try:
        from Functions.etoro import get_public_client_from_env
        client = get_public_client_from_env()
        portfolio = client.get_investor_portfolio(username)
        return jsonify({
            "username": portfolio.username,
            "positions": [
                {
                    "positionId": pos.position_id,
                    "instrumentId": pos.instrument_id,
                    "symbol": pos.symbol,
                    "displayName": pos.display_name,
                    "openTimestamp": pos.open_timestamp.isoformat() if pos.open_timestamp else None,
                    "openRate": pos.open_rate,
                    "isBuy": pos.is_buy,
                    "leverage": pos.leverage,
                    "takeProfitRate": pos.take_profit_rate,
                    "stopLossRate": pos.stop_loss_rate,
                    "investmentPct": pos.investment_pct,
                    "netProfit": pos.net_profit,
                    "realizedCreditPct": pos.realized_credit_pct,
                    "unrealizedCreditPct": pos.unrealized_credit_pct,
                    "socialTrades": [
                        {
                            "investorId": trade.investor_id,
                            "investorName": trade.investor_name,
                            "leverage": trade.leverage,
                            "isSell": trade.is_sell,
                            "positionId": trade.position_id,
                            "copyCloseTime": trade.copy_close_time.isoformat() if trade.copy_close_time else None,
                        }
                        for trade in pos.social_trades
                    ],
                }
                for pos in portfolio.positions
            ],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def eqs():
    url = "https://app.alphasentra.com/screener?asset_class=EQ"
    html = f"""
    <html>
    <head>
        <title>EQS Screener</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Screener...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html


def wcr():
    url = "https://app.alphasentra.com/screener?asset_class=FX"
    html = f"""
    <html>
    <head>
        <title>WCR Screener</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Screener...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html


def ana():
    url = "https://app.alphasentra.com/search"
    html = f"""
    <html>
    <head>
        <title>Analyse</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Analyse...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html


def cryp():
    url = "https://app.alphasentra.com/screener?asset_class=CR"
    html = f"""
    <html>
    <head>
        <title>CRYP Screener</title>
        <script>
            if (window.top !== window.self) {{
                window.top.location.href = "{url}";
            }} else {{
                window.location.href = "{url}";
            }}
        </script>
    </head>
    <body>
        <p>Redirecting to Screener...</p>
        <noscript>
            <meta http-equiv="refresh" content="0;url={url}">
            <a href="{url}">Click here if not redirected</a>
        </noscript>
    </body>
    </html>
    """
    return html



def register_route(app, path, description, handler, methods=None):
    ROUTES.append((path, description))
    app.route(path, methods=methods)(handler)
