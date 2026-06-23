from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AlphaSentra Functions</title>
</head>
<body>
    <h1>Hello, World!</h1>
</body>
</html>
"""

@app.route("/")
def hello():
    return render_template_string(HTML_TEMPLATE)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)
