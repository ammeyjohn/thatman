"""
TeamManager - 修仙组队管理器

管理修仙世界的组队系统，支持创建队伍、邀请成员、
队长转移、踢出成员、解散队伍等操作。
数据持久化到 CouchDB game_teams 数据库。

用法:
    from team_manager import get_team_manager

    mgr = get_team_manager()
    team = mgr.create_team("uid_001")
    mgr.invite_member("uid_001", "uid_002")
    mgr.accept_invite("uid_002", team["team_id"])
    team_info = mgr.get_team_info("uid_001")
"""

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

from gm_logger import debug_log, info_log, warn_log, error_log

# 最大队伍人数
MAX_TEAM_SIZE = 5

# CouchDB 数据库名
DB_NAME = "game_teams"


class TeamManager:
    """修仙组队管理器（线程安全）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._couch_local = threading.local()
        self._config: Optional[dict] = None
        self._couch_url: str = ""
        self._couch_user: str = ""
        self._couch_password: str = ""
        self._db_players: str = ""
        self._initialized: bool = False

    # ================================================================
    # 初始化与 CouchDB 辅助方法
    # ================================================================

    def _ensure_init(self) -> None:
        """延迟初始化，首次调用时加载配置并确保数据库存在"""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            # 加载配置
            config_path = Path(__file__).parent.parent / "config.yaml"
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        self._config = yaml.safe_load(f) or {}
                except Exception as e:
                    error_log(f"TeamManager 加载配置失败: {e}")
                    self._config = {}
            else:
                warn_log(f"配置文件不存在: {config_path}")
                self._config = {}

            # CouchDB 配置
            couch_cfg = self._config.get("couchdb", {})
            self._couch_url = couch_cfg.get("url", "http://localhost:5984").rstrip("/")
            self._couch_user = couch_cfg.get("user", "admin")
            self._couch_password = couch_cfg.get("password", "password")
            db_prefix = couch_cfg.get("db_prefix", "game_")
            self._db_players = f"{db_prefix}players"

            # 确保数据库存在
            self._ensure_db()

            self._initialized = True
            info_log("TeamManager 初始化完成")

    @property
    def _couch_client(self) -> httpx.Client:
        """
        获取当前线程的 CouchDB httpx.Client（线程安全）

        httpx.Client 不是线程安全的，使用线程本地存储确保
        每个线程拥有独立的 httpx.Client 实例。
        """
        client = getattr(self._couch_local, "client", None)
        if client is None:
            self._ensure_init()
            client = httpx.Client(
                base_url=self._couch_url,
                auth=(self._couch_user, self._couch_password),
                headers={"Content-Type": "application/json"},
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_keepalive_connections=0),
            )
            self._couch_local.client = client
        return client

    def _ensure_db(self) -> None:
        """确保 CouchDB 数据库存在，不存在则创建"""
        try:
            resp = self._couch_client.head(f"/{DB_NAME}")
            if resp.status_code == 404:
                resp = self._couch_client.put(f"/{DB_NAME}")
                if resp.status_code in (201, 202):
                    info_log(f"CouchDB 数据库已创建: {DB_NAME}")
                else:
                    warn_log(f"CouchDB 数据库创建失败: {DB_NAME}, 状态码: {resp.status_code}")
            else:
                debug_log(f"CouchDB 数据库已存在: {DB_NAME}")
        except Exception as e:
            error_log(f"检查/创建 CouchDB 数据库失败: {DB_NAME}, 错误: {e}")

        # 创建 Mango 索引，加速按成员 uid 查询
        self._ensure_mango_index()

    def _ensure_mango_index(self) -> None:
        """为 game_teams 创建 Mango 索引"""
        try:
            index_body = {
                "index": {
                    "fields": ["status", "leader_uid"]
                },
                "name": "by_status_leader",
                "type": "json",
            }
            self._couch_client.post(f"/{DB_NAME}/_index", json=index_body)

            # 为成员 uid 查询创建索引
            member_index_body = {
                "index": {
                    "fields": ["status", "members.uid"]
                },
                "name": "by_status_member_uid",
                "type": "json",
            }
            self._couch_client.post(f"/{DB_NAME}/_index", json=member_index_body)

            debug_log("Mango 索引创建完成")
        except Exception as e:
            warn_log(f"创建 Mango 索引失败: {e}")

    def _couch_request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[dict] = None,
    ) -> httpx.Response:
        """发送 CouchDB HTTP 请求"""
        self._ensure_init()
        return self._couch_client.request(method=method, url=path, json=json_data)

    def _now_iso(self) -> str:
        """获取当前 UTC 时间 ISO 格式"""
        return datetime.now(timezone.utc).isoformat()

    # ================================================================
    # 数据查询辅助方法
    # ================================================================

    def _get_player_info(self, uid: str) -> dict:
        """
        从 CouchDB 获取玩家信息（name, realm, realm_stage）

        Args:
            uid: 玩家唯一标识

        Returns:
            玩家信息字典
        """
        try:
            resp = self._couch_request("GET", f"/{self._db_players}/{uid}")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "uid": uid,
                    "name": data.get("name", ""),
                    "realm": data.get("realm", ""),
                    "realm_stage": data.get("realm_stage", ""),
                }
            else:
                warn_log(f"获取玩家信息失败: uid={uid}, 状态码={resp.status_code}")
                return {"uid": uid, "name": "", "realm": "", "realm_stage": ""}
        except Exception as e:
            error_log(f"获取玩家信息异常: uid={uid}, 错误={e}")
            return {"uid": uid, "name": "", "realm": "", "realm_stage": ""}

    def _find_team_by_uid(self, uid: str) -> Optional[dict]:
        """
        根据 uid 查找玩家所在队伍（活跃状态）

        优先匹配 leader_uid，其次匹配 members 数组中的 uid。

        Args:
            uid: 玩家唯一标识

        Returns:
            队伍文档字典，未找到返回 None
        """
        try:
            body = {
                "selector": {
                    "status": "active",
                    "$or": [
                        {"leader_uid": uid},
                        {"members.uid": uid},
                    ],
                },
                "limit": 1,
            }
            resp = self._couch_request("POST", f"/{DB_NAME}/_find", json_data=body)
            if resp.status_code == 200:
                docs = resp.json().get("docs", [])
                if docs:
                    return docs[0]
        except Exception as e:
            error_log(f"查找玩家队伍异常: uid={uid}, 错误={e}")
        return None

    def _get_team_by_id(self, team_id: str) -> Optional[dict]:
        """
        根据 team_id 获取队伍文档

        Args:
            team_id: 队伍 ID

        Returns:
            队伍文档字典，未找到返回 None
        """
        try:
            resp = self._couch_request("GET", f"/{DB_NAME}/{team_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            error_log(f"获取队伍文档异常: team_id={team_id}, 错误={e}")
        return None

    def _save_team(self, team_doc: dict, max_retries: int = 3) -> dict:
        """
        保存队伍文档到 CouchDB（新增或更新）

        遇到 409 冲突时自动重试（重新获取 _rev 后再写入）。

        Args:
            team_doc: 队伍文档
            max_retries: 最大重试次数

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        doc_id = team_doc.get("_id") or team_doc.get("team_id", "")
        if not doc_id:
            error_log("保存队伍失败: 缺少文档 ID")
            return {}

        # 确保 _id 字段存在
        team_doc["_id"] = doc_id
        team_doc["updated_at"] = self._now_iso()

        for attempt in range(max_retries):
            # 先查询现有文档获取 _rev
            try:
                resp = self._couch_request("GET", f"/{DB_NAME}/{doc_id}")
                if resp.status_code == 200:
                    existing = resp.json()
                    if "_rev" in existing:
                        team_doc["_rev"] = existing["_rev"]
                elif resp.status_code != 404:
                    warn_log(f"查询队伍文档失败: team_id={doc_id}, 状态码={resp.status_code}")
            except Exception as e:
                error_log(f"查询队伍文档异常: team_id={doc_id}, 错误={e}")

            # 写入文档
            try:
                resp = self._couch_request("PUT", f"/{DB_NAME}/{doc_id}", json_data=team_doc)
                if resp.status_code in (201, 202):
                    debug_log(f"保存队伍成功: team_id={doc_id}")
                    return resp.json()
                elif resp.status_code == 409 and attempt < max_retries - 1:
                    warn_log(f"保存队伍冲突，第 {attempt + 1} 次重试: team_id={doc_id}")
                    continue
                else:
                    warn_log(
                        f"保存队伍失败: team_id={doc_id}, 状态码={resp.status_code}, "
                        f"响应={resp.text[:200]}"
                    )
                    return {}
            except Exception as e:
                error_log(f"保存队伍异常: team_id={doc_id}, 错误={e}")
                return {}

        warn_log(f"保存队伍重试耗尽: team_id={doc_id}")
        return {}

    def _notify_uid(self, uid: str, event_type: str, data: dict) -> None:
        """通过 EventBus 推送通知给指定用户"""
        try:
            from event_bus import get_event_bus

            bus = get_event_bus()
            bus.publish_to_uid(uid, event_type, data)
        except Exception as e:
            error_log(f"推送组队通知失败: uid={uid}, event={event_type}, 错误={e}")

    @staticmethod
    def _clean_team_doc(team_doc: dict) -> dict:
        """清理 CouchDB 内部字段，返回可对外暴露的队伍信息"""
        team_doc.pop("_rev", None)
        return team_doc

    # ================================================================
    # 公开接口
    # ================================================================

    def create_team(self, uid: str) -> dict:
        """
        创建队伍，创建者为队长

        Args:
            uid: 创建者 uid

        Returns:
            队伍数据字典，失败返回含 error 的字典
        """
        self._ensure_init()

        # 检查是否已在队伍中
        existing = self._find_team_by_uid(uid)
        if existing:
            return {"error": "你已在队伍中，无法重复创建"}

        # 获取玩家信息
        player_info = self._get_player_info(uid)

        now = self._now_iso()
        team_id = f"team_{uuid.uuid4().hex[:12]}"

        team_doc = {
            "_id": team_id,
            "team_id": team_id,
            "leader_uid": uid,
            "members": [player_info],
            "pending_invites": [],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }

        result = self._save_team(team_doc)
        if not result:
            return {"error": "创建队伍失败"}

        info_log(f"创建队伍成功: team_id={team_id}, leader={uid}")

        # 通知创建者
        self._notify_uid(uid, "team_created", {
            "team_id": team_id,
            "leader_uid": uid,
            "members": [player_info],
        })

        return self._clean_team_doc(team_doc)

    def invite_member(self, uid: str, target_uid: str) -> dict:
        """
        邀请成员入队（仅队长可操作）

        Args:
            uid: 队长 uid
            target_uid: 被邀请者 uid

        Returns:
            操作结果字典
        """
        self._ensure_init()

        if uid == target_uid:
            return {"error": "不能邀请自己"}

        # 查找队伍
        team = self._find_team_by_uid(uid)
        if not team:
            return {"error": "你不在任何队伍中"}

        # 验证队长权限
        if team["leader_uid"] != uid:
            return {"error": "仅队长可以邀请成员"}

        # 检查目标是否已在队伍中
        target_team = self._find_team_by_uid(target_uid)
        if target_team:
            return {"error": "目标玩家已在队伍中"}

        # 检查队伍人数上限
        if len(team.get("members", [])) >= MAX_TEAM_SIZE:
            return {"error": f"队伍人数已达上限({MAX_TEAM_SIZE}人)"}

        # 检查是否已邀请
        pending = team.get("pending_invites", [])
        for inv in pending:
            if inv.get("uid") == target_uid:
                return {"error": "已邀请该玩家，请等待对方响应"}

        # 添加邀请记录
        pending.append({
            "uid": target_uid,
            "invited_at": self._now_iso(),
        })
        team["pending_invites"] = pending

        result = self._save_team(team)
        if not result:
            return {"error": "邀请失败，请重试"}

        info_log(f"邀请入队: team_id={team['team_id']}, inviter={uid}, target={target_uid}")

        # 通知被邀请者
        inviter_info = self._get_player_info(uid)
        self._notify_uid(target_uid, "team_invite", {
            "team_id": team["team_id"],
            "inviter_uid": uid,
            "inviter_name": inviter_info.get("name", ""),
            "members_count": len(team.get("members", [])),
        })

        return {
            "success": True,
            "team_id": team["team_id"],
            "target_uid": target_uid,
            "message": "邀请已发送",
        }

    def accept_invite(self, uid: str, team_id: str) -> dict:
        """
        接受入队邀请

        Args:
            uid: 接受者 uid
            team_id: 队伍 ID

        Returns:
            操作结果字典
        """
        self._ensure_init()

        # 检查是否已在队伍中
        existing = self._find_team_by_uid(uid)
        if existing:
            return {"error": "你已在队伍中，请先离开当前队伍"}

        # 获取队伍文档
        team = self._get_team_by_id(team_id)
        if not team:
            return {"error": "队伍不存在"}

        # 检查队伍状态
        if team.get("status") != "active":
            return {"error": "队伍已解散"}

        # 检查是否被邀请
        pending = team.get("pending_invites", [])
        invited = any(inv.get("uid") == uid for inv in pending)
        if not invited:
            return {"error": "你未被邀请加入该队伍"}

        # 检查队伍人数
        if len(team.get("members", [])) >= MAX_TEAM_SIZE:
            return {"error": "队伍人数已满"}

        # 获取玩家信息并加入队伍
        player_info = self._get_player_info(uid)
        team["members"].append(player_info)

        # 移除邀请记录
        team["pending_invites"] = [inv for inv in pending if inv.get("uid") != uid]

        result = self._save_team(team)
        if not result:
            return {"error": "加入队伍失败，请重试"}

        info_log(f"接受入队邀请: team_id={team_id}, uid={uid}")

        # 通知队伍所有成员
        for member in team["members"]:
            self._notify_uid(member["uid"], "team_member_joined", {
                "team_id": team_id,
                "new_member": player_info,
                "members": team["members"],
            })

        return self._clean_team_doc(team)

    def leave_team(self, uid: str) -> dict:
        """
        离开队伍

        队长离开则自动转移队长给最早入队的成员；
        仅剩一人则自动解散队伍。

        Args:
            uid: 离开者 uid

        Returns:
            操作结果字典
        """
        self._ensure_init()

        # 查找队伍
        team = self._find_team_by_uid(uid)
        if not team:
            return {"error": "你不在任何队伍中"}

        team_id = team["team_id"]
        members = team.get("members", [])

        # 分离离开者与剩余成员
        leaving_member = None
        new_members = []
        for m in members:
            if m["uid"] == uid:
                leaving_member = m
            else:
                new_members.append(m)

        if not leaving_member:
            return {"error": "你不在该队伍中"}

        # 仅剩一人 -> 解散队伍
        if len(new_members) == 0:
            team["status"] = "disbanded"
            team["members"] = []
            team["pending_invites"] = []
            self._save_team(team)

            info_log(f"队伍解散（最后一人离开）: team_id={team_id}, uid={uid}")

            self._notify_uid(uid, "team_disbanded", {
                "team_id": team_id,
                "reason": "last_member_left",
            })

            return {
                "success": True,
                "team_id": team_id,
                "message": "队伍已解散",
            }

        # 更新成员列表
        team["members"] = new_members

        # 如果离开的是队长，转移队长给最早入队的成员
        new_leader_uid = team["leader_uid"]
        if team["leader_uid"] == uid:
            new_leader = new_members[0]
            new_leader_uid = new_leader["uid"]
            team["leader_uid"] = new_leader_uid
            info_log(f"队长转移: team_id={team_id}, new_leader={new_leader_uid}")

            self._notify_uid(new_leader_uid, "team_leader_transferred", {
                "team_id": team_id,
                "previous_leader_uid": uid,
                "members": new_members,
            })

        # 清理离开者的待处理邀请
        team["pending_invites"] = [
            inv for inv in team.get("pending_invites", [])
            if inv.get("uid") != uid
        ]

        self._save_team(team)

        info_log(f"离开队伍: team_id={team_id}, uid={uid}")

        # 通知队伍剩余成员
        for member in new_members:
            self._notify_uid(member["uid"], "team_member_left", {
                "team_id": team_id,
                "left_member": leaving_member,
                "members": new_members,
                "new_leader_uid": new_leader_uid,
            })

        # 通知离开者
        self._notify_uid(uid, "team_left", {
            "team_id": team_id,
        })

        return {
            "success": True,
            "team_id": team_id,
            "message": "已离开队伍",
        }

    def kick_member(self, uid: str, target_uid: str) -> dict:
        """
        踢出成员（仅队长可操作）

        Args:
            uid: 队长 uid
            target_uid: 被踢出者 uid

        Returns:
            操作结果字典
        """
        self._ensure_init()

        if uid == target_uid:
            return {"error": "不能踢出自己，请使用离开队伍功能"}

        # 查找队伍
        team = self._find_team_by_uid(uid)
        if not team:
            return {"error": "你不在任何队伍中"}

        # 验证队长权限
        if team["leader_uid"] != uid:
            return {"error": "仅队长可以踢出成员"}

        # 查找目标成员
        target_member = None
        new_members = []
        for m in team.get("members", []):
            if m["uid"] == target_uid:
                target_member = m
            else:
                new_members.append(m)

        if not target_member:
            return {"error": "目标玩家不在队伍中"}

        # 更新成员列表
        team["members"] = new_members

        # 移除该成员的邀请记录（如果有）
        team["pending_invites"] = [
            inv for inv in team.get("pending_invites", [])
            if inv.get("uid") != target_uid
        ]

        self._save_team(team)

        info_log(f"踢出成员: team_id={team['team_id']}, leader={uid}, kicked={target_uid}")

        # 通知被踢出者
        self._notify_uid(target_uid, "team_kicked", {
            "team_id": team["team_id"],
        })

        # 通知队伍剩余成员
        for member in new_members:
            self._notify_uid(member["uid"], "team_member_kicked", {
                "team_id": team["team_id"],
                "kicked_member": target_member,
                "members": new_members,
            })

        return {
            "success": True,
            "team_id": team["team_id"],
            "message": f"已将 {target_member.get('name', target_uid)} 踢出队伍",
        }

    def transfer_leader(self, uid: str, target_uid: str) -> dict:
        """
        转移队长

        Args:
            uid: 当前队长 uid
            target_uid: 新队长 uid

        Returns:
            操作结果字典
        """
        self._ensure_init()

        if uid == target_uid:
            return {"error": "不能转移队长给自己"}

        # 查找队伍
        team = self._find_team_by_uid(uid)
        if not team:
            return {"error": "你不在任何队伍中"}

        # 验证队长权限
        if team["leader_uid"] != uid:
            return {"error": "仅队长可以转移队长"}

        # 验证目标是否为队伍成员
        target_member = None
        for m in team.get("members", []):
            if m["uid"] == target_uid:
                target_member = m
                break

        if not target_member:
            return {"error": "目标玩家不在队伍中"}

        # 转移队长
        team["leader_uid"] = target_uid
        self._save_team(team)

        info_log(f"转移队长: team_id={team['team_id']}, old_leader={uid}, new_leader={target_uid}")

        # 通知新队长
        self._notify_uid(target_uid, "team_leader_transferred", {
            "team_id": team["team_id"],
            "previous_leader_uid": uid,
            "members": team["members"],
        })

        # 通知原队长
        self._notify_uid(uid, "team_leader_demoted", {
            "team_id": team["team_id"],
            "new_leader_uid": target_uid,
        })

        # 通知其他成员
        for member in team["members"]:
            if member["uid"] not in (uid, target_uid):
                self._notify_uid(member["uid"], "team_leader_changed", {
                    "team_id": team["team_id"],
                    "new_leader_uid": target_uid,
                    "members": team["members"],
                })

        return {
            "success": True,
            "team_id": team["team_id"],
            "new_leader_uid": target_uid,
            "message": "队长已转移",
        }

    def disband_team(self, uid: str) -> dict:
        """
        解散队伍（仅队长可操作）

        Args:
            uid: 队长 uid

        Returns:
            操作结果字典
        """
        self._ensure_init()

        # 查找队伍
        team = self._find_team_by_uid(uid)
        if not team:
            return {"error": "你不在任何队伍中"}

        # 验证队长权限
        if team["leader_uid"] != uid:
            return {"error": "仅队长可以解散队伍"}

        team_id = team["team_id"]
        members = team.get("members", [])

        # 标记为已解散
        team["status"] = "disbanded"
        team["members"] = []
        team["pending_invites"] = []

        self._save_team(team)

        info_log(f"解散队伍: team_id={team_id}, leader={uid}")

        # 通知所有原成员
        for member in members:
            self._notify_uid(member["uid"], "team_disbanded", {
                "team_id": team_id,
                "reason": "leader_disbanded",
            })

        return {
            "success": True,
            "team_id": team_id,
            "message": "队伍已解散",
        }

    def get_team_info(self, uid: str) -> dict:
        """
        获取队伍信息

        Args:
            uid: 玩家 uid

        Returns:
            队伍信息字典，不在队伍中返回含 error 的字典
        """
        self._ensure_init()

        team = self._find_team_by_uid(uid)
        if not team:
            return {"error": "你不在任何队伍中"}

        return self._clean_team_doc(team)


# ================================================================
# 模块级单例
# ================================================================

_team_manager_instance: Optional[TeamManager] = None
_instance_lock = threading.Lock()


def get_team_manager() -> TeamManager:
    """获取 TeamManager 单例实例"""
    global _team_manager_instance
    if _team_manager_instance is None:
        with _instance_lock:
            if _team_manager_instance is None:
                _team_manager_instance = TeamManager()
                info_log("TeamManager 单例初始化完成")
    return _team_manager_instance
