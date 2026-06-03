"""
LangChain LLM 客户端
用于与 llama.cpp OpenAI 兼容服务交互
支持 Hindsight 记忆系统
"""
import os
from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks import StreamingStdOutCallbackHandler

from config import llm_config
from hindsight_memory import HindsightMemory


def load_prompt_file(filename: str) -> Optional[str]:
    """
    从 prompts 目录加载指定提示词文件

    Args:
        filename: 提示词文件名（如 "system.md"）

    Returns:
        提示词内容，如果文件不存在则返回 None
    """
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "prompts", filename)

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
    except Exception:
        return None


def load_system_prompt() -> Optional[str]:
    """
    从 prompts/system.md 加载系统提示词

    Returns:
        系统提示词内容，如果文件不存在则返回 None
    """
    return load_prompt_file("system.md")


def load_all_prompts() -> Dict[str, Optional[str]]:
    """
    加载所有提示词文件（system.md、assistant.md、user.md）

    Returns:
        包含所有提示词的字典，格式为 {"system": ..., "assistant": ..., "user": ...}
    """
    return {
        "system": load_prompt_file("system.md"),
        "assistant": load_prompt_file("assistant.md"),
        "user": load_prompt_file("user.md"),
    }


def build_combined_system_prompt(prompts: Dict[str, Optional[str]]) -> Optional[str]:
    """
    将多个提示词合并为一个系统提示词

    Args:
        prompts: 包含 system、assistant、user 提示词的字典

    Returns:
        合并后的系统提示词，如果没有有效内容则返回 None
    """
    sections = []

    # 添加 system 提示词（核心身份和规则）
    if prompts.get("system"):
        sections.append(prompts["system"])

    # 添加 assistant 提示词（AI 应答规则）
    if prompts.get("assistant"):
        if sections:
            sections.append("\n" + "=" * 50 + "\n")
        sections.append("【AI 应答规范】\n" + prompts["assistant"])

    # 添加 user 提示词（用户角色定义）
    if prompts.get("user"):
        if sections:
            sections.append("\n" + "=" * 50 + "\n")
        sections.append("【用户角色定义】\n" + prompts["user"])

    return "\n".join(sections) if sections else None


