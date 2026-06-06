from flask import Blueprint, request, jsonify
import json
import logging
import sys
from pathlib import Path

# 将 agents 目录添加到路径
agents_path = Path(__file__).parent.parent / "agents"
if str(agents_path) not in sys.path:
    sys.path.insert(0, str(agents_path))

from game_master import GameMaster, debug_log, info_log, error_log

# 配置日志
logger = logging.getLogger(__name__)

gm_bp = Blueprint('gm', __name__)

# 初始化 GameMaster 实例
_gm_instance = None


def get_gm():
    """获取或初始化 GameMaster 实例（单例）"""
    global _gm_instance
    if _gm_instance is None:
        try:
            _gm_instance = GameMaster()
            info_log("GameMaster 初始化成功")
        except Exception as e:
            error_log(f"GameMaster 初始化失败: {e}")
            raise
    return _gm_instance


@gm_bp.route('/gm/chat', methods=['POST'])
def gm_chat():
    """
    GM 聊天接口
    接收前端标准入参，调用 GameMaster 处理，返回标准结构体

    请求格式（JSON POST）:
    {
        "uid": "string(玩家唯一ID)",
        "user_input": "string(本次聊天内容)",
        "current_area": "string(当前所在地点名称)",
        "session_history": [{"role":"user|assistant","content":"string"}],
        "req_type": "chat|world_tick"
    }

    响应格式:
    {
        "dialog": "对外展示对话文本",
        "player_update": {},
        "ui_config": {"left_open":[],"right_open":[]}
    }
    """
    data = request.get_json()

    # 请求体为空
    if not data:
        return jsonify({
            'error': {
                'message': '请求体不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    # 解析请求参数
    uid = data.get('uid', '')
    user_input = data.get('user_input', '')
    current_area = data.get('current_area', '')
    session_history = data.get('session_history', [])
    req_type = data.get('req_type', 'chat')

    debug_log(f"收到 GM 请求 - req_type={req_type}, uid={uid}, current_area={current_area}")
    debug_log(f"user_input: {user_input}")
    debug_log(f"session_history: {json.dumps(session_history, ensure_ascii=False)}")

    # 验证必填字段
    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    if not user_input:
        return jsonify({
            'error': {
                'message': 'user_input 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        gm = get_gm()

        # 根据 req_type 分发处理
        if req_type == 'world_tick':
            info_log(f"处理 world_tick 请求 - uid={uid}")
            result = gm.world_tick_task()
        else:
            # 默认走 chat 逻辑
            info_log(f"处理 chat 请求 - uid={uid}, current_area={current_area}")
            result = gm.handle_chat(uid, user_input, current_area, session_history)

        # 返回标准结构体
        response_data = {
            'dialog': result.get('dialog', ''),
            'player_update': result.get('player_update', {}),
            'ui_config': result.get('ui_config', {'left_open': [], 'right_open': []})
        }

        debug_log(f"返回响应: {json.dumps(response_data, ensure_ascii=False)}")
        return jsonify(response_data)

    except Exception as e:
        error_log(f"处理 GM 请求时出错: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500
