import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Flask 服务配置类"""
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 8080))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'


class LLMConfig:
    """LLM 配置类 - 用于配置 llama.cpp OpenAI 兼容服务"""

    def __init__(self):
        # self.api_base: str = os.getenv("OPENAI_API_BASE", "http://128.1.1.48:7778/v1")
        self.api_base: str = os.getenv("OPENAI_API_BASE", "http://localhost:7778/v1")
        self.api_key: str = os.getenv("OPENAI_API_KEY", "not-needed")
        self.model_name: str = os.getenv("OPENAI_MODEL_NAME", "Qwen3.6-27B-UD-Q4_K_XL")
        # 平衡随机性与逻辑性，保证世界演化有变化、无荒诞剧情
        self.temperature: float = float(os.getenv("TEMPERATURE", "0.65"))
        # 约束输出方向，贴合修仙世界观，避免内容跑偏
        self.top_p: float = float(os.getenv("TOP_P", "0.85"))
        # 覆盖剧情、结构化JSON、UI配置完整输出，防止截断
        self.max_tokens: int = int(os.getenv("MAX_TOKENS", "8192"))
        # 减少重复剧情与事件，保证演化层层递进
        self.frequency_penalty: float = float(os.getenv("FREQUENCY_PENALTY", "0.1"))
        # 鼓励新生内容，支撑世界持续自演化
        self.presence_penalty: float = float(os.getenv("PRESENCE_PENALTY", "0.2"))
        # 强制结构化输出，适配后端解析与数据库存储
        self.response_format: dict = {"type": "json_object"}

        # hindsight 记忆库配置
        self.hindsight_base_url: str = os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888")
        self.hindsight_api_key: Optional[str] = os.getenv("HINDSIGHT_API_KEY")
        # 世界 bank 名称，用于存储世界演化相关的长期记忆
        self.hindsight_world_bank: str = os.getenv("HINDSIGHT_WORLD_BANK", "world")

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "base_url": self.api_base,
            "api_key": self.api_key,
            "model": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "response_format": self.response_format,
            "hindsight_base_url": self.hindsight_base_url,
            "hindsight_api_key": self.hindsight_api_key,
            "hindsight_world_bank": self.hindsight_world_bank,
        }


# 全局配置实例
llm_config = LLMConfig()
