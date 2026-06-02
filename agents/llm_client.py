"""
LangChain LLM 客户端
用于与 llama.cpp OpenAI 兼容服务交互
"""
from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks import StreamingStdOutCallbackHandler

from config import llm_config


class LLMClient:
    """LLM 客户端类"""

    def __init__(self, streaming: bool = False):
        """
        初始化 LLM 客户端

        Args:
            streaming: 是否启用流式输出
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
def get_llm_client(streaming: bool = False) -> LLMClient:
    """获取 LLM 客户端实例"""
    return LLMClient(streaming=streaming)
