"""
PlayerBusyManager - 玩家忙碌状态管理器

管理玩家耗时行为的忙碌状态和真实冷却期。
当玩家执行耗时行为（如打坐修炼、赶路、突破等）时，
游戏时间立即跳过，但玩家进入短暂"忙碌"冷却期，
期间不能发起新的耗时行为。

冷却时间计算规则：
- 基础30秒 + 每60游戏分钟加10秒
- 上限120秒（2分钟）

忙碌状态持久化到 CouchDB 玩家文档的 busy_state 字段，
防止服务重启后丢失。
"""

import time
from typing import Optional, Dict, Any

from gm_logger import debug_log, info_log, warn_log, error_log


class PlayerBusyManager:
    """玩家忙碌状态管理器"""

    # 冷却时间计算参数
    BASE_COOLDOWN_SECONDS = 30       # 基础冷却秒数
    COOLDOWN_PER_HOUR = 10           # 每60游戏分钟加10秒
    MAX_COOLDOWN_SECONDS = 120       # 冷却上限秒数

    def __init__(self, storage=None):
        """
        初始化玩家忙碌状态管理器

        Args:
            storage: GMStorage 实例，用于持久化忙碌状态到 CouchDB
        """
        self._storage = storage
        # 内存缓存: uid -> {action, game_minutes, cooldown_end, started_at}
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
