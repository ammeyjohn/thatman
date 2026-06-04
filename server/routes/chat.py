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

# 初始化 chat agent（延迟加载）
_chat_agent = None


def get_agent():
    """获取或初始化 chat agent"""
    global _chat_agent
    if _chat_agent is None:
        try:
            _chat_agent = get_chat_agent()
            info_log("ChatAgent 初始化成功")
        except Exception as e:
            error_log(f"ChatAgent 初始化失败: {e}")
            raise
    return _chat_agent


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

    debug_log(f"收到请求 - stream={stream}, temperature={temperature}")
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
        # 获取 chat agent
        agent = get_agent()

        if stream:
            # 流式响应
            def generate():
                debug_log("开始流式响应...")
                chunk_index = 0

                for chunk in agent.chat(messages, stream=True):
                    chunk_index += 1
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
                    debug_log(f"返回分块 [{chunk_index}]: {chunk[:50]}...")
                    yield response_line

                # 发送结束标记
                debug_log("流式响应结束，发送 [DONE] 标记")
                yield 'data: [DONE]\n\n'

            return Response(generate(), mimetype='text/plain')
        else:
            # 非流式响应
            debug_log("使用非流式响应")
            content = agent.chat_non_stream(messages)

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
            debug_log(f"返回响应: {json.dumps(response_data, ensure_ascii=False)[:200]}...")
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
