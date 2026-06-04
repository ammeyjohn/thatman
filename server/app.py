import traceback
from flask import Flask, jsonify
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

    # 全局错误处理
    @app.errorhandler(500)
    def internal_error(error):
        # 获取完整的错误堆栈
        stack_trace = traceback.format_exc()
        # 打印错误日志到控制台
        print(f"\033[31m[ERROR] 500 Internal Server Error:\033[0m")
        print(f"\033[31m{stack_trace}\033[0m")
        return jsonify({
            'error': {
                'message': '服务器内部错误',
                'type': 'internal_server_error',
                'code': 'internal_error',
                'details': str(error)
            }
        }), 500

    @app.errorhandler(Exception)
    def unhandled_exception(error):
        # 获取完整的错误堆栈
        stack_trace = traceback.format_exc()
        # 打印错误日志到控制台
        print(f"\033[31m[ERROR] Unhandled Exception:\033[0m")
        print(f"\033[31m{stack_trace}\033[0m")
        return jsonify({
            'error': {
                'message': '服务器发生未处理的异常',
                'type': 'unhandled_exception',
                'code': 'unhandled_error',
                'details': str(error)
            }
        }), 500

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG
    )
