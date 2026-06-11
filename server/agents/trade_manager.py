"""
TradeManager - 交易管理器

管理玩家之间的物品交易流程，包括发起交易、放置物品、确认/取消交易。
交易状态存储在内存中，不持久化到 CouchDB，服务重启后交易数据丢失。
物品转移通过 gm_storage 的 couch_get_player/couch_save_player 更新 inventory。

用法:
    from trade_manager import get_trade_manager

    mgr = get_trade_manager()
    trade = mgr.create_trade("uid_001", "uid_002")
    mgr.offer_items("uid_001", trade["trade_id"], [{"item_id": "herb_001", "name": "灵草", "quantity": 3}])
    mgr.confirm_trade("uid_001", trade["trade_id"])
    mgr.confirm_trade("uid_002", trade["trade_id"])  # 双方确认后自动执行物品转移
"""

import threading
import time
import uuid
from typing import Dict, List, Optional, Any

from gm_logger import debug_log, info_log, warn_log, error_log


class TradeManager:
    """交易管理器（线程安全）"""

    def __init__(self, storage=None):
        """
        初始化交易管理器

        Args:
            storage: GMStorage 实例，用于物品转移时读写玩家 inventory
        """
        self._active_trades: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._storage = storage

    def set_storage(self, storage) -> None:
        """
        设置 GMStorage 实例

        Args:
            storage: GMStorage 实例
        """
        self._storage = storage
        debug_log("TradeManager: storage 实例已设置")

    def create_trade(self, uid: str, target_uid: str) -> dict:
        """
        发起交易请求

        Args:
            uid: 发起方 uid
            target_uid: 目标方 uid

        Returns:
            交易信息字典
        """
        if not uid or not target_uid:
            return {"error": "uid 和 target_uid 不能为空"}

        if uid == target_uid:
            return {"error": "不能与自己交易"}

        # 检查双方是否已有进行中的交易
        with self._lock:
            for trade in self._active_trades.values():
                if trade["status"] != "pending":
                    continue
                participants = {trade["initiator_uid"], trade["target_uid"]}
                if uid in participants and target_uid in participants:
                    return {"error": "双方已有进行中的交易"}

        trade_id = f"trade_{uuid.uuid4().hex[:12]}"
        now = time.time()

        trade = {
            "trade_id": trade_id,
            "initiator_uid": uid,
            "target_uid": target_uid,
            "initiator_items": [],
            "target_items": [],
            "initiator_confirmed": False,
            "target_confirmed": False,
            "status": "pending",
            "created_at": now,
        }

        with self._lock:
            self._active_trades[trade_id] = trade

        info_log(f"交易创建: trade_id={trade_id}, 发起方={uid}, 目标方={target_uid}")

        # 通知目标方
        self._notify_player(target_uid, "trade_request", {
            "trade_id": trade_id,
            "from_uid": uid,
            "message": f"收到交易请求",
        })

        return self._format_trade_info(trade)

    def offer_items(self, uid: str, trade_id: str, items: List[dict]) -> dict:
        """
        放置交易物品

        任意一方放置物品后，双方确认状态重置为未确认。

        Args:
            uid: 放置物品的玩家 uid
            trade_id: 交易 ID
            items: 物品列表，每项包含 {item_id, name, quantity}

        Returns:
            更新后的交易信息字典
        """
        if not trade_id:
            return {"error": "trade_id 不能为空"}

        if not items or not isinstance(items, list):
            return {"error": "items 不能为空且必须为列表"}

        # 验证物品格式
        for item in items:
            if not isinstance(item, dict):
                return {"error": "每个物品必须为字典格式"}
            if "item_id" not in item or "name" not in item or "quantity" not in item:
                return {"error": "每个物品必须包含 item_id, name, quantity 字段"}
            if not isinstance(item["quantity"], int) or item["quantity"] <= 0:
                return {"error": "物品数量必须为正整数"}

        with self._lock:
            trade = self._active_trades.get(trade_id)
            if not trade:
                return {"error": "交易不存在"}

            if trade["status"] != "pending":
                return {"error": f"交易状态为 {trade['status']}，无法放置物品"}

            if uid != trade["initiator_uid"] and uid != trade["target_uid"]:
                return {"error": "你不是交易参与者"}

            # 更新物品列表
            if uid == trade["initiator_uid"]:
                trade["initiator_items"] = items
            else:
                trade["target_items"] = items

            # 放置物品后重置双方确认状态
            trade["initiator_confirmed"] = False
            trade["target_confirmed"] = False

            result = self._format_trade_info(trade)

        info_log(f"交易放置物品: trade_id={trade_id}, uid={uid}, 物品数={len(items)}")

        # 通知对方
        other_uid = trade["target_uid"] if uid == trade["initiator_uid"] else trade["initiator_uid"]
        self._notify_player(other_uid, "trade_offer", {
            "trade_id": trade_id,
            "from_uid": uid,
            "items": items,
            "message": "对方放置了交易物品",
        })

        return result

    def confirm_trade(self, uid: str, trade_id: str) -> dict:
        """
        确认交易

        双方都确认后自动执行物品转移。

        Args:
            uid: 确认方 uid
            trade_id: 交易 ID

        Returns:
            交易信息字典
        """
        if not trade_id:
            return {"error": "trade_id 不能为空"}

        with self._lock:
            trade = self._active_trades.get(trade_id)
            if not trade:
                return {"error": "交易不存在"}

            if trade["status"] != "pending":
                return {"error": f"交易状态为 {trade['status']}，无法确认"}

            if uid != trade["initiator_uid"] and uid != trade["target_uid"]:
                return {"error": "你不是交易参与者"}

            # 设置确认状态
            if uid == trade["initiator_uid"]:
                if trade["initiator_confirmed"]:
                    return {"error": "你已经确认过了"}
                trade["initiator_confirmed"] = True
            else:
                if trade["target_confirmed"]:
                    return {"error": "你已经确认过了"}
                trade["target_confirmed"] = True

            info_log(f"交易确认: trade_id={trade_id}, uid={uid}")

            # 检查是否双方都确认
            if trade["initiator_confirmed"] and trade["target_confirmed"]:
                # 双方确认，执行物品转移
                result = self._execute_trade(trade)
                return result

            # 通知对方
            other_uid = trade["target_uid"] if uid == trade["initiator_uid"] else trade["initiator_uid"]
            self._notify_player(other_uid, "trade_confirmed", {
                "trade_id": trade_id,
                "from_uid": uid,
                "message": "对方已确认交易",
            })

            return self._format_trade_info(trade)

    def cancel_trade(self, uid: str, trade_id: str) -> dict:
        """
        取消交易

        Args:
            uid: 取消方 uid
            trade_id: 交易 ID

        Returns:
            结果字典
        """
        if not trade_id:
            return {"error": "trade_id 不能为空"}

        with self._lock:
            trade = self._active_trades.get(trade_id)
            if not trade:
                return {"error": "交易不存在"}

            if trade["status"] != "pending":
                return {"error": f"交易状态为 {trade['status']}，无法取消"}

            if uid != trade["initiator_uid"] and uid != trade["target_uid"]:
                return {"error": "你不是交易参与者"}

            trade["status"] = "cancelled"

            # 从活跃交易中移除
            del self._active_trades[trade_id]

        info_log(f"交易取消: trade_id={trade_id}, 取消方={uid}")

        # 通知对方
        other_uid = trade["target_uid"] if uid == trade["initiator_uid"] else trade["initiator_uid"]
        self._notify_player(other_uid, "trade_cancelled", {
            "trade_id": trade_id,
            "cancelled_by": uid,
            "message": "交易已被取消",
        })

        return {
            "trade_id": trade_id,
            "status": "cancelled",
            "message": "交易已取消",
        }

    def get_trade_info(self, trade_id: str) -> dict:
        """
        获取交易状态

        Args:
            trade_id: 交易 ID

        Returns:
            交易信息字典
        """
        if not trade_id:
            return {"error": "trade_id 不能为空"}

        with self._lock:
            trade = self._active_trades.get(trade_id)

        if not trade:
            return {"error": "交易不存在或已结束"}

        return self._format_trade_info(trade)

    def get_player_trades(self, uid: str) -> List[dict]:
        """
        获取玩家参与的所有活跃交易

        Args:
            uid: 玩家 uid

        Returns:
            交易信息列表
        """
        with self._lock:
            trades = []
            for trade in self._active_trades.values():
                if trade["status"] == "pending" and (
                    uid == trade["initiator_uid"] or uid == trade["target_uid"]
                ):
                    trades.append(self._format_trade_info(trade))
        return trades

    # ================================================================
    # 内部方法
    # ================================================================

    def _execute_trade(self, trade: dict) -> dict:
        """
        执行交易物品转移（内部方法，需在锁内调用）

        Args:
            trade: 交易数据

        Returns:
            执行结果字典
        """
        trade_id = trade["trade_id"]
        initiator_uid = trade["initiator_uid"]
        target_uid = trade["target_uid"]
        initiator_items = trade["initiator_items"]
        target_items = trade["target_items"]

        debug_log(f"开始执行交易物品转移: trade_id={trade_id}")

        # 检查 storage 是否可用
        if not self._storage:
            error_log(f"交易执行失败: storage 未初始化, trade_id={trade_id}")
            trade["status"] = "cancelled"
            del self._active_trades[trade_id]
            return {"error": "storage 未初始化，无法执行交易"}

        try:
            # 获取双方玩家数据
            initiator_data = self._storage.couch_get_player(initiator_uid)
            target_data = self._storage.couch_get_player(target_uid)

            if not initiator_data or "_id" not in initiator_data:
                error_log(f"交易执行失败: 发起方玩家数据不存在, uid={initiator_uid}")
                trade["status"] = "cancelled"
                del self._active_trades[trade_id]
                return {"error": "发起方玩家数据不存在"}

            if not target_data or "_id" not in target_data:
                error_log(f"交易执行失败: 目标方玩家数据不存在, uid={target_uid}")
                trade["status"] = "cancelled"
                del self._active_trades[trade_id]
                return {"error": "目标方玩家数据不存在"}

            # 获取 inventory
            initiator_inventory = list(initiator_data.get("inventory", []))
            target_inventory = list(target_data.get("inventory", []))

            # 验证发起方物品是否在背包中
            for item in initiator_items:
                if not self._remove_item_from_inventory(initiator_inventory, item):
                    error_log(f"交易执行失败: 发起方物品不足, uid={initiator_uid}, item={item.get('item_id')}")
                    trade["status"] = "cancelled"
                    del self._active_trades[trade_id]
                    return {"error": f"发起方物品不足: {item.get('name', item.get('item_id'))}"}

            # 验证目标方物品是否在背包中
            for item in target_items:
                if not self._remove_item_from_inventory(target_inventory, item):
                    error_log(f"交易执行失败: 目标方物品不足, uid={target_uid}, item={item.get('item_id')}")
                    trade["status"] = "cancelled"
                    del self._active_trades[trade_id]
                    return {"error": f"目标方物品不足: {item.get('name', item.get('item_id'))}"}

            # 将发起方物品添加到目标方背包
            for item in initiator_items:
                self._add_item_to_inventory(target_inventory, item)

            # 将目标方物品添加到发起方背包
            for item in target_items:
                self._add_item_to_inventory(initiator_inventory, item)

            # 保存双方玩家数据
            initiator_data["inventory"] = initiator_inventory
            target_data["inventory"] = target_inventory

            self._storage.couch_save_player(initiator_uid, initiator_data)
            self._storage.couch_save_player(target_uid, target_data)

            # 更新交易状态
            trade["status"] = "completed"
            trade["completed_at"] = time.time()

            # 从活跃交易中移除
            del self._active_trades[trade_id]

            info_log(f"交易完成: trade_id={trade_id}, "
                     f"发起方={initiator_uid}({len(initiator_items)}件) -> "
                     f"目标方={target_uid}({len(target_items)}件)")

            # 通知双方
            self._notify_player(initiator_uid, "trade_completed", {
                "trade_id": trade_id,
                "received_items": target_items,
                "given_items": initiator_items,
                "message": "交易已完成",
            })
            self._notify_player(target_uid, "trade_completed", {
                "trade_id": trade_id,
                "received_items": initiator_items,
                "given_items": target_items,
                "message": "交易已完成",
            })

            return {
                "trade_id": trade_id,
                "status": "completed",
                "initiator_uid": initiator_uid,
                "target_uid": target_uid,
                "initiator_items": initiator_items,
                "target_items": target_items,
                "message": "交易已完成，物品已转移",
            }

        except Exception as e:
            error_log(f"交易执行异常: trade_id={trade_id}, 错误: {e}")
            trade["status"] = "cancelled"
            if trade_id in self._active_trades:
                del self._active_trades[trade_id]
            return {"error": f"交易执行异常: {str(e)}"}

    def _remove_item_from_inventory(self, inventory: list, item: dict) -> bool:
        """
        从背包中移除指定物品

        Args:
            inventory: 背包列表（原地修改）
            item: 要移除的物品 {item_id, name, quantity}

        Returns:
            True 如果移除成功，False 如果物品不足
        """
        item_id = item.get("item_id", "")
        quantity_needed = item.get("quantity", 0)

        # 查找背包中匹配的物品
        quantity_found = 0
        matching_indices = []

        for i, inv_item in enumerate(inventory):
            if not isinstance(inv_item, dict):
                continue
            if inv_item.get("item_id") == item_id:
                quantity_found += inv_item.get("quantity", 0)
                matching_indices.append(i)

        if quantity_found < quantity_needed:
            return False

        # 从后往前移除，避免索引偏移
        remaining = quantity_needed
        for i in reversed(matching_indices):
            inv_item = inventory[i]
            inv_quantity = inv_item.get("quantity", 0)
            if inv_quantity <= remaining:
                remaining -= inv_quantity
                inventory.pop(i)
            else:
                inv_item["quantity"] = inv_quantity - remaining
                remaining = 0
            if remaining <= 0:
                break

        return True

    def _add_item_to_inventory(self, inventory: list, item: dict) -> None:
        """
        向背包中添加物品

        如果背包中已有相同 item_id 的物品，合并数量；否则追加新条目。

        Args:
            inventory: 背包列表（原地修改）
            item: 要添加的物品 {item_id, name, quantity}
        """
        item_id = item.get("item_id", "")
        quantity = item.get("quantity", 0)
        name = item.get("name", "")

        # 查找是否已有相同物品
        for inv_item in inventory:
            if not isinstance(inv_item, dict):
                continue
            if inv_item.get("item_id") == item_id:
                inv_item["quantity"] = inv_item.get("quantity", 0) + quantity
                return

        # 没有找到，追加新条目
        inventory.append({
            "item_id": item_id,
            "name": name,
            "quantity": quantity,
        })

    def _notify_player(self, uid: str, event_type: str, data: dict) -> None:
        """
        通过 EventBus 推送交易通知

        Args:
            uid: 目标玩家 uid
            event_type: 事件类型
            data: 事件数据
        """
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish_to_uid(uid, event_type, data)
            debug_log(f"交易通知已推送: uid={uid}, event={event_type}")
        except Exception as e:
            error_log(f"推送交易通知失败: uid={uid}, event={event_type}, 错误={e}")

    def _format_trade_info(self, trade: dict) -> dict:
        """
        格式化交易信息为返回格式

        Args:
            trade: 内部交易数据

        Returns:
            格式化后的交易信息字典
        """
        return {
            "trade_id": trade["trade_id"],
            "initiator_uid": trade["initiator_uid"],
            "target_uid": trade["target_uid"],
            "initiator_items": trade["initiator_items"],
            "target_items": trade["target_items"],
            "initiator_confirmed": trade["initiator_confirmed"],
            "target_confirmed": trade["target_confirmed"],
            "status": trade["status"],
            "created_at": trade["created_at"],
        }


# ───────────────────────────────────────────────
# 全局单例
# ───────────────────────────────────────────────

_trade_manager_instance: Optional[TradeManager] = None


def get_trade_manager() -> TradeManager:
    """
    获取 TradeManager 单例实例

    Returns:
        TradeManager 实例
    """
    global _trade_manager_instance
    if _trade_manager_instance is None:
        _trade_manager_instance = TradeManager()
    return _trade_manager_instance
