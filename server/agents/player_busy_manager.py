"""
PlayerBusyManager - 玩家动作状态管理器

管理玩家耗时行为的完整状态，包括动作类型、约束、耗时、冷却等。
当玩家执行耗时行为（如打坐修炼、赶路、突破等）时，
游戏时间立即跳过，但玩家进入"动作状态"，
期间不能发起该动作禁止的其他耗时行为，但允许即时行为（聊天、查看背包等）。

冷却时间计算规则：
- 基础30秒 + 每60游戏分钟加10秒
- 上限120秒（2分钟）

动作状态持久化到 CouchDB 玩家文档的 action_state 字段，
防止服务重启后丢失。保留 busy_state 做兼容映射。
"""

import time
from typing import Optional, Dict, Any

from gm_logger import debug_log, info_log, warn_log, error_log


class PlayerBusyManager:
    """玩家动作状态管理器"""

    # 冷却时间计算参数
    BASE_COOLDOWN_SECONDS = 30       # 基础冷却秒数
    COOLDOWN_PER_HOUR = 10           # 每60游戏分钟加10秒
    MAX_COOLDOWN_SECONDS = 120       # 冷却上限秒数

    def __init__(self, storage=None, action_def_manager=None, time_cost_engine=None):
        """
        初始化玩家动作状态管理器

        Args:
            storage: GMStorage 实例，用于持久化状态到 CouchDB
            action_def_manager: ActionDefinitionManager 实例
            time_cost_engine: TimeCostEngine 实例
        """
        self._storage = storage
        self._action_def_manager = action_def_manager
        self._time_cost_engine = time_cost_engine
        # 内存缓存: uid -> action_state dict
        self._action_states: Dict[str, Dict[str, Any]] = {}
        # 兼容旧版 busy_state 缓存
        self._busy_states: Dict[str, Dict[str, Any]] = {}

    def set_busy(self, uid: str, action: str, game_minutes: int) -> Dict[str, Any]:
        """
        设置玩家忙碌状态

        Args:
            uid: 玩家唯一标识
            action: 行为描述（如"打坐修炼"）
            game_minutes: 行为消耗的游戏分钟数

        Returns:
            忙碌状态信息字典
        """
        cooldown_seconds = self._calc_real_cooldown(game_minutes)
        now = time.time()
        cooldown_end = now + cooldown_seconds

        busy_info = {
            "action": action,
            "game_minutes": game_minutes,
            "cooldown_end": cooldown_end,
            "cooldown_seconds": cooldown_seconds,
            "started_at": now,
        }

        # 更新内存缓存
        self._busy_states[uid] = busy_info

        # 持久化到 CouchDB
        self._save_busy_state_to_db(uid, busy_info)

        info_log(f"玩家进入忙碌状态: uid={uid}, action={action}, "
                 f"game_minutes={game_minutes}, cooldown={cooldown_seconds}s")

        return {
            "is_busy": True,
            "action": action,
            "game_minutes": game_minutes,
            "cooldown_seconds": cooldown_seconds,
            "cooldown_end_at": int(cooldown_end * 1000),  # 毫秒时间戳，供前端使用
        }

    def is_busy(self, uid: str) -> bool:
        """
        检查玩家是否处于忙碌状态（冷却未结束）

        Args:
            uid: 玩家唯一标识

        Returns:
            True 如果忙碌且冷却未结束
        """
        busy_info = self._get_busy_info(uid)
        if not busy_info:
            return False

        # 检查冷却是否已结束
        if time.time() >= busy_info.get("cooldown_end", 0):
            # 冷却已结束，自动清除
            self.clear_busy(uid)
            return False

        return True

    def get_busy_info(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家忙碌状态详情

        Args:
            uid: 玩家唯一标识

        Returns:
            忙碌状态信息字典，未忙碌时返回 None
        """
        if not self.is_busy(uid):
            return None

        busy_info = self._busy_states.get(uid)
        if not busy_info:
            return None

        now = time.time()
        remaining = max(0, busy_info["cooldown_end"] - now)

        return {
            "is_busy": True,
            "action": busy_info["action"],
            "game_minutes": busy_info["game_minutes"],
            "cooldown_seconds": busy_info["cooldown_seconds"],
            "cooldown_remaining_seconds": round(remaining, 1),
            "cooldown_end_at": int(busy_info["cooldown_end"] * 1000),
            "started_at": int(busy_info["started_at"] * 1000),
        }

    def clear_busy(self, uid: str) -> None:
        """
        清除玩家忙碌状态（冷却结束或中断）

        Args:
            uid: 玩家唯一标识
        """
        if uid in self._busy_states:
            action = self._busy_states[uid].get("action", "")
            del self._busy_states[uid]
            info_log(f"玩家忙碌状态已清除: uid={uid}, action={action}")

        # 从数据库中清除
        self._clear_busy_state_in_db(uid)

    # ================================================================
    # 新版动作状态管理（action_state）
    # ================================================================

    def start_action(
        self,
        uid: str,
        action_id: str,
        action_name: str = "",
        base_time_cost: int = 0,
        final_time_cost: int = 0,
        modifiers: list = None,
        game_start_time: dict = None,
        restrictions: dict = None,
    ) -> Dict[str, Any]:
        """
        开始一个耗时动作

        Args:
            uid: 玩家唯一标识
            action_id: 动作类型ID
            action_name: 动作显示名称
            base_time_cost: 基础耗时（分钟）
            final_time_cost: 最终耗时（分钟）
            modifiers: 耗时修正项列表
            game_start_time: 游戏开始时间 {"date": str, "hour": int, "minute": int}
            restrictions: 约束规则 {"forbidden_operations": [], "allowed_operations": [], "allow_interrupt": bool}

        Returns:
            动作状态信息字典
        """
        modifiers = modifiers or []
        game_start_time = game_start_time or {}
        restrictions = restrictions or {}

        cooldown_seconds = self._calc_real_cooldown(final_time_cost)
        now = time.time()
        cooldown_end = now + cooldown_seconds

        # 获取动作定义中的中断设置
        allow_interrupt = True
        interrupt_penalty = "none"
        if self._action_def_manager:
            allow_interrupt = self._action_def_manager.can_interrupt(action_id)
            interrupt_penalty = self._action_def_manager.get_interrupt_penalty(action_id)

        action_state = {
            "action_id": action_id,
            "action_name": action_name or action_id,
            "base_time_cost": base_time_cost,
            "final_time_cost": final_time_cost,
            "modifiers": modifiers,
            "game_start_time": game_start_time,
            "real_started_at": now,
            "cooldown_seconds": cooldown_seconds,
            "real_cooldown_end": cooldown_end,
            "restrictions": {
                "forbidden_operations": restrictions.get("forbidden_operations", []),
                "allowed_operations": restrictions.get("allowed_operations", []),
                "allow_interrupt": allow_interrupt,
                "interrupt_penalty": interrupt_penalty,
            },
            "status": "active",
        }

        # 更新内存缓存
        self._action_states[uid] = action_state

        # 同步兼容旧版 busy_state
        self._busy_states[uid] = {
            "action": action_name or action_id,
            "game_minutes": final_time_cost,
            "cooldown_end": cooldown_end,
            "cooldown_seconds": cooldown_seconds,
            "started_at": now,
        }

        # 持久化到数据库
        self._save_action_state_to_db(uid, action_state)

        info_log(
            f"玩家开始动作: uid={uid}, action={action_id}, "
            f"base={base_time_cost}m, final={final_time_cost}m, cooldown={cooldown_seconds}s"
        )

        return self._format_action_state_response(action_state)

    def get_action_state(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家完整动作状态

        Args:
            uid: 玩家唯一标识

        Returns:
            动作状态信息字典，未进行动作时返回 None
        """
        action_state = self._get_action_state_internal(uid)
        if not action_state:
            return None

        # 检查冷却是否已结束
        if time.time() >= action_state.get("real_cooldown_end", 0):
            # 冷却已结束，自动完成
            self.complete_action(uid)
            return None

        return self._format_action_state_response(action_state)

    def has_active_action(self, uid: str) -> bool:
        """
        检查玩家是否有进行中的动作

        Args:
            uid: 玩家唯一标识

        Returns:
            True 如果有进行中的动作
        """
        return self.get_action_state(uid) is not None

    def check_operation_allowed(self, uid: str, operation: str) -> bool:
        """
        检查某操作是否被允许

        Args:
            uid: 玩家唯一标识
            operation: 操作类型

        Returns:
            True 如果允许
        """
        action_state = self._get_action_state_internal(uid)
        if not action_state:
            return True

        # 检查冷却是否已结束
        if time.time() >= action_state.get("real_cooldown_end", 0):
            self.complete_action(uid)
            return True

        # 检查操作是否在禁止列表中
        restrictions = action_state.get("restrictions", {})
        forbidden = restrictions.get("forbidden_operations", [])

        if operation in forbidden:
            return False

        return True

    def interrupt_action(self, uid: str) -> Dict[str, Any]:
        """
        中断玩家当前动作

        Args:
            uid: 玩家唯一标识

        Returns:
            中断结果
        """
        action_state = self._get_action_state_internal(uid)
        if not action_state:
            return {
                "interrupted": False,
                "message": "当前没有进行中的耗时行为",
                "penalty": "none",
            }

        action_id = action_state.get("action_id", "")
        action_name = action_state.get("action_name", "耗时行为")
        restrictions = action_state.get("restrictions", {})

        if not restrictions.get("allow_interrupt", True):
            return {
                "interrupted": False,
                "message": f"【{action_name}】不可中断",
                "penalty": "full",
            }

        # 更新状态为 interrupted
        action_state["status"] = "interrupted"
        action_state["interrupted_at"] = time.time()

        # 更新内存缓存
        self._action_states[uid] = action_state

        # 同步清除旧版 busy_state
        if uid in self._busy_states:
            del self._busy_states[uid]

        # 持久化
        self._save_action_state_to_db(uid, action_state)

        penalty = restrictions.get("interrupt_penalty", "none")
        penalty_desc = {
            "none": "无惩罚",
            "partial": "获得部分效果（50%）",
            "full": "效果全部丧失",
        }.get(penalty, "无惩罚")

        info_log(f"玩家中断动作: uid={uid}, action={action_name}, penalty={penalty}")

        return {
            "interrupted": True,
            "message": f"已中断【{action_name}】，{penalty_desc}",
            "penalty": penalty,
            "action_state": self._format_action_state_response(action_state),
        }

    def complete_action(self, uid: str) -> None:
        """
        标记动作完成（冷却结束后自动调用）

        Args:
            uid: 玩家唯一标识
        """
        action_state = self._get_action_state_internal(uid)
        if not action_state:
            return

        action_name = action_state.get("action_name", "")
        action_state["status"] = "completed"
        action_state["completed_at"] = time.time()

        # 更新内存缓存
        self._action_states[uid] = action_state

        # 同步清除旧版 busy_state
        if uid in self._busy_states:
            del self._busy_states[uid]

        # 持久化
        self._save_action_state_to_db(uid, action_state)

        info_log(f"玩家动作完成: uid={uid}, action={action_name}")

    def _get_action_state_internal(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        获取动作状态（不检查冷却，不格式化）

        Args:
            uid: 玩家唯一标识

        Returns:
            原始动作状态字典
        """
        # 先查内存
        if uid in self._action_states:
            return self._action_states[uid]

        # 内存中没有，尝试从数据库恢复
        db_state = self._load_action_state_from_db(uid)
        if db_state:
            self._action_states[uid] = db_state
            return db_state

        return None

    def _format_action_state_response(self, action_state: Dict[str, Any]) -> Dict[str, Any]:
        """格式化动作状态为前端响应格式"""
        now = time.time()
        cooldown_end = action_state.get("real_cooldown_end", 0)
        remaining = max(0, cooldown_end - now)

        return {
            "is_busy": True,
            "action_id": action_state.get("action_id", ""),
            "action_name": action_state.get("action_name", ""),
            "base_time_cost": action_state.get("base_time_cost", 0),
            "final_time_cost": action_state.get("final_time_cost", 0),
            "modifiers": action_state.get("modifiers", []),
            "game_start_time": action_state.get("game_start_time", {}),
            "cooldown_seconds": action_state.get("cooldown_seconds", 0),
            "cooldown_remaining_seconds": round(remaining, 1),
            "cooldown_end_at": int(cooldown_end * 1000),
            "started_at": int(action_state.get("real_started_at", 0) * 1000),
            "restrictions": action_state.get("restrictions", {}),
            "status": action_state.get("status", "active"),
        }

    def _save_action_state_to_db(self, uid: str, action_state: Dict[str, Any]) -> None:
        """持久化动作状态到 CouchDB 玩家文档"""
        if not self._storage:
            debug_log(f"storage 未初始化，跳过动作状态持久化: uid={uid}")
            return

        try:
            player_data = self._storage.couch_get_player(uid)
            if player_data and "_id" in player_data:
                # 保存新版 action_state
                player_data["action_state"] = action_state
                # 同步保存兼容版 busy_state
                player_data["busy_state"] = {
                    "action": action_state.get("action_name", ""),
                    "game_minutes": action_state.get("final_time_cost", 0),
                    "cooldown_end": action_state.get("real_cooldown_end", 0),
                    "cooldown_seconds": action_state.get("cooldown_seconds", 0),
                    "started_at": action_state.get("real_started_at", 0),
                }
                self._storage.couch_save_player(uid, player_data)
                debug_log(f"动作状态已持久化: uid={uid}")
        except Exception as e:
            error_log(f"持久化动作状态失败: uid={uid}, 错误: {e}")

    def _load_action_state_from_db(self, uid: str) -> Optional[Dict[str, Any]]:
        """从 CouchDB 玩家文档中恢复动作状态"""
        if not self._storage:
            return None

        try:
            player_data = self._storage.couch_get_player(uid)
            if player_data and "action_state" in player_data:
                action_state = player_data["action_state"]
                if action_state and isinstance(action_state, dict) and "action_id" in action_state:
                    # 检查冷却是否已过期
                    if time.time() >= action_state.get("real_cooldown_end", 0):
                        # 冷却已过期，标记为完成
                        action_state["status"] = "completed"
                        self._save_action_state_to_db(uid, action_state)
                        return None
                    return action_state

            # 兼容旧版 busy_state
            if player_data and "busy_state" in player_data:
                busy_state = player_data["busy_state"]
                if busy_state and isinstance(busy_state, dict) and "action" in busy_state:
                    if time.time() >= busy_state.get("cooldown_end", 0):
                        return None
                    # 转换为 action_state 格式
                    migrated = {
                        "action_id": "unknown",
                        "action_name": busy_state.get("action", ""),
                        "base_time_cost": busy_state.get("game_minutes", 0),
                        "final_time_cost": busy_state.get("game_minutes", 0),
                        "modifiers": [],
                        "game_start_time": {},
                        "real_started_at": busy_state.get("started_at", 0),
                        "cooldown_seconds": busy_state.get("cooldown_seconds", 0),
                        "real_cooldown_end": busy_state.get("cooldown_end", 0),
                        "restrictions": {
                            "forbidden_operations": [],
                            "allowed_operations": [],
                            "allow_interrupt": True,
                            "interrupt_penalty": "none",
                        },
                        "status": "active",
                    }
                    return migrated
        except Exception as e:
            error_log(f"从数据库恢复动作状态失败: uid={uid}, 错误: {e}")

        return None

    def _get_busy_info(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        获取忙碌状态信息（不检查冷却是否结束）

        先查内存缓存，再查数据库。

        Args:
            uid: 玩家唯一标识

        Returns:
            忙碌状态信息字典，不存在返回 None
        """
        # 先查内存
        if uid in self._busy_states:
            return self._busy_states[uid]

        # 内存中没有，尝试从数据库恢复
        db_state = self._load_busy_state_from_db(uid)
        if db_state:
            self._busy_states[uid] = db_state
            return db_state

        return None

    def _calc_real_cooldown(self, game_minutes: int) -> int:
        """
        计算真实冷却秒数

        规则：基础30秒 + 每60游戏分钟加10秒，上限120秒

        Args:
            game_minutes: 游戏分钟数

        Returns:
            真实冷却秒数
        """
        cooldown = self.BASE_COOLDOWN_SECONDS
        cooldown += (game_minutes // 60) * self.COOLDOWN_PER_HOUR
        return min(cooldown, self.MAX_COOLDOWN_SECONDS)

    def _save_busy_state_to_db(self, uid: str, busy_info: Dict[str, Any]) -> None:
        """持久化忙碌状态到 CouchDB 玩家文档"""
        if not self._storage:
            debug_log(f"storage 未初始化，跳过忙碌状态持久化: uid={uid}")
            return

        try:
            player_data = self._storage.couch_get_player(uid)
            if player_data and "_id" in player_data:
                player_data["busy_state"] = {
                    "action": busy_info["action"],
                    "game_minutes": busy_info["game_minutes"],
                    "cooldown_end": busy_info["cooldown_end"],
                    "cooldown_seconds": busy_info["cooldown_seconds"],
                    "started_at": busy_info["started_at"],
                }
                self._storage.couch_save_player(uid, player_data)
                debug_log(f"忙碌状态已持久化: uid={uid}")
        except Exception as e:
            error_log(f"持久化忙碌状态失败: uid={uid}, 错误: {e}")

    def _clear_busy_state_in_db(self, uid: str) -> None:
        """从 CouchDB 玩家文档中清除忙碌状态"""
        if not self._storage:
            return

        try:
            player_data = self._storage.couch_get_player(uid)
            if player_data and "_id" in player_data and "busy_state" in player_data:
                player_data["busy_state"] = None
                self._storage.couch_save_player(uid, player_data)
                debug_log(f"数据库中忙碌状态已清除: uid={uid}")
        except Exception as e:
            error_log(f"清除数据库忙碌状态失败: uid={uid}, 错误: {e}")

    def _load_busy_state_from_db(self, uid: str) -> Optional[Dict[str, Any]]:
        """从 CouchDB 玩家文档中恢复忙碌状态"""
        if not self._storage:
            return None

        try:
            player_data = self._storage.couch_get_player(uid)
            if player_data and "busy_state" in player_data:
                busy_state = player_data["busy_state"]
                if busy_state and isinstance(busy_state, dict) and "action" in busy_state:
                    # 检查冷却是否已过期
                    if time.time() >= busy_state.get("cooldown_end", 0):
                        # 冷却已过期，清除数据库中的状态
                        self._clear_busy_state_in_db(uid)
                        return None
                    return busy_state
        except Exception as e:
            error_log(f"从数据库恢复忙碌状态失败: uid={uid}, 错误: {e}")

        return None


# ───────────────────────────────────────────────
# 全局单例引用
# ───────────────────────────────────────────────

_player_busy_manager_instance: Optional["PlayerBusyManager"] = None


def set_player_busy_manager(instance: "PlayerBusyManager"):
    """设置全局 PlayerBusyManager 实例"""
    global _player_busy_manager_instance
    _player_busy_manager_instance = instance


def get_player_busy_manager() -> Optional["PlayerBusyManager"]:
    """获取全局 PlayerBusyManager 实例"""
    return _player_busy_manager_instance
