import time as time_module
from flask import Blueprint, request, jsonify, Response
import json
import logging
import sys
from pathlib import Path

# 将 agents 目录添加到路径
agents_path = Path(__file__).parent.parent / "agents"
if str(agents_path) not in sys.path:
    sys.path.insert(0, str(agents_path))

from game_master import GameMaster
from gm_logger import debug_log, info_log, error_log
from layout_generator import LayoutGenerator, get_layout_generator

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


def _get_storage():
    """获取 GMStorage 实例"""
    gm = get_gm()
    return gm.storage


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
    stream = data.get('stream', False)

    debug_log(f"收到 GM 请求 - req_type={req_type}, uid={uid}, current_area={current_area}, stream={stream}")
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

    # 保存用户消息到聊天历史（与 LLM 无关，保证所有聊天都保存）
    try:
        storage = _get_storage()
        now_ms = int(time_module.time() * 1000)
        storage.save_chat_message(
            uid=uid,
            sender="player",
            content=user_input,
            timestamp=now_ms,
        )
    except Exception as e:
        error_log(f"保存用户聊天消息失败: {e}")

    try:
        gm = get_gm()

        # 根据 req_type 分发处理
        if req_type == 'world_tick':
            info_log(f"处理 world_tick 请求 - uid={uid}")
            result = gm.world_tick_task()
        elif stream:
            # 流式响应
            info_log(f"处理流式 chat 请求 - uid={uid}, current_area={current_area}")

            def generate_stream():
                dialog_text = ""
                result_data = {}
                for sse_event in gm.handle_chat_stream(uid, user_input, current_area, session_history):
                    yield sse_event
                    # 捕获 dialog_delta 和 result 事件用于保存聊天历史
                    if sse_event.startswith("event: dialog_delta"):
                        for line in sse_event.split("\n"):
                            if line.startswith("data: "):
                                try:
                                    delta = json.loads(line[6:])
                                    dialog_text += delta.get("content", "")
                                except json.JSONDecodeError:
                                    pass
                    elif sse_event.startswith("event: result"):
                        for line in sse_event.split("\n"):
                            if line.startswith("data: "):
                                try:
                                    result_data = json.loads(line[6:])
                                except json.JSONDecodeError:
                                    pass

                # 流式结束后保存 NPC 回复到聊天历史
                if dialog_text or result_data:
                    try:
                        storage = _get_storage()
                        now_ms = int(time_module.time() * 1000)
                        storage.save_chat_message(
                            uid=uid,
                            sender="npc",
                            content=result_data.get('dialog', dialog_text),
                            timestamp=now_ms,
                            actions=result_data.get('actions'),
                            player_update=result_data.get('player_update'),
                            ui_config=result_data.get('ui_config'),
                        )
                    except Exception as e:
                        error_log(f"流式保存NPC聊天消息失败: {e}")

            return Response(generate_stream(), mimetype='text/event-stream',
                          headers={
                              'Cache-Control': 'no-cache',
                              'X-Accel-Buffering': 'no',
                              'Connection': 'keep-alive',
                          })
        else:
            # 默认走 chat 逻辑（非流式）
            info_log(f"处理 chat 请求 - uid={uid}, current_area={current_area}")
            result = gm.handle_chat(uid, user_input, current_area, session_history)

        # 返回标准结构体
        response_data = {
            'dialog': result.get('dialog', ''),
            'actions': result.get('actions', []),
            'player_update': result.get('player_update', {}),
            'ui_config': result.get('ui_config', {'left_open': [], 'right_open': []})
        }

        # 保存 NPC 回复到聊天历史（与 LLM 无关，保证所有聊天都保存）
        try:
            storage = _get_storage()
            now_ms = int(time_module.time() * 1000)
            storage.save_chat_message(
                uid=uid,
                sender="npc",
                content=response_data.get('dialog', ''),
                timestamp=now_ms,
                actions=response_data.get('actions'),
                player_update=response_data.get('player_update'),
                ui_config=response_data.get('ui_config'),
            )
        except Exception as e:
            error_log(f"保存NPC聊天消息失败: {e}")

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


