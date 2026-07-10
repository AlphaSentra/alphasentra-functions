"""
Portfolio input form HTML template.
"""

from Functions.themes import (
    _TEXT_PRIMARY, _TEXT_HEADING, _BRAND_PRIMARY, _HOVER_SURFACE, _BORDER_DEFAULT,
    _BG_SUBTLE, _NEUTRAL_0, _BG_DEFAULT, _TEXT_MUTED, _GRID_LINE, BORDER_DIVIDER,
    font as _font_module
)

FONT_FAMILY = _font_module.FONT_PRIMARY

PORTFOLIO_FORM_HTML = f"""<!DOCTYPE html>
<html>
<head>
    <title>Portfolio Function - input</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
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
        /* Status Overlay Styling - Based on provided image */
        #status-overlay {{
            display: none;
            position: fixed;
            inset: 0;
            background-color: #080c10; /* Very dark blue/grey from image */
            z-index: 9999;
            flex-direction: column;
            padding: clamp(1rem, 3vh, 2.5rem) clamp(1rem, 3vw, 4rem);
            font-family: {FONT_FAMILY};
            overflow: hidden;
            color: {_TEXT_PRIMARY};
            height: 100vh;
            box-sizing: border-box;
        }}
        #status-overlay.active {{
            display: flex;
        }}
        #status-header {{
            font-size: clamp(0.9rem, 1.2vw, 1.15em);
            color: #5ce0d8; /* Teal from image */
            margin-bottom: clamp(0.5rem, 1vh, 0.8em);
            letter-spacing: 0.03em;
            line-height: 1.3;
            flex-shrink: 0;
        }}
        #status-divider {{
            height: 1px;
            background-color: #1e2730; /* Dark grey line from image */
            margin-bottom: clamp(0.75rem, 1.5vh, 2em);
            flex-shrink: 0;
        }}
        #status-list {{
            display: flex;
            flex-direction: column;
            gap: clamp(0.5rem, 1.2vh, 1.75em); /* Spacing between steps from image */
            padding-left: 0;
            list-style: none;
            flex: 1;
            overflow-y: auto;
            min-height: 0;
        }}
        .status-item {{
            display: flex;
            align-items: flex-start;
            gap: clamp(0.6rem, 1.2vw, 1.2em);
            opacity: 0;
            transform: translateY(10px);
            transition: opacity 0.5s ease-out, transform 0.5s ease-out;
            flex-shrink: 0;
        }}
        .status-item.visible {{
            opacity: 1;
            transform: translateY(0);
        }}
        .status-item.active .status-title {{
            color: #5ce0d8; /* Teal for active title */
            animation: pulse-text 1.8s ease-in-out infinite;
        }}
        .status-item.completed .status-title {{
            color: #5ce0d8; /* Teal for completed title */
        }}
        .status-icon {{
            width: clamp(0.9rem, 1.2vw, 1.2em);
            height: clamp(0.9rem, 1.2vw, 1.2em);
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-top: 0.1em;
            font-size: clamp(0.7rem, 0.9vw, 0.9em); /* Smaller icon size */
        }}
        .status-icon .check {{
            color: #5ce0d8; /* Teal checkmark */
            font-size: clamp(0.8rem, 1vw, 1.1em); /* Adjust size */
            line-height: 1;
        }}
        .status-icon .spinner {{
            width: clamp(0.6rem, 0.8vw, 0.8em);
            height: clamp(0.6rem, 0.8vw, 0.8em);
            border: 2px solid #1e2730; /* Dark grey spinner border */
            border-top-color: #5ce0d8; /* Teal spinner top */
            border-radius: 50%;
            animation: spin 0.9s linear infinite;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        .status-body {{
            flex: 1;
        }}
        .status-title {{
            font-size: clamp(0.85rem, 1.1vw, 1.05em); /* Slightly larger than description */
            font-weight: bold;
            color: #c5c8c6; /* Default light grey for title */
            margin-bottom: clamp(0.2rem, 0.4vh, 0.4em);
            letter-spacing: 0.02em;
            line-height: 1.25;
        }}
        .status-desc {{
            font-size: clamp(0.8rem, 1vw, 1em);
            color: #6b7a88; /* Lighter grey for description */
            line-height: 1.35;
            max-width: 640px;
        }}
        @keyframes pulse-text {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.6; }}
        }}
    </style>
</head>
<body>
    <form id="portfolio-form" method="POST">
        <label for="etoro_username">eToro Username:</label>
        <input type="text" id="etoro_username" name="etoro_username" required autofocus>
        <label for="etoro_cid">eToro Customer ID (optional):</label>
        <input type="text" id="etoro_cid" name="etoro_cid" placeholder="e.g. 123456789">
        <label for="benchmark_ticker">Benchmark Ticker (optional):</label>
        <input type="text" id="benchmark_ticker" name="benchmark_ticker" placeholder="e.g. ^GSPC">
        <button type="submit" id="submit-btn">Generate Report</button>
    </form>
    <div id="status-overlay">
        <div id="status-header">Analysing and working on <span id="status-username">portfolio</span>, might take a few minutes...</div>
        <div id="status-divider"></div>
        <ul id="status-list"></ul>
    </div>
    <script>
        (function() {{
            const form = document.getElementById('portfolio-form');
            const overlay = document.getElementById('status-overlay');
            const list = document.getElementById('status-list');
            const usernameEl = document.getElementById('status-username');
            const submitBtn = document.getElementById('submit-btn');

            const steps = [
                            {{
                                title: 'Initializing generation...',
                                desc: 'Spinning up the analysis engine, loading configuration files, and establishing secure connections to data providers.',
                                duration: 2000
                            }},
                            {{
                                title: 'Collecting eToro & Market Data',
                                desc: 'Calling the eToro API to pull portfolio holdings and transaction history, then fetching real-time market data for all assets and benchmarks.',
                                duration: 5000
                            }},
                            {{
                                title: 'Processing Market Data & Timeseries',
                                desc: 'Aligning price series across assets, computing historical returns, and reconstructing market structure for each position.',
                                duration: 5000
                            }},
                            {{
                                title: 'Running Risk & Performance Analysis',
                                desc: 'Running Monte Carlo simulations, computing VaR and Expected Shortfall, and stress-testing the portfolio across multiple scenarios.',
                                duration: 5000
                            }},
                            {{
                                title: 'Normalizing & Cleaning Datasets',
                                desc: 'Cross-checking data integrity, flagging anomalies such as re-listed tickers, and normalizing all inputs into a consistent format.',
                                duration: 5000
                            }},
                            {{
                                title: 'Generating Report & Insights',
                                desc: 'Compiling interactive charts and tables, then finalizing the AI-generated commentary for the report.',
                                duration: 2000
                            }},
                            {{
                                title: 'Thinking...',
                                desc: 'Reasoning... Almost done. Hang tight!',
                                duration: 1000
                            }}
                        ];

            let cancelled = false;
            let currentStepIndex = -1;
            let timeouts = [];

            function clearAllTimeouts() {{
                timeouts.forEach(id => clearTimeout(id));
                timeouts = [];
            }}

            // renderAllSteps removed as steps are now created dynamically in activateStep

            function activateStep(index) {{
                if (cancelled || index >= steps.length) {{
                    // All steps completed or cancelled, now submit the form
                    setTimeout(() => {{
                        if (!cancelled) {{
                            form.submit();
                        }}
                    }}, 500); // Small delay before final submission
                    return;
                }}

                currentStepIndex = index;

                // Create item and its children
                const item = document.createElement('li'); // Use li for list item
                item.className = 'status-item';
                item.id = 'step-' + index;

                const icon = document.createElement('div');
                icon.className = 'status-icon';
                icon.innerHTML = '&nbsp;'; // Placeholder for icon initially

                const body = document.createElement('div');
                body.className = 'status-body';
                body.innerHTML = `<div class="status-title">${{steps[index].title}}</div><div class="status-desc">${{steps[index].desc}}</div>`;

                // Append children to item first, then item to list
                item.appendChild(icon);
                item.appendChild(body);
                list.appendChild(item);

                // Add visible class on the next animation frame to trigger fade-in transition
                requestAnimationFrame(function() {{
                    if (!cancelled) {{
                        item.classList.add('visible');
                    }}
                }});

                // Mark previous step as completed
                if (index > 0) {{
                    const prevItem = document.getElementById('step-' + (index - 1));
                    prevItem.classList.remove('active');
                    prevItem.classList.add('completed');
                    const prevIcon = prevItem.querySelector('.status-icon');
                    prevIcon.innerHTML = '<span class="check">&#x2713;</span>'; // Checkmark Unicode
                }}

                // Activate current step
                item.classList.add('active');
                icon.innerHTML = '<div class="spinner"></div>';

                // Schedule next step activation
                const t = setTimeout(() => {{
                    if (!cancelled) {{
                        activateStep(index + 1);
                    }}
                }}, steps[index].duration);
                timeouts.push(t);
            }}

            form.addEventListener('submit', async function(e) {{
                e.preventDefault();

                const username = document.getElementById('etoro_username').value.trim();
                usernameEl.textContent = username || 'portfolio';

                submitBtn.disabled = true; // Disable button immediately

                // Collect form data for fetch request
                const formData = new FormData();
                formData.append('etoro_username', username);
                formData.append('etoro_cid', document.getElementById('etoro_cid').value.trim());
                formData.append('benchmark_ticker', document.getElementById('benchmark_ticker').value.trim());

                try {{
                    // Check cache status first
                    const response = await fetch('/port/check_cache', {{
                        method: 'POST',
                        body: formData
                    }});
                    const data = await response.json();

                    if (data.cached) {{
                        // If cached, skip animation and submit form directly
                        console.log('Cache hit: Submitting form directly.');
                        form.submit();
                    }} else {{
                        // If not cached, show animation and then submit
                        console.log('Cache miss: Showing progress animation.');
                        overlay.classList.add('active');
                        list.innerHTML = ''; // Clear any old steps
                        cancelled = false;
                        clearAllTimeouts();
                        // Start the animation sequence by creating and activating the first step
                        setTimeout(() => activateStep(0), 50);
                    }}
                }} catch (error) {{
                    console.error('Error checking cache status:', error);
                    // Fallback: show animation even if cache check fails
                    overlay.classList.add('active');
                    list.innerHTML = ''; // Clear any old steps
                    cancelled = false;
                    clearAllTimeouts();
                    setTimeout(() => activateStep(0), 50);
                }}
            }});

            window.addEventListener('beforeunload', function() {{
                cancelled = true;
                clearAllTimeouts();
            }});
        }})();
    </script>
</body>
</html>
"""
