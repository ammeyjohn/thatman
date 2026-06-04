"""
Chat Agent - 聊天代理模块
接收用户聊天内容，增加system提示词，连接大模型获取结果，并返回内容。
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
import yaml

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

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


class ChatAgent:
    """聊天代理类，负责与大模型交互"""

    def __init__(self):
        self.llm: Optional[ChatOpenAI] = None
        self.system_prompt: str = ""
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._load_system_prompt()
        self._init_llm()

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
            )
            info_log(f"LLM 初始化成功 - 模型: {model_name}, API: {api_base}")
        except Exception as e:
            error_log(f"LLM 初始化失败: {e}")
            raise

    def chat(self, messages: List[Dict[str, str]], stream: bool = True) -> Iterator[str]:
        """
        处理聊天请求

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            stream: 是否使用流式响应

        Yields:
            大模型生成的内容片段
        """
        if not self.llm:
            error_log("LLM 未初始化")
            raise RuntimeError("LLM 未初始化")

        # 构建消息列表
        langchain_messages = [SystemMessage(content=self.system_prompt)]

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

        try:
            if stream:
                # 流式响应
                debug_log("开始使用流式模式调用大模型...")
                for chunk in self.llm.stream(langchain_messages):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        debug_log(f"收到流式片段: {content[:50]}...")
                        yield content
                debug_log("流式响应结束")
            else:
                # 非流式响应
                debug_log("开始使用非流式模式调用大模型...")
                response = self.llm.invoke(langchain_messages)
                content = response.content if hasattr(response, 'content') else str(response)
                debug_log(f"收到完整响应: {content[:100]}...")
                yield content

        except Exception as e:
            error_log(f"大模型调用失败: {e}")
            raise

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


# 全局单例实例
_chat_agent: Optional[ChatAgent] = None


def get_chat_agent() -> ChatAgent:
    """获取 ChatAgent 单例实例"""
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = ChatAgent()
    return _chat_agent


def chat_with_llm(messages: List[Dict[str, str]], stream: bool = True) -> Iterator[str]:
    """
    便捷函数：与大模型聊天

    Args:
        messages: 消息列表
        stream: 是否流式响应

    Yields:
        内容片段
    """
    agent = get_chat_agent()
    yield from agent.chat(messages, stream)


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