class LLMClient:
    """LLM 客户端类，支持 Hindsight 记忆系统"""

    def __init__(
        self,
        streaming: bool = False,
        auto_load_system_prompt: bool = True,
        load_all_prompts_flag: bool = True,
        enable_memory: bool = False,
        memory_config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化 LLM 客户端

        Args:
            streaming: 是否启用流式输出
            auto_load_system_prompt: 是否自动从 prompts/system.md 加载系统提示词
            load_all_prompts_flag: 是否加载所有提示词文件（system.md、assistant.md、user.md）
            enable_memory: 是否启用 hindsight 记忆系统
            memory_config: 记忆系统配置，如 {"storage_dir": "./memory", "short_term_window": 10}
        """
        callbacks = [StreamingStdOutCallbackHandler()] if streaming else []

        self.llm = ChatOpenAI(
            base_url=llm_config.api_base,
            api_key=llm_config.api_key,
            model=llm_config.model_name,
            temperature=llm_config.temperature,
            max_tokens=llm_config.max_tokens,
            streaming=streaming,
            callbacks=callbacks,
        )

        # 加载系统提示词
        self.system_prompt = None
        if load_all_prompts_flag:
            # 加载所有提示词并合并
            all_prompts = load_all_prompts()
            self.system_prompt = build_combined_system_prompt(all_prompts)
        elif auto_load_system_prompt:
            # 仅加载 system.md
            self.system_prompt = load_system_prompt()

        # 初始化 hindsight 记忆系统
        self.memory: Optional[HindsightMemory] = None
        if enable_memory:
            memory_config = memory_config or {}
            self.memory = HindsightMemory(**memory_config)

    def _build_messages_with_memory(
        self,
        messages: List[Dict[str, str]],
        use_memory: bool = True,
    ) -> List[Dict[str, str]]:
        """
        构建包含 hindsight 记忆的消息列表

        Args:
            messages: 原始消息列表
            use_memory: 是否使用记忆

        Returns:
            包含记忆上下文的消息列表
        """
        if not use_memory or not self.memory:
            return messages

        # 获取最后一条用户消息作为查询
        last_user_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if not last_user_msg:
            return messages

        # 构建 hindsight 记忆上下文
        memory_context = self.memory.build_context(
            query=last_user_msg,
            max_memories=5,
            include_recent=True,
        )

        if not memory_context:
            return messages

        # 构建新的消息列表，插入记忆上下文
        result_messages = []
        has_system = False

        for msg in messages:
            if msg.get("role") == "system":
                # 在系统提示词后附加记忆上下文
                enhanced_content = f"{msg.get('content', '')}\n\n{memory_context}"
                result_messages.append({"role": "system", "content": enhanced_content})
                has_system = True
            else:
                result_messages.append(msg)

        # 如果没有系统消息，在开头添加记忆上下文
        if not has_system:
            result_messages.insert(0, {"role": "system", "content": memory_context})

        return result_messages

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_memory: bool = True,
        save_to_memory: bool = True,
    ) -> str:
        """
        发送聊天消息

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            temperature: 温度参数（可选）
            max_tokens: 最大 token 数（可选）
            use_memory: 是否使用记忆上下文（默认 True）
            save_to_memory: 是否保存对话到记忆（默认 True）

        Returns:
            AI 的回复内容
        """
        # 构建包含记忆的消息
        messages_with_memory = self._build_messages_with_memory(messages, use_memory)

        # 转换消息格式
        langchain_messages = []

        # 如果已加载系统提示词且消息列表中没有系统消息，则自动添加
        has_system_message = any(msg.get("role") == "system" for msg in messages_with_memory)
        if self.system_prompt and not has_system_message:
            langchain_messages.append(SystemMessage(content=self.system_prompt))

        for msg in messages_with_memory:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))

        # 设置参数
        kwargs = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # 调用 LLM
        response = self.llm.invoke(langchain_messages, **kwargs)
        response_content = response.content

        # 保存到 hindsight 记忆系统
        if save_to_memory and self.memory:
            # 获取最后一条用户消息
            last_user_msg = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_msg = msg.get("content", "")
                    break
            if last_user_msg:
                # 使用 hindsight retain 存储对话
                self.memory.retain_conversation(last_user_msg, response_content)

        return response_content

    def simple_chat(self, prompt: str, use_memory: bool = True) -> str:
        """
        简单的单轮对话

        Args:
            prompt: 用户输入
            use_memory: 是否使用记忆上下文

        Returns:
            AI 的回复内容
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, use_memory=use_memory)

    def chat_with_memory(
        self,
        prompt: str,
        auto_retain: bool = True,
    ) -> str:
        """
        带 hindsight 记忆的对话

        Args:
            prompt: 用户输入
            auto_retain: 是否自动保存到 hindsight（默认开启）

        Returns:
            AI 的回复内容
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, use_memory=True, save_to_memory=auto_retain)

    def add_hindsight(self, content: str, context: str = "conversation") -> None:
        """
        手动添加 hindsight 记忆

        Args:
            content: 记忆内容
            context: 上下文标签
        """
        if self.memory:
            self.memory.retain(content, context=context)

    def recall_hindsight(self, query: str) -> List[Dict[str, Any]]:
        """
        从 hindsight 检索记忆

        Args:
            query: 查询内容

        Returns:
            记忆列表
        """
        if self.memory:
            return self.memory.recall(query)
        return []

    def get_memory_stats(self) -> Optional[Dict[str, Any]]:
        """
        获取 hindsight 记忆统计信息

        Returns:
            记忆统计信息字典
        """
        if self.memory:
            return self.memory.get_stats()
        return None

    def clear_memory(self, clear_short_term_only: bool = False) -> None:
        """
        清空记忆

        Args:
            clear_short_term_only: 是否只清空短期记忆
        """
        if self.memory:
            if clear_short_term_only:
                self.memory.clear_short_term()
            else:
                self.memory.clear_bank()

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
    ) -> Any:
        """
        流式聊天

        Args:
            messages: 消息列表

        Returns:
            流式响应生成器
        """
        # 转换消息格式
        langchain_messages = []

        # 如果已加载系统提示词且消息列表中没有系统消息，则自动添加
        has_system_message = any(msg.get("role") == "system" for msg in messages)
        if self.system_prompt and not has_system_message:
            langchain_messages.append(SystemMessage(content=self.system_prompt))

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                langchain_messages.append(HumanMessage(content=content))

        return self.llm.stream(langchain_messages)


# 创建默认客户端实例
def get_llm_client(
    streaming: bool = False,
    auto_load_system_prompt: bool = True,
    load_all_prompts_flag: bool = True,
    enable_memory: bool = False,
    memory_config: Optional[Dict[str, Any]] = None,
) -> LLMClient:
    """
    获取 LLM 客户端实例

    Args:
        streaming: 是否启用流式输出
        auto_load_system_prompt: 是否自动从 prompts/system.md 加载系统提示词
        load_all_prompts_flag: 是否加载所有提示词文件（system.md、assistant.md、user.md）
        enable_memory: 是否启用 hindsight 记忆系统
        memory_config: 记忆系统配置

    Returns:
        LLMClient 实例
    """
    return LLMClient(
        streaming=streaming,
        auto_load_system_prompt=auto_load_system_prompt,
        load_all_prompts_flag=load_all_prompts_flag,
        enable_memory=enable_memory,
        memory_config=memory_config,
    )


def get_llm_client_with_memory(
    bank_id: str = "default-agent",
    base_url: str = "http://localhost:8888",
    api_key: Optional[str] = None,
    streaming: bool = False,
    mission: Optional[str] = None,
) -> LLMClient:
    """
    获取带 hindsight 记忆的 LLM 客户端实例（便捷函数）

    Args:
        bank_id: Hindsight memory bank ID
        base_url: Hindsight API 服务地址
        api_key: Hindsight API 密钥
        streaming: 是否启用流式输出
        mission: Bank 使命描述

    Returns:
        启用 hindsight 记忆的 LLMClient 实例
    """
    memory_config = {
        "bank_id": bank_id,
        "base_url": base_url,
        "api_key": api_key,
        "mission": mission,
    }
    return get_llm_client(
        streaming=streaming,
        enable_memory=True,
        memory_config=memory_config,
    )
