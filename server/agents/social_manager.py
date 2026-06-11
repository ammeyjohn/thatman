"""
SocialManager - 修仙游戏社交关系管理器

管理好友系统、师徒系统、道侣系统三大社交子系统，
所有社交关系数据存储在 CouchDB game_links 数据库中。

用法:
    from social_manager import get_social_manager

    sm = get_social_manager(config)

    # 好友系统
    sm.send_friend_request("uid_001", "uid_002")
    sm.accept_friend_request("uid_002", "uid_001")
    sm.get_friends("uid_001")

    # 师徒系统
    sm.send_master_request("uid_002", "uid_001")  # uid_002 拜师 uid_001
    sm.accept_master_request("uid_001", "uid_002")
    sm.get_master_info("uid_002")

    # 道侣系统
    sm.send_companion_request("uid_001", "uid_002")
    sm.accept_companion_request("uid_002", "uid_001")
    sm.get_companion_info("uid_001")
"""

import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import httpx

from gm_logger import debug_log, info_log, warn_log, error_log
from event_bus import get_event_bus


# ───────────────────────────────────────────────
# 社交关系类型常量
# ───────────────────────────────────────────────

LINK_TYPE_FRIEND = "friend"
LINK_TYPE_FRIEND_REQUEST = "friend_request"
LINK_TYPE_MASTER_DISCIPLE = "master_disciple"
LINK_TYPE_MASTER_REQUEST = "master_request"
LINK_TYPE_DAO_COMPANION = "dao_companion"
LINK_TYPE_COMPANION_REQUEST = "companion_request"

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"


