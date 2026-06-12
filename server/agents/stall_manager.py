"""
StallManager - 坊市摊位管理器

管理玩家和NPC的摆摊交易流程，包括创建/关闭摊位、购买/出售物品、灵石结算。
摊位数据持久化到 CouchDB game_stalls 数据库。

用法:
    from stall_manager import get_stall_manager

    mgr = get_stall_manager()
    stall = mgr.create_stall("uid_001", "张三的灵药铺", items=[...])
    mgr.buy_item("uid_002", stall["stall_id"], "herb_001", 3)
    mgr.close_stall("uid_001")
"""

import threading
import time
import uuid
from typing import Dict, List, Optional, Any

from gm_logger import debug_log, info_log, warn_log, error_log


# 灵石兑换比率
STONE_RATIO = 10  # 10下品 = 1中品, 10中品 = 1上品, 10上品 = 1极品

# 灵石品级顺序（低到高）
STONE_GRADES = ["low", "medium", "high", "top"]


class StallManager:
    """坊市摊位管理器（线程安全）"""

    def __init__(self, storage=None):
        """
        初始化摊位管理器

        Args:
            storage: GMStorage 实例，用于读写玩家和摊位数据
        """
        self._lock = threading.Lock()
        self._storage = storage

    def set_storage(self, storage) -> None:
        """设置 GMStorage 实例"""
        self._storage = storage
        debug_log("StallManager: storage 实例已设置")

    # ================================================================
    # 摊位 CRUD
    # ================================================================

    def create_stall(
        self,
        uid: str,
        stall_name: str,
        items: List[dict],
    ) -> dict:
        """
        创建玩家摊位

        从玩家背包中提取物品上架，物品从背包移除。
        未指定价格的物品使用世界均价。

        Args:
            uid: 玩家uid
            stall_name: 摊位名称
            items: 上架物品列表，每项 {item_id, name, type, description, quantity, price?}

        Returns:
            摊位信息字典
        """
        if not uid:
            return {"error": "uid 不能为空"}
        if not stall_name:
            return {"error": "摊位名称不能为空"}
        if not items or not isinstance(items, list):
            return {"error": "上架物品不能为空"}

        # 检查是否已有摊位
        existing = self.get_stall_by_owner(uid)
        if existing and existing.get("status") == "open":
            return {"error": "你已有进行中的摊位，请先关闭"}

        if not self._storage:
            return {"error": "storage 未初始化"}

        try:
            # 获取玩家数据
            player_data = self._storage.couch_get_player(uid)
            if not player_data or "_id" not in player_data:
                return {"error": "玩家数据不存在"}

            inventory = list(player_data.get("inventory", []))
            current_location = player_data.get("current_location", "")

            # 获取均价管理器
            from price_manager import get_price_manager
            price_mgr = get_price_manager()

            # 验证并处理上架物品
            stall_items = []
            for item in items:
                if not isinstance(item, dict):
                    return {"error": "每个物品必须为字典格式"}
                if "item_id" not in item or "name" not in item or "quantity" not in item:
                    return {"error": "每个物品必须包含 item_id, name, quantity 字段"}
                if not isinstance(item["quantity"], int) or item["quantity"] <= 0:
                    return {"error": "物品数量必须为正整数"}

                # 从背包中移除物品
                if not self._remove_item_from_inventory(inventory, item):
                    return {"error": f"背包中物品不足: {item.get('name', item.get('item_id'))}"}

                # 确定价格
                price = item.get("price")
                is_custom_price = price is not None
                if not is_custom_price:
                    price = price_mgr.get_average_price(
                        name=item.get("name", ""),
                        item_type=item.get("type", "其他"),
                        grade=item.get("grade", "凡品"),
                        item_id=item.get("item_id", ""),
                    )

                stall_items.append({
                    "item_id": item["item_id"],
                    "name": item["name"],
                    "type": item.get("type", "其他"),
                    "description": item.get("description", ""),
                    "grade": item.get("grade", "凡品"),
                    "quantity": item["quantity"],
                    "price": max(1, int(price)),
                    "is_custom_price": is_custom_price,
                })

            # 保存玩家数据（更新背包）
            player_data["inventory"] = inventory
            self._storage.couch_save_player(uid, player_data)

            # 创建摊位
            stall_id = f"stall_{uuid.uuid4().hex[:12]}"
            now = time.time()

            stall_data = {
                "type": "stall",
                "stall_id": stall_id,
                "owner_uid": uid,
                "owner_name": player_data.get("name", ""),
                "owner_type": "player",
                "stall_name": stall_name,
                "location": current_location,
                "items": stall_items,
                "status": "open",
                "created_at": now,
                "updated_at": now,
            }

            # 保存摊位到 CouchDB
            self._save_stall_to_couch(stall_id, stall_data)

            info_log(f"摊位创建: stall_id={stall_id}, owner={uid}, name={stall_name}, items={len(stall_items)}")

            # 通知附近玩家
            self._notify_area(current_location, "stall_created", {
                "stall_id": stall_id,
                "owner_uid": uid,
                "owner_name": player_data.get("name", ""),
                "stall_name": stall_name,
                "location": current_location,
            })

            return self._format_stall_info(stall_data)

        except Exception as e:
            error_log(f"创建摊位异常: uid={uid}, 错误: {e}")
            return {"error": f"创建摊位异常: {str(e)}"}

    def create_npc_stall(
        self,
        npc_id: str,
        npc_name: str,
        location: str,
        stall_name: str,
        items: List[dict],
    ) -> dict:
        """
        创建NPC摊位（由LLM GM调用）

        Args:
            npc_id: NPC标识
            npc_name: NPC名称
            location: 摊位位置
            stall_name: 摊位名称
            items: 出售物品列表，每项 {item_id, name, type, description, quantity, price}

        Returns:
            摊位信息字典
        """
        if not npc_id:
            return {"error": "npc_id 不能为空"}
        if not stall_name:
            return {"error": "摊位名称不能为空"}
        if not items or not isinstance(items, list):
            return {"error": "出售物品不能为空"}

        # 检查NPC是否已有摊位
        existing = self.get_stall_by_owner(npc_id)
        if existing and existing.get("status") == "open":
            return {"error": f"NPC {npc_name} 已有进行中的摊位"}

        # 获取均价管理器
        from price_manager import get_price_manager
        price_mgr = get_price_manager()

        stall_items = []
        for item in items:
            if not isinstance(item, dict):
                return {"error": "每个物品必须为字典格式"}
            if "name" not in item or "quantity" not in item:
                return {"error": "每个物品必须包含 name, quantity 字段"}

            price = item.get("price")
            is_custom_price = price is not None
            if not is_custom_price:
                price = price_mgr.get_average_price(
                    name=item.get("name", ""),
                    item_type=item.get("type", "其他"),
                    grade=item.get("grade", "凡品"),
                    item_id=item.get("item_id", ""),
                )

            stall_items.append({
                "item_id": item.get("item_id", f"npc_item_{uuid.uuid4().hex[:6]}"),
                "name": item["name"],
                "type": item.get("type", "其他"),
                "description": item.get("description", ""),
                "grade": item.get("grade", "凡品"),
                "quantity": item["quantity"],
                "price": max(1, int(price)),
                "is_custom_price": is_custom_price,
            })

        stall_id = f"stall_{uuid.uuid4().hex[:12]}"
        now = time.time()

        stall_data = {
            "type": "stall",
            "stall_id": stall_id,
            "owner_uid": npc_id,
            "owner_name": npc_name,
            "owner_type": "npc",
            "stall_name": stall_name,
            "location": location,
            "items": stall_items,
            "status": "open",
            "created_at": now,
            "updated_at": now,
        }

        self._save_stall_to_couch(stall_id, stall_data)

        info_log(f"NPC摊位创建: stall_id={stall_id}, npc={npc_name}, name={stall_name}, items={len(stall_items)}")

        # 通知附近玩家
        self._notify_area(location, "stall_created", {
            "stall_id": stall_id,
            "owner_uid": npc_id,
            "owner_name": npc_name,
            "stall_name": stall_name,
            "location": location,
        })

        return self._format_stall_info(stall_data)

    def close_stall(self, uid: str) -> dict:
        """
        关闭摊位，物品归还背包

        Args:
            uid: 摊主uid

        Returns:
            结果字典
        """
        if not uid:
            return {"error": "uid 不能为空"}

        if not self._storage:
            return {"error": "storage 未初始化"}

        try:
            stall = self.get_stall_by_owner(uid)
            if not stall:
                return {"error": "没有进行中的摊位"}
            if stall.get("status") != "open":
                return {"error": "摊位已关闭"}

            stall_id = stall["stall_id"]

            # 如果是玩家摊位，归还物品到背包
            if stall.get("owner_type") == "player":
                player_data = self._storage.couch_get_player(uid)
                if player_data and "_id" in player_data:
                    inventory = list(player_data.get("inventory", []))
                    for item in stall.get("items", []):
                        self._add_item_to_inventory(inventory, item)
                    player_data["inventory"] = inventory
                    self._storage.couch_save_player(uid, player_data)

            # 更新摊位状态
            stall["status"] = "closed"
            stall["updated_at"] = time.time()
            self._save_stall_to_couch(stall_id, stall)

            info_log(f"摊位关闭: stall_id={stall_id}, owner={uid}")

            # 通知
            self._notify_area(stall.get("location", ""), "stall_closed", {
                "stall_id": stall_id,
                "owner_uid": uid,
                "owner_name": stall.get("owner_name", ""),
                "stall_name": stall.get("stall_name", ""),
            })

            return {
                "stall_id": stall_id,
                "status": "closed",
                "message": "摊位已关闭，物品已归还背包",
            }

        except Exception as e:
            error_log(f"关闭摊位异常: uid={uid}, 错误: {e}")
            return {"error": f"关闭摊位异常: {str(e)}"}

    def get_stall(self, stall_id: str) -> Optional[dict]:
        """
        获取摊位详情

        Args:
            stall_id: 摊位ID

        Returns:
            摊位信息字典，不存在返回None
        """
        if not stall_id:
            return None

        try:
            stall = self._load_stall_from_couch(stall_id)
            if stall and stall.get("status") == "open":
                return self._format_stall_info(stall)
            return None
        except Exception as e:
            error_log(f"获取摊位异常: stall_id={stall_id}, 错误: {e}")
            return None

    def get_stall_by_owner(self, uid: str) -> Optional[dict]:
        """
        获取某角色的摊位

        Args:
            uid: 角色uid

        Returns:
            摊位信息字典，不存在返回None
        """
        if not uid:
            return None

        try:
            stalls = self._find_stalls_in_couch({"owner_uid": uid, "status": "open"})
            if stalls:
                return stalls[0]
            return None
        except Exception as e:
            error_log(f"获取角色摊位异常: uid={uid}, 错误: {e}")
            return None

    def get_stalls_by_location(self, location: str) -> List[dict]:
        """
        获取某位置的所有摊位

        Args:
            location: 位置名称

        Returns:
            摊位信息列表
        """
        if not location:
            return []

        try:
            stalls = self._find_stalls_in_couch({"location": location, "status": "open"})
            return [self._format_stall_info(s) for s in stalls]
        except Exception as e:
            error_log(f"获取位置摊位异常: location={location}, 错误: {e}")
            return []

    # ================================================================
    # 交易操作
    # ================================================================

    def buy_item(
        self,
        buyer_uid: str,
        stall_id: str,
        item_id: str,
        quantity: int = 1,
    ) -> dict:
        """
        从摊位购买物品

        Args:
            buyer_uid: 买家uid
            stall_id: 摊位ID
            item_id: 物品ID
            quantity: 购买数量

        Returns:
            交易结果字典
        """
        if not buyer_uid:
            return {"error": "买家uid不能为空"}
        if not stall_id:
            return {"error": "摊位ID不能为空"}
        if not item_id:
            return {"error": "物品ID不能为空"}
        if not isinstance(quantity, int) or quantity <= 0:
            return {"error": "购买数量必须为正整数"}

        if not self._storage:
            return {"error": "storage 未初始化"}

        with self._lock:
            try:
                # 获取摊位
                stall = self._load_stall_from_couch(stall_id)
                if not stall or stall.get("status") != "open":
                    return {"error": "摊位不存在或已关闭"}

                # 不能买自己的
                if stall["owner_uid"] == buyer_uid:
                    return {"error": "不能购买自己摊位的物品"}

                # 查找物品
                stall_item = None
                for item in stall.get("items", []):
                    if item["item_id"] == item_id:
                        stall_item = item
                        break

                if not stall_item:
                    return {"error": "摊位中没有该物品"}

                if stall_item["quantity"] < quantity:
                    return {"error": f"物品数量不足，当前库存: {stall_item['quantity']}"}

                # 计算总价
                total_price = stall_item["price"] * quantity

                # 获取买家数据
                buyer_data = self._storage.couch_get_player(buyer_uid)
                if not buyer_data or "_id" not in buyer_data:
                    return {"error": "买家数据不存在"}

                buyer_stones = dict(buyer_data.get("spirit_stones", {"low": 0, "medium": 0, "high": 0, "top": 0}))

                # 检查并扣除灵石
                if not self._deduct_spirit_stones(buyer_stones, total_price):
                    return {"error": f"灵石不足，需要 {total_price} 下品灵石"}

                # 买家获得物品
                buyer_inventory = list(buyer_data.get("inventory", []))
                self._add_item_to_inventory(buyer_inventory, {
                    "item_id": stall_item["item_id"],
                    "name": stall_item["name"],
                    "type": stall_item.get("type", "其他"),
                    "description": stall_item.get("description", ""),
                    "quantity": quantity,
                })

                # 保存买家数据
                buyer_data["spirit_stones"] = buyer_stones
                buyer_data["inventory"] = buyer_inventory
                self._storage.couch_save_player(buyer_uid, buyer_data)

                # 卖家获得灵石（如果是玩家摊位）
                if stall.get("owner_type") == "player":
                    seller_data = self._storage.couch_get_player(stall["owner_uid"])
                    if seller_data and "_id" in seller_data:
                        seller_stones = dict(seller_data.get("spirit_stones", {"low": 0, "medium": 0, "high": 0, "top": 0}))
                        self._add_spirit_stones(seller_stones, total_price)
                        seller_data["spirit_stones"] = seller_stones
                        self._storage.couch_save_player(stall["owner_uid"], seller_data)

                # 更新摊位物品数量
                stall_item["quantity"] -= quantity
                if stall_item["quantity"] <= 0:
                    stall["items"] = [i for i in stall["items"] if i["item_id"] != item_id]

                stall["updated_at"] = time.time()
                self._save_stall_to_couch(stall_id, stall)

                info_log(f"摊位购买: buyer={buyer_uid}, stall={stall_id}, item={stall_item['name']}, qty={quantity}, price={total_price}")

                # 通知买家
                self._notify_player(buyer_uid, "trade_completed", {
                    "type": "buy",
                    "stall_id": stall_id,
                    "item_name": stall_item["name"],
                    "quantity": quantity,
                    "total_price": total_price,
                    "message": f"购买了 {stall_item['name']} ×{quantity}，花费 {total_price} 灵石",
                })

                # 通知卖家
                if stall.get("owner_type") == "player":
                    self._notify_player(stall["owner_uid"], "trade_completed", {
                        "type": "sold",
                        "stall_id": stall_id,
                        "item_name": stall_item["name"],
                        "quantity": quantity,
                        "total_price": total_price,
                        "buyer_name": buyer_data.get("name", ""),
                        "message": f"{buyer_data.get('name', '某修士')} 购买了 {stall_item['name']} ×{quantity}，获得 {total_price} 灵石",
                    })

                return {
                    "success": True,
                    "item_name": stall_item["name"],
                    "quantity": quantity,
                    "total_price": total_price,
                    "message": f"购买成功: {stall_item['name']} ×{quantity}，花费 {total_price} 灵石",
                }

            except Exception as e:
                error_log(f"购买物品异常: buyer={buyer_uid}, stall={stall_id}, 错误: {e}")
                return {"error": f"购买物品异常: {str(e)}"}

    def sell_to_stall(
        self,
        seller_uid: str,
        stall_id: str,
        item_id: str,
        quantity: int = 1,
        price: Optional[int] = None,
    ) -> dict:
        """
        向摊位出售物品

        Args:
            seller_uid: 卖家uid
            stall_id: 摊位ID
            item_id: 物品ID
            quantity: 出售数量
            price: 出售单价（下品灵石），不指定则使用世界均价

        Returns:
            交易结果字典
        """
        if not seller_uid:
            return {"error": "卖家uid不能为空"}
        if not stall_id:
            return {"error": "摊位ID不能为空"}
        if not item_id:
            return {"error": "物品ID不能为空"}
        if not isinstance(quantity, int) or quantity <= 0:
            return {"error": "出售数量必须为正整数"}

        if not self._storage:
            return {"error": "storage 未初始化"}

        with self._lock:
            try:
                # 获取摊位
                stall = self._load_stall_from_couch(stall_id)
                if not stall or stall.get("status") != "open":
                    return {"error": "摊位不存在或已关闭"}

                # 不能卖给自己
                if stall["owner_uid"] == seller_uid:
                    return {"error": "不能向自己的摊位出售物品"}

                # 获取卖家数据
                seller_data = self._storage.couch_get_player(seller_uid)
                if not seller_data or "_id" not in seller_data:
                    return {"error": "卖家数据不存在"}

                seller_inventory = list(seller_data.get("inventory", []))

                # 从卖家背包中查找物品
                sell_item = None
                for inv_item in seller_inventory:
                    if not isinstance(inv_item, dict):
                        continue
                    if inv_item.get("item_id") == item_id or inv_item.get("id") == item_id:
                        sell_item = inv_item
                        break

                if not sell_item:
                    return {"error": "背包中没有该物品"}

                available_qty = sell_item.get("quantity", 0)
                if available_qty < quantity:
                    return {"error": f"物品数量不足，当前持有: {available_qty}"}

                # 确定价格
                from price_manager import get_price_manager
                price_mgr = get_price_manager()

                if price is None:
                    price = price_mgr.get_average_price(
                        name=sell_item.get("name", ""),
                        item_type=sell_item.get("type", "其他"),
                        grade=sell_item.get("grade", "凡品"),
                        item_id=item_id,
                    )

                # 出售价为均价的80%（收购折扣）
                sell_price = max(1, int(price * 0.8))
                total_price = sell_price * quantity

                # 检查摊主灵石是否足够（仅玩家摊位）
                if stall.get("owner_type") == "player":
                    owner_data = self._storage.couch_get_player(stall["owner_uid"])
                    if owner_data and "_id" in owner_data:
                        owner_stones = dict(owner_data.get("spirit_stones", {"low": 0, "medium": 0, "high": 0, "top": 0}))
                        if not self._has_enough_spirit_stones(owner_stones, total_price):
                            return {"error": "摊主灵石不足，无法收购"}

                # 从卖家背包移除物品
                if not self._remove_item_from_inventory(seller_inventory, {
                    "item_id": item_id,
                    "name": sell_item.get("name", ""),
                    "quantity": quantity,
                }):
                    return {"error": "从背包移除物品失败"}

                # 卖家获得灵石
                seller_stones = dict(seller_data.get("spirit_stones", {"low": 0, "medium": 0, "high": 0, "top": 0}))
                self._add_spirit_stones(seller_stones, total_price)

                # 保存卖家数据
                seller_data["spirit_stones"] = seller_stones
                seller_data["inventory"] = seller_inventory
                self._storage.couch_save_player(seller_uid, seller_data)

                # 摊主扣除灵石（仅玩家摊位）
                if stall.get("owner_type") == "player":
                    owner_data = self._storage.couch_get_player(stall["owner_uid"])
                    if owner_data and "_id" in owner_data:
                        owner_stones = dict(owner_data.get("spirit_stones", {"low": 0, "medium": 0, "high": 0, "top": 0}))
                        self._deduct_spirit_stones(owner_stones, total_price)
                        owner_data["spirit_stones"] = owner_stones
                        self._storage.couch_save_player(stall["owner_uid"], owner_data)

                # 物品加入摊位
                self._add_item_to_stall(stall, {
                    "item_id": item_id,
                    "name": sell_item.get("name", ""),
                    "type": sell_item.get("type", "其他"),
                    "description": sell_item.get("description", ""),
                    "grade": sell_item.get("grade", "凡品"),
                    "quantity": quantity,
                    "price": max(1, int(price)),  # 转卖价格使用原价
                    "is_custom_price": False,
                })

                stall["updated_at"] = time.time()
                self._save_stall_to_couch(stall_id, stall)

                info_log(f"摊位出售: seller={seller_uid}, stall={stall_id}, item={sell_item.get('name')}, qty={quantity}, price={total_price}")

                # 通知卖家
                self._notify_player(seller_uid, "trade_completed", {
                    "type": "sell",
                    "stall_id": stall_id,
                    "item_name": sell_item.get("name", ""),
                    "quantity": quantity,
                    "total_price": total_price,
                    "message": f"出售了 {sell_item.get('name', '')} ×{quantity}，获得 {total_price} 灵石",
                })

                return {
                    "success": True,
                    "item_name": sell_item.get("name", ""),
                    "quantity": quantity,
                    "total_price": total_price,
                    "message": f"出售成功: {sell_item.get('name', '')} ×{quantity}，获得 {total_price} 灵石",
                }

            except Exception as e:
                error_log(f"出售物品异常: seller={seller_uid}, stall={stall_id}, 错误: {e}")
                return {"error": f"出售物品异常: {str(e)}"}

    # ================================================================
    # 灵石操作
    # ================================================================

    def get_spirit_stones(self, uid: str) -> dict:
        """
        获取玩家灵石余额

        Args:
            uid: 玩家uid

        Returns:
            灵石余额字典
        """
        if not uid:
            return {"error": "uid 不能为空"}

        if not self._storage:
            return {"error": "storage 未初始化"}

        try:
            player_data = self._storage.couch_get_player(uid)
            if not player_data or "_id" not in player_data:
                return {"error": "玩家数据不存在"}

            stones = player_data.get("spirit_stones", {"low": 0, "medium": 0, "high": 0, "top": 0})
            return {
                "uid": uid,
                "spirit_stones": stones,
            }
        except Exception as e:
            error_log(f"获取灵石余额异常: uid={uid}, 错误: {e}")
            return {"error": f"获取灵石余额异常: {str(e)}"}

    def _deduct_spirit_stones(self, stones: dict, amount: int) -> bool:
        """
        从灵石中扣除指定数量（下品灵石），支持自动兑换

        Args:
            stones: 灵石字典 {"low": x, "medium": x, "high": x, "top": x}
            amount: 需要扣除的下品灵石数量

        Returns:
            是否扣除成功
        """
        # 先将所有灵石兑换为下品灵石计算总额
        total_low = self._to_low_stones(stones)
        if total_low < amount:
            return False

        # 从低到高扣除
        remaining = amount
        for grade in STONE_GRADES:
            if remaining <= 0:
                break
            available = stones.get(grade, 0)
            grade_value = self._grade_to_low_value(grade)

            if grade_value > 1 and available > 0:
                # 需要兑换高品灵石
                needed_grades = (remaining + grade_value - 1) // grade_value  # 向上取整
                deduct = min(available, needed_grades)
                stones[grade] = available - deduct
                remaining -= deduct * grade_value
            elif grade_value == 1:
                # 下品灵石直接扣除
                deduct = min(available, remaining)
                stones[grade] = available - deduct
                remaining -= deduct

        # 如果还有剩余（从高品兑换后多出的），加回低品
        if remaining < 0:
            stones["low"] = stones.get("low", 0) + (-remaining)

        return True

    def _add_spirit_stones(self, stones: dict, amount: int) -> None:
        """
        增加灵石（下品灵石），自动进位

        Args:
            stones: 灵石字典
            amount: 增加的下品灵石数量
        """
        stones["low"] = stones.get("low", 0) + amount
        # 自动进位
        for i in range(len(STONE_GRADES) - 1):
            low_grade = STONE_GRADES[i]
            high_grade = STONE_GRADES[i + 1]
            if stones[low_grade] >= STONE_RATIO:
                carry = stones[low_grade] // STONE_RATIO
                stones[low_grade] %= STONE_RATIO
                stones[high_grade] = stones.get(high_grade, 0) + carry

    def _has_enough_spirit_stones(self, stones: dict, amount: int) -> bool:
        """检查灵石是否足够"""
        return self._to_low_stones(stones) >= amount

    def _to_low_stones(self, stones: dict) -> int:
        """将所有灵石兑换为下品灵石总量"""
        total = 0
        for grade in STONE_GRADES:
            total += stones.get(grade, 0) * self._grade_to_low_value(grade)
        return total

    def _grade_to_low_value(self, grade: str) -> int:
        """获取品级对应的下品灵石价值"""
        if grade == "low":
            return 1
        elif grade == "medium":
            return STONE_RATIO
        elif grade == "high":
            return STONE_RATIO ** 2
        elif grade == "top":
            return STONE_RATIO ** 3
        return 1

    # ================================================================
    # 背包操作（复用 trade_manager 逻辑）
    # ================================================================

    def _remove_item_from_inventory(self, inventory: list, item: dict) -> bool:
        """从背包中移除指定物品"""
        item_id = item.get("item_id", "")
        quantity_needed = item.get("quantity", 0)

        quantity_found = 0
        matching_indices = []

        for i, inv_item in enumerate(inventory):
            if not isinstance(inv_item, dict):
                continue
            if inv_item.get("item_id") == item_id or inv_item.get("id") == item_id:
                quantity_found += inv_item.get("quantity", 0)
                matching_indices.append(i)

        if quantity_found < quantity_needed:
            return False

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
        """向背包中添加物品"""
        item_id = item.get("item_id", "")
        quantity = item.get("quantity", 0)
        name = item.get("name", "")

        for inv_item in inventory:
            if not isinstance(inv_item, dict):
                continue
            if inv_item.get("item_id") == item_id:
                inv_item["quantity"] = inv_item.get("quantity", 0) + quantity
                return

        inventory.append({
            "item_id": item_id,
            "name": name,
            "type": item.get("type", "其他"),
            "description": item.get("description", ""),
            "quantity": quantity,
        })

    def _add_item_to_stall(self, stall: dict, item: dict) -> None:
        """向摊位添加物品"""
        for stall_item in stall.get("items", []):
            if stall_item["item_id"] == item["item_id"]:
                stall_item["quantity"] += item["quantity"]
                return

        stall.setdefault("items", []).append(item)

    # ================================================================
    # CouchDB 摊位持久化
    # ================================================================

    def _save_stall_to_couch(self, stall_id: str, stall_data: dict) -> None:
        """保存摊位到 CouchDB"""
        if not self._storage:
            return

        try:
            db_name = self._storage._db_stalls

            # 检查是否已存在
            existing = self._storage._couch_request(
                "GET",
                f"/{db_name}/{stall_id}",
            )
            if existing.status_code == 200:
                rev = existing.json().get("_rev")
                if rev:
                    stall_data["_rev"] = rev

            resp = self._storage._couch_request(
                "PUT",
                f"/{db_name}/{stall_id}",
                json_data=stall_data,
            )
            if resp.status_code in (201, 202):
                debug_log(f"摊位保存成功: {stall_id}")
            else:
                error_log(f"摊位保存失败: {stall_id}, 状态码: {resp.status_code}")

        except Exception as e:
            error_log(f"保存摊位异常: stall_id={stall_id}, 错误: {e}")

    def _load_stall_from_couch(self, stall_id: str) -> Optional[dict]:
        """从 CouchDB 加载摊位"""
        if not self._storage:
            return None

        try:
            db_name = self._storage._db_stalls
            resp = self._storage._couch_request(
                "GET",
                f"/{db_name}/{stall_id}",
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            error_log(f"加载摊位异常: stall_id={stall_id}, 错误: {e}")
            return None

    def _find_stalls_in_couch(self, query: dict) -> List[dict]:
        """在 CouchDB 中查找摊位"""
        if not self._storage:
            return []

        try:
            db_name = self._storage._db_stalls

            # 构建 Mango 查询
            selector = {"type": "stall"}
            selector.update(query)

            body = {
                "selector": selector,
                "limit": 50,
            }

            resp = self._storage._couch_request(
                "POST",
                f"/{db_name}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                docs = resp.json().get("docs", [])
                return docs
            return []
        except Exception as e:
            error_log(f"查找摊位异常: query={query}, 错误: {e}")
            return []

    # ================================================================
    # 通知
    # ================================================================

    def _notify_player(self, uid: str, event_type: str, data: dict) -> None:
        """通过 EventBus 推送通知给玩家"""
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish_to_uid(uid, event_type, data)
            debug_log(f"摊位通知已推送: uid={uid}, event={event_type}")
        except Exception as e:
            error_log(f"推送通知失败: uid={uid}, event={event_type}, 错误={e}")

    def _notify_area(self, location: str, event_type: str, data: dict) -> None:
        """通过 EventBus 推送区域通知"""
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish_to_channel(f"area:{location}", event_type, data)
            debug_log(f"区域通知已推送: location={location}, event={event_type}")
        except Exception as e:
            error_log(f"推送区域通知失败: location={location}, event={event_type}, 错误={e}")

    # ================================================================
    # 格式化
    # ================================================================

    def _format_stall_info(self, stall: dict) -> dict:
        """格式化摊位信息"""
        return {
            "stall_id": stall.get("stall_id", ""),
            "owner_uid": stall.get("owner_uid", ""),
            "owner_name": stall.get("owner_name", ""),
            "owner_type": stall.get("owner_type", "npc"),
            "stall_name": stall.get("stall_name", ""),
            "location": stall.get("location", ""),
            "items": stall.get("items", []),
            "status": stall.get("status", "closed"),
            "created_at": stall.get("created_at", 0),
            "updated_at": stall.get("updated_at", 0),
        }


# ───────────────────────────────────────────────
# 全局单例
# ───────────────────────────────────────────────

_stall_manager_instance: Optional[StallManager] = None


def get_stall_manager() -> StallManager:
    """
    获取 StallManager 单例实例

    Returns:
        StallManager 实例
    """
    global _stall_manager_instance
    if _stall_manager_instance is None:
        _stall_manager_instance = StallManager()
    return _stall_manager_instance
