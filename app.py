from flask import Flask
from Functions.routes import index, portfolio, register_route

app = Flask(__name__)

register_route(app, '/', 'Function Index', index)
register_route(app, '/port', 'Portfolio Function', portfolio)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888, debug=True)
