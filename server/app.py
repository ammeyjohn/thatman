import traceback
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
import yaml
from routes.chat import chat_bp
from routes.gm import gm_bp
from routes.auth import auth_bp


def load_yaml_config() -> dict:
    """加载 YAML 配置文件"""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


# 加载 YAML 配置
_yaml_config = load_yaml_config()
_flask_config = _yaml_config.get("flask", {})


class Config:
    """Flask 服务配置类"""
    FLASK_ENV = _flask_config.get("env", "development")
    FLASK_PORT = _flask_config.get("port", 8080)
    FLASK_DEBUG = _flask_config.get("debug", True)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)

    app.register_blueprint(chat_bp, url_prefix='/v1')
    app.register_blueprint(gm_bp, url_prefix='/v1')
    app.register_blueprint(auth_bp, url_prefix='/v1')

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
    # 禁用 reloader：fork 会复制 torch/MPS 资源到子进程，
    # 子进程退出时释放未分配的指针导致 malloc 崩溃
    app.run(
        host='0.0.0.0',
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG,
        use_reloader=False,
        threaded=True,
    )
