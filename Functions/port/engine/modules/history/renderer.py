"""
HTML report generation and table utilities.
"""

import pandas as pd
import re
from jinja2 import Template


def _safe_to_float(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def minify_css(css_content: str) -> str:
    """Minify CSS content to reduce file size."""
    # Remove CSS comments
    css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)
    # Remove whitespace around structural characters
    css_content = re.sub(r'\s*([{}:;,])\s*', r'\1', css_content)
    # Remove trailing semicolons in rule blocks
    css_content = re.sub(r';}', '}', css_content)
    # Collapse multiple whitespace to single space
    css_content = re.sub(r'\s+', ' ', css_content)
    return css_content.strip()

def minify_js(js_content: str) -> str:
    """Minify JavaScript content to reduce file size."""
    # Remove single-line comments (but not URLs like http://)
    js_content = re.sub(r'(?<!:)//.*$', '', js_content, flags=re.MULTILINE)
    # Remove multi-line comments
    js_content = re.sub(r'/\*.*?\*/', '', js_content, flags=re.DOTALL)
    # Remove whitespace around operators and punctuation
    js_content = re.sub(r'\s*([{}();,+\-*/=<>&|!?:])\s*', r'\1', js_content)
    # Remove unnecessary semicolons (at end of statement before another statement)
    js_content = re.sub(r';(\s*[}\)\]])', r'\1', js_content)
    # Collapse multiple whitespace to single space (but preserve in strings)
    js_content = re.sub(r'\s+', ' ', js_content)
    return js_content.strip()

def minify_html(html_content: str) -> str:
    """
    Minify HTML content to reduce file size without external dependencies.
    Removes comments, collapses whitespace, and optimizes tags including CSS and JavaScript.
    """
    # Remove HTML comments (but not conditional comments like <!--[if IE]>)
    html_content = re.sub(r'<!--(?!\[|!)[^\[]*?-->', '', html_content, flags=re.DOTALL)
    
    # Split by tags that preserve content structure
    parts = re.split(
        r'(<pre\b[^>]*>.*?</pre>|<code\b[^>]*>.*?</code>|<style\b[^>]*>.*?</style>|<textarea\b[^>]*>.*?</textarea>|<script\b[^>]*>.*?</script>)',
        html_content, flags=re.DOTALL | re.IGNORECASE
    )
    
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # Odd indices are content within preserving tags
            # Check if it's a <style> tag and minify its CSS content
            if part.lower().startswith('<style'):
                css_match = re.search(r'<style[^>]*>(.*?)</style>', part, re.DOTALL | re.IGNORECASE)
                if css_match:
                    css_content = css_match.group(1)
                    minified_css = minify_css(css_content)
                    part = re.sub(r'(<style[^>]*>).*?(</style>)', 
                                  lambda m: m.group(1) + minified_css + m.group(2), 
                                  part, flags=re.DOTALL | re.IGNORECASE)
            # Check if it's a <script> tag and minify its JavaScript content
            elif part.lower().startswith('<script'):
                script_match = re.search(r'<script[^>]*>(.*?)</script>', part, re.DOTALL | re.IGNORECASE)
                if script_match:
                    js_content = script_match.group(1)
                    # Only minify if not a type we should preserve (e.g., not application/json or other non-JS)
                    type_attr = re.search(r'type\s*=\s*["\']([^"\']+)["\']', part, re.IGNORECASE)
                    if not type_attr or 'javascript' in type_attr.group(1).lower() or 'text/javascript' in type_attr.group(1).lower():
                        minified_js = minify_js(js_content)
                        part = re.sub(r'(<script[^>]*>).*?(</script>)',
                                      lambda m: m.group(1) + minified_js + m.group(2),
                                      part, flags=re.DOTALL | re.IGNORECASE)
            result.append(part)
        else:
            part = re.sub(r'>\s+<', '><', part)
            part = part.strip()
            part = re.sub(r'(\s)+', r'\1', part)
            result.append(part)
    
    return ''.join(result).strip()


