from flask import Flask
from flask_cors import CORS
from config import Config
from routes.chat import chat_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)

    app.register_blueprint(chat_bp, url_prefix='/v1')

    @app.route('/health')
    def health_check():
        return {'status': 'ok', 'message': '服务运行正常'}

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG
    )
