"""
ChatManager - 玩家间聊天管理器

管理私聊和区域聊天消息的发送、存储和推送。

用法:
    from chat_manager import get_chat_manager

    mgr = get_chat_manager()
    mgr.send_private_message("uid_001", "uid_002", "道友你好")
    messages = mgr.get_private_messages("uid_001", "uid_002")
"""

import time
import uuid
import threading
from typing import Dict, Any, List, Optional

from gm_logger import debug_log, info_log, error_log


class ChatManager:
    """玩家间聊天管理器"""

    def __init__(self, storage=None):
        self._storage = storage
        self._lock = threading.Lock()

    def _ensure_storage(self):
        """确保 storage 可用"""
        if self._storage is None:
            try:
                from gm_storage import GMStorage
                import yaml
                from pathlib import Path
                config_path = Path(__file__).parent.parent / "config.yaml"
                config = {}
                if config_path.exists():
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = yaml.safe_load(f) or {}
                self._storage = GMStorage(config)
            except Exception as e:
                error_log(f"ChatManager 初始化 storage 失败: {e}")
        return self._storage

    def send_private_message(self, from_uid: str, to_uid: str, content: str) -> dict:
        """
        发送私聊消息

        Args:
            from_uid: 发送者 uid
            to_uid: 接收者 uid
            content: 消息内容

        Returns:
            消息数据字典
        """
        if not content or not content.strip():
            return {"error": "消息内容不能为空"}

        if from_uid == to_uid:
            return {"error": "不能给自己发消息"}

        storage = self._ensure_storage()
        if not storage:
            return {"error": "存储服务不可用"}

        # 获取发送者和接收者信息
        from_player = storage.couch_get_player(from_uid)
        to_player = storage.couch_get_player(to_uid)

        from_name = from_player.get("name", "") if from_player else ""
        to_name = to_player.get("name", "") if to_player else ""

        if not to_player:
            return {"error": "目标玩家不存在"}

        # 构建消息
        msg_id = f"pmsg_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        timestamp = int(time.time() * 1000)

        msg_data = {
            "from_uid": from_uid,
            "from_name": from_name,
            "to_uid": to_uid,
            "to_name": to_name,
            "content": content.strip(),
            "timestamp": timestamp,
            "read": False,
        }

        # 保存到 CouchDB
        try:
            storage.couch_save_private_message(msg_id, msg_data)
        except Exception as e:
            error_log(f"保存私聊消息失败: {e}")
            return {"error": "消息保存失败"}

        # 通过 EventBus 定向推送给接收者
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish_to_uid(to_uid, "private_message", {
                "from_uid": from_uid,
                "from_name": from_name,
                "to_uid": to_uid,
                "to_name": to_name,
                "content": content.strip(),
                "timestamp": timestamp,
                "msg_id": msg_id,
            })
        except Exception as e:
            error_log(f"推送私聊消息失败: {e}")

        info_log(f"私聊消息: {from_name}({from_uid}) -> {to_name}({to_uid})")

        return {
            "msg_id": msg_id,
            "from_uid": from_uid,
            "from_name": from_name,
            "to_uid": to_uid,
            "to_name": to_name,
            "content": content.strip(),
            "timestamp": timestamp,
        }

    def send_area_message(self, from_uid: str, content: str, location: str = "") -> dict:
        """
        发送区域消息

        Args:
            from_uid: 发送者 uid
            content: 消息内容
            location: 区域位置（如未指定则从玩家数据获取）

        Returns:
            消息数据字典
        """
        if not content or not content.strip():
            return {"error": "消息内容不能为空"}

        storage = self._ensure_storage()
        if not storage:
            return {"error": "存储服务不可用"}

        # 获取发送者信息
        from_player = storage.couch_get_player(from_uid)
        from_name = from_player.get("name", "") if from_player else ""

        if not location and from_player:
            location = from_player.get("current_location", "")

        if not location:
            return {"error": "无法确定区域位置"}

        # 构建消息
        msg_id = f"amsg_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        timestamp = int(time.time() * 1000)

        msg_data = {
            "from_uid": from_uid,
            "from_name": from_name,
            "location": location,
            "content": content.strip(),
            "timestamp": timestamp,
        }

        # 保存到 CouchDB
        try:
            storage.couch_save_area_message(msg_id, msg_data)
        except Exception as e:
            error_log(f"保存区域消息失败: {e}")

        # 通过 EventBus 频道推送
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish_to_channel(f"area:{location}", "area_message", {
                "from_uid": from_uid,
                "from_name": from_name,
                "location": location,
                "content": content.strip(),
                "timestamp": timestamp,
                "msg_id": msg_id,
            })
        except Exception as e:
            error_log(f"推送区域消息失败: {e}")

        info_log(f"区域消息: {from_name}({from_uid}) @ {location}")

        return {
            "msg_id": msg_id,
            "from_uid": from_uid,
            "from_name": from_name,
            "location": location,
            "content": content.strip(),
            "timestamp": timestamp,
        }

    def get_private_messages(self, uid: str, peer_uid: str, limit: int = 50) -> List[dict]:
        """
        获取与某人的私聊记录

        Args:
            uid: 当前用户 uid
            peer_uid: 对方 uid
            limit: 返回条数

        Returns:
            消息列表（按时间倒序）
        """
        storage = self._ensure_storage()
        if not storage:
            return []

        try:
            messages = storage.couch_get_private_messages(uid, peer_uid, limit=limit)
            # 标记为已读
            for msg in messages:
                if msg.get("to_uid") == uid and not msg.get("read", False):
                    try:
                        storage.couch_mark_private_message_read(msg.get("_id", ""))
                    except Exception:
                        pass
            return messages
        except Exception as e:
            error_log(f"获取私聊记录失败: {e}")
            return []

    def get_area_messages(self, location: str, limit: int = 50) -> List[dict]:
        """
        获取区域聊天记录

        Args:
            location: 区域位置
            limit: 返回条数

        Returns:
            消息列表（按时间倒序）
        """
        storage = self._ensure_storage()
        if not storage:
            return []

        try:
            return storage.couch_get_area_messages(location, limit=limit)
        except Exception as e:
            error_log(f"获取区域聊天记录失败: {e}")
            return []

    def get_chat_contacts(self, uid: str) -> List[dict]:
        """
        获取聊天联系人列表（最近聊过的人）

        Args:
            uid: 当前用户 uid

        Returns:
            联系人列表
        """
        storage = self._ensure_storage()
        if not storage:
            return []

        try:
            return storage.couch_get_chat_contacts(uid)
        except Exception as e:
            error_log(f"获取聊天联系人失败: {e}")
            return []


# 模块级单例
_chat_manager_instance: Optional[ChatManager] = None
_instance_lock = threading.Lock()


def get_chat_manager() -> ChatManager:
    """获取 ChatManager 单例实例"""
    global _chat_manager_instance
    if _chat_manager_instance is None:
        with _instance_lock:
            if _chat_manager_instance is None:
                _chat_manager_instance = ChatManager()
                info_log("ChatManager 单例初始化完成")
    return _chat_manager_instance
