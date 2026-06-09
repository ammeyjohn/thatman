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
from world_time_service import WorldTimeService, set_world_time_service
from player_busy_manager import PlayerBusyManager, set_player_busy_manager, get_player_busy_manager
from routes.auth import _verify_token

# 配置日志
logger = logging.getLogger(__name__)

gm_bp = Blueprint('gm', __name__)

# 初始化 GameMaster 实例
_gm_instance = None

# 初始化 WorldTimeService 实例
_world_time_service = None


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


def get_world_time_service():
    """获取或初始化 WorldTimeService 实例（单例）"""
    global _world_time_service
    if _world_time_service is None:
        try:
            gm = get_gm()
            if gm.storage:
                _world_time_service = WorldTimeService(gm.storage)
                _world_time_service.start()
                set_world_time_service(_world_time_service)
                info_log("WorldTimeService 初始化并启动成功")
            else:
                error_log("WorldTimeService 初始化失败: GMStorage 不可用")
        except Exception as e:
            error_log(f"WorldTimeService 初始化失败: {e}")
    return _world_time_service


# 初始化 PlayerBusyManager 实例
_player_busy_manager = None


def get_player_busy_mgr():
    """获取或初始化 PlayerBusyManager 实例（单例）"""
    global _player_busy_manager
    if _player_busy_manager is None:
        try:
            gm = get_gm()
            _player_busy_manager = PlayerBusyManager(gm.storage)
            set_player_busy_manager(_player_busy_manager)
            info_log("PlayerBusyManager 初始化成功")
        except Exception as e:
            error_log(f"PlayerBusyManager 初始化失败: {e}")
    return _player_busy_manager


def _get_storage():
    """获取 GMStorage 实例"""
    gm = get_gm()
    return gm.storage


