import json
import time
import requests
from flask import Blueprint, request, Response, stream_with_context
from openai import OpenAI
from config import Config

chat_bp = Blueprint('chat', __name__)

client = OpenAI(
    api_key=Config.OPENAI_API_KEY or 'no-key',
    base_url=Config.OPENAI_BASE_URL
)


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
    model = data.get('model', Config.OPENAI_MODEL)
    stream = data.get('stream', False)
    temperature = data.get('temperature', 0.7)
    max_tokens = data.get('max_tokens')
    top_p = data.get('top_p', 1.0)
    frequency_penalty = data.get('frequency_penalty', 0.0)
    presence_penalty = data.get('presence_penalty', 0.0)
    stop = data.get('stop')

    # llama.cpp 特有参数
    return_progress = data.get('return_progress', False)
    reasoning_format = data.get('reasoning_format', 'auto')
    backend_sampling = data.get('backend_sampling', False)
    timings_per_token = data.get('timings_per_token', False)

    try:
        if stream:
            return stream_chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                return_progress=return_progress,
                reasoning_format=reasoning_format,
                backend_sampling=backend_sampling,
                timings_per_token=timings_per_token
            )
        else:
            return non_stream_chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                stop=stop,
                return_progress=return_progress,
                reasoning_format=reasoning_format,
                backend_sampling=backend_sampling,
                timings_per_token=timings_per_token
            )
    except Exception as e:
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


def build_payload(messages, model, temperature, max_tokens, top_p,
                  frequency_penalty, presence_penalty, stop,
                  return_progress, reasoning_format, backend_sampling, timings_per_token):
    """构建请求体，支持 llama.cpp 特有参数"""
    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'top_p': top_p
    }

    if max_tokens is not None:
        payload['max_tokens'] = max_tokens
    if frequency_penalty != 0.0:
        payload['frequency_penalty'] = frequency_penalty
    if presence_penalty != 0.0:
        payload['presence_penalty'] = presence_penalty
    if stop is not None:
        payload['stop'] = stop

    # llama.cpp 特有参数
    if return_progress:
        payload['return_progress'] = return_progress
    if reasoning_format != 'auto':
        payload['reasoning_format'] = reasoning_format
    if backend_sampling:
        payload['backend_sampling'] = backend_sampling
    if timings_per_token:
        payload['timings_per_token'] = timings_per_token

    return payload


def non_stream_chat_completion(messages, model, temperature, max_tokens, top_p,
                                frequency_penalty, presence_penalty, stop,
                                return_progress, reasoning_format, backend_sampling, timings_per_token):
    payload = build_payload(
        messages, model, temperature, max_tokens, top_p,
        frequency_penalty, presence_penalty, stop,
        return_progress, reasoning_format, backend_sampling, timings_per_token
    )
    payload['stream'] = False

    url = f"{Config.OPENAI_BASE_URL}/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {Config.OPENAI_API_KEY or "no-key"}'
    }

    response = requests.post(url, headers=headers, json=payload)
    return response.json()


def stream_chat_completion(messages, model, temperature, max_tokens, top_p,
                           frequency_penalty, presence_penalty, stop,
                           return_progress, reasoning_format, backend_sampling, timings_per_token):
    payload = build_payload(
        messages, model, temperature, max_tokens, top_p,
        frequency_penalty, presence_penalty, stop,
        return_progress, reasoning_format, backend_sampling, timings_per_token
    )
    payload['stream'] = True

    url = f"{Config.OPENAI_BASE_URL}/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {Config.OPENAI_API_KEY or "no-key"}'
    }

    def generate():
        with requests.post(url, headers=headers, json=payload, stream=True) as r:
            for line in r.iter_lines():
                if line:
                    yield line.decode('utf-8') + '\n\n'

    return Response(
        stream_with_context(generate()),
        mimetype='text/plain',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@chat_bp.route('/models', methods=['GET'])
def list_models():
    try:
        models = client.models.list()
        return {
            'object': 'list',
            'data': [
                {
                    'id': model.id,
                    'object': 'model',
                    'created': getattr(model, 'created', int(time.time())),
                    'owned_by': getattr(model, 'owned_by', 'llama.cpp')
                }
                for model in models.data
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
    model = data.get('model', Config.OPENAI_MODEL)
    stream = data.get('stream', False)
    temperature = data.get('temperature', 0.7)
    max_tokens = data.get('max_tokens', 512)
    top_p = data.get('top_p', 1.0)

    try:
        url = f"{Config.OPENAI_BASE_URL}/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {Config.OPENAI_API_KEY or "no-key"}'
        }
        payload = {
            'model': model,
            'prompt': prompt,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'top_p': top_p,
            'stream': stream
        }

        if stream:
            def generate():
                with requests.post(url, headers=headers, json=payload, stream=True) as r:
                    for line in r.iter_lines():
                        if line:
                            yield line.decode('utf-8') + '\n\n'
            return Response(stream_with_context(generate()), mimetype='text/plain')
        else:
            response = requests.post(url, headers=headers, json=payload)
            return response.json()

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
    """llama.cpp tokenize 接口"""
    data = request.get_json()

    if not data or 'content' not in data:
        return {
            'error': {
                'message': '请求体必须包含 content 字段',
                'type': 'invalid_request_error',
                'code': 'missing_content'
            }
        }, 400

    try:
        url = f"{Config.OPENAI_BASE_URL}/tokenize"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {Config.OPENAI_API_KEY or "no-key"}'
        }
        response = requests.post(url, headers=headers, json=data)
        return response.json()
    except Exception as e:
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


@chat_bp.route('/detokenize', methods=['POST'])
def detokenize():
    """llama.cpp detokenize 接口"""
    data = request.get_json()

    if not data or 'tokens' not in data:
        return {
            'error': {
                'message': '请求体必须包含 tokens 字段',
                'type': 'invalid_request_error',
                'code': 'missing_tokens'
            }
        }, 400

    try:
        url = f"{Config.OPENAI_BASE_URL}/detokenize"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {Config.OPENAI_API_KEY or "no-key"}'
        }
        response = requests.post(url, headers=headers, json=data)
        return response.json()
    except Exception as e:
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500


@chat_bp.route('/embeddings', methods=['POST'])
def embeddings():
    """llama.cpp embeddings 接口"""
    data = request.get_json()

    if not data or 'input' not in data:
        return {
            'error': {
                'message': '请求体必须包含 input 字段',
                'type': 'invalid_request_error',
                'code': 'missing_input'
            }
        }, 400

    try:
        url = f"{Config.OPENAI_BASE_URL}/embeddings"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {Config.OPENAI_API_KEY or "no-key"}'
        }
        response = requests.post(url, headers=headers, json=data)
        return response.json()
    except Exception as e:
        return {
            'error': {
                'message': str(e),
                'type': 'api_error',
                'code': 'internal_error'
            }
        }, 500
