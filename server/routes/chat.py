import json
import time
import sys
import os
import traceback
import threading
from typing import Dict, Optional
from pathlib import Path
from flask import Blueprint, request, Response, stream_with_context
import yaml


def load_yaml_config() -> dict:
    """加载 YAML 配置文件"""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


# 加载 YAML 配置
_yaml_config = load_yaml_config()
_llm_config = _yaml_config.get("llm", {})

# 从配置获取模型名称
AGENTS_MODEL_NAME = _llm_config.get("model_name", "Qwen3.6-27B-UD-Q4_K_XL")

# 将 agents 目录加入 Python 路径
agents_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agents')
if agents_dir not in sys.path:
    sys.path.insert(0, agents_dir)

# 导入 GameMaster
from game_master import create_game_master, GameMaster

chat_bp = Blueprint('chat', __name__)

# 用户 GameMaster 实例缓存
user_gm_instances: Dict[str, GameMaster] = {}


def log_error(context: str, error: Exception):
    """打印详细错误日志"""
    stack_trace = traceback.format_exc()
    print(f"\033[31m[ERROR] {context}:\033[0m")
    print(f"\033[31m  Error: {str(error)}\033[0m")
    print(f"\033[90m{stack_trace}\033[0m")


def get_user_gm(user_id: str) -> GameMaster:
    """获取或创建用户的 GameMaster 实例"""
    if user_id not in user_gm_instances:
        user_gm_instances[user_id] = create_game_master(
            player_id=user_id,
            player_name=f"修士{user_id[:8]}",
            enable_memory=True,
        )
        print(f"\033[32m[INFO] 为用户 {user_id} 创建新的 GameMaster 实例\033[0m")
    return user_gm_instances[user_id]


@chat_bp.route('/chat/completions', methods=['POST'])
def chat_completions():
    data = request.get_json()

    if not data or 'messages' not in data:
        return {
            'error': {
                'message': '请求体必须包含 messages 字段',
                'type': 'invalid_request_error',
                'code': 'missing_messages'
            }
        }, 400

    # 从请求头获取用户ID
    user_id = request.headers.get('X-User-Id', 'anonymous')

    messages = data.get('messages', [])
    stream = data.get('stream', False)
    temperature = data.get('temperature', 0.7)
    max_tokens = data.get('max_tokens')

    try:
        if stream:
            return stream_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                user_id=user_id
            )
        else:
            return non_stream_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                user_id=user_id
            )
    except Exception as e:
        log_error(f"chat_completions (user: {user_id})", e)
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


def non_stream_chat_completion(messages, temperature, max_tokens, user_id='anonymous'):
    """非流式聊天完成 - 使用 GameMaster"""
    try:
        print(f"\033[36m[INFO] 非流式请求 - user_id: {user_id}, messages: {len(messages)}\033[0m")

        # 获取用户的 GameMaster 实例
        gm = get_user_gm(user_id)

        # 提取最后一条用户消息
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_user_msg = msg.get('content', '')
                break

        if not last_user_msg:
            return {
                'error': {
                    'message': '没有找到用户消息',
                    'type': 'invalid_request_error',
                    'code': 'missing_user_message'
                }
            }, 400

        # 使用 GameMaster 处理用户输入
        gm_response = gm.process(last_user_msg)

        # 解析响应内容
        if gm_response.is_json:
            try:
                response_data = json.loads(gm_response.content)
                # 优先使用 narrative 字段作为展示内容
                content = response_data.get('narrative', gm_response.content)
            except json.JSONDecodeError:
                content = gm_response.content
        else:
            content = gm_response.content

    except Exception as e:
        log_error(f"non_stream_chat_completion (user: {user_id})", e)
        raise

    # 构建 OpenAI 兼容格式的响应
    return {
        'id': f'chatcmpl-{int(time.time() * 1000)}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': AGENTS_MODEL_NAME,
        'choices': [
            {
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': content
                },
                'finish_reason': 'stop'
            }
        ],
        'usage': {
            'prompt_tokens': -1,
            'completion_tokens': -1,
            'total_tokens': -1
        }
    }


