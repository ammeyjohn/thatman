"""
OnlineManager - 玩家在线状态管理器

追踪玩家在线/离线状态，维护在线玩家列表。
内存存储，不持久化，重启后所有玩家离线。

用法:
    from online_manager import get_online_manager

    mgr = get_online_manager()
    mgr.player_online("uid_001", "张三", "云溪村")
    mgr.player_offline("uid_001")
    online_list = mgr.get_online_players(location="云溪村")
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from gm_logger import debug_log, info_log, warn_log, error_log


@dataclass
class OnlinePlayerInfo:
    """在线玩家信息"""
    uid: str
    character_name: str
    location: str
    realm: str = ""
    realm_stage: str = ""
    status: str = ""
    last_heartbeat: float = 0.0
    online_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "character_name": self.character_name,
            "location": self.location,
            "realm": self.realm,
            "realm_stage": self.realm_stage,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "online_at": self.online_at,
        }


# 心跳超时阈值（秒）
HEARTBEAT_TIMEOUT = 60


class OnlineManager:
    """玩家在线状态管理器（线程安全）"""

    def __init__(self):
        self._online_players: Dict[str, OnlinePlayerInfo] = {}
        self._lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        """启动心跳超时清理线程"""
        if self._running:
            return
        self._running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        info_log("OnlineManager 心跳清理线程已启动")

    def stop(self):
        """停止清理线程"""
        self._running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        info_log("OnlineManager 已停止")

    def _cleanup_loop(self):
        """定期清理超时离线的玩家"""
        while self._running:
            try:
                time.sleep(15)
                self._check_timeouts()
            except Exception as e:
                error_log(f"OnlineManager 清理线程异常: {e}")

    def _check_timeouts(self):
        """检查并移除心跳超时的玩家"""
        now = time.time()
        timeout_uids = []

        with self._lock:
            for uid, info in self._online_players.items():
                if now - info.last_heartbeat > HEARTBEAT_TIMEOUT:
                    timeout_uids.append(uid)

        for uid in timeout_uids:
            self.player_offline(uid, reason="heartbeat_timeout")
            warn_log(f"玩家心跳超时自动离线: uid={uid}")

    def player_online(self, uid: str, character_name: str, location: str,
                      realm: str = "", realm_stage: str = "", status: str = "") -> None:
        """
        标记玩家上线

        Args:
            uid: 玩家唯一标识
            character_name: 角色名
            location: 当前位置
            realm: 境界
            realm_stage: 境界阶段
            status: 当前状态
        """
        now = time.time()
        with self._lock:
            self._online_players[uid] = OnlinePlayerInfo(
                uid=uid,
                character_name=character_name,
                location=location,
                realm=realm,
                realm_stage=realm_stage,
                status=status,
                last_heartbeat=now,
                online_at=now,
            )

        info_log(f"玩家上线: {character_name}({uid}), 位置={location}, 在线人数={len(self._online_players)}")

        # 发布上线事件
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish("player_online", {
                "uid": uid,
                "character_name": character_name,
                "location": location,
                "realm": realm,
                "realm_stage": realm_stage,
                "status": status,
                "online_at": now,
            })
        except Exception as e:
            error_log(f"发布 player_online 事件失败: {e}")

    def player_offline(self, uid: str, reason: str = "manual") -> None:
        """
        标记玩家下线

        Args:
            uid: 玩家唯一标识
            reason: 下线原因（manual/heartbeat_timeout）
        """
        info = None
        with self._lock:
            info = self._online_players.pop(uid, None)

        if info:
            info_log(f"玩家下线: {info.character_name}({uid}), 原因={reason}, 在线人数={len(self._online_players)}")

            # 发布下线事件
            try:
                from event_bus import get_event_bus
                bus = get_event_bus()
                bus.publish("player_offline", {
                    "uid": uid,
                    "character_name": info.character_name,
                    "location": info.location,
                    "reason": reason,
                })
            except Exception as e:
                error_log(f"发布 player_offline 事件失败: {e}")

    def update_heartbeat(self, uid: str) -> bool:
        """
        更新玩家心跳

        Args:
            uid: 玩家唯一标识

        Returns:
            是否成功更新（玩家不在线则返回 False）
        """
        with self._lock:
            info = self._online_players.get(uid)
            if info:
                info.last_heartbeat = time.time()
                return True
        return False

    def update_location(self, uid: str, location: str) -> None:
        """
        更新玩家位置

        Args:
            uid: 玩家唯一标识
            location: 新位置
        """
        old_location = ""
        with self._lock:
            info = self._online_players.get(uid)
            if info:
                old_location = info.location
                info.location = location
                info.last_heartbeat = time.time()

        if old_location and old_location != location:
            debug_log(f"玩家位置变化: uid={uid}, {old_location} -> {location}")

            # 发布位置变化事件
            try:
                from event_bus import get_event_bus
                bus = get_event_bus()
                bus.publish("player_location_change", {
                    "uid": uid,
                    "old_location": old_location,
                    "new_location": location,
                })
            except Exception as e:
                error_log(f"发布 player_location_change 事件失败: {e}")

    def update_status(self, uid: str, status: str) -> None:
        """
        更新玩家状态

        Args:
            uid: 玩家唯一标识
            status: 新状态
        """
        with self._lock:
            info = self._online_players.get(uid)
            if info:
                info.status = status
                info.last_heartbeat = time.time()

    def is_online(self, uid: str) -> bool:
        """检查玩家是否在线"""
        with self._lock:
            return uid in self._online_players

    def get_player_info(self, uid: str) -> Optional[dict]:
        """获取单个在线玩家信息"""
        with self._lock:
            info = self._online_players.get(uid)
            return info.to_dict() if info else None

    def get_online_players(self, location: str = None) -> List[dict]:
        """
        获取在线玩家列表

        Args:
            location: 可选，按位置过滤

        Returns:
            在线玩家信息列表
        """
        with self._lock:
            players = list(self._online_players.values())

        if location:
            players = [p for p in players if p.location == location]

        return [p.to_dict() for p in players]

    def get_online_count(self) -> int:
        """获取在线人数"""
        with self._lock:
            return len(self._online_players)

    def get_nearby_online_players(self, uid: str) -> List[dict]:
        """
        获取与指定玩家同位置的在线玩家（排除自己）

        Args:
            uid: 玩家唯一标识

        Returns:
            同位置在线玩家列表
        """
        with self._lock:
            my_info = self._online_players.get(uid)
            if not my_info:
                return []

            location = my_info.location
            players = [
                p for p in self._online_players.values()
                if p.location == location and p.uid != uid
            ]

        return [p.to_dict() for p in players]


# 模块级单例
_online_manager_instance: Optional[OnlineManager] = None
_instance_lock = threading.Lock()


def get_online_manager() -> OnlineManager:
    """获取 OnlineManager 单例实例"""
    global _online_manager_instance
    if _online_manager_instance is None:
        with _instance_lock:
            if _online_manager_instance is None:
                _online_manager_instance = OnlineManager()
                _online_manager_instance.start()
                info_log("OnlineManager 单例初始化完成")
    return _online_manager_instance
