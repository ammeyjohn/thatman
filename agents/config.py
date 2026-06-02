"""
LangChain 配置模块
用于配置 llama.cpp OpenAI 兼容服务
"""
import os
from typing import Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class LLMConfig:
    """LLM 配置类"""

    def __init__(self):
        self.api_base: str = os.getenv("OPENAI_API_BASE", "http://localhost:7778/v1")
        self.api_key: str = os.getenv("OPENAI_API_KEY", "not-needed")
        self.model_name: str = os.getenv("OPENAI_MODEL_NAME", "llama-2-7b-chat")
        self.temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
        self.max_tokens: int = int(os.getenv("MAX_TOKENS", "2048"))

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "base_url": self.api_base,
            "api_key": self.api_key,
            "model": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


# 全局配置实例
llm_config = LLMConfig()
