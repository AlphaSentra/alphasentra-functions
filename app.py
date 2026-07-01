from flask import Flask
from Functions.routes import index, port, register_route, eqs, wcr, cryp, ana, etoro_gain, etoro_portfolio

app = Flask(__name__)

register_route(app, '/', 'Function Index', index)
register_route(app, '/ana', 'Analyse', ana)
register_route(app, '/port', 'Portfolio & Risk Analytics', port, methods=['GET', 'POST'])
register_route(app, '/eqs', 'Stocks AI Screener', eqs)
register_route(app, '/wcr', 'Forex AI Screener', wcr)
register_route(app, '/cryp', 'Cryptocurrency AI Screener', cryp)
register_route(app, '/etoro', 'eToro Investor Gain', etoro_gain)
register_route(app, '/etoro-portfolio', 'eToro Popular Investor Portfolio', etoro_portfolio)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=True)
