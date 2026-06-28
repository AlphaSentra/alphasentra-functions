from flask import Flask
from Functions.routes import index, port, port_commentary, register_route, eqs, wcr, cryp, ana

app = Flask(__name__)

register_route(app, '/', 'Function Index', index)
register_route(app, '/ana', 'Analyse', ana)
register_route(app, '/port', 'Portfolio & Risk Analytics', port)
register_route(app, '/eqs', 'Stocks AI Screener', eqs)
register_route(app, '/wcr', 'Forex AI Screener', wcr)
register_route(app, '/cryp', 'Cryptocurrency AI Screener', cryp)
register_route(app, '/port/commentary', 'Portfolio AI Commentary', port_commentary)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=True)