class SocialManager:
    """
    修仙游戏社交关系管理器

    管理好友、师徒、道侣三大社交子系统，
    使用 CouchDB game_links 数据库存储关系数据，
    通过 EventBus 推送社交通知。
    """

    def __init__(self, config: dict):
        """
        初始化 SocialManager

        Args:
            config: 配置字典，包含 CouchDB 连接参数
        """
        self.config = config

        # ── CouchDB 配置 ──
        couch_cfg = config.get("couchdb", {})
        self._couch_url: str = couch_cfg.get("url", "http://localhost:5984").rstrip("/")
        self._couch_db_prefix: str = couch_cfg.get("db_prefix", "game_")
        self._couch_user: str = couch_cfg.get("user", "admin")
        self._couch_password: str = couch_cfg.get("password", "password")

        # CouchDB 数据库名
        self._db_links: str = f"{self._couch_db_prefix}links"

        # 线程本地存储，避免多线程共享 httpx.Client 导致连接池损坏
        self._couch_local = threading.local()

        # 操作锁，保证同一社交操作的原子性
        self._lock = threading.Lock()

        # 确保 CouchDB 数据库存在
        self._ensure_couch_db()

        # 确保 Mango 索引存在
        self._ensure_indexes()

        info_log("SocialManager 初始化完成")

    # ================================================================
    # CouchDB 辅助方法
    # ================================================================

    @property
    def _couch_client(self) -> httpx.Client:
        """
        获取当前线程的 CouchDB httpx.Client（线程安全）

        httpx.Client 不是线程安全的，多线程共享同一个实例会导致
        连接池状态损坏，后续请求永久挂起。使用线程本地存储确保
        每个线程拥有独立的 httpx.Client 实例。
        """
        client = getattr(self._couch_local, "client", None)
        if client is None:
            client = httpx.Client(
                base_url=self._couch_url,
                auth=(self._couch_user, self._couch_password),
                headers={"Content-Type": "application/json"},
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_keepalive_connections=0),
            )
            self._couch_local.client = client
        return client

    def _couch_request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[dict] = None,
    ) -> httpx.Response:
        """
        发送 CouchDB HTTP 请求

        Args:
            method: HTTP 方法
            path: 请求路径
            json_data: JSON 请求体

        Returns:
            httpx.Response
        """
        response = self._couch_client.request(
            method=method,
            url=path,
            json=json_data,
        )
        return response

    def _ensure_couch_db(self) -> None:
        """确保 CouchDB links 数据库存在"""
        try:
            resp = self._couch_client.head(f"/{self._db_links}")
            if resp.status_code == 404:
                resp = self._couch_client.put(f"/{self._db_links}")
                if resp.status_code in (201, 202):
                    info_log(f"CouchDB 数据库已创建: {self._db_links}")
                else:
                    warn_log(f"CouchDB 数据库创建失败: {self._db_links}, 状态码: {resp.status_code}")
            else:
                debug_log(f"CouchDB 数据库已存在: {self._db_links}")
        except Exception as e:
            error_log(f"检查/创建 CouchDB 数据库失败: {self._db_links}, 错误: {e}")

    def _ensure_indexes(self) -> None:
        """确保 game_links 数据库有必要的 Mango 索引"""
        indexes = [
            {
                "index": {"fields": ["link_type"]},
                "name": "link_type-index",
                "type": "json",
            },
            {
                "index": {"fields": ["link_type", "status"]},
                "name": "link_type-status-index",
                "type": "json",
            },
            {
                "index": {"fields": ["link_type", "from_uid", "to_uid"]},
                "name": "link_type-from-to-index",
                "type": "json",
            },
        ]
        for index_doc in indexes:
            try:
                resp = self._couch_request(
                    "POST",
                    f"/{self._db_links}/_index",
                    json_data=index_doc,
                )
                if resp.status_code in (200, 201):
                    debug_log(f"links 索引创建/已存在: {index_doc['name']}")
                else:
                    warn_log(f"links 索引创建失败: {index_doc['name']}, 状态码={resp.status_code}")
            except Exception as e:
                error_log(f"links 索引创建异常: {index_doc['name']}, 错误: {e}")

    def _find_links(self, selector: dict, limit: int = 100) -> list:
        """
        通用 Mango 查询方法

        Args:
            selector: Mango 查询选择器
            limit: 返回文档数量上限

        Returns:
            匹配的文档列表
        """
        try:
            body = {"selector": selector, "limit": limit}
            resp = self._couch_request(
                "POST",
                f"/{self._db_links}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                return docs
            else:
                warn_log(f"Mango 查询失败: 状态码={resp.status_code}, 响应={resp.text[:200]}")
                return []
        except Exception as e:
            error_log(f"Mango 查询异常: {e}")
            return []

    def _save_link_doc(self, doc: dict) -> dict:
        """
        保存 link 文档到 CouchDB

        如果文档包含 _id 则使用 PUT，否则使用 POST 自动生成 ID。

        Args:
            doc: 文档数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            doc_id = doc.get("_id")
            if doc_id:
                # 检查是否已存在，获取 _rev
                resp = self._couch_request("GET", f"/{self._db_links}/{doc_id}")
                if resp.status_code == 200:
                    existing = resp.json()
                    if "_rev" in existing:
                        doc["_rev"] = existing["_rev"]
                resp = self._couch_request("PUT", f"/{self._db_links}/{doc_id}", json_data=doc)
            else:
                resp = self._couch_request("POST", f"/{self._db_links}", json_data=doc)

            if resp.status_code in (201, 202):
                return resp.json()
            else:
                warn_log(f"保存 link 文档失败: 状态码={resp.status_code}, 响应={resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存 link 文档异常: {e}")
            return {}

    def _delete_link_doc(self, doc_id: str, rev: str) -> bool:
        """
        删除 link 文档

        Args:
            doc_id: 文档 ID
            rev: 文档修订版本

        Returns:
            True 表示删除成功，False 表示失败
        """
        try:
            resp = self._couch_request(
                "DELETE",
                f"/{self._db_links}/{doc_id}?rev={rev}",
            )
            if resp.status_code in (200, 202):
                return True
            else:
                warn_log(f"删除 link 文档失败: doc_id={doc_id}, 状态码={resp.status_code}")
                return False
        except Exception as e:
            error_log(f"删除 link 文档异常: doc_id={doc_id}, 错误={e}")
            return False

    def _now_iso(self) -> str:
        """获取当前 UTC 时间的 ISO 格式字符串"""
        return datetime.now(timezone.utc).isoformat()

    def _notify_user(self, uid: str, event_type: str, data: dict) -> None:
        """
        通过 EventBus 向指定用户推送通知

        Args:
            uid: 目标用户 uid
            event_type: 事件类型
            data: 事件数据
        """
        try:
            bus = get_event_bus()
            bus.publish_to_uid(uid, event_type, data)
            debug_log(f"社交通知已推送: uid={uid}, event={event_type}")
        except Exception as e:
            error_log(f"社交通知推送失败: uid={uid}, event={event_type}, 错误={e}")

    # ================================================================
    # 好友系统
    # ================================================================

    def send_friend_request(self, uid: str, target_uid: str) -> dict:
        """
        发送好友申请

        检查是否已经是好友、是否已有待处理申请，避免重复发送。

        Args:
            uid: 发起者 uid
            target_uid: 目标 uid

        Returns:
            操作结果字典，包含 success 和 message 字段
        """
        if uid == target_uid:
            return {"success": False, "message": "不能向自己发送好友申请"}

        with self._lock:
            # 检查是否已经是好友
            friend_docs = self._find_links({
                "link_type": LINK_TYPE_FRIEND,
                "$or": [
                    {"uid_1": uid, "uid_2": target_uid},
                    {"uid_1": target_uid, "uid_2": uid},
                ],
            })
            if friend_docs:
                return {"success": False, "message": "已经是好友关系"}

            # 检查是否已有待处理的申请（任一方向）
            pending_docs = self._find_links({
                "link_type": LINK_TYPE_FRIEND_REQUEST,
                "status": STATUS_PENDING,
                "$or": [
                    {"from_uid": uid, "to_uid": target_uid},
                    {"from_uid": target_uid, "to_uid": uid},
                ],
            })
            if pending_docs:
                return {"success": False, "message": "已存在待处理的好友申请"}

            # 创建好友申请文档
            now = self._now_iso()
            doc = {
                "link_type": LINK_TYPE_FRIEND_REQUEST,
                "from_uid": uid,
                "to_uid": target_uid,
                "status": STATUS_PENDING,
                "created_at": now,
                "updated_at": now,
            }
            result = self._save_link_doc(doc)
            if result:
                info_log(f"好友申请已发送: {uid} -> {target_uid}")
                # 推送通知给目标用户
                self._notify_user(target_uid, "friend_request", {
                    "from_uid": uid,
                    "message": "收到一条好友申请",
                })
                return {"success": True, "message": "好友申请已发送", "data": result}
            else:
                return {"success": False, "message": "好友申请发送失败"}

    def accept_friend_request(self, uid: str, from_uid: str) -> dict:
        """
        接受好友申请

        将申请状态更新为 accepted，并创建双向好友关系文档。

        Args:
            uid: 接受者 uid（即申请的 to_uid）
            from_uid: 申请发起者 uid

        Returns:
            操作结果字典
        """
        with self._lock:
            # 查找待处理的好友申请
            pending_docs = self._find_links({
                "link_type": LINK_TYPE_FRIEND_REQUEST,
                "from_uid": from_uid,
                "to_uid": uid,
                "status": STATUS_PENDING,
            })
            if not pending_docs:
                return {"success": False, "message": "没有待处理的好友申请"}

            request_doc = pending_docs[0]

            # 更新申请状态为 accepted
            now = self._now_iso()
            request_doc["status"] = STATUS_ACCEPTED
            request_doc["updated_at"] = now
            update_result = self._save_link_doc(request_doc)
            if not update_result:
                return {"success": False, "message": "更新申请状态失败"}

            # 创建好友关系文档
            friend_doc = {
                "link_type": LINK_TYPE_FRIEND,
                "uid_1": from_uid,
                "uid_2": uid,
                "created_at": now,
            }
            friend_result = self._save_link_doc(friend_doc)
            if friend_result:
                info_log(f"好友关系已建立: {from_uid} <-> {uid}")
                # 通知申请发起者
                self._notify_user(from_uid, "friend_accepted", {
                    "by_uid": uid,
                    "message": "好友申请已被接受",
                })
                return {"success": True, "message": "好友申请已接受", "data": friend_result}
            else:
                return {"success": False, "message": "创建好友关系失败"}

    def reject_friend_request(self, uid: str, from_uid: str) -> dict:
        """
        拒绝好友申请

        将申请状态更新为 rejected。

        Args:
            uid: 拒绝者 uid（即申请的 to_uid）
            from_uid: 申请发起者 uid

        Returns:
            操作结果字典
        """
        with self._lock:
            # 查找待处理的好友申请
            pending_docs = self._find_links({
                "link_type": LINK_TYPE_FRIEND_REQUEST,
                "from_uid": from_uid,
                "to_uid": uid,
                "status": STATUS_PENDING,
            })
            if not pending_docs:
                return {"success": False, "message": "没有待处理的好友申请"}

            request_doc = pending_docs[0]

            # 更新申请状态为 rejected
            now = self._now_iso()
            request_doc["status"] = STATUS_REJECTED
            request_doc["updated_at"] = now
            update_result = self._save_link_doc(request_doc)
            if update_result:
                info_log(f"好友申请已拒绝: {from_uid} -> {uid}")
                # 通知申请发起者
                self._notify_user(from_uid, "friend_rejected", {
                    "by_uid": uid,
                    "message": "好友申请已被拒绝",
                })
                return {"success": True, "message": "好友申请已拒绝"}
            else:
                return {"success": False, "message": "拒绝好友申请失败"}

    def delete_friend(self, uid: str, target_uid: str) -> dict:
        """
        删除好友

        删除好友关系文档，同时清理相关的已接受申请记录。

        Args:
            uid: 发起删除的 uid
            target_uid: 被删除的好友 uid

        Returns:
            操作结果字典
        """
        with self._lock:
            # 查找好友关系文档
            friend_docs = self._find_links({
                "link_type": LINK_TYPE_FRIEND,
                "$or": [
                    {"uid_1": uid, "uid_2": target_uid},
                    {"uid_1": target_uid, "uid_2": uid},
                ],
            })
            if not friend_docs:
                return {"success": False, "message": "好友关系不存在"}

            # 删除好友关系文档
            deleted_count = 0
            for doc in friend_docs:
                doc_id = doc.get("_id", "")
                rev = doc.get("_rev", "")
                if doc_id and rev and self._delete_link_doc(doc_id, rev):
                    deleted_count += 1

            # 清理相关的已接受申请记录
            accepted_docs = self._find_links({
                "link_type": LINK_TYPE_FRIEND_REQUEST,
                "status": STATUS_ACCEPTED,
                "$or": [
                    {"from_uid": uid, "to_uid": target_uid},
                    {"from_uid": target_uid, "to_uid": uid},
                ],
            })
            for doc in accepted_docs:
                doc_id = doc.get("_id", "")
                rev = doc.get("_rev", "")
                if doc_id and rev:
                    self._delete_link_doc(doc_id, rev)

            info_log(f"好友关系已删除: {uid} <-> {target_uid}, 删除文档数={deleted_count}")
            # 通知对方
            self._notify_user(target_uid, "friend_deleted", {
                "by_uid": uid,
                "message": "已被对方删除好友",
            })
            return {"success": True, "message": "好友关系已删除"}

    def get_friends(self, uid: str) -> dict:
        """
        获取好友列表

        Args:
            uid: 用户 uid

        Returns:
            操作结果字典，data 中包含好友 uid 列表
        """
        # 查询所有包含该 uid 的好友关系
        friend_docs = self._find_links({
            "link_type": LINK_TYPE_FRIEND,
            "$or": [
                {"uid_1": uid},
                {"uid_2": uid},
            ],
        })

        friends = []
        for doc in friend_docs:
            uid_1 = doc.get("uid_1", "")
            uid_2 = doc.get("uid_2", "")
            friend_uid = uid_2 if uid_1 == uid else uid_1
            if friend_uid:
                friends.append({
                    "uid": friend_uid,
                    "created_at": doc.get("created_at", ""),
                })

        debug_log(f"获取好友列表: uid={uid}, 数量={len(friends)}")
        return {"success": True, "message": "获取好友列表成功", "data": friends}

    def get_friend_requests(self, uid: str) -> dict:
        """
        获取待处理好友申请列表

        Args:
            uid: 用户 uid

        Returns:
            操作结果字典，data 中包含待处理申请列表
        """
        pending_docs = self._find_links({
            "link_type": LINK_TYPE_FRIEND_REQUEST,
            "to_uid": uid,
            "status": STATUS_PENDING,
        })

        requests = []
        for doc in pending_docs:
            requests.append({
                "from_uid": doc.get("from_uid", ""),
                "created_at": doc.get("created_at", ""),
            })

        debug_log(f"获取好友申请列表: uid={uid}, 数量={len(requests)}")
        return {"success": True, "message": "获取好友申请列表成功", "data": requests}

    # ================================================================
    # 师徒系统
    # ================================================================

    def send_master_request(self, uid: str, target_uid: str) -> dict:
        """
        拜师请求

        uid 向 target_uid 发起拜师请求，target_uid 为师父。

        Args:
            uid: 徒弟 uid（发起者）
            target_uid: 师父 uid（目标）

        Returns:
            操作结果字典
        """
        if uid == target_uid:
            return {"success": False, "message": "不能拜自己为师"}

        with self._lock:
            # 检查是否已有师徒关系（任一方向）
            existing_docs = self._find_links({
                "link_type": LINK_TYPE_MASTER_DISCIPLE,
                "$or": [
                    {"master_uid": uid},
                    {"disciple_uid": uid},
                    {"master_uid": target_uid},
                    {"disciple_uid": target_uid},
                ],
            })
            for doc in existing_docs:
                if doc.get("master_uid") == uid or doc.get("disciple_uid") == uid:
                    if doc.get("disciple_uid") == uid:
                        return {"success": False, "message": "你已有师父，不能重复拜师"}
                    if doc.get("master_uid") == uid:
                        return {"success": False, "message": "你已收徒，不能拜师"}
                if doc.get("master_uid") == target_uid or doc.get("disciple_uid") == target_uid:
                    if doc.get("master_uid") == target_uid:
                        # target_uid 已经是师父，检查是否已有该徒弟
                        pass
                    if doc.get("disciple_uid") == target_uid:
                        return {"success": False, "message": "对方已有师父，无法拜师"}

            # 检查是否已有待处理的拜师请求
            pending_docs = self._find_links({
                "link_type": LINK_TYPE_MASTER_REQUEST,
                "status": STATUS_PENDING,
                "$or": [
                    {"from_uid": uid, "to_uid": target_uid},
                    {"from_uid": target_uid, "to_uid": uid},
                ],
            })
            if pending_docs:
                return {"success": False, "message": "已存在待处理的拜师请求"}

            # 创建拜师请求文档
            now = self._now_iso()
            doc = {
                "link_type": LINK_TYPE_MASTER_REQUEST,
                "from_uid": uid,        # 徒弟
                "to_uid": target_uid,   # 师父
                "status": STATUS_PENDING,
                "created_at": now,
                "updated_at": now,
            }
            result = self._save_link_doc(doc)
            if result:
                info_log(f"拜师请求已发送: {uid} -> {target_uid}")
                # 通知师父
                self._notify_user(target_uid, "master_request", {
                    "from_uid": uid,
                    "message": "收到一条拜师请求",
                })
                return {"success": True, "message": "拜师请求已发送", "data": result}
            else:
                return {"success": False, "message": "拜师请求发送失败"}

    def accept_master_request(self, uid: str, from_uid: str) -> dict:
        """
        接受拜师请求

        师父（uid）接受徒弟（from_uid）的拜师请求。

        Args:
            uid: 师父 uid（即请求的 to_uid）
            from_uid: 徒弟 uid（请求发起者）

        Returns:
            操作结果字典
        """
        with self._lock:
            # 查找待处理的拜师请求
            pending_docs = self._find_links({
                "link_type": LINK_TYPE_MASTER_REQUEST,
                "from_uid": from_uid,
                "to_uid": uid,
                "status": STATUS_PENDING,
            })
            if not pending_docs:
                return {"success": False, "message": "没有待处理的拜师请求"}

            request_doc = pending_docs[0]

            # 再次检查双方是否已有师徒关系
            existing_docs = self._find_links({
                "link_type": LINK_TYPE_MASTER_DISCIPLE,
                "$or": [
                    {"master_uid": uid},
                    {"disciple_uid": uid},
                    {"master_uid": from_uid},
                    {"disciple_uid": from_uid},
                ],
            })
            for doc in existing_docs:
                if doc.get("disciple_uid") == from_uid:
                    return {"success": False, "message": "对方已有师父"}
                if doc.get("disciple_uid") == uid:
                    return {"success": False, "message": "你已有师父，不能收徒"}
                if doc.get("master_uid") == from_uid:
                    return {"success": False, "message": "对方已收徒，不能拜师"}

            # 更新请求状态为 accepted
            now = self._now_iso()
            request_doc["status"] = STATUS_ACCEPTED
            request_doc["updated_at"] = now
            update_result = self._save_link_doc(request_doc)
            if not update_result:
                return {"success": False, "message": "更新拜师请求状态失败"}

            # 创建师徒关系文档
            master_doc = {
                "link_type": LINK_TYPE_MASTER_DISCIPLE,
                "master_uid": uid,         # 师父
                "disciple_uid": from_uid,   # 徒弟
                "created_at": now,
            }
            master_result = self._save_link_doc(master_doc)
            if master_result:
                info_log(f"师徒关系已建立: 师父={uid}, 徒弟={from_uid}")
                # 通知徒弟
                self._notify_user(from_uid, "master_accepted", {
                    "by_uid": uid,
                    "message": "拜师请求已被接受",
                })
                return {"success": True, "message": "拜师请求已接受", "data": master_result}
            else:
                return {"success": False, "message": "创建师徒关系失败"}

    def break_master_relation(self, uid: str, target_uid: str) -> dict:
        """
        解除师徒关系

        任一方均可发起解除。

        Args:
            uid: 发起解除的 uid
            target_uid: 对方 uid

        Returns:
            操作结果字典
        """
        with self._lock:
            # 查找师徒关系文档
            master_docs = self._find_links({
                "link_type": LINK_TYPE_MASTER_DISCIPLE,
                "$or": [
                    {"master_uid": uid, "disciple_uid": target_uid},
                    {"master_uid": target_uid, "disciple_uid": uid},
                ],
            })
            if not master_docs:
                return {"success": False, "message": "师徒关系不存在"}

            # 删除师徒关系文档
            deleted_count = 0
            for doc in master_docs:
                doc_id = doc.get("_id", "")
                rev = doc.get("_rev", "")
                if doc_id and rev and self._delete_link_doc(doc_id, rev):
                    deleted_count += 1

            # 清理相关的已接受请求记录
            accepted_docs = self._find_links({
                "link_type": LINK_TYPE_MASTER_REQUEST,
                "status": STATUS_ACCEPTED,
                "$or": [
                    {"from_uid": uid, "to_uid": target_uid},
                    {"from_uid": target_uid, "to_uid": uid},
                ],
            })
            for doc in accepted_docs:
                doc_id = doc.get("_id", "")
                rev = doc.get("_rev", "")
                if doc_id and rev:
                    self._delete_link_doc(doc_id, rev)

            info_log(f"师徒关系已解除: {uid} <-> {target_uid}, 删除文档数={deleted_count}")
            # 通知对方
            self._notify_user(target_uid, "master_broken", {
                "by_uid": uid,
                "message": "师徒关系已被解除",
            })
            return {"success": True, "message": "师徒关系已解除"}

    def get_master_info(self, uid: str) -> dict:
        """
        获取师徒信息

        查询该用户的师父和徒弟列表。

        Args:
            uid: 用户 uid

        Returns:
            操作结果字典，data 中包含 master（师父信息）和 disciples（徒弟列表）
        """
        # 查询师父
        master_docs = self._find_links({
            "link_type": LINK_TYPE_MASTER_DISCIPLE,
            "disciple_uid": uid,
        })
        master = None
        if master_docs:
            master_doc = master_docs[0]
            master = {
                "uid": master_doc.get("master_uid", ""),
                "created_at": master_doc.get("created_at", ""),
            }

        # 查询徒弟
        disciple_docs = self._find_links({
            "link_type": LINK_TYPE_MASTER_DISCIPLE,
            "master_uid": uid,
        })
        disciples = []
        for doc in disciple_docs:
            disciples.append({
                "uid": doc.get("disciple_uid", ""),
                "created_at": doc.get("created_at", ""),
            })

        debug_log(f"获取师徒信息: uid={uid}, 师父={'有' if master else '无'}, 徒弟数={len(disciples)}")
        return {
            "success": True,
            "message": "获取师徒信息成功",
            "data": {
                "master": master,
                "disciples": disciples,
            },
        }

    # ================================================================
    # 道侣系统
    # ================================================================

    def send_companion_request(self, uid: str, target_uid: str) -> dict:
        """
        结为道侣请求

        Args:
            uid: 发起者 uid
            target_uid: 目标 uid

        Returns:
            操作结果字典
        """
        if uid == target_uid:
            return {"success": False, "message": "不能与自己结为道侣"}

        with self._lock:
            # 检查是否已有道侣关系（任一方）
            existing_docs = self._find_links({
                "link_type": LINK_TYPE_DAO_COMPANION,
                "$or": [
                    {"uid_1": uid},
                    {"uid_2": uid},
                    {"uid_1": target_uid},
                    {"uid_2": target_uid},
                ],
            })
            if existing_docs:
                for doc in existing_docs:
                    if doc.get("uid_1") == uid or doc.get("uid_2") == uid:
                        return {"success": False, "message": "你已有道侣"}
                    if doc.get("uid_1") == target_uid or doc.get("uid_2") == target_uid:
                        return {"success": False, "message": "对方已有道侣"}

            # 检查是否已有待处理的道侣请求（任一方向）
            pending_docs = self._find_links({
                "link_type": LINK_TYPE_COMPANION_REQUEST,
                "status": STATUS_PENDING,
                "$or": [
                    {"from_uid": uid, "to_uid": target_uid},
                    {"from_uid": target_uid, "to_uid": uid},
                ],
            })
            if pending_docs:
                return {"success": False, "message": "已存在待处理的道侣请求"}

            # 创建道侣请求文档
            now = self._now_iso()
            doc = {
                "link_type": LINK_TYPE_COMPANION_REQUEST,
                "from_uid": uid,
                "to_uid": target_uid,
                "status": STATUS_PENDING,
                "created_at": now,
                "updated_at": now,
            }
            result = self._save_link_doc(doc)
            if result:
                info_log(f"道侣请求已发送: {uid} -> {target_uid}")
                # 通知目标用户
                self._notify_user(target_uid, "companion_request", {
                    "from_uid": uid,
                    "message": "收到一条道侣请求",
                })
                return {"success": True, "message": "道侣请求已发送", "data": result}
            else:
                return {"success": False, "message": "道侣请求发送失败"}

    def accept_companion_request(self, uid: str, from_uid: str) -> dict:
        """
        接受道侣请求

        Args:
            uid: 接受者 uid（即请求的 to_uid）
            from_uid: 请求发起者 uid

        Returns:
            操作结果字典
        """
        with self._lock:
            # 查找待处理的道侣请求
            pending_docs = self._find_links({
                "link_type": LINK_TYPE_COMPANION_REQUEST,
                "from_uid": from_uid,
                "to_uid": uid,
                "status": STATUS_PENDING,
            })
            if not pending_docs:
                return {"success": False, "message": "没有待处理的道侣请求"}

            request_doc = pending_docs[0]

            # 再次检查双方是否已有道侣
            existing_docs = self._find_links({
                "link_type": LINK_TYPE_DAO_COMPANION,
                "$or": [
                    {"uid_1": uid},
                    {"uid_2": uid},
                    {"uid_1": from_uid},
                    {"uid_2": from_uid},
                ],
            })
            if existing_docs:
                for doc in existing_docs:
                    if doc.get("uid_1") == uid or doc.get("uid_2") == uid:
                        return {"success": False, "message": "你已有道侣"}
                    if doc.get("uid_1") == from_uid or doc.get("uid_2") == from_uid:
                        return {"success": False, "message": "对方已有道侣"}

            # 更新请求状态为 accepted
            now = self._now_iso()
            request_doc["status"] = STATUS_ACCEPTED
            request_doc["updated_at"] = now
            update_result = self._save_link_doc(request_doc)
            if not update_result:
                return {"success": False, "message": "更新道侣请求状态失败"}

            # 创建道侣关系文档
            companion_doc = {
                "link_type": LINK_TYPE_DAO_COMPANION,
                "uid_1": from_uid,
                "uid_2": uid,
                "created_at": now,
            }
            companion_result = self._save_link_doc(companion_doc)
            if companion_result:
                info_log(f"道侣关系已建立: {from_uid} <-> {uid}")
                # 通知请求发起者
                self._notify_user(from_uid, "companion_accepted", {
                    "by_uid": uid,
                    "message": "道侣请求已被接受",
                })
                return {"success": True, "message": "道侣请求已接受", "data": companion_result}
            else:
                return {"success": False, "message": "创建道侣关系失败"}

    def break_companion_relation(self, uid: str, target_uid: str) -> dict:
        """
        解除道侣关系

        任一方均可发起解除。

        Args:
            uid: 发起解除的 uid
            target_uid: 对方 uid

        Returns:
            操作结果字典
        """
        with self._lock:
            # 查找道侣关系文档
            companion_docs = self._find_links({
                "link_type": LINK_TYPE_DAO_COMPANION,
                "$or": [
                    {"uid_1": uid, "uid_2": target_uid},
                    {"uid_1": target_uid, "uid_2": uid},
                ],
            })
            if not companion_docs:
                return {"success": False, "message": "道侣关系不存在"}

            # 删除道侣关系文档
            deleted_count = 0
            for doc in companion_docs:
                doc_id = doc.get("_id", "")
                rev = doc.get("_rev", "")
                if doc_id and rev and self._delete_link_doc(doc_id, rev):
                    deleted_count += 1

            # 清理相关的已接受请求记录
            accepted_docs = self._find_links({
                "link_type": LINK_TYPE_COMPANION_REQUEST,
                "status": STATUS_ACCEPTED,
                "$or": [
                    {"from_uid": uid, "to_uid": target_uid},
                    {"from_uid": target_uid, "to_uid": uid},
                ],
            })
            for doc in accepted_docs:
                doc_id = doc.get("_id", "")
                rev = doc.get("_rev", "")
                if doc_id and rev:
                    self._delete_link_doc(doc_id, rev)

            info_log(f"道侣关系已解除: {uid} <-> {target_uid}, 删除文档数={deleted_count}")
            # 通知对方
            self._notify_user(target_uid, "companion_broken", {
                "by_uid": uid,
                "message": "道侣关系已被解除",
            })
            return {"success": True, "message": "道侣关系已解除"}

    def get_companion_info(self, uid: str) -> dict:
        """
        获取道侣信息

        Args:
            uid: 用户 uid

        Returns:
            操作结果字典，data 中包含道侣信息，无道侣时为 None
        """
        companion_docs = self._find_links({
            "link_type": LINK_TYPE_DAO_COMPANION,
            "$or": [
                {"uid_1": uid},
                {"uid_2": uid},
            ],
        })

        companion = None
        if companion_docs:
            doc = companion_docs[0]
            uid_1 = doc.get("uid_1", "")
            uid_2 = doc.get("uid_2", "")
            companion_uid = uid_2 if uid_1 == uid else uid_1
            companion = {
                "uid": companion_uid,
                "created_at": doc.get("created_at", ""),
            }

        debug_log(f"获取道侣信息: uid={uid}, 道侣={'有' if companion else '无'}")
        return {
            "success": True,
            "message": "获取道侣信息成功",
            "data": companion,
        }

    # ================================================================
    # 生命周期管理
    # ================================================================

    def close(self) -> None:
        """关闭 CouchDB 客户端连接"""
        client = getattr(self._couch_local, "client", None)
        if client:
            try:
                client.close()
                debug_log("SocialManager CouchDB 连接已关闭")
            except Exception as e:
                warn_log(f"关闭 SocialManager CouchDB 连接时出错: {e}")
            finally:
                self._couch_local.client = None

        info_log("SocialManager 已关闭")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False


# ───────────────────────────────────────────────
# 全局单例
# ───────────────────────────────────────────────

_social_manager_instance: Optional[SocialManager] = None
_singleton_lock = threading.Lock()


def get_social_manager(config: dict = None) -> SocialManager:
    """
    获取 SocialManager 全局单例实例（懒加载，线程安全）

    Args:
        config: 配置字典，首次调用时必须提供

    Returns:
        SocialManager 实例
    """
    global _social_manager_instance
    if _social_manager_instance is None:
        with _singleton_lock:
            if _social_manager_instance is None:
                if config is None:
                    raise ValueError("首次调用 get_social_manager 必须提供 config 参数")
                _social_manager_instance = SocialManager(config)
    return _social_manager_instance