def generate_trades_table(transactions_df, sector_industry_df=None, price_data=None):
    """
    Generates an HTML table of all trades ordered by date descending (most recent first).

    Args:
        transactions_df (pd.DataFrame): DataFrame containing transaction data with columns:
                                       'Date', 'Ticker', 'Side', 'EntryPrice', 'ExitPrice', 'PnL'.
        sector_industry_df (pd.DataFrame, optional): DataFrame with 'name' for each ticker.
        price_data (pd.DataFrame, optional): DataFrame with latest prices for each ticker.

    Returns:
        str: HTML string for the trades table.
    """
    if transactions_df.empty:
        return "<p>No trades available.</p>"

    trades_df = transactions_df.copy()
    trades_df = trades_df.dropna(subset=["Date", "Ticker", "Side", "EntryPrice", "ExitPrice", "PnL"])
    if trades_df.empty:
        return "<p>No trades available.</p>"
    trades_df = trades_df.sort_values(by="Date", ascending=False)

    name_map = {}
    if sector_industry_df is not None and not sector_industry_df.empty:
        name_map = sector_industry_df['name'].to_dict()

    table_html = """
<div id="trades-table-wrapper">
    <table id="trades-table">
        <thead>
            <tr class="trades-header-row">
                <th>Date</th>
                <th>Ticker</th>
                <th>Name</th>
                <th>Side</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>PnL</th>
            </tr>
        </thead>
        <tbody>
    """

    for orig_idx, row in trades_df.iterrows():
        side = row["Side"]
        side_class = "trades-side-buy" if side == "BUY" else "trades-side-sell"
        date_val = row["Date"]
        if pd.isna(date_val):
            date_str = "-"
        elif hasattr(date_val, 'strftime'):
            date_str = date_val.strftime("%Y-%m-%d")
        else:
            date_str = str(date_val)[:10]
        ticker = row["Ticker"]
        name = row.get("Name") or name_map.get(ticker, ticker)

        entry_price = _safe_to_float(row.get("EntryPrice"))
        exit_price = _safe_to_float(row.get("ExitPrice"))
        pnl_value = _safe_to_float(row.get("PnL"))

        if pnl_value:
            pnl_class = "pnl-positive" if pnl_value > 0 else "pnl-negative" if pnl_value < 0 else "pnl-neutral"
            pnl_str = f'<span class="{pnl_class}">{pnl_value:+.2f}%</span>'
        else:
            pnl_str = "-"

        table_html += f"""
            <tr>
                <td>{date_str}</td>
                <td>{ticker}</td>
                <td>{name}</td>
                <td class="trades-side-cell">
                    <div class="trades-side-badge {side_class}">
                        {side}
                    </div>
                </td>
                <td>${entry_price:.2f}</td>
                <td>${exit_price:.2f}</td>
                <td>{pnl_str}</td>
            </tr>
        """

    table_html += """
        </tbody>
    </table>
    </div>
    """
    return table_html


def render_trades_tab(trades_table, sector_industry_df=None, price_data=None, holdings_df=None, charts=None) -> str:
    """
    Renders the Trades tab HTML block.
    """
    template_src = """
<div id="History" class="tab-content">
    <!-- Header strip: key trade metrics -->
    <div class="chart-container m-b-10">
        {{ charts.trades_metrics_strip | safe }}
    </div>

    <div class="chart-container trades-chart-container">
        <h2>Trade History</h2>
        <button onclick="exportTradesTableToCSV(this, 'trade_history')" class="trades-export-btn">
            <span class="trades-export-icon">&#128196;</span> Export Excel
        </button>
        <p>List of trades ordered by date (most recent first).</p>
        {{ trades_table | safe }}
    </div>
</div>
<script>
    function exportTradesTableToCSV(btn, filename) {
        var originalText = btn.innerHTML;
        btn.innerHTML = '<span class="trades-export-icon">⏳</span> Exporting...';
        
        var table = document.getElementById("trades-table");
        var csv = [];
        var rows = table.querySelectorAll('tr');
        
        for (var i = 0; i < rows.length; i++) {
            var row = [], cols = rows[i].querySelectorAll('td, th');
            
            for (var j = 0; j < cols.length; j++) {
                var cellText = "";
                var valDiv = cols[j].querySelector('div');
                if (valDiv) {
                    cellText = valDiv.innerText.replace(/"/g, '""').trim();
                } else {
                    var clone = cols[j].cloneNode(true);
                    cellText = clone.innerText.replace(/"/g, '""').trim();
                }
                row.push('"' + cellText + '"');
            }
            csv.push(row.join(','));
        }
        
        var csvFile = new Blob([csv.join('\\n')], {type: 'text/csv'});
        var downloadLink = document.createElement("a");
        downloadLink.download = filename + ".csv";
        downloadLink.href = window.URL.createObjectURL(csvFile);
        downloadLink.style.display = "none";
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
        
        setTimeout(function() {
            btn.innerHTML = originalText;
        }, 1000);
    }
</script>
"""
    template = Template(template_src)
    return template.render(
        trades_table=trades_table,
        charts=charts or {}
    )


