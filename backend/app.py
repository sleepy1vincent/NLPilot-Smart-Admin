from flask import Flask
from flask_cors import CORS
from config import Config
from routes.product_routes import bp as product_bp
from routes.chat_routes import bp as chat_bp
from response import success

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.register_blueprint(product_bp)
app.register_blueprint(chat_bp)

@app.route("/api/health")
def health():
    return success(data="NLPilot running")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)