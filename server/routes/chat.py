import json
import time
import sys
import os
import importlib.util
from flask import Blueprint, request, Response, stream_with_context

# 导入 server 的配置
from config import Config

# 动态加载 agents/llm_client.py
agents_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'agents')
llm_client_path = os.path.join(agents_dir, 'llm_client.py')

# 加载 agents.config 模块
config_spec = importlib.util.spec_from_file_location("agents_config", os.path.join(agents_dir, "config.py"))
agents_config = importlib.util.module_from_spec(config_spec)
sys.modules["agents_config"] = agents_config
config_spec.loader.exec_module(agents_config)

# 加载 agents.llm_client 模块
llm_spec = importlib.util.spec_from_file_location("agents_llm_client", llm_client_path)
llm_module = importlib.util.module_from_spec(llm_spec)
sys.modules["agents_llm_client"] = llm_module

# 在 llm_client 模块执行前，替换其导入的 config
original_config = sys.modules.get('config')
sys.modules['config'] = agents_config

try:
    llm_spec.loader.exec_module(llm_module)
finally:
    # 恢复 config 模块
    if original_config:
        sys.modules['config'] = original_config
    else:
        del sys.modules['config']

get_llm_client = llm_module.get_llm_client

chat_bp = Blueprint('chat', __name__)

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

    messages = data.get('messages', [])
    stream = data.get('stream', False)
    temperature = data.get('temperature', 0.7)
    max_tokens = data.get('max_tokens')

    try:
        if stream:
            return stream_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        else:
            return non_stream_chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
    except Exception as e:
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


def non_stream_chat_completion(messages, temperature, max_tokens):
    """非流式聊天完成"""
    kwargs = {'temperature': temperature}
    if max_tokens is not None:
        kwargs['max_tokens'] = max_tokens

    content = llm_client.chat(messages, **kwargs)

    # 构建 OpenAI 兼容格式的响应
    return {
        'id': f'chatcmpl-{int(time.time() * 1000)}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': Config.OPENAI_MODEL,
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


def stream_chat_completion(messages, temperature, max_tokens):
    """流式聊天完成"""
    kwargs = {'temperature': temperature}
    if max_tokens is not None:
        kwargs['max_tokens'] = max_tokens

    def generate():
        # 发送起始事件
        start_data = {
            'id': f'chatcmpl-{int(time.time() * 1000)}',
            'object': 'chat.completion.chunk',
            'created': int(time.time()),
            'model': Config.OPENAI_MODEL,
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
        for chunk in llm_client_stream.stream_chat(messages):
            if hasattr(chunk, 'content') and chunk.content:
                content = chunk.content
                full_content += content
                data = {
                    'id': f'chatcmpl-{int(time.time() * 1000)}',
                    'object': 'chat.completion.chunk',
                    'created': int(time.time()),
                    'model': Config.OPENAI_MODEL,
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
            'model': Config.OPENAI_MODEL,
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
                    'id': Config.OPENAI_MODEL,
                    'object': 'model',
                    'created': int(time.time()),
                    'owned_by': 'llama.cpp'
                }
            ]
        }
    except Exception as e:
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
                            'model': Config.OPENAI_MODEL,
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
                'model': Config.OPENAI_MODEL,
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
