"""
Chat Agent - 聊天代理模块
接收用户聊天内容，增加system提示词，连接大模型获取结果，并返回内容。
集成记忆功能，自动检索相关世界记忆和角色记忆。
"""

import json
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
import yaml

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# 导入记忆管理模块
from memory_manager import MemoryManager, get_memory_manager

# 配置日志
logger = logging.getLogger(__name__)


def debug_log(message: str):
    """输出 DEBUG 级别日志（灰色）"""
    logger.debug(message)
    print(f"\033[90m[DEBUG] {message}\033[0m")


def info_log(message: str):
    """输出 INFO 级别日志（白色）"""
    logger.info(message)
    print(f"\033[97m[INFO] {message}\033[0m")


def warn_log(message: str):
    """输出 WARN 级别日志（黄色）"""
    logger.warning(message)
    print(f"\033[93m[WARN] {message}\033[0m")


def error_log(message: str):
    """输出 ERROR 级别日志（红色）"""
    logger.error(message)
    print(f"\033[91m[ERROR] {message}\033[0m")


# 导入剧情检索 skill（放在 debug_log 定义之后避免 NameError）
try:
    from skills.search_episode import search_similar_episodes, format_episodes_as_context
    _HAS_SEARCH_EPISODE = True
except Exception as _ep_err:
    _HAS_SEARCH_EPISODE = False
    debug_log(f"search_episode skill 加载失败: {_ep_err}")


