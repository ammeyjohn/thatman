# LangChain + llama.cpp 基础代码

本项目提供了使用 LangChain 调用 llama.cpp OpenAI 兼容服务的基础代码。

## 项目结构

```
agents/
├── config.py           # 配置管理
├── llm_client.py       # LLM 客户端封装
├── example.py          # 使用示例
├── requirements.txt    # 依赖列表
├── .env.example        # 环境变量示例
└── README.md           # 项目说明
```

## 快速开始

### 1. 安装依赖

```bash
cd /Users/patrick/Workspaces/ThatMan/agents
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# llama.cpp 服务地址
OPENAI_API_BASE=http://localhost:8080/v1

# API Key (llama.cpp 默认不需要)
OPENAI_API_KEY=not-needed

# 模型名称
OPENAI_MODEL_NAME=llama-2-7b-chat
```

### 3. 启动 llama.cpp 服务

确保你已经编译了 llama.cpp 并下载了模型文件：

```bash
# 进入 llama.cpp 目录
cd /path/to/llama.cpp

# 启动服务器
./server -m models/llama-2-7b-chat.gguf --port 8080 --host 0.0.0.0
```

### 4. 运行示例

```bash
# 运行所有示例
python example.py

# 简单对话
python example.py simple

# 多轮对话
python example.py multi

# 流式输出
python example.py stream

# 自定义参数
python example.py params

# 交互式聊天
python example.py interactive
```

## 使用说明

### 基础使用

```python
from llm_client import get_llm_client

# 创建客户端
client = get_llm_client()

# 简单对话
response = client.simple_chat("你好，请介绍一下你自己。")
print(response)
```

### 多轮对话

```python
from llm_client import get_llm_client

client = get_llm_client()

messages = [
    {"role": "system", "content": "你是一个有帮助的AI助手。"},
    {"role": "user", "content": "什么是机器学习？"},
]

response = client.chat(messages)
print(response)
```

### 流式输出

```python
from llm_client import get_llm_client

client = get_llm_client(streaming=True)
response = client.simple_chat("请写一首关于春天的诗。")
```

## 配置选项

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| OPENAI_API_BASE | llama.cpp 服务地址 | http://localhost:8080/v1 |
| OPENAI_API_KEY | API Key (llama.cpp 不需要) | not-needed |
| OPENAI_MODEL_NAME | 模型名称 | llama-2-7b-chat |
| TEMPERATURE | 温度参数 | 0.7 |
| MAX_TOKENS | 最大 token 数 | 2048 |

## 注意事项

1. 确保 llama.cpp 服务已启动并可访问
2. llama.cpp 的 OpenAI 兼容 API 默认在 `/v1/chat/completions` 路径
3. 如果连接失败，请检查防火墙设置和服务地址配置