def _get_game_time_and_location(current_area: str) -> dict:
    """
    获取当前游戏时间和地点信息，用于 save_chat_message

    Args:
        current_area: 当前区域

    Returns:
        包含 game_date, game_shichen, location 的字典
    """
    game_date = ""
    game_shichen = ""
    try:
        from world_time_service import get_world_time_service_instance
        wts = get_world_time_service_instance()
        if wts:
            time_info = wts.get_current_time()
            game_date = time_info.get("game_date", "")
            game_shichen = f"{time_info.get('shichen_name', '')}·{time_info.get('shichen_period', '')}"
    except Exception:
        pass
    return {
        "game_date": game_date,
        "game_shichen": game_shichen,
        "location": current_area,
    }


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
    message_id = data.get('message_id', '')

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
        time_loc = _get_game_time_and_location(current_area)
        storage.save_chat_message(
            uid=uid,
            sender="player",
            content=user_input,
            timestamp=now_ms,
            game_date=time_loc["game_date"],
            game_shichen=time_loc["game_shichen"],
            location=time_loc["location"],
            doc_id=message_id or None,
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
                npc_message_id = None
                if dialog_text or result_data:
                    try:
                        storage = _get_storage()
                        now_ms = int(time_module.time() * 1000)
                        time_loc = _get_game_time_and_location(current_area)
                        save_resp = storage.save_chat_message(
                            uid=uid,
                            sender="npc",
                            content=result_data.get('dialog', dialog_text),
                            timestamp=now_ms,
                            actions=result_data.get('actions'),
                            player_update=result_data.get('player_update'),
                            ui_config=result_data.get('ui_config'),
                            game_date=time_loc["game_date"],
                            game_shichen=time_loc["game_shichen"],
                            location=time_loc["location"],
                        )
                        npc_message_id = save_resp.get('id') if save_resp else None
                    except Exception as e:
                        error_log(f"流式保存NPC聊天消息失败: {e}")

                # 返回 NPC 消息 id，供前端同步
                if npc_message_id:
                    yield f"event: saved\ndata: {json.dumps({'npc_message_id': npc_message_id}, ensure_ascii=False)}\n\n"

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
            'ui_config': result.get('ui_config', {'left_open': [], 'right_open': []}),
            'time_cost': result.get('time_cost', 0),
        }
        # 附加时间推进信息
        if result.get('time_advance'):
            response_data['time_advance'] = result['time_advance']
        # 附加忙碌状态信息
        if result.get('busy_state'):
            response_data['busy_state'] = result['busy_state']

        # 保存 NPC 回复到聊天历史（与 LLM 无关，保证所有聊天都保存）
        try:
            storage = _get_storage()
            now_ms = int(time_module.time() * 1000)
            time_loc = _get_game_time_and_location(current_area)
            save_resp = storage.save_chat_message(
                uid=uid,
                sender="npc",
                content=response_data.get('dialog', ''),
                timestamp=now_ms,
                actions=response_data.get('actions'),
                player_update=response_data.get('player_update'),
                ui_config=response_data.get('ui_config'),
                game_date=time_loc["game_date"],
                game_shichen=time_loc["game_shichen"],
                location=time_loc["location"],
            )
            if save_resp and save_resp.get('id'):
                response_data['npc_message_id'] = save_resp['id']
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
    获取用户聊天历史（支持分页）

    查询参数:
        uid: 玩家唯一ID（必填）
        limit: 返回消息数量上限，默认100
        before_timestamp: 分页时间戳，获取此时间戳之前的消息
    """
    uid = request.args.get('uid', '')
    limit = int(request.args.get('limit', 100))
    before_timestamp = request.args.get('before_timestamp')
    if before_timestamp:
        try:
            before_timestamp = int(before_timestamp)
        except ValueError:
            before_timestamp = None

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
        docs = storage.get_chat_history(uid, limit=limit, before_timestamp=before_timestamp)
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


@gm_bp.route('/chat/history/<message_id>', methods=['DELETE'])
def delete_chat_message(message_id: str):
    """
    删除单条聊天消息

    路径参数:
        message_id: 消息文档ID（必填）
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

    if not message_id:
        return jsonify({
            'error': {
                'message': 'message_id 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        storage = _get_storage()
        result = storage.delete_chat_message(uid, message_id)
        if result is True:
            return jsonify({'success': True, 'message': '消息已删除'})
        elif result == "not_found":
            return jsonify({
                'error': {
                    'message': '消息不存在',
                    'type': 'not_found_error',
                    'code': 'not_found'
                }
            }), 404
        elif result == "forbidden":
            return jsonify({
                'error': {
                    'message': '无权删除该消息',
                    'type': 'forbidden_error',
                    'code': 'forbidden'
                }
            }), 403
        else:
            return jsonify({
                'error': {
                    'message': '删除消息失败',
                    'type': 'internal_server_error',
                    'code': 'internal_error'
                }
            }), 500
    except Exception as e:
        error_log(f"删除聊天消息失败: {e}")
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

        # 获取最近游戏事件
        recent_events = []
        try:
            chat_docs = storage.get_chat_history(uid, limit=10)
            for doc in chat_docs:
                if isinstance(doc, dict) and doc.get("sender") == "npc":
                    content = doc.get("content", "")
                    if content and len(content) > 20:
                        # 截取前100字作为摘要
                        recent_events.append(content[:100])
            # 只保留最近5条
            recent_events = recent_events[-5:]
        except Exception as e:
            error_log(f"获取聊天历史失败: {e}")

        # 获取记忆
        memory_text = ""
        try:
            memory_text = storage.recall_all_memory(uid, "角色状态 世界事件")
        except Exception as e:
            error_log(f"获取记忆失败: {e}")

        # 获取世界快照
        world_snapshot = {}
        try:
            world_snapshot = storage.couch_get_last_world_snap()
            world_snapshot.pop("_id", None)
            world_snapshot.pop("_rev", None)
        except Exception as e:
            error_log(f"获取世界快照失败: {e}")

        # 构建游戏上下文
        game_context = {}
        if recent_events:
            game_context["recent_events"] = recent_events
        if memory_text:
            # 尝试拆分个人记忆和世界记忆
            char_memories = ""
            world_memories = ""
            if "【个人记忆】" in memory_text and "【世界记忆】" in memory_text:
                char_part = memory_text.split("【世界记忆】")[0]
                world_part = memory_text.split("【世界记忆】")[1]
                # 去掉【个人记忆】标记
                char_memories = char_part.replace("【个人记忆】", "").strip()
                world_memories = world_part.strip()
            elif "【个人记忆】" in memory_text:
                char_memories = memory_text.replace("【个人记忆】", "").strip()
            elif "【世界记忆】" in memory_text:
                world_memories = memory_text.replace("【世界记忆】", "").strip()
            else:
                char_memories = memory_text

            if char_memories:
                game_context["character_memories"] = char_memories
            if world_memories:
                game_context["world_memories"] = world_memories
        if world_snapshot:
            game_context["world_snapshot"] = world_snapshot

        debug_log(f"游戏上下文: recent_events={len(recent_events)}, "
                  f"has_character_memories={'character_memories' in game_context}, "
                  f"has_world_memories={'world_memories' in game_context}, "
                  f"has_world_snapshot={'world_snapshot' in game_context}")

        result = layout_gen.generate_layout(uid, panel_type, current_data, game_context=game_context)

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


@gm_bp.route('/gm/tutorial', methods=['POST'])
def gm_tutorial():
    """
    GM 引导教程接口

    为新玩家提供初始引导，调用 GameMaster 生成引导剧情。
    支持 stream 参数，当 stream=true 时以 SSE 格式流式返回。

    请求格式（JSON POST）:
    {
        "uid": "string(玩家唯一ID)",
        "stream": false
    }

    响应格式（非流式）:
    {
        "dialog": "引导对话文本",
        "actions": [],
        "player_update": {},
        "ui_config": {"left_open":[],"right_open":[]}
    }

    响应格式（流式 stream=true）:
    SSE 事件流，格式与 /gm/chat 流式响应一致
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
    stream = data.get('stream', False)

    if not uid:
        return jsonify({
            'error': {
                'message': 'uid 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        gm = get_gm()
        storage = _get_storage()

        # 固定的引导 prompt
        tutorial_prompt = "新修士初入青墟古域，请作为引路仙灵，为这位新修士介绍青墟古域的世界观、基本生存法则、修炼入门之道，并描述其初始场景。"

        if stream:
            # 流式引导教程
            info_log(f"处理流式引导教程请求 - uid={uid}")

            def generate_tutorial_stream():
                dialog_text = ""
                result_data = {}
                for sse_event in gm.handle_chat_stream(
                    uid, tutorial_prompt, "青墟古域·云溪村", [], req_type="tutorial"
                ):
                    yield sse_event
                    # 捕获 dialog_delta 和 result 事件
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

                # 流式结束后更新 is_new 标记
                try:
                    player_data = storage.couch_get_player(uid)
                    if player_data and player_data.get("is_new") is True:
                        player_data["is_new"] = False
                        storage.couch_save_player(uid, player_data)
                        info_log(f"流式引导教程完成，已更新玩家 is_new 标记: uid={uid}")
                except Exception as e:
                    error_log(f"更新玩家 is_new 标记失败: uid={uid}, 错误: {e}")

                # 保存引导消息到聊天历史
                try:
                    now_ms = int(time_module.time() * 1000)
                    time_loc = _get_game_time_and_location("青墟古域·云溪村")
                    storage.save_chat_message(
                        uid=uid,
                        sender="player",
                        content=tutorial_prompt,
                        timestamp=now_ms,
                        game_date=time_loc["game_date"],
                        game_shichen=time_loc["game_shichen"],
                        location=time_loc["location"],
                    )
                    storage.save_chat_message(
                        uid=uid,
                        sender="npc",
                        content=result_data.get('dialog', dialog_text),
                        timestamp=now_ms + 1,
                        actions=result_data.get('actions'),
                        player_update=result_data.get('player_update'),
                        ui_config=result_data.get('ui_config'),
                        game_date=time_loc["game_date"],
                        game_shichen=time_loc["game_shichen"],
                        location=time_loc["location"],
                    )
                except Exception as e:
                    error_log(f"流式保存引导教程聊天消息失败: {e}")

            return Response(generate_tutorial_stream(), mimetype='text/event-stream',
                          headers={
                              'Cache-Control': 'no-cache',
                              'X-Accel-Buffering': 'no',
                              'Connection': 'keep-alive',
                          })
        else:
            # 非流式引导教程（向后兼容）
            info_log(f"处理引导教程请求 - uid={uid}")
            result = gm.handle_chat(uid, tutorial_prompt, "青墟古域·云溪村", [], req_type="tutorial")

            # 返回标准 GM 响应格式
            response_data = {
                'dialog': result.get('dialog', ''),
                'actions': result.get('actions', []),
                'player_update': result.get('player_update', {}),
                'ui_config': result.get('ui_config', {'left_open': [], 'right_open': []})
            }

            # 将玩家数据的 is_new 标记更新为 False
            try:
                player_data = storage.couch_get_player(uid)
                if player_data and player_data.get("is_new") is True:
                    player_data["is_new"] = False
                    storage.couch_save_player(uid, player_data)
                    info_log(f"引导教程完成，已更新玩家 is_new 标记: uid={uid}")
            except Exception as e:
                error_log(f"更新玩家 is_new 标记失败: uid={uid}, 错误: {e}")

            # 保存引导消息到聊天历史
            try:
                now_ms = int(time_module.time() * 1000)
                time_loc = _get_game_time_and_location("青墟古域·云溪村")
                storage.save_chat_message(
                    uid=uid,
                    sender="player",
                    content=tutorial_prompt,
                    timestamp=now_ms,
                    game_date=time_loc["game_date"],
                    game_shichen=time_loc["game_shichen"],
                    location=time_loc["location"],
                )
                storage.save_chat_message(
                    uid=uid,
                    sender="npc",
                    content=response_data.get('dialog', ''),
                    timestamp=now_ms + 1,
                    actions=response_data.get('actions'),
                    player_update=response_data.get('player_update'),
                    ui_config=response_data.get('ui_config'),
                    game_date=time_loc["game_date"],
                    game_shichen=time_loc["game_shichen"],
                    location=time_loc["location"],
                )
            except Exception as e:
                error_log(f"保存引导教程聊天消息失败: {e}")

            debug_log(f"引导教程响应: {json.dumps(response_data, ensure_ascii=False)}")
            return jsonify(response_data)

    except Exception as e:
        error_log(f"处理引导教程请求时出错: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/world-time', methods=['GET'])
def get_world_time():
    """
    获取当前世界时间

    响应格式:
    {
        "game_date": "天元三千六百年·正月初一",
        "game_year": 3600,
        "game_month": 1,
        "game_day": 1,
        "game_hour": 0,
        "game_minute": 0,
        "shichen_name": "子时",
        "shichen_period": "深夜",
        "shichen_index": 0,
        "time_ratio": 10
    }
    """
    try:
        wts = get_world_time_service()
        if wts is None:
            return jsonify({
                'error': {
                    'message': '世界时间服务不可用',
                    'type': 'internal_server_error',
                    'code': 'internal_error'
                }
            }), 500

        time_info = wts.get_current_time()
        return jsonify(time_info)
    except Exception as e:
        error_log(f"获取世界时间失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/world-time/sse', methods=['GET'])
def world_time_sse():
    """
    世界时间 SSE 订阅接口

    当游戏时辰变化时，推送时间信息事件流。
    事件格式:
        event: shichen_change
        data: {"game_date": "...", "shichen_name": "...", ...}
    """
    try:
        wts = get_world_time_service()
        if wts is None:
            return jsonify({
                'error': {
                    'message': '世界时间服务不可用',
                    'type': 'internal_server_error',
                    'code': 'internal_error'
                }
            }), 500

        def generate():
            # 使用队列在回调与 SSE 生成器之间传递数据
            import queue
            q = queue.Queue()

            def on_shichen_change(time_info):
                """时辰变化回调，将数据放入队列"""
                try:
                    q.put(time_info, timeout=5)
                except Exception:
                    pass

            # 订阅时辰变化
            wts.subscribe(on_shichen_change)

            try:
                # 先发送当前时间
                current_time = wts.get_current_time()
                yield f"event: current_time\ndata: {json.dumps(current_time, ensure_ascii=False)}\n\n"

                # 持续监听时辰变化
                while True:
                    try:
                        time_info = q.get(timeout=30)
                        yield f"event: shichen_change\ndata: {json.dumps(time_info, ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        # 发送心跳，防止连接超时
                        yield f"event: heartbeat\ndata: {{}}\n\n"
            except GeneratorExit:
                # 客户端断开连接
                pass
            finally:
                wts.unsubscribe(on_shichen_change)

        return Response(generate(), mimetype='text/event-stream',
                      headers={
                          'Cache-Control': 'no-cache',
                          'X-Accel-Buffering': 'no',
                          'Connection': 'keep-alive',
                      })
    except Exception as e:
        error_log(f"世界时间 SSE 订阅失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/inventory', methods=['GET'])
def get_inventory():
    """
    查询玩家背包/物品栏

    查询参数:
        uid: 玩家唯一ID（必填）

    请求头:
        Authorization: Bearer <token>（必填）

    响应格式:
    {
        "uid": "user_123_abc",
        "inventory": [
            {"id": "item1", "name": "灵石", "type": "currency", "description": "修仙界通用货币", "quantity": 100}
        ]
    }
    """
    # 验证 Bearer token
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({
            'error': {
                'message': '未授权访问',
                'type': 'authentication_error',
                'code': 'unauthorized'
            }
        }), 401

    token = auth_header[7:]  # 去掉 "Bearer " 前缀
    payload = _verify_token(token)
    if not payload:
        return jsonify({
            'error': {
                'message': '未授权访问',
                'type': 'authentication_error',
                'code': 'unauthorized'
            }
        }), 401

    # 验证 uid 参数
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

        # 玩家不存在或 inventory 字段缺失时返回空数组
        inventory = []
        if player_data and 'inventory' in player_data:
            inventory = player_data['inventory']

        return jsonify({
            'uid': uid,
            'inventory': inventory,
        })
    except Exception as e:
        error_log(f"获取玩家背包失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/equipment', methods=['GET'])
def get_equipment():
    """
    查询玩家装备与服饰

    查询参数:
        uid: 玩家唯一ID（必填）

    请求头:
        Authorization: Bearer <token>（必填）

    响应格式:
    {
        "uid": "user_123_abc",
        "equipment": [...],
        "clothing": ""
    }
    """
    # 验证 Bearer token
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({
            'error': {
                'message': '未授权访问',
                'type': 'authentication_error',
                'code': 'unauthorized'
            }
        }), 401

    token = auth_header[7:]  # 去掉 "Bearer " 前缀
    payload = _verify_token(token)
    if not payload:
        return jsonify({
            'error': {
                'message': '未授权访问',
                'type': 'authentication_error',
                'code': 'unauthorized'
            }
        }), 401

    # 验证 uid 参数
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

        equipment = player_data.get('equipment', []) if player_data else []
        clothing = player_data.get('clothing', '') if player_data else ''

        return jsonify({
            'uid': uid,
            'equipment': equipment,
            'clothing': clothing,
        })
    except Exception as e:
        error_log(f"获取玩家装备失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/busy-state', methods=['GET'])
def get_busy_state():
    """
    查询玩家忙碌状态

    查询参数:
        uid: 玩家唯一ID（必填）

    响应格式:
    {
        "uid": "string",
        "is_busy": false,
        "busy_state": null
    }
    或
    {
        "uid": "string",
        "is_busy": true,
        "busy_state": {
            "action": "打坐修炼",
            "game_minutes": 120,
            "cooldown_seconds": 50,
            "cooldown_remaining_seconds": 35.2,
            "cooldown_end_at": 1717834567890,
            "started_at": 1717834517890
        }
    }
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
        busy_mgr = get_player_busy_mgr()
        busy_info = busy_mgr.get_busy_info(uid) if busy_mgr else None

        return jsonify({
            'uid': uid,
            'is_busy': busy_info is not None,
            'busy_state': busy_info,
        })
    except Exception as e:
        error_log(f"获取玩家忙碌状态失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500


@gm_bp.route('/gm/interrupt', methods=['POST'])
def interrupt_action():
    """
    中断玩家当前耗时行为

    请求格式（JSON POST）:
    {
        "uid": "string(玩家唯一ID)"
    }

    响应格式:
    {
        "uid": "string",
        "interrupted": true,
        "message": "已中断打坐修炼"
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
        busy_mgr = get_player_busy_mgr()
        if not busy_mgr:
            return jsonify({
                'uid': uid,
                'interrupted': False,
                'message': '忙碌状态管理器不可用',
            })

        busy_info = busy_mgr.get_busy_info(uid)
        if not busy_info:
            return jsonify({
                'uid': uid,
                'interrupted': False,
                'message': '当前没有进行中的耗时行为',
            })

        action = busy_info.get("action", "耗时行为")
        busy_mgr.clear_busy(uid)
        info_log(f"玩家中断耗时行为: uid={uid}, action={action}")

        return jsonify({
            'uid': uid,
            'interrupted': True,
            'message': f'已中断{action}',
        })
    except Exception as e:
        error_log(f"中断耗时行为失败: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500