class ChatAgent:
    """聊天代理类，负责与大模型交互，集成记忆功能"""

    def __init__(self, character_id: Optional[str] = None, user_id: Optional[str] = None):
        self.llm: Optional[ChatOpenAI] = None
        self.system_prompt: str = ""
        self.config: Dict[str, Any] = {}
        self.character_id: Optional[str] = character_id
        self.user_id: Optional[str] = user_id
        self.memory_manager: Optional[MemoryManager] = None

        self._load_config()
        self._load_system_prompt()
        self._init_llm()
        self._init_memory_manager()

    def _load_config(self) -> None:
        """加载配置文件"""
        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
            debug_log(f"加载配置文件: {config_path}")
        else:
            warn_log(f"配置文件不存在: {config_path}")
            self.config = {}

    def _load_system_prompt(self) -> None:
        """加载系统提示词"""
        prompt_path = Path(__file__).parent / "prompts" / "system.md"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.system_prompt = f.read()
            debug_log(f"加载系统提示词: {prompt_path}")
            debug_log(f"系统提示词长度: {len(self.system_prompt)} 字符")
        else:
            warn_log(f"系统提示词文件不存在: {prompt_path}")
            self.system_prompt = "你是一个 helpful assistant。"

    def _init_llm(self) -> None:
        """初始化大模型连接"""
        llm_config = self.config.get("llm", {})

        api_base = llm_config.get("api_base", "http://localhost:7778/v1")
        api_key = llm_config.get("api_key", "not-needed")
        model_name = llm_config.get("model_name", "Qwen3.6-27B-UD-Q4_K_XL")

        # 也支持从环境变量读取
        api_base = os.getenv("LLM_API_BASE", api_base)
        api_key = os.getenv("LLM_API_KEY", api_key)
        model_name = os.getenv("LLM_MODEL_NAME", model_name)

        try:
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
            info_log(f"LLM 初始化成功 - 模型: {model_name}, API: {api_base}")
        except Exception as e:
            error_log(f"LLM 初始化失败: {e}")
            raise

    def _init_memory_manager(self) -> None:
        """初始化记忆管理器"""
        try:
            hindsight_config = self.config.get("hindsight", {})
            base_url = hindsight_config.get("base_url", "http://localhost:8888")
            api_key = hindsight_config.get("api_key")

            # 也支持从环境变量读取
            base_url = os.getenv("HINDSIGHT_BASE_URL", base_url)
            api_key = os.getenv("HINDSIGHT_API_KEY", api_key)

            self.memory_manager = get_memory_manager(
                character_id=self.character_id,
                user_id=self.user_id,
                base_url=base_url,
                api_key=api_key,
            )
            info_log(f"记忆管理器初始化成功 - 角色: {self.character_id or '无'}, 用户: {self.user_id or '无'}")
        except Exception as e:
            warn_log(f"记忆管理器初始化失败: {e}")
            self.memory_manager = None

    def _retrieve_memories_for_context(self, messages: List[Dict[str, str]]) -> str:
        """
        检索相关记忆并格式化为上下文

        Args:
            messages: 对话消息列表

        Returns:
            格式化的记忆上下文字符串
        """
        if not self.memory_manager:
            return ""

        try:
            # 获取最后一条用户消息作为查询
            last_user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_message = msg.get("content", "")
                    break

            if not last_user_message:
                return ""

            # 检索相关记忆
            memory_context = self.memory_manager.retrieve_memories_as_context(
                query=last_user_message,
                conversation_history=messages,
            )

            if memory_context:
                debug_log(f"检索到相关记忆，长度: {len(memory_context)} 字符")
                return memory_context

            return ""

        except Exception as e:
            warn_log(f"检索记忆时出错: {e}")
            return ""

    def _retrieve_episodes_for_context(self, messages: List[Dict[str, str]]) -> str:
        """
        检索相似剧情片段并格式化为上下文

        Args:
            messages: 对话消息列表

        Returns:
            格式化的剧情上下文字符串
        """
        if not _HAS_SEARCH_EPISODE:
            return ""

        try:
            # 获取最后一条用户消息作为查询
            last_user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_message = msg.get("content", "")
                    break

            if not last_user_message:
                return ""

            # 检索相似剧情
            result = search_similar_episodes(
                query=last_user_message,
                conversation_history=messages,
                top_k=3,
            )

            if result.get("success"):
                episode_context = format_episodes_as_context(result, max_chars=2048)
                if episode_context:
                    debug_log(f"检索到相似剧情，长度: {len(episode_context)} 字符")
                    return episode_context

            return ""

        except Exception as e:
            warn_log(f"检索相似剧情时出错: {e}")
            return ""

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
        except (json.JSONDecodeError, TypeError):
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

    def _save_conversation_memory(
        self,
        messages: List[Dict[str, str]],
        assistant_response: str,
    ) -> None:
        """
        保存对话记忆到角色记忆库

        Args:
            messages: 对话消息列表
            assistant_response: 助手回复内容
        """
        if not self.memory_manager or not self.character_id:
            return

        try:
            # 获取最后一条用户消息
            last_user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_message = msg.get("content", "")
                    break

            if not last_user_message:
                return

            # 构建记忆内容
            memory_content = self._extract_memory_content(last_user_message, assistant_response)

            # 保存到角色记忆库
            success = self.memory_manager.save_character_memory(
                content=memory_content,
                context="character_history",
                metadata={
                    "type": "conversation",
                    "character_id": self.character_id,
                }
            )

            if success:
                debug_log(f"对话记忆保存成功 - 角色: {self.character_id}")
            else:
                warn_log(f"对话记忆保存失败 - 角色: {self.character_id}")

        except Exception as e:
            warn_log(f"保存对话记忆时出错: {e}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True,
        use_memory: bool = True,
    ) -> Iterator[str]:
        """
        处理聊天请求

        所有同步操作（记忆检索、消息构建）在函数内立即执行，
        仅 LLM 流式输出封装为内部 generator，避免在 Flask streaming
        上下文中执行 hindsight-client 调用。

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            stream: 是否使用流式响应
            use_memory: 是否使用记忆功能

        Returns:
            生成大模型内容片段的 iterator
        """
        if not self.llm:
            error_log("LLM 未初始化")
            raise RuntimeError("LLM 未初始化")

        # 构建系统提示词（包含记忆上下文）— 同步操作立即执行
        system_content = self.system_prompt
        context_parts = []

        # 如果启用记忆功能，检索相关记忆
        if use_memory and self.memory_manager:
            memory_context = self._retrieve_memories_for_context(messages)
            if memory_context:
                context_parts.append(memory_context)

        # 检索相似剧情片段
        if use_memory:
            episode_context = self._retrieve_episodes_for_context(messages)
            if episode_context:
                context_parts.append(episode_context)

        if context_parts:
            system_content = f"{self.system_prompt}\n\n" + "\n\n".join(context_parts)

        # 构建消息列表
        langchain_messages = [SystemMessage(content=system_content)]

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:  # user 或其他
                langchain_messages.append(HumanMessage(content=content))

        debug_log(f"发送消息数量: {len(langchain_messages)}")
        debug_log(f"最后一条用户消息: {messages[-1].get('content', '') if messages else 'None'}")

        # 内部 generator：仅负责 LLM 输出，不执行 hindsight-client 调用
        def _stream():
            full_response = ""
            try:
                if stream:
                    debug_log("开始使用流式模式调用大模型...")
                    for chunk in self.llm.stream(langchain_messages):
                        content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                        if content:
                            full_response += content
                            yield content
                    debug_log("流式响应结束")
                else:
                    debug_log("开始使用非流式模式调用大模型...")
                    response = self.llm.invoke(langchain_messages)
                    content = response.content if hasattr(response, 'content') else str(response)
                    full_response = content
                    debug_log(f"收到完整响应: {content}")
                    yield content

            except Exception as e:
                error_log(f"大模型调用失败: {e}")
                raise

        return _stream()

    def save_chat_memory(
        self,
        messages: List[Dict[str, str]],
        assistant_response: str,
    ) -> bool:
        """
        保存对话记忆到用户记忆库

        聊天内容保存到以 user_id 为名称的 bank 中。

        Args:
            messages: 对话消息列表
            assistant_response: 助手回复内容

        Returns:
            True 表示保存成功
        """
        if not self.memory_manager:
            return False

        try:
            # 获取最后一条用户消息
            last_user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_message = msg.get("content", "")
                    break

            if not last_user_message:
                return False

            # 构建记忆内容
            memory_content = self._extract_memory_content(last_user_message, assistant_response)

            # 保存到用户记忆库（以 user_id 为 bank 名称）
            success = self.memory_manager.save_user_memory(
                content=memory_content,
                context="conversation",
                metadata={
                    "type": "conversation",
                    "character_id": self.character_id,
                    "user_id": self.user_id,
                }
            )

            if success:
                debug_log(f"对话记忆保存成功 - 用户: {self.user_id}")
            else:
                warn_log(f"对话记忆保存失败 - 用户: {self.user_id}")

            return success
        except Exception as e:
            error_log(f"保存对话记忆失败: {e}")
            return False

    def chat_non_stream(self, messages: List[Dict[str, str]]) -> str:
        """
        非流式聊天请求

        Args:
            messages: 消息列表

        Returns:
            完整的响应内容
        """
        result = ""
        for chunk in self.chat(messages, stream=False):
            result += chunk
        return result