@gm_bp.route('/chat/history', methods=['GET'])
def get_chat_history():
    """
    获取用户聊天历史

    查询参数:
        uid: 玩家唯一ID（必填）
        limit: 返回消息数量上限，默认100
    """
    uid = request.args.get('uid', '')
    limit = int(request.args.get('limit', 100))

    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        storage = _get_storage()
        docs = storage.get_chat_history(uid, limit=limit)
        return jsonify({
            'uid': uid,
            'messages': docs,
            'total': len(docs),
        })
    except Exception as e:
        error_log(f"获取聊天历史失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/chat/history', methods=['DELETE'])
def clear_chat_history():
    """
    清除用户聊天历史

    查询参数:
        uid: 玩家唯一ID（必填）
    """
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        storage = _get_storage()
        success = storage.clear_chat_history(uid)
        if success:
            return jsonify({'success': True, 'message': '聊天历史已清除'})
        else:
            return jsonify({
                'error': {
                    'message': '清除聊天历史失败',
                    'type': 'internal_server_error',
                    'code': 'internal_error'
                }
            }), 500
    except Exception as e:
        error_log(f"清除聊天历史失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/user/info', methods=['GET'])
def get_user_info():
    """
    获取用户基本信息

    查询参数:
        uid: 玩家唯一ID（必填）
    """
    uid = request.args.get('uid', '')

    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        storage = _get_storage()
        player_data = storage.couch_get_player(uid)
        if not player_data or '_id' not in player_data:
            return jsonify({
                'uid': uid,
                'exists': False,
                'info': None,
            })
        # 移除 CouchDB 内部字段
        player_data.pop('_rev', None)
        player_data.pop('_id', None)
        return jsonify({
            'uid': uid,
            'exists': True,
            'info': player_data,
        })
    except Exception as e:
        error_log(f"获取用户信息失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/user/init', methods=['POST'])
def init_user():
    """
    初始化用户（如果不存在则创建基础记录）

    请求格式（JSON POST）:
    {
        "uid": "string(玩家唯一ID)"
    }
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

    uid = data.get('uid', '')
    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        storage = _get_storage()
        player_data = storage.couch_get_player(uid)

        if not player_data or '_id' not in player_data:
            # 创建基础用户记录
            initial_data = {
                "name": "",
                "current_location": "",
                "current_status": "",
            }
            storage.couch_save_player(uid, initial_data)
            info_log(f"初始化新用户: {uid}")
            return jsonify({
                'uid': uid,
                'created': True,
                'info': initial_data,
            })
        else:
            # 用户已存在
            player_data.pop('_rev', None)
            player_data.pop('_id', None)
            return jsonify({
                'uid': uid,
                'created': False,
                'info': player_data,
            })
    except Exception as e:
        error_log(f"初始化用户失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/generate-layout', methods=['POST'])
def generate_layout():
    """
    生成面板布局接口

    请求格式（JSON POST）:
    {
        "uid": "string(玩家唯一ID)",
        "panel_type": "character | world",
        "current_data": {}
    }

    响应格式:
    {
        "panel_type": "character | world",
        "layout": { "sections": [...] },
        "version": "string"
    }
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

    uid = data.get('uid', '')
    panel_type = data.get('panel_type', '')
    current_data = data.get('current_data', {})

    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    if panel_type not in ('character', 'world'):
        return jsonify({
            'error': {
                'message': 'panel_type 必须为 character 或 world',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        gm = get_gm()
        storage = gm.storage

        if not storage:
            return jsonify({
                'error': {
                    'message': '存储层不可用',
                    'type': 'internal_server_error',
                    'code': 'internal_error'
                }
            }), 500

        # 获取 LayoutGenerator 实例
        layout_gen = get_layout_generator(gm.config, storage)

        # 如果未提供 current_data，从数据库获取
        if not current_data:
            if panel_type == 'character':
                current_data = storage.couch_get_player(uid)
                # 移除 CouchDB 内部字段
                current_data.pop('_id', None)
                current_data.pop('_rev', None)
            else:
                # 世界数据从最新快照获取
                current_data = storage.couch_get_last_world_snap()
                current_data.pop('_id', None)
                current_data.pop('_rev', None)

        info_log(f"生成布局请求: uid={uid}, panel_type={panel_type}")

        result = layout_gen.generate_layout(uid, panel_type, current_data)

        return jsonify(result)

    except Exception as e:
        error_log(f"生成布局失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/layout', methods=['GET'])
def get_layout():
    """
    获取已保存的面板布局

    查询参数:
        uid: 玩家唯一ID（必填）
        panel_type: 面板类型，character 或 world（必填）
    """
    uid = request.args.get('uid', '')
    panel_type = request.args.get('panel_type', '')

    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    if panel_type not in ('character', 'world'):
        return jsonify({
            'error': {
                'message': 'panel_type 必须为 character 或 world',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        storage = _get_storage()
        layout_data = storage.couch_get_layout(uid, panel_type)

        if not layout_data or '_id' not in layout_data:
            # 布局不存在，返回默认空布局
            return jsonify({
                'panel_type': panel_type,
                'layout': '',
                'version': '',
            })

        # 移除 CouchDB 内部字段
        layout_data.pop('_id', None)
        layout_data.pop('_rev', None)

        return jsonify(layout_data)

    except Exception as e:
        error_log(f"获取布局失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500
