# 实施计划：记忆内容调整 & 强制 JSON 返回

## 一、总结

1. **记忆内容调整**：提交给记忆的内容从当前的 `玩家: {msg}\n回复: {full_response}` 改为只包含 user 发送内容、答复的 message、time、location，使用 markdown 格式上传
2. **强制 JSON 返回**：将 `config.yaml` 中已配置但未生效的 `response_format` 传递给 `ChatOpenAI`，强制 LLM 输出 JSON 格式

## 二、当前状态分析

### 记忆保存现状
- `ChatAgent._save_conversation_memory()`（[chat_agent.py:205](file:///Users/patrick/Workspaces/ThatMan/server/agents/chat_agent.py#L205)）：保存到角色记忆库，格式为 `玩家: {user_msg}\n回复: {assistant_response}`，其中 `assistant_response` 是 LLM 完整输出（可能包含整个 JSON 字符串）
- `ChatAgent.save_chat_memory()`（[chat_agent.py:334](file:///Users/patrick/Workspaces/ThatMan/server/agents/chat_agent.py#L334)）：保存到用户记忆库，格式同上
- `MemoryManager.save_conversation_memory()`（[memory_manager.py:407-409](file:///Users/patrick/Workspaces/ThatMan/server/agents/memory_manager.py#L407)）：格式为 `玩家: {user_msg}\n结果: {assistant_msg[:200]}...`，同样保存完整响应

**问题**：当前将 LLM 的完整 JSON 输出作为记忆内容保存，包含大量冗余信息（actions、location、time 等结构化字段），不利于记忆检索的精准性。

### JSON 格式强制现状
- `config.yaml` 第 23-24 行配置了 `response_format: {type: json_object}`
- 但 `ChatAgent._init_llm()`（[chat_agent.py:100-110](file:///Users/patrick/Workspaces/ThatMan/server/agents/chat_agent.py#L100)）初始化 `ChatOpenAI` 时**未传递此参数**
- 当前 JSON 输出完全依赖 system.md 的 prompt 约束，无代码层面保障

## 三、具体修改

### 修改 1：`server/agents/chat_agent.py` — 强制 JSON 格式

**位置**：`_init_llm()` 方法，第 100-110 行

**修改内容**：从 config 中读取 `response_format` 配置并传递给 `ChatOpenAI`

```python
self.llm = ChatOpenAI(
    base_url=api_base,
    api_key=api_key,
    model=model_name,
    temperature=llm_config.get("temperature", 0.65),
    max_tokens=llm_config.get("max_tokens", 8192),
    top_p=llm_config.get("top_p", 0.85),
    frequency_penalty=llm_config.get("frequency_penalty", 0.1),
    presence_penalty=llm_config.get("presence_penalty", 0.2),
    streaming=True,
    model_kwargs={"response_format": llm_config.get("response_format", {"type": "json_object"})},
)
```

> 使用 `model_kwargs` 传递 `response_format`，因为 `ChatOpenAI` 不直接支持该参数，需要通过 `model_kwargs` 透传到底层 API。

### 修改 2：`server/agents/chat_agent.py` — 调整记忆内容格式

**新增辅助方法**：`_extract_memory_content()`，从 LLM 响应中解析 JSON 并提取 message/time/location，格式化为 markdown

```python
def _extract_memory_content(self, user_message: str, assistant_response: str) -> str:
    """
    从助手回复中提取关键字段，构建 markdown 格式的记忆内容

    Args:
        user_message: 用户发送的消息
        assistant_response: 助手的完整回复（期望为 JSON 格式）

    Returns:
        markdown 格式的记忆内容
    """
    message = ""
    time_info = ""
    location = ""

    try:
        data = json.loads(assistant_response)
        message = data.get("message", "")
        time_info = data.get("time", "")
        location = data.get("location", "")
    except (json.JSONError, TypeError):
        # JSON 解析失败时，使用原始响应作为 message
        message = assistant_response

    parts = [f"**玩家**: {user_message}"]
    if message:
        parts.append(f"**回复**: {message}")
    if time_info:
        parts.append(f"**时间**: {time_info}")
    if location:
        parts.append(f"**地点**: {location}")

    return "\n\n".join(parts)
```

**修改 `_save_conversation_memory()`**（第 204-205 行）：

```python
# 修改前
memory_content = f"玩家: {last_user_message}\n回复: {assistant_response}"

# 修改后
memory_content = self._extract_memory_content(last_user_message, assistant_response)
```

**修改 `save_chat_memory()`**（第 333-334 行）：

```python
# 修改前
memory_content = f"玩家: {last_user_message}\n回复: {assistant_response}"

# 修改后
memory_content = self._extract_memory_content(last_user_message, assistant_response)
```

### 修改 3：`server/agents/memory_manager.py` — 调整 `save_conversation_memory()` 格式

**位置**：`save_conversation_memory()` 方法，第 406-409 行

**修改内容**：同样改为 markdown 格式，从 assistant 回复中提取关键字段

```python
# 修改前
memory_content = f"玩家: {user_msg}"
if assistant_msg:
    memory_content += f"\n结果: {assistant_msg[:200]}..."

# 修改后
parts = [f"**玩家**: {user_msg}"]
if assistant_msg:
    # 尝试从 JSON 中提取关键字段
    try:
        import json as _json
        data = _json.loads(assistant_msg)
        if data.get("message"):
            parts.append(f"**回复**: {data['message']}")
        if data.get("time"):
            parts.append(f"**时间**: {data['time']}")
        if data.get("location"):
            parts.append(f"**地点**: {data['location']}")
    except (ValueError, TypeError):
        parts.append(f"**回复**: {assistant_msg[:200]}")
memory_content = "\n\n".join(parts)
```

## 四、涉及文件清单

| 文件 | 修改内容 |
|------|---------|
| `server/agents/chat_agent.py` | 1. 新增 `_extract_memory_content()` 方法 2. 修改 `_save_conversation_memory()` 和 `save_chat_memory()` 的记忆内容构建 3. `_init_llm()` 传递 `response_format` |
| `server/agents/memory_manager.py` | 修改 `save_conversation_memory()` 的记忆内容构建为 markdown 格式 |

## 五、假设与决策

1. **`response_format` 透传方式**：使用 `model_kwargs` 传递，因为 LangChain 的 `ChatOpenAI` 不直接支持 `response_format` 参数。如果底层 LLM 服务（llama.cpp）不支持 `response_format` 参数，该配置会被忽略，不影响现有行为。
2. **JSON 解析失败兜底**：当 LLM 输出非 JSON 时，`_extract_memory_content()` 会将完整响应作为 message 字段，确保记忆不丢失。
3. **记忆内容格式**：使用 markdown 格式（`**字段名**: 值`），字段间用双换行分隔，便于记忆检索时匹配关键词。

## 六、验证步骤

1. 启动服务，发送聊天请求，确认 LLM 返回内容为 JSON 格式
2. 检查日志中保存的记忆内容，确认格式为 markdown（`**玩家**: ...`、`**回复**: ...`、`**时间**: ...`、`**地点**: ...`）
3. 确认 JSON 解析失败时，记忆内容仍能正常保存（兜底逻辑）