# 全局实例缓存（按 character_id 和 user_id 区分）
_chat_agents: Dict[str, ChatAgent] = {}


def get_chat_agent(character_id: Optional[str] = None, user_id: Optional[str] = None) -> ChatAgent:
    """
    获取 ChatAgent 实例（按角色ID和用户ID缓存）

    Args:
        character_id: 角色ID，用于关联角色记忆
        user_id: 用户ID，用于保存聊天记忆到用户个人记忆库

    Returns:
        ChatAgent 实例
    """
    global _chat_agents
    cache_key = f"{character_id or '_no_char_'}_{user_id or '_no_user_'}"

    if cache_key not in _chat_agents:
        _chat_agents[cache_key] = ChatAgent(character_id=character_id, user_id=user_id)

    return _chat_agents[cache_key]


def chat_with_llm(
    messages: List[Dict[str, str]],
    stream: bool = True,
    character_id: Optional[str] = None,
    use_memory: bool = True,
) -> Iterator[str]:
    """
    便捷函数：与大模型聊天

    Args:
        messages: 消息列表
        stream: 是否流式响应
        character_id: 角色ID，用于关联角色记忆
        use_memory: 是否使用记忆功能

    Yields:
        内容片段
    """
    agent = get_chat_agent(character_id=character_id)
    yield from agent.chat(messages, stream=stream, use_memory=use_memory)


def save_character_event(
    character_id: str,
    content: str,
    context: str = "character_history",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    保存角色事件记忆

    Args:
        character_id: 角色ID
        content: 记忆内容
        context: 上下文标签
        metadata: 附加元数据

    Returns:
        True 表示保存成功
    """
    try:
        mgr = get_memory_manager(character_id=character_id)
        return mgr.save_character_memory(content, context, metadata)
    except Exception as e:
        error_log(f"保存角色事件失败: {e}")
        return False


def save_world_event(
    content: str,
    context: str = "world_event",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    保存世界事件记忆

    Args:
        content: 记忆内容
        context: 上下文标签
        metadata: 附加元数据

    Returns:
        True 表示保存成功
    """
    try:
        mgr = get_memory_manager()
        return mgr.save_world_memory(content, context, metadata)
    except Exception as e:
        error_log(f"保存世界事件失败: {e}")
        return False


if __name__ == "__main__":
    # 测试代码
    info_log("测试 ChatAgent...")

    agent = ChatAgent()

    test_messages = [
        {"role": "user", "content": "你好，请介绍一下你自己"}
    ]

    info_log("流式响应测试:")
    for chunk in agent.chat(test_messages, stream=True):
        print(chunk, end="", flush=True)
    print()
