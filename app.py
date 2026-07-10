from flask import Flask
from Functions.routes import index, port, register_route, eqs, wcr, cryp, ana, port_cache_status # Import port_cache_status

app = Flask(__name__)

register_route(app, '/', 'Function Index', index)
register_route(app, '/ana', 'Analyse', ana)
register_route(app, '/port', 'Portfolio & Risk Analytics', port, methods=['GET', 'POST'])
register_route(app, '/port/check_cache', 'Check Portfolio Cache Status', port_cache_status, methods=['POST']) # New route
register_route(app, '/eqs', 'Stocks AI Screener', eqs)
register_route(app, '/wcr', 'Forex AI Screener', wcr)
register_route(app, '/cryp', 'Cryptocurrency AI Screener', cryp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=True)
