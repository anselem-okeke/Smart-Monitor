from flask import Flask
from .api import api_bp
from .views import ui_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)
    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=True)