def stream_chat_completion(messages, temperature, max_tokens, user_id='anonymous'):
    """流式聊天完成 - 使用 GameMaster"""
    try:
        print(f"\033[36m[INFO] 流式请求 - user_id: {user_id}, messages: {len(messages)}\033[0m")

        # 获取用户的 GameMaster 实例
        gm = get_user_gm(user_id)

        # 提取最后一条用户消息
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_user_msg = msg.get('content', '')
                break

        if not last_user_msg:
            return Response(
                f'data: {json.dumps({"error": "没有找到用户消息"})}\n\ndata: [DONE]\n\n',
                mimetype='text/event-stream'
            )

    except Exception as e:
        log_error(f"stream_chat_completion 初始化失败 (user: {user_id})", e)
        raise

    def generate():
        try:
            # 使用 GameMaster 处理用户输入
            gm_response = gm.process(last_user_msg)

            # 解析响应内容
            if gm_response.is_json:
                try:
                    response_data = json.loads(gm_response.content)
                    full_content = response_data.get('narrative', gm_response.content)
                except json.JSONDecodeError:
                    full_content = gm_response.content
            else:
                full_content = gm_response.content

            # 发送起始事件
            start_data = {
                'id': f'chatcmpl-{int(time.time() * 1000)}',
                'object': 'chat.completion.chunk',
                'created': int(time.time()),
                'model': AGENTS_MODEL_NAME,
                'choices': [
                    {
                        'index': 0,
                        'delta': {'role': 'assistant'},
                        'finish_reason': None
                    }
                ]
            }
            yield f'data: {json.dumps(start_data)}\n\n'

            # 模拟流式输出 - 将内容分块发送
            chunk_size = 4  # 每块字符数
            for i in range(0, len(full_content), chunk_size):
                chunk = full_content[i:i+chunk_size]
                data = {
                    'id': f'chatcmpl-{int(time.time() * 1000)}',
                    'object': 'chat.completion.chunk',
                    'created': int(time.time()),
                    'model': AGENTS_MODEL_NAME,
                    'choices': [
                        {
                            'index': 0,
                            'delta': {'content': chunk},
                            'finish_reason': None
                        }
                    ]
                }
                yield f'data: {json.dumps(data)}\n\n'

            # 发送结束事件
            end_data = {
                'id': f'chatcmpl-{int(time.time() * 1000)}',
                'object': 'chat.completion.chunk',
                'created': int(time.time()),
                'model': AGENTS_MODEL_NAME,
                'choices': [
                    {
                        'index': 0,
                        'delta': {},
                        'finish_reason': 'stop'
                    }
                ]
            }
            yield f'data: {json.dumps(end_data)}\n\n'
            yield 'data: [DONE]\n\n'

        except Exception as e:
            log_error(f"stream generate (user: {user_id})", e)
            # 发送错误事件到客户端
            error_data = {
                'id': f'chatcmpl-{int(time.time() * 1000)}',
                'object': 'chat.completion.chunk',
                'created': int(time.time()),
                'model': AGENTS_MODEL_NAME,
                'choices': [
                    {
                        'index': 0,
                        'delta': {'content': f'\n[服务器错误: {str(e)}]'},
                        'finish_reason': 'stop'
                    }
                ]
            }
            yield f'data: {json.dumps(error_data)}\n\n'
            yield 'data: [DONE]\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Content-Type': 'text/event-stream'
        }
    )


@chat_bp.route('/models', methods=['GET'])
def list_models():
    """列出可用模型"""
    try:
        return {
            'object': 'list',
            'data': [
                {
                    'id': AGENTS_MODEL_NAME,
                    'object': 'model',
                    'created': int(time.time()),
                    'owned_by': 'llama.cpp'
                }
            ]
        }
    except Exception as e:
        log_error("list_models", e)
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


