"""
Portfolio Pro Investor selection interface HTML template.
"""

from Functions.themes import (
    _TEXT_PRIMARY, _TEXT_HEADING, _BRAND_PRIMARY, _HOVER_SURFACE, _BORDER_DEFAULT,
    _BG_SUBTLE, _NEUTRAL_0, _BG_DEFAULT, _TEXT_MUTED, _GRID_LINE, BORDER_DIVIDER,
    _SEMANTIC_POSITIVE, _SEMANTIC_NEGATIVE, _SEMANTIC_WARNING, _SEMANTIC_NEUTRAL,
    _NEUTRAL_SURFACE,
    font as _font_module
)

FONT_FAMILY = _font_module.FONT_PRIMARY

PORTFOLIO_SELECTION_HTML = f"""<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Function - Select Investor</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
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
          overflow: hidden;
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

        .selection-container {{
            font-family: {FONT_FAMILY};
            padding: 20px;
            color: {_TEXT_PRIMARY};
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

        .performance-positive {{
            color: {_SEMANTIC_POSITIVE};
            font-size: 13px;
        }}

        .performance-negative {{
            color: {_SEMANTIC_NEGATIVE};
            font-size: 13px;
        }}

        .performance-neutral {{
            color: {_TEXT_MUTED};
            font-size: 13px;
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
    </style>
</head>
<body>
    <div class="selection-background-wrapper">
        <div class="selection-foreground">
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
                            <th>Week</th>
                            <th>Month</th>
                            <th>Year</th>
                            <th>7D Trend</th>
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
                            <td><span class="my-portfolio-performance my-portfolio-performance-positive">+0.42%</span></td>
                            <td><span class="my-portfolio-performance my-portfolio-performance-positive">+1.85%</span></td>
                            <td><span class="my-portfolio-performance my-portfolio-performance-positive">+14.20%</span></td>
                            <td>
                                <svg class="my-portfolio-trend" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,20 12,18 24,19 36,16 48,15 60,14 72,10 84,8 100,4"/>
                                </svg>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="selection-container">
                <div class="selection-header">
                    <h2 class="selection-title">
                        Pro Investors Trending This Week
                    </h2>
                </div>
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
                            <th>Pro Investor</th>
                            <th>Country</th>
                            <th>AUM</th>
                            <th>Copiers</th>
                            <th>Week</th>
                            <th>Month</th>
                            <th>Year</th>
                            <th>7D Trend</th>
                        </tr>
                    </thead>
                    <tbody id="investor-table-body">
                        <tr data-search="sarah miller @compoundvalue healthcare consumer elite pro us">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Sarah Miller</span>
                                            <span class="badge badge-elite-pro">ELITE PRO</span>
                                        </div>
                                        <span class="investor-username">@CompoundValue</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1FA&#x1F1F8;</span>
                                    US
                                </span>
                            </td>
                            <td><span class="aum-value">$14.5M</span></td>
                            <td>
                                <div class="copiers-value">32,800</div>
                                <div class="copiers-change">&#x25B2; 3.1% 1M</div>
                            </td>
                            <td><span class="performance-positive">+0.42%</span></td>
                            <td><span class="performance-positive">+1.85%</span></td>
                            <td><span class="performance-positive">+14.20%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,20 12,18 24,19 36,16 48,15 60,14 72,10 84,8 100,4"/>
                                </svg>
                            </td>
                        </tr>
                        <tr data-search="helena vance @greenmacro_vance clean energy infrastr elite gb">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Helena Vance</span>
                                            <span class="badge badge-elite">ELITE</span>
                                        </div>
                                        <span class="investor-username">@GreenMacro_Vance</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1EC&#x1F1E7;</span>
                                    GB
                                </span>
                            </td>
                            <td><span class="aum-value">$12.2M</span></td>
                            <td>
                                <div class="copiers-value">24,100</div>
                                <div class="copiers-change">&#x25B2; 5.2% 1M</div>
                            </td>
                            <td><span class="performance-positive">+0.72%</span></td>
                            <td><span class="performance-positive">+2.45%</span></td>
                            <td><span class="performance-positive">+16.85%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,22 12,20 24,21 36,18 48,17 60,15 72,12 84,10 100,6"/>
                                </svg>
                            </td>
                        </tr>
                        <tr data-search="ruben sanchez @techbull_sanchez tech ai elite pro es">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Ruben Sanchez</span>
                                            <span class="badge badge-elite-pro">ELITE PRO</span>
                                        </div>
                                        <span class="investor-username">@TechBull_Sanchez</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1EA&#x1F1F8;</span>
                                    ES
                                </span>
                            </td>
                            <td><span class="aum-value">$8.4M</span></td>
                            <td>
                                <div class="copiers-value">18,450</div>
                                <div class="copiers-change">&#x25B2; 14.8% 1M</div>
                            </td>
                            <td><span class="performance-positive">+2.84%</span></td>
                            <td><span class="performance-positive">+8.12%</span></td>
                            <td><span class="performance-positive">+42.65%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,24 12,22 24,20 36,21 48,18 60,16 72,14 84,10 100,4"/>
                                </svg>
                            </td>
                        </tr>
                        <tr data-search="line nielsen @nordiccap_nielsen healthcare logistics elite dk">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Line Nielsen</span>
                                            <span class="badge badge-elite">ELITE</span>
                                        </div>
                                        <span class="investor-username">@NordicCap_Nielsen</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1E9&#x1F1F0;</span>
                                    DK
                                </span>
                            </td>
                            <td><span class="aum-value">$7.9M</span></td>
                            <td>
                                <div class="copiers-value">14,200</div>
                                <div class="copiers-change">&#x25B2; 9.1% 1M</div>
                            </td>
                            <td><span class="performance-positive">+1.65%</span></td>
                            <td><span class="performance-positive">+5.24%</span></td>
                            <td><span class="performance-positive">+28.40%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,22 12,20 24,21 36,19 48,17 60,15 72,12 84,9 100,5"/>
                                </svg>
                            </td>
                        </tr>
                        <tr data-search="yuki sato @cryptoquantum cryptocurrency blockc champion jp">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Yuki Sato</span>
                                            <span class="badge badge-champion">CHAMPION</span>
                                        </div>
                                        <span class="investor-username">@CryptoQuantum</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1EF&#x1F1F5;</span>
                                    JP
                                </span>
                            </td>
                            <td><span class="aum-value">$4.1M</span></td>
                            <td>
                                <div class="copiers-value">11,350</div>
                                <div class="copiers-change">&#x25B2; 28.6% 1M</div>
                            </td>
                            <td><span class="performance-negative">-4.32%</span></td>
                            <td><span class="performance-positive">+14.50%</span></td>
                            <td><span class="performance-positive">+89.20%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,14 12,10 24,12 36,8 48,6 60,10 72,8 84,6 100,4"/>
                                </svg>
                            </td>
                        </tr>
                        <tr data-search="lin wong @shenzhenvanguard asian tech evs elite sg">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Lin Wong</span>
                                            <span class="badge badge-elite">ELITE</span>
                                        </div>
                                        <span class="investor-username">@ShenzhenVanguard</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1F8&#x1F1EC;</span>
                                    SG
                                </span>
                            </td>
                            <td><span class="aum-value">$6.7M</span></td>
                            <td>
                                <div class="copiers-value">10,800</div>
                                <div class="copiers-change">&#x25B2; 18.2% 1M</div>
                            </td>
                            <td><span class="performance-positive">+3.42%</span></td>
                            <td><span class="performance-positive">+9.55%</span></td>
                            <td><span class="performance-positive">+32.80%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,22 12,20 24,18 36,19 48,16 60,14 72,12 84,8 100,5"/>
                                </svg>
                            </td>
                        </tr>
                        <tr data-search="maximilian weber @alphadividends financials consumer elite de">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Maximilian Weber</span>
                                            <span class="badge badge-elite">ELITE</span>
                                        </div>
                                        <span class="investor-username">@AlphaDividends</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1E9&#x1F1EA;</span>
                                    DE
                                </span>
                            </td>
                            <td><span class="aum-value">$5.8M</span></td>
                            <td>
                                <div class="copiers-value">9,200</div>
                                <div class="copiers-change">&#x25B2; 8.4% 1M</div>
                            </td>
                            <td><span class="performance-positive">+1.15%</span></td>
                            <td><span class="performance-positive">+4.10%</span></td>
                            <td><span class="performance-positive">+19.40%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,20 12,19 24,18 36,17 48,16 60,14 72,12 84,10 100,7"/>
                                </svg>
                            </td>
                        </tr>
                        <tr data-search="chloe laurent @trendrider_chloe luxury brand saas elite fr">
                            <td>
                                <div class="investor-info">
                                    <img class="investor-avatar" src="https://cdn.brandfetch.io/idCL5_YhIb/w/400/h/400/theme/dark/icon.jpeg?c=1bxid64Mup7aczewSAYMX&t=1694087448850" alt="avatar" onerror="this.style.display='none'">
                                    <div class="investor-details">
                                        <div class="investor-name-row">
                                            <span class="investor-name">Chloe Laurent</span>
                                            <span class="badge badge-elite">ELITE</span>
                                        </div>
                                        <span class="investor-username">@TrendRider_Chloe</span>
                                    </div>
                                </div>
                            </td>
                            <td>
                                <span class="country-badge">
                                    <span class="country-flag">&#x1F1EB&#x1F1F7;</span>
                                    FR
                                </span>
                            </td>
                            <td><span class="aum-value">$6.2M</span></td>
                            <td>
                                <div class="copiers-value">8,700</div>
                                <div class="copiers-change">&#x25B2; 11.2% 1M</div>
                            </td>
                            <td><span class="performance-positive">+2.14%</span></td>
                            <td><span class="performance-positive">+6.80%</span></td>
                            <td><span class="performance-positive">+26.90%</span></td>
                            <td>
                                <svg class="trend-chart" viewBox="0 0 100 28" preserveAspectRatio="none">
                                    <polyline fill="none" stroke="{_SEMANTIC_POSITIVE}" stroke-width="1.5" points="0,22 12,20 24,19 36,18 48,16 60,14 72,11 84,8 100,5"/>
                                </svg>
                            </td>
                        </tr>
                    </tbody>
                </table>
                <div class="no-results hidden" id="no-results">No investors match your search.</div>
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
</body>
</html>
"""
