from flask import Flask
from Functions.routes import index, port, register_route, eqs, wcr, cryp, ana, port_cache_status, sel # Import sel

app = Flask(__name__)

register_route(app, '/', 'Function Index', index)
register_route(app, '/ana', 'Analyse', ana)
register_route(app, '/etopi', 'Portfolio & Risk Analytics', port, methods=['GET', 'POST'], show_in_index=False)
app.route('/etopi/check_cache', methods=['POST'])(port_cache_status) # Keep endpoint but exclude from Function Index
register_route(app, '/port', 'Portfolio Investor Selection', sel)
register_route(app, '/eqs', 'Stocks AI Screener', eqs)
register_route(app, '/wcr', 'Forex AI Screener', wcr)
register_route(app, '/cryp', 'Cryptocurrency AI Screener', cryp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=True)