@chat_bp.route('/completions', methods=['POST'])
def completions():
    """llama.cpp 旧版 completion 接口（非 chat 格式）"""
    data = request.get_json()

    if not data or 'prompt' not in data:
        return {
            'error': {
                'message': '请求体必须包含 prompt 字段',
                'type': 'invalid_request_error',
                'code': 'missing_prompt'
            }
        }, 400

    prompt = data.get('prompt', '')
    stream = data.get('stream', False)
    temperature = data.get('temperature', 0.7)
    max_tokens = data.get('max_tokens', 512)

    # 从请求头获取用户ID
    user_id = request.headers.get('X-User-Id', 'anonymous')

    try:
        # 获取用户的 GameMaster 实例
        gm = get_user_gm(user_id)

        # 使用 GameMaster 处理
        gm_response = gm.process(prompt)

        # 解析响应内容
        if gm_response.is_json:
            try:
                response_data = json.loads(gm_response.content)
                content = response_data.get('narrative', gm_response.content)
            except json.JSONDecodeError:
                content = gm_response.content
        else:
            content = gm_response.content

        if stream:
            def generate():
                # 模拟流式输出
                chunk_size = 4
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i+chunk_size]
                    data = {
                        'id': f'cmpl-{int(time.time() * 1000)}',
                        'object': 'text_completion',
                        'created': int(time.time()),
                        'model': AGENTS_MODEL_NAME,
                        'choices': [
                            {
                                'text': chunk,
                                'index': 0,
                                'logprobs': None,
                                'finish_reason': None
                            }
                        ]
                    }
                    yield f'data: {json.dumps(data)}\n\n'
                yield 'data: [DONE]\n\n'

            return Response(
                stream_with_context(generate()),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            return {
                'id': f'cmpl-{int(time.time() * 1000)}',
                'object': 'text_completion',
                'created': int(time.time()),
                'model': AGENTS_MODEL_NAME,
                'choices': [
                    {
                        'text': content,
                        'index': 0,
                        'logprobs': None,
                        'finish_reason': 'stop'
                    }
                ],
                'usage': {
                    'prompt_tokens': -1,
                    'completion_tokens': -1,
                    'total_tokens': -1
                }
            }

    except Exception as e:
        log_error("completions", e)
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


@chat_bp.route('/tokenize', methods=['POST'])
def tokenize():
    """llama.cpp tokenize 接口 - 使用简单估算"""
    data = request.get_json()

    if not data or 'content' not in data:
        return {
            'error': {
                'message': '请求体必须包含 content 字段',
                'type': 'invalid_request_error',
                'code': 'missing_content'
            }
        }, 400

    content = data.get('content', '')
    # 简单估算：每 4 个字符约 1 个 token
    estimated_tokens = len(content) // 4 + 1

    return {
        'tokens': list(range(estimated_tokens)),
        'count': estimated_tokens
    }


@chat_bp.route('/detokenize', methods=['POST'])
def detokenize():
    """llama.cpp detokenize 接口 - 返回提示信息"""
    data = request.get_json()

    if not data or 'tokens' not in data:
        return {
            'error': {
                'message': '请求体必须包含 tokens 字段',
                'type': 'invalid_request_error',
                'code': 'missing_tokens'
            }
        }, 400

    # 由于使用 GameMaster，无法直接 detokenize
    return {
        'content': '[Detokenize not supported with GameMaster]'
    }


@chat_bp.route('/embeddings', methods=['POST'])
def embeddings():
    """llama.cpp embeddings 接口 - 返回错误提示"""
    data = request.get_json()

    if not data or 'input' not in data:
        return {
            'error': {
                'message': '请求体必须包含 input 字段',
                'type': 'invalid_request_error',
                'code': 'missing_input'
            }
        }, 400

    # 当前 GameMaster 不支持 embeddings
    return {
        'error': {
            'message': 'Embeddings not supported with GameMaster',
            'type': 'not_implemented_error',
            'code': 'not_implemented'
        }
    }, 501
