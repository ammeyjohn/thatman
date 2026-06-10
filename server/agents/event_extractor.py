"""
EventExtractor - 关键事件提取服务

从 GM 对话文本中使用 LLM 提取关键事件，
保存到 CouchDB 的 key_events 数据库。

事件提取为异步操作，不阻塞主响应返回。
"""

import json
import logging
import os
from typing import Dict, Any, Optional, List

from openai import OpenAI

from gm_logger import debug_log, info_log, warn_log, error_log

logger = logging.getLogger(__name__)

# 事件提取 prompt
EVENT_EXTRACTION_SYSTEM_PROMPT = """你是一个修仙世界的事件分析助手。你的任务是从游戏对话中提取关键事件。

关键事件是指对角色有重要影响的事情，包括但不限于：
- 角色获得或失去重要物品、能力
- 角色与重要 NPC 建立或改变关系
- 角色接受或完成任务、委托
- 角色遭遇危险或危机
- 角色突破修炼境界
- 角色发现重要秘密或线索
- 世界发生重大变化影响角色

请以 JSON 格式返回提取结果，格式如下：
{
  "events": [
    {
      "title": "事件简短标题（10字以内）",
      "description": "事件详细描述（50字以内，包含关键信息）",
      "status": "ongoing 或 completed"
    }
  ]
}

规则：
1. status 为 "ongoing" 表示事件仍在进行中（如：正在进行的任务、未解决的危机）
2. status 为 "completed" 表示事件已经结束（如：已获得的物品、已完成的事件）
3. 如果对话中没有关键事件，返回空数组 {"events": []}
4. 每次最多提取 3 个最关键的事件
5. 只提取真正重要的事件，忽略日常琐事
6. 必须返回合法 JSON，不要包含其他文本"""


class EventExtractor:
    """关键事件提取器"""

    def __init__(self, config: dict):
        """
        初始化 EventExtractor

        Args:
            config: 配置字典，包含 chat_model 段
        """
        self.config = config
        chat_cfg = config.get("chat_model", {})
        self._api_base = os.getenv("GM_CHAT_API_BASE", chat_cfg.get("api_base", "http://localhost:7778/v1"))
        self._api_key = os.getenv("GM_CHAT_API_KEY", chat_cfg.get("api_key", "not-needed"))
        self._model_name = os.getenv("GM_CHAT_MODEL_NAME", chat_cfg.get("model_name", "Qwen3.6-35B-A3B"))
        info_log(f"EventExtractor 初始化完成 - 模型: {self._model_name}")

    def extract_events(self, dialog_text: str, user_input: str = "") -> List[Dict[str, Any]]:
        """
        从对话文本中提取关键事件

        Args:
            dialog_text: NPC 回复文本
            user_input: 玩家输入文本（可选，提供上下文）

        Returns:
            事件列表，每项包含 title, description, status
        """
        if not dialog_text or not dialog_text.strip():
            debug_log("对话文本为空，跳过事件提取")
            return []

        try:
            client = OpenAI(
                base_url=self._api_base,
                api_key=self._api_key,
            )

            # 构建用户消息
            user_message = ""
            if user_input:
                user_message += f"【玩家说】{user_input}\n\n"
            user_message += f"【GM回复】{dialog_text}"

            response = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": EVENT_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                debug_log("LLM 返回空内容，无事件提取")
                return []

            # 解析 JSON
            result = json.loads(content)
            events = result.get("events", [])

            if not isinstance(events, list):
                warn_log(f"事件提取结果格式异常: events 不是列表")
                return []

            # 过滤无效事件
            valid_events = []
            for event in events:
                if not isinstance(event, dict):
                    continue
                title = event.get("title", "").strip()
                description = event.get("description", "").strip()
                status = event.get("status", "ongoing")
                if not title:
                    continue
                if status not in ("ongoing", "completed"):
                    status = "ongoing"
                valid_events.append({
                    "title": title,
                    "description": description,
                    "status": status,
                })

            if valid_events:
                info_log(f"事件提取完成: 提取到 {len(valid_events)} 个关键事件")
            else:
                debug_log("未提取到关键事件")

            return valid_events

        except json.JSONDecodeError as e:
            warn_log(f"事件提取 JSON 解析失败: {e}")
            return []
        except Exception as e:
            error_log(f"事件提取异常: {e}")
            return []


# 全局单例
_event_extractor: Optional[EventExtractor] = None


def get_event_extractor(config: dict) -> EventExtractor:
    """获取或创建 EventExtractor 单例"""
    global _event_extractor
    if _event_extractor is None:
        _event_extractor = EventExtractor(config)
    return _event_extractor
