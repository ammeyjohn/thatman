import hashlib
import base64
import json
import time
import uuid
import logging
import sys
from pathlib import Path

from flask import Blueprint, request, jsonify

# 将 agents 目录添加到路径
agents_path = Path(__file__).parent.parent / "agents"
if str(agents_path) not in sys.path:
    sys.path.insert(0, str(agents_path))

from gm_storage import GMStorage
from gm_logger import debug_log, info_log, error_log

# 配置日志
logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# GMStorage 实例缓存
_storage_instance = None


def _get_storage() -> GMStorage:
    """获取或初始化 GMStorage 实例（单例）"""
    global _storage_instance
    if _storage_instance is None:
        try:
            # 加载配置
            import yaml
            config_path = Path(__file__).parent.parent / "config.yaml"
            config = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
            _storage_instance = GMStorage(config)
            info_log("Auth 模块 GMStorage 初始化成功")
        except Exception as e:
            error_log(f"Auth 模块 GMStorage 初始化失败: {e}")
            raise
    return _storage_instance


def _hash_password(password: str, username: str) -> str:
    """
    对密码进行加盐 hash

    盐值格式: "thatman_salt_" + username

    Args:
        password: 明文密码
        username: 用户名（用于生成盐值）

    Returns:
        SHA256 hex 摘要
    """
    salt = f"thatman_salt_{username}"
    salted = salt + password
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def _generate_token(uid: str, username: str) -> str:
    """
    生成简单 token

    使用 base64 编码的 JSON，包含 uid、username、exp（7天后过期时间戳）

    Args:
        uid: 用户唯一标识
        username: 用户名

    Returns:
        base64 编码的 token 字符串
    """
    exp = int(time.time()) + 7 * 24 * 3600  # 7天后过期
    payload = {
        "uid": uid,
        "username": username,
        "exp": exp,
    }
    json_str = json.dumps(payload, ensure_ascii=False)
    token_bytes = base64.urlsafe_b64encode(json_str.encode("utf-8"))
    return token_bytes.decode("utf-8")


def _verify_token(token: str) -> dict:
    """
    验证 token 并返回载荷数据

    Args:
        token: base64 编码的 token 字符串

    Returns:
        载荷字典，验证失败返回空字典
    """
    try:
        json_bytes = base64.urlsafe_b64decode(token.encode("utf-8"))
        payload = json.loads(json_bytes.decode("utf-8"))
        # 检查过期时间
        if payload.get("exp", 0) < int(time.time()):
            return {}
        return payload
    except Exception:
        return {}


@auth_bp.route('/auth/register', methods=['POST'])
def register():
    """
    注册接口

    请求体: {username, password, character_name}
    校验: username 3-20字符, password >= 6字符, character_name 2-10字符
    """
    data = request.get_json()

    if not data:
        return jsonify({
            'error': {
                'message': '请求体不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    character_name = data.get('character_name', '').strip()

    # 参数校验
    if not username or len(username) < 3 or len(username) > 20:
        return jsonify({
            'error': {
                'message': '用户名长度需为3-20个字符',
                'type': 'invalid_request_error',
                'code': 'invalid_username'
            }
        }), 400

    if not password or len(password) < 6:
        return jsonify({
            'error': {
                'message': '密码长度不能少于6个字符',
                'type': 'invalid_request_error',
                'code': 'invalid_password'
            }
        }), 400

    if not character_name or len(character_name) < 2 or len(character_name) > 10:
        return jsonify({
            'error': {
                'message': '角色名长度需为2-10个字符',
                'type': 'invalid_request_error',
                'code': 'invalid_character_name'
            }
        }), 400

    try:
        storage = _get_storage()

        # 1. 检查用户名是否已存在
        existing_user = storage.couch_get_user(username)
        if existing_user:
            return jsonify({
                'error': {
                    'message': '用户名已存在',
                    'type': 'invalid_request_error',
                    'code': 'username_exists'
                }
            }), 409

        # 2. 生成 uid
        uid = f"user_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        # 3. 密码 hash
        password_hash = _hash_password(password, username)

        # 4. 在 thatman_users 中创建用户记录
        user_data = {
            "username": username,
            "password_hash": password_hash,
            "uid": uid,
            "character_name": character_name,
            "created_at": int(time.time()),
        }
        save_result = storage.couch_save_user(username, user_data)
        if not save_result:
            return jsonify({
                'error': {
                    'message': '用户创建失败',
                    'type': 'internal_server_error',
                    'code': 'internal_error'
                }
            }), 500

        # 5. 在 thatman_players 中创建初始玩家数据
        player_data = {
            "name": character_name,
            "current_location": "",
            "current_status": "",
            "is_new": True,
        }
        storage.couch_save_player(uid, player_data)

        # 6. 生成 token
        token = _generate_token(uid, username)

        info_log(f"用户注册成功: {username}, uid={uid}")

        # 7. 返回结果
        return jsonify({
            'token': token,
            'user': {
                'uid': uid,
                'username': username,
                'character_name': character_name,
            }
        }), 201

    except Exception as e:
        error_log(f"注册失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@auth_bp.route('/auth/login', methods=['POST'])
def login():
    """
    登录接口

    请求体: {username, password}
    """
    data = request.get_json()

    if not data:
        return jsonify({
            'error': {
                'message': '请求体不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username:
        return jsonify({
            'error': {
                'message': '用户名不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    if not password:
        return jsonify({
            'error': {
                'message': '密码不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        storage = _get_storage()

        # 1. 查询用户记录
        user_data = storage.couch_get_user(username)
        if not user_data:
            return jsonify({
                'error': {
                    'message': '用户名或密码错误',
                    'type': 'authentication_error',
                    'code': 'invalid_credentials'
                }
            }), 401

        # 2. 验证密码 hash
        password_hash = _hash_password(password, username)
        if user_data.get("password_hash") != password_hash:
            return jsonify({
                'error': {
                    'message': '用户名或密码错误',
                    'type': 'authentication_error',
                    'code': 'invalid_credentials'
                }
            }), 401

        # 3. 生成 token
        uid = user_data.get("uid", "")
        token = _generate_token(uid, username)

        info_log(f"用户登录成功: {username}, uid={uid}")

        # 4. 返回结果
        return jsonify({
            'token': token,
            'user': {
                'uid': uid,
                'username': username,
                'character_name': user_data.get("character_name", ""),
            }
        })

    except Exception as e:
        error_log(f"登录失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@auth_bp.route('/auth/logout', methods=['POST'])
def logout():
    """
    登出接口

    请求体: {uid: "xxx"}（可选，用于标记离线）
    前端负责清除本地存储的 token，后端标记玩家离线并返回成功响应。
    """
    data = request.get_json() or {}
    uid = data.get('uid', '')

    if uid:
        try:
            from online_manager import get_online_manager
            online_mgr = get_online_manager()
            online_mgr.player_offline(uid, reason="logout")
        except Exception as e:
            error_log(f"登出离线处理失败: uid={uid}, 错误={e}")

    return jsonify({'success': True})
