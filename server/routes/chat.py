from flask import Blueprint, request, jsonify, Response
import json
import time
import logging
import sys
from pathlib import Path

# 将 agents 目录添加到路径
agents_path = Path(__file__).parent.parent / "agents"
if str(agents_path) not in sys.path:
    sys.path.insert(0, str(agents_path))

from chat_agent import get_chat_agent, debug_log, info_log, error_log

# 配置日志
logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__)

# 初始化 chat agent 缓存（按 character_id 和 user_id 区分）
_chat_agents = {}


def get_agent(character_id=None, user_id=None):
    """获取或初始化 chat agent（按 character_id 和 user_id 缓存）"""
    cache_key = f"{character_id or '_no_char_'}_{user_id or '_no_user_'}"
    if cache_key not in _chat_agents:
        try:
            _chat_agents[cache_key] = get_chat_agent(character_id=character_id, user_id=user_id)
            info_log(f"ChatAgent 初始化成功 - character_id: {character_id or 'default'}, user_id: {user_id or 'default'}")
        except Exception as e:
            error_log(f"ChatAgent 初始化失败: {e}")
            raise
    return _chat_agents[cache_key]


@chat_bp.route('/chat/completions', methods=['POST'])
def chat_completions():
    """
    聊天补全接口
    接收前端发送的聊天消息，调用大模型获取结果，支持流式和非流式响应
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

    messages = data.get('messages', [])
    stream = data.get('stream', False)
    temperature = data.get('temperature', 0.7)
    character_id = data.get('character_id')
    # 从请求头中获取 X-User-Id 作为 user_id
    user_id = request.headers.get('X-User-Id')

    debug_log(f"收到请求 - stream={stream}, temperature={temperature}, character_id={character_id}, user_id={user_id}")
    debug_log(f"收到消息内容: {json.dumps(messages, ensure_ascii=False)}")

    if not messages:
        return jsonify({
            'error': {
                'message': 'messages 不能为空',
                'type': 'invalid_request_error',
                'code': 'invalid_request'
            }
        }), 400

    try:
        # 获取 chat agent（按 character_id 和 user_id 区分）
        agent = get_chat_agent(character_id=character_id, user_id=user_id)

        if stream:
            # 流式响应
            def generate():
                debug_log("开始流式响应...")
                full_content = []

                for chunk in agent.chat(messages, stream=True):
                    full_content.append(chunk)
                    response_data = {
                        'id': f'chatcmpl-{int(time.time() * 1000)}',
                        'object': 'chat.completion.chunk',
                        'created': int(time.time()),
                        'model': 'chat-agent',
                        'choices': [{
                            'index': 0,
                            'delta': {
                                'content': chunk
                            },
                            'finish_reason': None
                        }]
                    }
                    response_line = f'data: {json.dumps(response_data, ensure_ascii=False)}\n\n'
                    yield response_line

                # 发送结束标记
                complete_content = ''.join(full_content)
                debug_log(f"完整内容: {complete_content}")
                yield 'data: [DONE]\n\n'

                # 流式响应结束后，保存对话记忆（在生成器外部执行）
                try:
                    agent.save_chat_memory(messages, complete_content)
                except Exception as e:
                    error_log(f"流式响应后保存记忆失败: {e}")

            return Response(generate(), mimetype='text/plain')
        else:
            # 非流式响应
            debug_log("使用非流式响应")
            content = agent.chat_non_stream(messages)

            # 保存对话记忆
            try:
                agent.save_chat_memory(messages, content)
            except Exception as e:
                error_log(f"非流式响应后保存记忆失败: {e}")

            response_data = {
                'id': f'chatcmpl-{int(time.time() * 1000)}',
                'object': 'chat.completion',
                'created': int(time.time()),
                'model': 'chat-agent',
                'choices': [{
                    'index': 0,
                    'message': {
                        'role': 'assistant',
                        'content': content
                    },
                    'finish_reason': 'stop'
                }],
                'usage': {
                    'prompt_tokens': len(json.dumps(messages)),
                    'completion_tokens': len(content),
                    'total_tokens': len(json.dumps(messages)) + len(content)
                }
            }
            debug_log(f"返回响应: {json.dumps(response_data, ensure_ascii=False)}")
            return jsonify(response_data)

    except Exception as e:
        error_log(f"处理请求时出错: {e}")
        return jsonify({
            'error': {
                'message': f'服务器内部错误: {str(e)}',
                'type': 'internal_server_error',
                'code': 'internal_error'
            }
        }), 500
