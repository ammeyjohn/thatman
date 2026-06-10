"""
HistoryExtractor - 角色历史进程提取服务

从 GM 对话文本中使用 LLM 提取角色历史进程，
保存到 CouchDB 的 history 数据库。

历史提取为异步操作，不阻塞主响应返回。
"""

import json
import logging
import os
import hashlib
from typing import Dict, Any, Optional, List

from openai import OpenAI

from gm_logger import debug_log, info_log, warn_log, error_log

logger = logging.getLogger(__name__)

# 历史提取 prompt
HISTORY_EXTRACTION_SYSTEM_PROMPT = """你是一个修仙世界的史官。你的任务是从游戏对话中提取角色的历史进程记录。

你需要归纳本段对话中角色经历了什么、发生了什么变化，以时间线的形式记录。

请以 JSON 格式返回提取结果，格式如下：
{
  "entry": {
    "period": "时辰时段（如：卯时·清晨）",
    "summary": "本段对话的简要概述（30-80字，描述角色做了什么、发生了什么）",
    "location": "角色所在地点",
    "realm_snapshot": "角色当前境界（如：炼气期·中期）",
    "key_changes": ["关键变化1", "关键变化2"]
  }
}

规则：
1. summary 要精炼概括，突出关键行动和结果，不要复述对话内容
2. key_changes 记录角色状态的重要变化，如境界突破、获得/失去物品、关系变化等，最多5条
3. 如果对话中没有实质性的角色进展（如纯闲聊），返回 {"entry": null}
4. 必须返回合法 JSON，不要包含其他文本
5. period、location、realm_snapshot 从上下文中获取，如果无法确定则留空字符串"""

# 日总结 prompt
DAILY_SUMMARY_SYSTEM_PROMPT = """你是一个修仙世界的史官。你需要根据角色一天内的所有活动记录，撰写一段当日总结。

请以 JSON 格式返回：
{
  "daily_summary": "当日总结（50-150字，概括一天的主要经历和成就）"
}

规则：
1. 总结要涵盖当天最重要的2-3件事
2. 语言简洁有力，体现修仙世界的风格
3. 必须返回合法 JSON"""


class HistoryExtractor:
    """角色历史进程提取器"""

    def __init__(self, config: dict):
        """
        初始化 HistoryExtractor

        Args:
            config: 配置字典，包含 chat_model 段
        """
        self.config = config
        chat_cfg = config.get("chat_model", {})
        self._api_base = os.getenv("GM_CHAT_API_BASE", chat_cfg.get("api_base", "http://localhost:7778/v1"))
        self._api_key = os.getenv("GM_CHAT_API_KEY", chat_cfg.get("api_key", "not-needed"))
        self._model_name = os.getenv("GM_CHAT_MODEL_NAME", chat_cfg.get("model_name", "Qwen3.6-35B-A3B"))
        info_log(f"HistoryExtractor 初始化完成 - 模型: {self._model_name}")

    def _create_client(self) -> OpenAI:
        """创建 OpenAI 客户端（线程安全，每次创建新实例）"""
        return OpenAI(
            base_url=self._api_base,
            api_key=self._api_key,
        )

    def extract_history_entry(
        self,
        dialog_text: str,
        user_input: str = "",
        game_date: str = "",
        game_shichen: str = "",
        location: str = "",
        realm_info: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        从对话文本中提取历史进程 entry

        Args:
            dialog_text: NPC 回复文本
            user_input: 玩家输入文本
            game_date: 游戏日期
            game_shichen: 游戏时辰
            location: 当前地点
            realm_info: 当前境界信息

        Returns:
            历史 entry 字典，包含 period, summary, location, realm_snapshot, key_changes；
            如果无实质进展则返回 None
        """
        if not dialog_text or not dialog_text.strip():
            debug_log("对话文本为空，跳过历史提取")
            return None

        try:
            client = self._create_client()

            # 构建用户消息
            user_message = ""
            if game_date:
                user_message += f"【游戏日期】{game_date}\n"
            if game_shichen:
                user_message += f"【时辰】{game_shichen}\n"
            if location:
                user_message += f"【地点】{location}\n"
            if realm_info:
                user_message += f"【境界】{realm_info}\n"
            user_message += "\n"
            if user_input:
                user_message += f"【玩家说】{user_input}\n\n"
            user_message += f"【GM回复】{dialog_text}"

            response = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": HISTORY_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                debug_log("LLM 返回空内容，无历史提取")
                return None

            # 解析 JSON
            result = json.loads(content)
            entry = result.get("entry")

            if entry is None:
                debug_log("LLM 判定无实质性角色进展，跳过历史记录")
                return None

            if not isinstance(entry, dict):
                warn_log("历史提取结果格式异常: entry 不是字典")
                return None

            # 验证和清理字段
            summary = entry.get("summary", "").strip()
            if not summary:
                debug_log("历史提取 summary 为空，跳过")
                return None

            valid_entry = {
                "period": entry.get("period", game_shichen).strip(),
                "summary": summary,
                "location": entry.get("location", location).strip(),
                "realm_snapshot": entry.get("realm_snapshot", realm_info).strip(),
                "key_changes": [
                    c.strip() for c in entry.get("key_changes", [])
                    if isinstance(c, str) and c.strip()
                ][:5],
            }

            info_log(f"历史提取完成: period={valid_entry['period']}, summary={valid_entry['summary'][:30]}...")
            return valid_entry

        except json.JSONDecodeError as e:
            warn_log(f"历史提取 JSON 解析失败: {e}")
            return None
        except Exception as e:
            error_log(f"历史提取异常: {e}")
            return None

    def generate_daily_summary(self, entries: List[Dict[str, Any]]) -> Optional[str]:
        """
        根据一天的所有 entry 生成日总结

        Args:
            entries: 当天所有历史 entry 列表

        Returns:
            日总结文本，失败返回 None
        """
        if not entries:
            return None

        try:
            client = self._create_client()

            # 构建输入
            entries_text = ""
            for i, entry in enumerate(entries, 1):
                entries_text += f"{i}. [{entry.get('period', '')}] {entry.get('summary', '')}\n"
                changes = entry.get("key_changes", [])
                if changes:
                    entries_text += f"   变化: {', '.join(changes)}\n"

            user_message = f"以下是角色今日的所有活动记录：\n\n{entries_text}\n请撰写今日总结。"

            response = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": DAILY_SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.5,
                max_tokens=512,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                return None

            result = json.loads(content)
            daily_summary = result.get("daily_summary", "").strip()

            if daily_summary:
                info_log(f"日总结生成完成: {daily_summary[:30]}...")
                return daily_summary
            return None

        except Exception as e:
            error_log(f"日总结生成异常: {e}")
            return None

    @staticmethod
    def generate_doc_id(uid: str, game_date: str) -> str:
        """
        生成历史文档 ID

        使用 uid + game_date 的哈希值，确保文档 ID 合法且唯一

        Args:
            uid: 玩家唯一标识
            game_date: 游戏日期

        Returns:
            文档 ID，格式: history_{hash}
        """
        raw = f"{uid}_{game_date}"
        hash_val = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
        return f"history_{hash_val}"


# 全局单例
_history_extractor: Optional[HistoryExtractor] = None


def get_history_extractor(config: dict) -> HistoryExtractor:
    """获取或创建 HistoryExtractor 单例"""
    global _history_extractor
    if _history_extractor is None:
        _history_extractor = HistoryExtractor(config)
    return _history_extractor
