"""
Portfolio input handler - form display and request processing.
"""

from flask import request
from Functions.themes import (
    _TEXT_PRIMARY, _TEXT_HEADING, _BRAND_PRIMARY, _HOVER_SURFACE, _BORDER_DEFAULT,
    _BG_SUBTLE, _NEUTRAL_0, font as _font_module
)

FONT_FAMILY = _font_module.FONT_PRIMARY

PORTFOLIO_FORM_HTML = f"""<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Function - input</title>
    <style>
        body {{
            font-family: {FONT_FAMILY};
            background-color: {_BG_SUBTLE};
            color: {_TEXT_PRIMARY};
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
        }}
        label {{
            color: {_TEXT_HEADING};
            font-family: {FONT_FAMILY};
        }}
        input[type="text"] {{
            width: 100%;
            padding: 10px;
            margin: 10px 0;
            box-sizing: border-box;
            background-color: {_HOVER_SURFACE};
            border: 1px solid {_BORDER_DEFAULT};
            color: {_TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            border-radius: 4px;
        }}
        button {{
            padding: 10px 20px;
            background-color: {_BRAND_PRIMARY};
            color: {_NEUTRAL_0};
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-family: {FONT_FAMILY};
            font-weight: bold;
        }}
        button:hover {{
            background-color: {_HOVER_SURFACE};
            color: {_BRAND_PRIMARY};
        }}
    </style>
</head>
<body>
    <form method="POST">
        <label for="etoro_username">eToro Username:</label>
        <input type="text" id="etoro_username" name="etoro_username" required autofocus>
        <button type="submit">Generate Report</button>
    </form>
</body>
</html>
"""



def handle_portfolio_input():
    etoro_username = ""
    if request.method == "POST":
        etoro_username = request.form.get("etoro_username", "").strip()
    elif request.args.get("etoro_username"):
        etoro_username = request.args.get("etoro_username", "").strip()

    if etoro_username:
        from Functions.port.main import generate_portfolio_html
        return generate_portfolio_html(etoro_username=etoro_username)
    return PORTFOLIO_FORM_HTML
