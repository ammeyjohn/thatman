"""
ActionDefinitionManager - 动作类型定义管理器

管理所有游戏动作类型的定义，支持预定义动作和 GM LLM 动态创建。
每个动作类型包含基础耗时、难度、约束规则（允许/禁止的操作）、耗时影响因子等。

动作定义持久化到 CouchDB 的 action_definitions 数据库。
"""

import time
from typing import Optional, Dict, Any, List

from gm_logger import debug_log, info_log, warn_log, error_log


# ───────────────────────────────────────────────
# 预定义动作类型
# ───────────────────────────────────────────────

DEFAULT_ACTION_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "action_id": "meditate_basic",
        "name": "基础打坐",
        "category": "修炼",
        "base_time_cost": {"min": 30, "max": 60},
        "difficulty": 1,
        "restrictions": {
            "forbidden_operations": ["move", "combat", "gather", "craft", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": True,
            "spirit_concentration_factor": True,
            "weather_factor": False,
        },
        "description": "基础打坐调息，吸纳天地灵气，恢复修为",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "meditate_depth",
        "name": "深度修炼",
        "category": "修炼",
        "base_time_cost": {"min": 120, "max": 240},
        "difficulty": 3,
        "restrictions": {
            "forbidden_operations": ["move", "combat", "gather", "craft", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "partial",
        },
        "time_modifiers": {
            "realm_factor": True,
            "spirit_concentration_factor": True,
            "weather_factor": False,
        },
        "description": "深度闭关修炼，专心吸纳灵气提升修为",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "breakthrough",
        "name": "境界突破",
        "category": "突破",
        "base_time_cost": {"min": 360, "max": 2880},
        "difficulty": 8,
        "restrictions": {
            "forbidden_operations": ["move", "combat", "gather", "craft", "meditate", "chat"],
            "allowed_operations": ["view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": False,
            "interrupt_penalty": "full",
        },
        "time_modifiers": {
            "realm_factor": True,
            "spirit_concentration_factor": True,
            "weather_factor": False,
        },
        "description": "冲击境界瓶颈，一旦开始不可中断",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "move_region",
        "name": "区域内移动",
        "category": "移动",
        "base_time_cost": {"min": 30, "max": 60},
        "difficulty": 1,
        "restrictions": {
            "forbidden_operations": ["combat", "gather", "craft", "meditate", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": True,
        },
        "description": "在同一区域内移动，探索周边环境",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "move_cross_region",
        "name": "跨区域赶路",
        "category": "移动",
        "base_time_cost": {"min": 120, "max": 480},
        "difficulty": 2,
        "restrictions": {
            "forbidden_operations": ["combat", "gather", "craft", "meditate", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": True,
        },
        "description": "跨区域长途跋涉，受地形和天气影响",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "gather",
        "name": "采集资源",
        "category": "采集",
        "base_time_cost": {"min": 30, "max": 90},
        "difficulty": 2,
        "restrictions": {
            "forbidden_operations": ["move", "combat", "craft", "meditate", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": True,
        },
        "description": "采集灵草、矿石、灵药等资源",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "craft_pill",
        "name": "炼丹",
        "category": "炼制",
        "base_time_cost": {"min": 120, "max": 360},
        "difficulty": 4,
        "restrictions": {
            "forbidden_operations": ["move", "combat", "gather", "meditate", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "partial",
        },
        "time_modifiers": {
            "realm_factor": True,
            "spirit_concentration_factor": True,
            "weather_factor": False,
        },
        "description": "炼制丹药，需要专注和灵气环境",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "craft_equip",
        "name": "炼器",
        "category": "炼制",
        "base_time_cost": {"min": 120, "max": 360},
        "difficulty": 4,
        "restrictions": {
            "forbidden_operations": ["move", "combat", "gather", "meditate", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "partial",
        },
        "time_modifiers": {
            "realm_factor": True,
            "spirit_concentration_factor": True,
            "weather_factor": False,
        },
        "description": "炼制法宝、武器、防具",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "combat",
        "name": "战斗",
        "category": "战斗",
        "base_time_cost": {"min": 15, "max": 60},
        "difficulty": 3,
        "restrictions": {
            "forbidden_operations": ["move", "gather", "craft", "meditate", "breakthrough"],
            "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": True,
            "spirit_concentration_factor": False,
            "weather_factor": True,
        },
        "description": "与妖兽、敌人战斗",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "rest",
        "name": "休息进食",
        "category": "休息",
        "base_time_cost": {"min": 15, "max": 30},
        "difficulty": 1,
        "restrictions": {
            "forbidden_operations": ["combat", "gather", "craft", "meditate", "breakthrough"],
            "allowed_operations": ["move", "chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": False,
        },
        "description": "休息恢复体力和精神",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "chat",
        "name": "日常对话",
        "category": "社交",
        "base_time_cost": {"min": 0, "max": 0},
        "difficulty": 0,
        "restrictions": {
            "forbidden_operations": [],
            "allowed_operations": ["move", "combat", "gather", "craft", "meditate", "breakthrough", "chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": False,
        },
        "description": "与NPC或玩家闲聊，不消耗时间",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "view_inventory",
        "name": "查看背包",
        "category": "即时",
        "base_time_cost": {"min": 0, "max": 0},
        "difficulty": 0,
        "restrictions": {
            "forbidden_operations": [],
            "allowed_operations": ["move", "combat", "gather", "craft", "meditate", "breakthrough", "chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": False,
        },
        "description": "查看储物袋中的物品",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "view_equipment",
        "name": "查看装备",
        "category": "即时",
        "base_time_cost": {"min": 0, "max": 0},
        "difficulty": 0,
        "restrictions": {
            "forbidden_operations": [],
            "allowed_operations": ["move", "combat", "gather", "craft", "meditate", "breakthrough", "chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": False,
        },
        "description": "查看已穿戴的装备和法宝",
        "created_by": "system",
        "created_at": 0,
    },
    {
        "action_id": "check_status",
        "name": "查看状态",
        "category": "即时",
        "base_time_cost": {"min": 0, "max": 0},
        "difficulty": 0,
        "restrictions": {
            "forbidden_operations": [],
            "allowed_operations": ["move", "combat", "gather", "craft", "meditate", "breakthrough", "chat", "view_inventory", "view_equipment", "check_status"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": False,
        },
        "description": "查看角色当前状态和属性",
        "created_by": "system",
        "created_at": 0,
    },
]


# ───────────────────────────────────────────────
# 操作类型关键词映射（用于快速识别用户输入）
# ───────────────────────────────────────────────

OPERATION_KEYWORDS: Dict[str, List[str]] = {
    "chat": ["聊", "说", "问", "谈", "告", "吩咐", "吩咐", "吩咐"],
    "view_inventory": ["背包", "储物袋", "物品", "行囊", "包裹", "inventory", "bag"],
    "view_equipment": ["装备", "法宝", "武器", "防具", "穿戴", "equipment", "equip"],
    "check_status": ["状态", "属性", "修为", "境界", "血量", "status", "面板"],
    "move": ["走", "去", "到", "赶", "移动", "前往", "来", "回", "跑", "飞", "遁"],
    "combat": ["打", "杀", "战", "斗", "攻", "砍", "刺", "放", "出招", "战斗"],
    "gather": ["采", "挖", "摘", "捡", "收集", "采集", "gather", "采集"],
    "craft": ["炼", "制", "造", "铸", "打造", "炼丹", "炼器", "craft"],
    "meditate": ["打坐", "修炼", "修行", "吐纳", "闭关", "调息", "meditate"],
    "breakthrough": ["突破", "冲关", "破境", "晋升", "渡劫", "breakthrough"],
    "rest": ["休息", "睡", "吃", "喝", "进食", "恢复", "躺", "rest"],
}


class ActionDefinitionManager:
    """动作类型定义管理器"""

    def __init__(self, storage=None):
        """
        初始化动作定义管理器

        Args:
            storage: GMStorage 实例，用于持久化到 CouchDB
        """
        self._storage = storage
        # 内存缓存: action_id -> definition
        self._definitions: Dict[str, Dict[str, Any]] = {}
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """确保预定义动作已加载到数据库"""
        if self._initialized:
            return

        if self._storage:
            # 从数据库加载所有动作定义
            docs = self._storage.couch_list_action_definitions()
            for doc in docs:
                action_id = doc.get("action_id")
                if action_id:
                    self._definitions[action_id] = doc

            # 如果数据库为空，初始化预定义动作
            if not self._definitions:
                info_log("动作定义数据库为空，初始化预定义动作类型")
                for definition in DEFAULT_ACTION_DEFINITIONS:
                    action_id = definition["action_id"]
                    definition["created_at"] = int(time.time())
                    self._storage.couch_save_action_definition(action_id, definition)
                    self._definitions[action_id] = definition
                info_log(f"已初始化 {len(DEFAULT_ACTION_DEFINITIONS)} 个预定义动作类型")
            else:
                info_log(f"已从数据库加载 {len(self._definitions)} 个动作定义")
        else:
            # storage 不可用，仅使用内存中的预定义动作
            warn_log("storage 未初始化，动作定义仅缓存在内存中")
            for definition in DEFAULT_ACTION_DEFINITIONS:
                self._definitions[definition["action_id"]] = definition

        self._initialized = True

    def get_action_definition(self, action_id: str) -> Optional[Dict[str, Any]]:
        """
        获取动作类型定义

        Args:
            action_id: 动作唯一标识

        Returns:
            动作定义字典，不存在返回 None
        """
        self._ensure_initialized()
        return self._definitions.get(action_id)

    def create_or_update_action(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建或更新动作类型定义

        Args:
            definition: 动作定义字典，必须包含 action_id

        Returns:
            保存后的动作定义
        """
        self._ensure_initialized()

        action_id = definition.get("action_id")
        if not action_id:
            raise ValueError("动作定义必须包含 action_id 字段")

        # 补充默认字段
        if "created_at" not in definition:
            definition["created_at"] = int(time.time())
        if "created_by" not in definition:
            definition["created_by"] = "llm"

        # 更新内存缓存
        self._definitions[action_id] = definition

        # 持久化到数据库
        if self._storage:
            self._storage.couch_save_action_definition(action_id, definition)
            info_log(f"动作定义已保存: {action_id}")
        else:
            warn_log(f"storage 未初始化，动作定义 {action_id} 未持久化")

        return definition

    def list_action_definitions(self, category: str = "") -> List[Dict[str, Any]]:
        """
        列出所有动作类型定义

        Args:
            category: 类别过滤，为空则返回所有

        Returns:
            动作定义列表
        """
        self._ensure_initialized()

        if category:
            return [d for d in self._definitions.values() if d.get("category") == category]
        return list(self._definitions.values())

    def is_operation_allowed(self, action_id: str, operation: str) -> bool:
        """
        检查某操作是否被允许

        Args:
            action_id: 当前动作类型ID
            operation: 要检查的操作类型

        Returns:
            True 如果允许
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            # 未知动作类型，默认允许所有操作
            return True

        restrictions = definition.get("restrictions", {})
        forbidden = restrictions.get("forbidden_operations", [])
        allowed = restrictions.get("allowed_operations", [])

        # 如果在禁止列表中 → 不允许
        if operation in forbidden:
            return False

        # 如果在允许列表中 → 允许
        if operation in allowed:
            return True

        # 默认允许（向前兼容）
        return True

    def get_forbidden_operations(self, action_id: str) -> List[str]:
        """
        获取某动作类型禁止的操作列表

        Args:
            action_id: 动作类型ID

        Returns:
            禁止的操作列表
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            return []
        return definition.get("restrictions", {}).get("forbidden_operations", [])

    def get_allowed_operations(self, action_id: str) -> List[str]:
        """
        获取某动作类型允许的操作列表

        Args:
            action_id: 动作类型ID

        Returns:
            允许的操作列表
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            return []
        return definition.get("restrictions", {}).get("allowed_operations", [])

    def can_interrupt(self, action_id: str) -> bool:
        """
        检查某动作是否允许中断

        Args:
            action_id: 动作类型ID

        Returns:
            True 如果允许中断
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            return True
        return definition.get("restrictions", {}).get("allow_interrupt", True)

    def get_interrupt_penalty(self, action_id: str) -> str:
        """
        获取中断惩罚类型

        Args:
            action_id: 动作类型ID

        Returns:
            惩罚类型: none / partial / full
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            return "none"
        return definition.get("restrictions", {}).get("interrupt_penalty", "none")

    def is_instant_action(self, action_id: str) -> bool:
        """
        检查是否为即时行为（不消耗时间）

        Args:
            action_id: 动作类型ID

        Returns:
            True 如果是即时行为
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            return False
        base_time = definition.get("base_time_cost", {})
        return base_time.get("min", 0) == 0 and base_time.get("max", 0) == 0

    def recognize_operation(self, user_input: str) -> str:
        """
        根据用户输入识别操作类型

        使用关键词匹配，返回最可能的操作类型。
        如果无法识别，返回 "unknown"。

        Args:
            user_input: 用户输入文本

        Returns:
            操作类型标识
        """
        user_input_lower = user_input.lower()

        # 关键词匹配
        scores: Dict[str, int] = {}
        for operation, keywords in OPERATION_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in user_input_lower:
                    score += 1
            if score > 0:
                scores[operation] = score

        if scores:
            # 返回得分最高的操作类型
            return max(scores, key=scores.get)

        return "unknown"

    def get_base_time_cost(self, action_id: str) -> Dict[str, int]:
        """
        获取动作的基础耗时范围

        Args:
            action_id: 动作类型ID

        Returns:
            {"min": x, "max": y}
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            return {"min": 0, "max": 0}
        return definition.get("base_time_cost", {"min": 0, "max": 0})

    def get_action_name(self, action_id: str) -> str:
        """
        获取动作显示名称

        Args:
            action_id: 动作类型ID

        Returns:
            动作名称
        """
        definition = self.get_action_definition(action_id)
        if not definition:
            return action_id
        return definition.get("name", action_id)


# ───────────────────────────────────────────────
# 全局单例引用
# ───────────────────────────────────────────────

_action_definition_manager_instance: Optional["ActionDefinitionManager"] = None


def set_action_definition_manager(instance: "ActionDefinitionManager"):
    """设置全局 ActionDefinitionManager 实例"""
    global _action_definition_manager_instance
    _action_definition_manager_instance = instance


def get_action_definition_manager() -> Optional["ActionDefinitionManager"]:
    """获取全局 ActionDefinitionManager 实例"""
    return _action_definition_manager_instance
