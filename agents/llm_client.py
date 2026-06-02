"""
LangChain LLM 客户端
用于与 llama.cpp OpenAI 兼容服务交互
"""
import os
from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks import StreamingStdOutCallbackHandler

from config import llm_config


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
    """LLM 客户端类"""

    def __init__(
        self,
        streaming: bool = False,
        auto_load_system_prompt: bool = True,
        load_all_prompts_flag: bool = True,
    ):
        """
        初始化 LLM 客户端

        Args:
            streaming: 是否启用流式输出
            auto_load_system_prompt: 是否自动从 prompts/system.md 加载系统提示词
            load_all_prompts_flag: 是否加载所有提示词文件（system.md、assistant.md、user.md）
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

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        发送聊天消息

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            temperature: 温度参数（可选）
            max_tokens: 最大 token 数（可选）

        Returns:
            AI 的回复内容
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

        # 设置参数
        kwargs = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # 调用 LLM
        response = self.llm.invoke(langchain_messages, **kwargs)
        return response.content

    def simple_chat(self, prompt: str) -> str:
        """
        简单的单轮对话

        Args:
            prompt: 用户输入

        Returns:
            AI 的回复内容
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages)

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
) -> LLMClient:
    """
    获取 LLM 客户端实例

    Args:
        streaming: 是否启用流式输出
        auto_load_system_prompt: 是否自动从 prompts/system.md 加载系统提示词
        load_all_prompts_flag: 是否加载所有提示词文件（system.md、assistant.md、user.md）

    Returns:
        LLMClient 实例
    """
    return LLMClient(
        streaming=streaming,
        auto_load_system_prompt=auto_load_system_prompt,
        load_all_prompts_flag=load_all_prompts_flag,
    )
