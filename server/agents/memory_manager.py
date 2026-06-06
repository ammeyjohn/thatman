"""
Memory Manager - 记忆管理模块

统一管理角色记忆和世界记忆，为 ChatAgent 提供记忆检索和存储接口。
支持根据对话内容自动检索相关记忆，并在适当时候保存新的记忆。

用法:
    from memory_manager import MemoryManager, get_memory_manager

    # 获取记忆管理器实例
    memory_mgr = get_memory_manager(character_id="player_001")

    # 检索相关记忆（自动结合角色记忆和世界记忆）
    memories = memory_mgr.retrieve_memories(
        query="我想学习炼丹",
        conversation_history=messages
    )

    # 保存角色事件记忆
    memory_mgr.save_character_memory(
        content="玩家成功炼制了第一颗筑基丹",
        context="achievement",
        metadata={"type": "炼丹", "result": "success"}
    )

    # 保存世界事件记忆
    memory_mgr.save_world_memory(
        content="青墟历三千零二十四年，灵潮爆发",
        context="world_event",
        metadata={"year": 3024}
    )
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field

# 导入 hindsight_memory 模块
from hindsight_memory import (
    HindsightMemoryStore,
    get_world_memory_store,
    get_character_memory_store,
    get_memory_store,
    debug_log,
    info_log,
    warn_log,
    error_log,
)

# 配置日志
logger = logging.getLogger(__name__)


@dataclass
class MemoryConfig:
    """记忆管理配置"""
    # 世界记忆库配置
    world_bank: str = "world"
    world_memories_limit: int = 5  # 检索世界记忆数量

    # 角色记忆库配置
    character_memories_limit: int = 5  # 检索角色记忆数量

    # 记忆阈值
    min_relevance_score: float = 0.5  # 最低相关度分数

    # 自动保存配置
    auto_save_character_events: bool = True  # 自动保存角色事件
    auto_save_world_events: bool = False  # 是否自动保存世界事件（通常由GM系统控制）

    # 记忆上下文标签
    context_tags = {
        "character_history": "角色历史",
        "character_relationship": "角色关系",
        "character_achievement": "角色成就",
        "world_event": "世界事件",
        "world_lore": "世界设定",
        "world_location": "地点信息",
        "world_npc": "NPC信息",
    }


class MemoryManager:
    """
    记忆管理器

    统一管理角色记忆和世界记忆，提供统一的检索和存储接口。
    自动根据对话内容检索相关记忆，并在适当时候保存新的记忆。
    """

    def __init__(
        self,
        character_id: Optional[str] = None,
        user_id: Optional[str] = None,
        config: Optional[MemoryConfig] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        初始化记忆管理器

        Args:
            character_id: 角色ID，用于角色记忆库
            user_id: 用户ID，用于用户个人记忆库（聊天记忆保存到这里）
            config: 记忆配置
            base_url: Hindsight 服务地址
            api_key: API 密钥
        """
        self.character_id = character_id
        self.user_id = user_id
        self.config = config or MemoryConfig()
        self.base_url = base_url or os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888")
        self.api_key = api_key or os.getenv("HINDSIGHT_API_KEY")

        # 记忆库实例
        self._world_store: Optional[HindsightMemoryStore] = None
        self._character_store: Optional[HindsightMemoryStore] = None
        self._user_store: Optional[HindsightMemoryStore] = None

        # 初始化
        self._init_stores()

    def _init_stores(self) -> None:
        """初始化记忆库连接"""
        try:
            # 初始化世界记忆库
            self._world_store = get_world_memory_store(
                base_url=self.base_url,
                api_key=self.api_key,
            )
            debug_log(f"世界记忆库初始化成功")

            # 初始化角色记忆库（如果提供了角色ID）
            if self.character_id:
                self._character_store = get_character_memory_store(
                    character_id=self.character_id,
                    base_url=self.base_url,
                    api_key=self.api_key,
                )
                debug_log(f"角色记忆库初始化成功: {self.character_id}")

            # 初始化用户记忆库（如果提供了用户ID）
            if self.user_id:
                self._user_store = get_memory_store(
                    bank_id=self.user_id,
                    base_url=self.base_url,
                    api_key=self.api_key,
                )
                debug_log(f"用户记忆库初始化成功: {self.user_id}")

        except Exception as e:
            error_log(f"记忆库初始化失败: {e}")
            raise

    def retrieve_memories(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        include_world: bool = True,
        include_character: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        检索相关记忆

        根据查询内容从世界记忆库和角色记忆库中检索相关记忆。

        Args:
            query: 查询内容
            conversation_history: 对话历史，用于增强检索
            include_world: 是否包含世界记忆
            include_character: 是否包含角色记忆（需要设置 character_id）

        Returns:
            包含 world_memories 和 character_memories 的字典
        """
        result = {
            "world_memories": [],
            "character_memories": [],
        }

        # 构建增强查询
        enhanced_query = self._build_enhanced_query(query, conversation_history)

        # 检索世界记忆
        if include_world and self._world_store:
            try:
                world_memories = self._world_store.recall(
                    query=enhanced_query,
                    n=self.config.world_memories_limit,
                )
                # 过滤低相关度记忆
                result["world_memories"] = [
                    mem for mem in world_memories
                    if mem.get("score", 0) >= self.config.min_relevance_score
                ]
                debug_log(f"检索到 {len(result['world_memories'])} 条相关世界记忆")
            except Exception as e:
                warn_log(f"检索世界记忆失败: {e}")

        # 检索角色记忆
        if include_character and self._character_store:
            try:
                character_memories = self._character_store.recall(
                    query=enhanced_query,
                    n=self.config.character_memories_limit,
                )
                # 过滤低相关度记忆
                result["character_memories"] = [
                    mem for mem in character_memories
                    if mem.get("score", 0) >= self.config.min_relevance_score
                ]
                debug_log(f"检索到 {len(result['character_memories'])} 条相关角色记忆")
            except Exception as e:
                warn_log(f"检索角色记忆失败: {e}")

        return result

    def retrieve_memories_as_context(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        检索记忆并格式化为上下文字符串

        将检索到的世界记忆和角色记忆格式化为可供 LLM 使用的上下文字符串。

        Args:
            query: 查询内容
            conversation_history: 对话历史

        Returns:
            格式化的记忆上下文字符串
        """
        memories = self.retrieve_memories(query, conversation_history)

        context_parts = []

        # 世界记忆部分
        world_memories = memories.get("world_memories", [])
        if world_memories:
            context_parts.append("【世界背景知识】")
            for i, mem in enumerate(world_memories, 1):
                content = mem.get("content", "").strip()
                if content:
                    context_parts.append(f"{i}. {content}")
            context_parts.append("")

        # 角色记忆部分
        character_memories = memories.get("character_memories", [])
        if character_memories:
            context_parts.append("【角色过往经历】")
            for i, mem in enumerate(character_memories, 1):
                content = mem.get("content", "").strip()
                if content:
                    context_parts.append(f"{i}. {content}")
            context_parts.append("")

        return "\n".join(context_parts)

    def save_character_memory(
        self,
        content: str,
        context: str = "character_history",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        保存角色记忆

        Args:
            content: 记忆内容
            context: 上下文标签
            metadata: 附加元数据

        Returns:
            True 表示保存成功
        """
        if not self._character_store:
            warn_log("未设置角色ID，无法保存角色记忆")
            return False

        try:
            success = self._character_store.retain(
                content=content,
                context=context,
                metadata=metadata or {},
            )
            if success:
                debug_log(f"角色记忆保存成功: {content[:50]}...")
            return success
        except Exception as e:
            error_log(f"保存角色记忆失败: {e}")
            return False

    def save_world_memory(
        self,
        content: str,
        context: str = "world_event",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        保存世界记忆

        Args:
            content: 记忆内容
            context: 上下文标签
            metadata: 附加元数据

        Returns:
            True 表示保存成功
        """
        if not self._world_store:
            warn_log("世界记忆库未初始化")
            return False

        try:
            success = self._world_store.retain(
                content=content,
                context=context,
                metadata=metadata or {},
            )
            if success:
                debug_log(f"世界记忆保存成功: {content[:50]}...")
            return success
        except Exception as e:
            error_log(f"保存世界记忆失败: {e}")
            return False

    def save_user_memory(
        self,
        content: str,
        context: str = "conversation",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        保存用户记忆到用户个人记忆库

        Args:
            content: 记忆内容
            context: 上下文标签
            metadata: 附加元数据

        Returns:
            True 表示保存成功
        """
        if not self._user_store:
            warn_log("未设置用户ID，无法保存用户记忆")
            return False

        try:
            success = self._user_store.retain(
                content=content,
                context=context,
                metadata=metadata or {},
            )
            if success:
                debug_log(f"用户记忆保存成功: {content[:50]}...")
            return success
        except Exception as e:
            error_log(f"保存用户记忆失败: {e}")
            return False

    def save_conversation_memory(
        self,
        messages: List[Dict[str, str]],
        importance: str = "normal",
    ) -> bool:
        """
        保存对话中的重要记忆

        分析对话内容，提取重要信息保存到角色记忆库。

        Args:
            messages: 对话消息列表
            importance: 重要程度 (low, normal, high, critical)

        Returns:
            True 表示保存成功
        """
        if not self._character_store or not messages:
            return False

        # 根据重要程度决定是否保存
        if importance == "low":
            return False

        # 提取最后一条用户消息和助手回复
        user_msg = None
        assistant_msg = None

        for msg in reversed(messages):
            role = msg.get("role", "")
            if role == "user" and not user_msg:
                user_msg = msg.get("content", "")
            elif role == "assistant" and not assistant_msg:
                assistant_msg = msg.get("content", "")

            if user_msg and assistant_msg:
                break

        if not user_msg:
            return False

        # 构建记忆内容
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

        # 根据重要程度设置上下文
        context_map = {
            "normal": "character_history",
            "high": "character_achievement",
            "critical": "character_achievement",
        }
        context = context_map.get(importance, "character_history")

        return self.save_character_memory(
            content=memory_content,
            context=context,
            metadata={
                "importance": importance,
                "type": "conversation",
            }
        )

    def get_character_stats(self) -> Dict[str, Any]:
        """获取角色记忆库统计信息"""
        if self._character_store:
            return self._character_store.get_stats()
        return {}

    def get_world_stats(self) -> Dict[str, Any]:
        """获取世界记忆库统计信息"""
        if self._world_store:
            return self._world_store.get_stats()
        return {}

    def _build_enhanced_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        构建增强查询

        结合当前查询和对话历史构建更全面的查询内容。

        Args:
            query: 当前查询
            conversation_history: 对话历史

        Returns:
            增强后的查询字符串
        """
        if not conversation_history:
            return query

        # 取最近3轮对话
        recent = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history

        # 提取关键内容
        key_parts = [query]

        for msg in recent:
            content = msg.get("content", "").strip()
            if len(content) > 10:  # 过滤太短的片段
                # 只取前100字符避免查询过长
                key_parts.append(content[:100])

        return " ".join(key_parts)

    def close(self) -> None:
        """关闭所有记忆库连接"""
        if self._world_store:
            self._world_store.close()
            self._world_store = None

        if self._character_store:
            self._character_store.close()
            self._character_store = None

        debug_log("记忆管理器已关闭")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False


# ───────────────────────────────────────────────
# 便捷函数
# ───────────────────────────────────────────────

# 全局记忆管理器缓存
_memory_managers: Dict[str, MemoryManager] = {}


def get_memory_manager(
    character_id: Optional[str] = None,
    user_id: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> MemoryManager:
    """
    获取记忆管理器实例（带缓存）

    Args:
        character_id: 角色ID
        user_id: 用户ID
        base_url: Hindsight 服务地址
        api_key: API 密钥

    Returns:
        MemoryManager 实例
    """
    cache_key = f"{character_id or '_no_char_'}_{user_id or '_no_user_'}"

    if cache_key not in _memory_managers:
        _memory_managers[cache_key] = MemoryManager(
            character_id=character_id,
            user_id=user_id,
            base_url=base_url,
            api_key=api_key,
        )

    return _memory_managers[cache_key]


def clear_memory_manager_cache() -> None:
    """清空记忆管理器缓存"""
    global _memory_managers
    for mgr in _memory_managers.values():
        mgr.close()
    _memory_managers = {}
    debug_log("记忆管理器缓存已清空")


def extract_key_events_from_response(
    response: str,
) -> List[Dict[str, str]]:
    """
    从AI响应中提取关键事件

    简单的启发式方法，识别响应中的重要事件描述。

    Args:
        response: AI 响应内容

    Returns:
        关键事件列表
    """
    events = []

    # 识别成就/突破类描述
    achievement_keywords = [
        "突破", "成功", "获得", "领悟", "炼制成功",
        "击败", "完成", "达成", "晋升", "觉醒"
    ]

    # 识别关系类描述
    relationship_keywords = [
        "结识", "拜师", "收徒", "结盟", "结仇",
        "背叛", "相助", "相救", "相识"
    ]

    # 简单分句
    sentences = response.replace("。", "|").replace("！", "|").replace("？", "|").split("|")

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 10:
            continue

        # 检查是否包含成就关键词
        for keyword in achievement_keywords:
            if keyword in sentence:
                events.append({
                    "content": sentence,
                    "type": "achievement",
                    "context": "character_achievement",
                })
                break

        # 检查是否包含关系关键词
        for keyword in relationship_keywords:
            if keyword in sentence:
                events.append({
                    "content": sentence,
                    "type": "relationship",
                    "context": "character_relationship",
                })
                break

    return events


if __name__ == "__main__":
    # 测试代码
    info_log("测试 MemoryManager...")

    try:
        # 测试记忆管理器
        mgr = get_memory_manager(character_id="test_player")

        # 测试保存记忆
        mgr.save_character_memory(
            content="测试角色在青墟山脚下遇到了一位神秘老者",
            context="character_history",
            metadata={"location": "青墟山", "npc": "神秘老者"}
        )

        mgr.save_world_memory(
            content="青墟山是修仙界著名的灵脉汇聚之地",
            context="world_location",
            metadata={"region": "青墟山脉"}
        )

        # 测试检索记忆
        memories = mgr.retrieve_memories("青墟山")
        info_log(f"检索到 {len(memories['world_memories'])} 条世界记忆")
        info_log(f"检索到 {len(memories['character_memories'])} 条角色记忆")

        # 测试格式化为上下文
        context = mgr.retrieve_memories_as_context("青墟山")
        print("\n格式化的记忆上下文:")
        print(context)

        # 统计信息
        info_log(f"世界记忆库统计: {mgr.get_world_stats()}")
        info_log(f"角色记忆库统计: {mgr.get_character_stats()}")

        mgr.close()

    except Exception as e:
        error_log(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
