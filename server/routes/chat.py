import json
import time
import sys
import os
import traceback
import threading
from flask import Blueprint, request, Response, stream_with_context

# 导入 server 的配置
from config import Config, llm_config

# 将 agents 目录加入 Python 路径
agents_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agents')
if agents_dir not in sys.path:
    sys.path.insert(0, agents_dir)

# 导入 agents 模块
from agents.llm_client import get_llm_client

# 从配置获取模型名称
AGENTS_MODEL_NAME = llm_config.model_name

chat_bp = Blueprint('chat', __name__)


def log_error(context: str, error: Exception):
    """打印详细错误日志"""
    stack_trace = traceback.format_exc()
    print(f"\033[31m[ERROR] {context}:\033[0m")
    print(f"\033[31m  Error: {str(error)}\033[0m")
    print(f"\033[90m{stack_trace}\033[0m")

# 初始化 LLM 客户端
llm_client = get_llm_client(streaming=False)
llm_client_stream = get_llm_client(streaming=True)


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


def _save_memory_async(user_llm_client, last_user_msg, content, user_id):
    """异步保存记忆到 hindsight"""
    try:
        if user_llm_client.memory:
            user_llm_client.memory.retain(
                content=f"用户: {last_user_msg}\nAI: {content}",
                context="conversation"
            )
    except Exception as mem_e:
        print(f"\033[33m[WARN] 记忆存储失败 (user: {user_id}): {mem_e}\033[0m")


def non_stream_chat_completion(messages, temperature, max_tokens, user_id='anonymous'):
    """非流式聊天完成"""
    try:
        kwargs = {'temperature': temperature}
        if max_tokens is not None:
            kwargs['max_tokens'] = max_tokens

        print(f"\033[36m[INFO] 非流式请求 - user_id: {user_id}, messages: {len(messages)}\033[0m")

        # 根据用户ID获取对应的LLM客户端（带独立记忆）
        from agents.llm_client import get_llm_client_with_memory
        user_llm_client = get_llm_client_with_memory(
            bank_id=f"user-{user_id}",
            streaming=False
        )

        # 调用聊天（会自动从用户记忆库和世界记忆库获取记忆）
        content = user_llm_client.chat(messages, **kwargs)

        # 保存对话到用户记忆库（异步执行，不阻塞响应）
        last_user_msg = None
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_user_msg = msg.get('content', '')
                break
        if last_user_msg and user_llm_client.memory:
            # 使用独立线程保存记忆，不阻塞 API 响应
            memory_thread = threading.Thread(
                target=_save_memory_async,
                args=(user_llm_client, last_user_msg, content, user_id),
                daemon=True
            )
            memory_thread.start()
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
            'prompt_tokens': -1,  # LangChain 不直接返回 token 数
            'completion_tokens': -1,
            'total_tokens': -1
        }
    }


def stream_chat_completion(messages, temperature, max_tokens, user_id='anonymous'):
    """流式聊天完成"""
    try:
        kwargs = {'temperature': temperature}
        if max_tokens is not None:
            kwargs['max_tokens'] = max_tokens

        print(f"\033[36m[INFO] 流式请求 - user_id: {user_id}, messages: {len(messages)}\033[0m")

        # 根据用户ID获取对应的流式LLM客户端（带独立记忆）
        from agents.llm_client import get_llm_client_with_memory
        user_llm_client = get_llm_client_with_memory(
            bank_id=f"user-{user_id}",
            streaming=True
        )
    except Exception as e:
        log_error(f"stream_chat_completion 初始化失败 (user: {user_id})", e)
        raise

    def generate():
        try:
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

            # 使用流式客户端获取响应
            full_content = ''
            for chunk in user_llm_client.stream_chat(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    content = chunk.content
                    full_content += content
                    data = {
                        'id': f'chatcmpl-{int(time.time() * 1000)}',
                        'object': 'chat.completion.chunk',
                        'created': int(time.time()),
                        'model': AGENTS_MODEL_NAME,
                        'choices': [
                            {
                                'index': 0,
                                'delta': {'content': content},
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

            # 流式响应结束后，异步保存完整对话到用户记忆库
            if full_content and messages:
                last_user_msg = None
                for msg in reversed(messages):
                    if msg.get('role') == 'user':
                        last_user_msg = msg.get('content', '')
                        break
                if last_user_msg and user_llm_client.memory:
                    # 使用独立线程保存记忆，不阻塞响应
                    memory_thread = threading.Thread(
                        target=_save_memory_async,
                        args=(user_llm_client, last_user_msg, full_content, user_id),
                        daemon=True
                    )
                    memory_thread.start()
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
        log_error("completions", e)
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


@chat_bp.route('/embeddings', methods=['POST'])
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

    # 将 prompt 转换为 messages 格式
    messages = [{'role': 'user', 'content': prompt}]

    try:
        kwargs = {'temperature': temperature, 'max_tokens': max_tokens}

        if stream:
            def generate():
                full_content = ''
                for chunk in llm_client_stream.stream_chat(messages):
                    if hasattr(chunk, 'content') and chunk.content:
                        content = chunk.content
                        full_content += content
                        data = {
                            'id': f'cmpl-{int(time.time() * 1000)}',
                            'object': 'text_completion',
                            'created': int(time.time()),
                            'model': AGENTS_MODEL_NAME,
                            'choices': [
                                {
                                    'text': content,
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
            content = llm_client.chat(messages, **kwargs)
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
        log_error("list_models", e)
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

    # 由于使用 LangChain 客户端，无法直接 detokenize
    # 返回提示信息
    return {
        'content': '[Detokenize not supported with LangChain client]'
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

    # 当前 llm_client 不支持 embeddings
    return {
        'error': {
            'message': 'Embeddings not supported with current LangChain client implementation',
            'type': 'not_implemented_error',
            'code': 'not_implemented'
        }
    }, 501
