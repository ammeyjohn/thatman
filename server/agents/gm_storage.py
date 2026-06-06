"""
GM Storage - GM 存储执行层

封装 CouchDB / Qdrant / Hindsight 记忆的读写操作，
以及 save_flag 分发逻辑。

用法:
    from gm_storage import GMStorage

    storage = GMStorage(config)

    # CouchDB 操作
    player = storage.couch_get_player("uid_001")
    storage.couch_save_player("uid_001", {"name": "张三", "level": 5})

    # Qdrant 剧情向量操作
    results = storage.search_plot_vector("灵潮爆发", top_k=3)
    storage.insert_plot_vector("灵潮爆发，灵气浓度骤增", {"type": "world_event", "area": "青墟"})

    # Hindsight 记忆操作
    memory_text = storage.recall_all_memory("uid_001", "灵潮")
    storage.save_memory("user_uid_001", "玩家在青墟山突破筑基期")

    # save_flag 分发
    storage.save_dispatcher("player_update", "uid_001", "青墟山", resp_json)
"""

import json
import logging
import uuid
from typing import Dict, Any, Optional, List

import httpx

# 复用 hindsight_memory 模块
from hindsight_memory import (
    HindsightMemoryStore,
    get_memory_store,
)

# 复用 gm_logger 的 debug 开关控制日志函数
from gm_logger import debug_log, info_log, warn_log, error_log

# 复用 search_episode 的 EmbeddingClient 和 QdrantClient
from skills.search_episode import (
    _get_embedding_client,
    _get_qdrant_client,
    EmbeddingClient,
)

# 配置日志
logger = logging.getLogger(__name__)


class GMStorage:
    """
    GM 存储执行层

    封装 CouchDB / Qdrant / Hindsight 记忆的读写操作，
    以及 save_flag 分发逻辑。
    """

    def __init__(self, config: dict):
        """
        初始化 GMStorage

        Args:
            config: 配置字典，包含 CouchDB/Qdrant/Hindsight 连接参数
        """
        self.config = config

        # ── CouchDB 配置 ──
        gm_cfg = config.get("gm", {})
        couch_cfg = gm_cfg.get("couchdb", {})
        self._couch_url: str = couch_cfg.get("url", "http://localhost:5984").rstrip("/")
        self._couch_db_prefix: str = couch_cfg.get("db_prefix", "game_")
        self._couch_user: str = couch_cfg.get("user", "admin")
        self._couch_password: str = couch_cfg.get("password", "password")

        # CouchDB 数据库名
        self._db_players: str = f"{self._couch_db_prefix}players"
        self._db_entities: str = f"{self._couch_db_prefix}entities"
        self._db_links: str = f"{self._couch_db_prefix}links"
        self._db_world_snaps: str = f"{self._couch_db_prefix}world_snaps"

        # 初始化 CouchDB httpx 客户端
        self._couch_client: httpx.Client = httpx.Client(
            base_url=self._couch_url,
            auth=(self._couch_user, self._couch_password),
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )

        # 确保 CouchDB 数据库存在
        self._ensure_couch_dbs()

        # ── Qdrant 配置 ──
        qdrant_cfg = gm_cfg.get("qdrant", {})
        self._qdrant_collection: str = qdrant_cfg.get("collection", "episode")

        # ── Hindsight 配置 ──
        hindsight_cfg = gm_cfg.get("hindsight", {})
        self._hindsight_base_url: str = hindsight_cfg.get(
            "base_url", "http://localhost:8888"
        )
        self._hindsight_api_key: Optional[str] = hindsight_cfg.get("api_key")

        # Hindsight 记忆库实例缓存
        self._memory_stores: Dict[str, HindsightMemoryStore] = {}

        info_log("GMStorage 初始化完成")

    # ================================================================
    # CouchDB 辅助方法
    # ================================================================

    def _ensure_couch_dbs(self) -> None:
        """确保 CouchDB 所需数据库存在，不存在则创建"""
        db_names = [
            self._db_players,
            self._db_entities,
            self._db_links,
            self._db_world_snaps,
        ]
        for db_name in db_names:
            try:
                resp = self._couch_client.head(f"/{db_name}")
                if resp.status_code == 404:
                    # 数据库不存在，创建
                    resp = self._couch_client.put(f"/{db_name}")
                    if resp.status_code in (201, 202):
                        info_log(f"CouchDB 数据库已创建: {db_name}")
                    else:
                        warn_log(f"CouchDB 数据库创建失败: {db_name}, 状态码: {resp.status_code}")
                else:
                    debug_log(f"CouchDB 数据库已存在: {db_name}")
            except Exception as e:
                error_log(f"检查/创建 CouchDB 数据库失败: {db_name}, 错误: {e}")

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

    # ================================================================
    # CouchDB CRUD 操作
    # ================================================================

    def couch_get_player(self, uid: str) -> dict:
        """
        获取玩家数据

        Args:
            uid: 玩家唯一标识

        Returns:
            玩家数据字典，失败返回空字典
        """
        try:
            resp = self._couch_request("GET", f"/{self._db_players}/{uid}")
            if resp.status_code == 200:
                data = resp.json()
                debug_log(f"获取玩家数据成功: {uid}")
                return data
            elif resp.status_code == 404:
                warn_log(f"玩家不存在: {uid}")
                return {}
            else:
                warn_log(f"获取玩家数据失败: {uid}, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"获取玩家数据异常: {uid}, 错误: {e}")
            return {}

    def couch_save_player(self, uid: str, data: dict) -> dict:
        """
        保存玩家数据（新增或更新）

        如果文档已存在，自动携带 _rev 进行更新。

        Args:
            uid: 玩家唯一标识
            data: 玩家数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            # 先查询现有文档获取 _rev
            existing = self.couch_get_player(uid)
            if existing and "_rev" in existing:
                data["_rev"] = existing["_rev"]

            resp = self._couch_request("PUT", f"/{self._db_players}/{uid}", json_data=data)
            if resp.status_code in (201, 202):
                info_log(f"保存玩家数据成功: {uid}")
                return resp.json()
            else:
                warn_log(f"保存玩家数据失败: {uid}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存玩家数据异常: {uid}, 错误: {e}")
            return {}

    def couch_get_entity(self, entity_id: str) -> dict:
        """
        获取实体数据

        Args:
            entity_id: 实体唯一标识

        Returns:
            实体数据字典，失败返回空字典
        """
        try:
            resp = self._couch_request("GET", f"/{self._db_entities}/{entity_id}")
            if resp.status_code == 200:
                data = resp.json()
                debug_log(f"获取实体数据成功: {entity_id}")
                return data
            elif resp.status_code == 404:
                warn_log(f"实体不存在: {entity_id}")
                return {}
            else:
                warn_log(f"获取实体数据失败: {entity_id}, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"获取实体数据异常: {entity_id}, 错误: {e}")
            return {}

    def couch_save_entity(self, entity_id: str, entity_data: dict) -> dict:
        """
        保存实体数据（新增或更新）

        如果文档已存在，自动携带 _rev 进行更新。

        Args:
            entity_id: 实体唯一标识
            entity_data: 实体数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            # 先查询现有文档获取 _rev
            existing = self.couch_get_entity(entity_id)
            if existing and "_rev" in existing:
                entity_data["_rev"] = existing["_rev"]

            resp = self._couch_request("PUT", f"/{self._db_entities}/{entity_id}", json_data=entity_data)
            if resp.status_code in (201, 202):
                info_log(f"保存实体数据成功: {entity_id}")
                return resp.json()
            else:
                warn_log(f"保存实体数据失败: {entity_id}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存实体数据异常: {entity_id}, 错误: {e}")
            return {}

    def couch_get_link(self, target_id: str, rel_type: str = "") -> dict:
        """
        查询关联关系

        Args:
            target_id: 目标实体 ID
            rel_type: 关系类型过滤，为空则返回所有关系

        Returns:
            关联关系数据，失败返回空字典
        """
        try:
            # 使用 CouchDB Mango 查询
            selector: Dict[str, Any] = {
                "$or": [
                    {"from_id": target_id},
                    {"to_id": target_id},
                ]
            }
            if rel_type:
                selector["rel_type"] = rel_type

            body = {
                "selector": selector,
                "limit": 100,
            }

            resp = self._couch_request(
                "POST",
                f"/{self._db_links}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                debug_log(f"查询关联关系成功: target_id={target_id}, rel_type={rel_type}, 找到 {len(docs)} 条")
                return {"docs": docs, "total": len(docs)}
            else:
                warn_log(f"查询关联关系失败: target_id={target_id}, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"查询关联关系异常: target_id={target_id}, 错误: {e}")
            return {}

    def couch_save_link(self, from_id: str, to_id: str, rel_type: str, desc: str) -> dict:
        """
        新增关联关系

        Args:
            from_id: 关系起点实体 ID
            to_id: 关系终点实体 ID
            rel_type: 关系类型
            desc: 关系描述

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            link_doc = {
                "from_id": from_id,
                "to_id": to_id,
                "rel_type": rel_type,
                "desc": desc,
            }

            resp = self._couch_request("POST", f"/{self._db_links}", json_data=link_doc)
            if resp.status_code in (201, 202):
                info_log(f"保存关联关系成功: {from_id} --[{rel_type}]--> {to_id}")
                return resp.json()
            else:
                warn_log(f"保存关联关系失败: {from_id}->{to_id}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存关联关系异常: {from_id}->{to_id}, 错误: {e}")
            return {}

    def couch_get_last_world_snap(self) -> dict:
        """
        获取最新的世界快照

        按 _id 降序取第一条，或使用专门的 latest 视图。

        Returns:
            世界快照数据，失败返回空字典
        """
        try:
            # 使用 Mango 查询按时间降序取最新一条
            body = {
                "selector": {},
                "sort": [{"created_at": "desc"}],
                "limit": 1,
            }

            resp = self._couch_request(
                "POST",
                f"/{self._db_world_snaps}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                if docs:
                    debug_log("获取最新世界快照成功")
                    return docs[0]
                else:
                    warn_log("世界快照为空")
                    return {}
            else:
                warn_log(f"获取最新世界快照失败, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"获取最新世界快照异常: {e}")
            return {}

    def couch_save_world_snap(self, snap_data: dict) -> dict:
        """
        保存世界快照

        使用自动生成的 UUID 作为文档 ID。

        Args:
            snap_data: 世界快照数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            doc_id = f"snap_{uuid.uuid4().hex[:12]}"
            resp = self._couch_request("PUT", f"/{self._db_world_snaps}/{doc_id}", json_data=snap_data)
            if resp.status_code in (201, 202):
                info_log(f"保存世界快照成功: {doc_id}")
                return resp.json()
            else:
                warn_log(f"保存世界快照失败, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存世界快照异常: {e}")
            return {}

    # ================================================================
    # Qdrant 剧情向量操作
    # ================================================================

    def search_plot_vector(self, query: str, top_k: int = 3) -> list:
        """
        语义检索过往剧情

        复用 search_episode 的 EmbeddingClient 和 QdrantClient。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            相似剧情列表，每项包含 content 和 score，失败返回空列表
        """
        try:
            embedding_client = _get_embedding_client()
            if not embedding_client:
                warn_log("EmbeddingClient 未初始化，无法检索剧情向量")
                return []

            qdrant_client = _get_qdrant_client()
            if not qdrant_client:
                warn_log("QdrantClient 未连接，无法检索剧情向量")
                return []

            # 生成查询向量
            embeddings = embedding_client.embed([query])
            vector = embeddings[0]
            if all(v == 0.0 for v in vector):
                warn_log("查询向量为零向量，跳过检索")
                return []

            # 执行搜索（qdrant-client >= 1.12 使用 query_points 替代 search）
            from qdrant_client.models import models
            search_result = qdrant_client.query_points(
                collection_name=self._qdrant_collection,
                query=vector,
                limit=top_k,
                with_payload=True,
            )

            # 整理结果（query_points 返回 QueryResponse，points 在 .points 属性中）
            points = search_result.points if hasattr(search_result, "points") else search_result
            episodes = []
            for point in points:
                payload = point.payload or {}
                episodes.append({
                    "content": payload.get("content", ""),
                    "score": float(point.score) if point.score is not None else 0.0,
                })

            info_log(f"剧情向量检索完成: query={query}, 找到 {len(episodes)} 条")
            return episodes

        except Exception as e:
            error_log(f"剧情向量检索异常: {e}")
            return []

    def insert_plot_vector(self, content: str, meta: dict) -> bool:
        """
        剧情入库

        复用 search_episode 的 EmbeddingClient 和 QdrantClient。

        Args:
            content: 剧情文本内容
            meta: 剧情元数据，包含 type 和 area 等字段

        Returns:
            True 表示入库成功，False 表示失败
        """
        try:
            if not content or not content.strip():
                warn_log("剧情内容为空，跳过入库")
                return False

            embedding_client = _get_embedding_client()
            if not embedding_client:
                warn_log("EmbeddingClient 未初始化，无法入库剧情向量")
                return False

            qdrant_client = _get_qdrant_client()
            if not qdrant_client:
                warn_log("QdrantClient 未连接，无法入库剧情向量")
                return False

            # 生成向量
            embeddings = embedding_client.embed([content.strip()])
            vector = embeddings[0]
            if all(v == 0.0 for v in vector):
                warn_log("生成向量为零向量，跳过入库")
                return False

            # 构建载荷
            payload = {
                "content": content.strip(),
                **meta,
            }

            # 生成唯一 ID
            point_id = uuid.uuid4().hex

            # 插入向量
            from qdrant_client.models import PointStruct
            point = PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
            qdrant_client.upsert(
                collection_name=self._qdrant_collection,
                points=[point],
            )

            info_log(f"剧情向量入库成功: {content}")
            return True

        except Exception as e:
            error_log(f"剧情向量入库异常: {e}")
            return False

    # ================================================================
    # Hindsight 长效记忆操作
    # ================================================================

    def _get_memory_store(self, bank_id: str) -> Optional[HindsightMemoryStore]:
        """
        获取或创建 Hindsight 记忆库实例（带缓存）

        Args:
            bank_id: 记忆库 ID

        Returns:
            HindsightMemoryStore 实例，失败返回 None
        """
        if bank_id in self._memory_stores:
            return self._memory_stores[bank_id]

        try:
            store = get_memory_store(
                bank_id=bank_id,
                base_url=self._hindsight_base_url,
                api_key=self._hindsight_api_key,
            )
            self._memory_stores[bank_id] = store
            debug_log(f"Hindsight 记忆库实例创建成功: {bank_id}")
            return store
        except Exception as e:
            error_log(f"Hindsight 记忆库实例创建失败: {bank_id}, 错误: {e}")
            return None

    def recall_all_memory(self, uid: str, query: str) -> str:
        """
        合并召回个人记忆和世界记忆

        个人记忆使用 bank_id = f"user_{uid}"，
        世界记忆使用 bank_id = "world"，
        合并两者结果并格式化为文本。

        Args:
            uid: 玩家唯一标识
            query: 检索查询文本

        Returns:
            格式化的记忆文本，失败返回空字符串
        """
        parts = []

        # ── 个人记忆 ──
        user_bank_id = f"user_{uid}"
        user_store = self._get_memory_store(user_bank_id)
        if user_store:
            try:
                user_memories = user_store.recall(query=query, n=5)
                if user_memories:
                    parts.append("【个人记忆】")
                    for i, mem in enumerate(user_memories, 1):
                        content = mem.get("content", "").strip()
                        if content:
                            parts.append(f"{i}. {content}")
                    parts.append("")
            except Exception as e:
                warn_log(f"召回个人记忆失败: uid={uid}, 错误: {e}")

        # ── 世界记忆 ──
        world_store = self._get_memory_store("world")
        if world_store:
            try:
                world_memories = world_store.recall(query=query, n=5)
                if world_memories:
                    parts.append("【世界记忆】")
                    for i, mem in enumerate(world_memories, 1):
                        content = mem.get("content", "").strip()
                        if content:
                            parts.append(f"{i}. {content}")
                    parts.append("")
            except Exception as e:
                warn_log(f"召回世界记忆失败: 错误: {e}")

        result = "\n".join(parts)
        if result:
            info_log(f"合并召回记忆成功: uid={uid}, query={query}")
        else:
            debug_log(f"未召回相关记忆: uid={uid}, query={query}")
        return result

    def save_memory(self, namespace: str, summary: str) -> bool:
        """
        保存记忆

        namespace 格式：user_{uid} 或 world_global_history

        Args:
            namespace: 记忆命名空间
            summary: 记忆摘要内容

        Returns:
            True 表示保存成功，False 表示失败
        """
        try:
            if not summary or not summary.strip():
                warn_log("记忆摘要为空，跳过保存")
                return False

            # world_global_history 映射到 world bank
            bank_id = "world" if namespace == "world_global_history" else namespace

            store = self._get_memory_store(bank_id)
            if not store:
                warn_log(f"记忆库不可用: {bank_id}")
                return False

            success = store.retain(
                content=summary.strip(),
                context="gm_event",
            )
            if success:
                info_log(f"记忆保存成功: namespace={namespace}, content={summary}")
            else:
                warn_log(f"记忆保存返回失败: namespace={namespace}")
            return success

        except Exception as e:
            error_log(f"记忆保存异常: namespace={namespace}, 错误: {e}")
            return False

    # ================================================================
    # save_dispatcher - 存储分发逻辑
    # ================================================================

    def save_dispatcher(
        self,
        save_flag: str,
        uid: str,
        current_area: str,
        resp_json: dict,
    ) -> None:
        """
        根据 save_flag 分发存储逻辑

        四种分支：
        - "" (空): 无操作
        - "player_update": 玩家数据更新
        - "new_entity": 新增世界实体
        - "world_change": 世界变更
        - "world_snap": 世界快照

        Args:
            save_flag: 存储标记
            uid: 玩家唯一标识
            current_area: 当前地域
            resp_json: GM 响应 JSON 数据
        """
        if not save_flag:
            debug_log("save_flag 为空，无需存储")
            return

        info_log(f"save_dispatcher 触发: flag={save_flag}, uid={uid}, area={current_area}")
        debug_log(f"[save_dispatcher] 开始分发: flag={save_flag}, resp_keys={list(resp_json.keys())}")

        try:
            if save_flag == "player_update":
                debug_log("[save_dispatcher] 进入 player_update 分支")
                self._dispatch_player_update(uid, current_area, resp_json)
                debug_log("[save_dispatcher] player_update 分支完成")
            elif save_flag == "new_entity":
                debug_log("[save_dispatcher] 进入 new_entity 分支")
                self._dispatch_new_entity(uid, current_area, resp_json)
                debug_log("[save_dispatcher] new_entity 分支完成")
            elif save_flag == "world_change":
                debug_log("[save_dispatcher] 进入 world_change 分支")
                self._dispatch_world_change(uid, current_area, resp_json)
                debug_log("[save_dispatcher] world_change 分支完成")
            elif save_flag == "world_snap":
                debug_log("[save_dispatcher] 进入 world_snap 分支")
                self._dispatch_world_snap(uid, current_area, resp_json)
                debug_log("[save_dispatcher] world_snap 分支完成")
            else:
                warn_log(f"未知 save_flag: {save_flag}")
        except Exception as e:
            error_log(f"save_dispatcher 执行异常: flag={save_flag}, 错误: {e}")

    def _dispatch_player_update(
        self,
        uid: str,
        current_area: str,
        resp_json: dict,
    ) -> None:
        """
        player_update 分支：玩家数据更新

        - couch_save_player
        - 解析 player_update 中的 link_data 并 couch_save_link
        - save_memory 个人记忆
        - insert_plot_vector 对话剧情

        Args:
            uid: 玩家唯一标识
            current_area: 当前地域
            resp_json: GM 响应数据
        """
        # 保存玩家数据
        player_update = resp_json.get("player_update", {})
        if player_update:
            debug_log(f"[_dispatch_player_update] 保存玩家数据: uid={uid}, 字段={list(player_update.keys())}")
            self.couch_save_player(uid, player_update)
            debug_log(f"[_dispatch_player_update] 玩家数据保存完成: uid={uid}")
        else:
            warn_log(f"player_update 分支缺少 player_update 数据: uid={uid}")

        # 解析并保存关联关系
        link_data = player_update.get("link_data") if player_update else None
        if link_data and isinstance(link_data, list):
            debug_log(f"[_dispatch_player_update] 保存关联关系: {len(link_data)}条")
            for link in link_data:
                from_id = link.get("from_id", uid)
                to_id = link.get("to_id", "")
                rel_type = link.get("rel_type", "")
                desc = link.get("desc", "")
                if to_id and rel_type:
                    self.couch_save_link(from_id, to_id, rel_type, desc)
            debug_log(f"[_dispatch_player_update] 关联关系保存完成")

        # 保存个人记忆
        dialog = resp_json.get("dialog", "")
        if dialog:
            # 截取摘要，避免过长
            summary = dialog[:500] if len(dialog) > 500 else dialog
            debug_log(f"[_dispatch_player_update] 保存个人记忆: uid={uid}, 摘要长度={len(summary)}")
            self.save_memory(f"user_{uid}", summary)

        # 剧情向量入库
        if dialog:
            debug_log(f"[_dispatch_player_update] 剧情向量入库: area={current_area}")
            self.insert_plot_vector(
                content=dialog,
                meta={"type": "player_event", "area": current_area},
            )

    def _dispatch_new_entity(
        self,
        uid: str,
        current_area: str,
        resp_json: dict,
    ) -> None:
        """
        new_entity 分支：新增世界实体

        - 自动生成唯一 entity_id
        - couch_save_entity
        - 解析 entity_data 中的 init_link 并 couch_save_link
        - save_memory 世界记忆
        - insert_plot_vector 实体背景

        Args:
            uid: 玩家唯一标识
            current_area: 当前地域
            resp_json: GM 响应数据
        """
        entity_data = resp_json.get("entity_data", {})
        if not entity_data:
            warn_log(f"new_entity 分支缺少 entity_data: uid={uid}")
            return

        # 自动生成唯一 entity_id
        entity_id = entity_data.get("id") or f"entity_{uuid.uuid4().hex[:12]}"
        entity_data["id"] = entity_id
        debug_log(f"[_dispatch_new_entity] 生成实体: id={entity_id}, type={entity_data.get('entity_type', 'unknown')}")

        # 保存实体数据
        debug_log(f"[_dispatch_new_entity] 保存实体数据: {entity_id}")
        self.couch_save_entity(entity_id, entity_data)
        debug_log(f"[_dispatch_new_entity] 实体数据保存完成: {entity_id}")

        # 解析并保存初始关联关系
        init_link = entity_data.get("init_link")
        if init_link and isinstance(init_link, list):
            debug_log(f"[_dispatch_new_entity] 保存初始关联: {len(init_link)}条")
            for link in init_link:
                from_id = link.get("from_id", entity_id)
                to_id = link.get("to_id", "")
                rel_type = link.get("rel_type", "")
                desc = link.get("desc", "")
                if to_id and rel_type:
                    self.couch_save_link(from_id, to_id, rel_type, desc)
            debug_log(f"[_dispatch_new_entity] 初始关联保存完成")

        # 保存世界记忆
        entity_name = entity_data.get("name", entity_data.get("title", "未知实体"))
        entity_type = entity_data.get("type", "unknown")
        debug_log(f"[_dispatch_new_entity] 保存世界记忆: {entity_name}")
        self.save_memory("world_global_history", f"新世界实体诞生：{entity_name}（类型：{entity_type}）")

        # 剧情向量入库 - 实体完整背景
        background = entity_data.get("background", entity_data.get("description", ""))
        if background:
            debug_log(f"[_dispatch_new_entity] 实体背景入库: 长度={len(background)}")
            self.insert_plot_vector(
                content=background,
                meta={"type": entity_type, "area": current_area},
            )

    def _dispatch_world_change(
        self,
        uid: str,
        current_area: str,
        resp_json: dict,
    ) -> None:
        """
        world_change 分支：世界变更

        - couch_save_entity 变动实体
        - couch_save_link 变更关系
        - save_memory 世界记忆
        - insert_plot_vector 变更剧情

        Args:
            uid: 玩家唯一标识
            current_area: 当前地域
            resp_json: GM 响应数据
        """
        # 保存变更实体
        changed_entities = resp_json.get("changed_entities", [])
        if isinstance(changed_entities, list):
            debug_log(f"[_dispatch_world_change] 保存变更实体: {len(changed_entities)}个")
            for entity in changed_entities:
                entity_id = entity.get("id", "")
                if entity_id:
                    self.couch_save_entity(entity_id, entity)
            debug_log(f"[_dispatch_world_change] 变更实体保存完成")

        # 保存变更关系
        changed_links = resp_json.get("changed_links", [])
        if isinstance(changed_links, list):
            debug_log(f"[_dispatch_world_change] 保存变更关系: {len(changed_links)}条")
            for link in changed_links:
                from_id = link.get("from_id", "")
                to_id = link.get("to_id", "")
                rel_type = link.get("rel_type", "")
                desc = link.get("desc", "")
                if from_id and to_id and rel_type:
                    self.couch_save_link(from_id, to_id, rel_type, desc)
            debug_log(f"[_dispatch_world_change] 变更关系保存完成")

        # 保存世界记忆
        change_summary = resp_json.get("change_summary", "")
        if change_summary:
            debug_log(f"[_dispatch_world_change] 保存世界记忆: 长度={len(change_summary)}")
            self.save_memory("world_global_history", change_summary)

        # 剧情向量入库
        change_plot = resp_json.get("change_plot", change_summary)
        if change_plot:
            meta_tags = resp_json.get("meta_tags", {})
            meta = {"type": meta_tags.get("type", "world_change"), "area": current_area}
            debug_log(f"[_dispatch_world_change] 变更剧情入库: area={current_area}")
            self.insert_plot_vector(content=change_plot, meta=meta)

    def _dispatch_world_snap(
        self,
        uid: str,
        current_area: str,
        resp_json: dict,
    ) -> None:
        """
        world_snap 分支：世界快照

        - couch_save_world_snap
        - 批量 couch_save_entity
        - 批量 couch_save_link
        - save_memory 世界记忆
        - 批量 insert_plot_vector

        Args:
            uid: 玩家唯一标识
            current_area: 当前地域
            resp_json: GM 响应数据
        """
        # 保存世界快照
        snap_data = resp_json.get("snap_data", {})
        if snap_data:
            debug_log(f"[_dispatch_world_snap] 保存世界快照: keys={list(snap_data.keys())[:5]}")
            self.couch_save_world_snap(snap_data)
            debug_log(f"[_dispatch_world_snap] 世界快照保存完成")

        # 批量保存新增实体
        new_entities = resp_json.get("new_entities", [])
        if isinstance(new_entities, list):
            debug_log(f"[_dispatch_world_snap] 批量保存实体: {len(new_entities)}个")
            for entity in new_entities:
                entity_id = entity.get("id", f"entity_{uuid.uuid4().hex[:12]}")
                self.couch_save_entity(entity_id, entity)
            debug_log(f"[_dispatch_world_snap] 批量实体保存完成")

        # 批量保存新增关系
        new_links = resp_json.get("new_links", [])
        if isinstance(new_links, list):
            debug_log(f"[_dispatch_world_snap] 批量保存关系: {len(new_links)}条")
            for link in new_links:
                from_id = link.get("from_id", "")
                to_id = link.get("to_id", "")
                rel_type = link.get("rel_type", "")
                desc = link.get("desc", "")
                if from_id and to_id and rel_type:
                    self.couch_save_link(from_id, to_id, rel_type, desc)
            debug_log(f"[_dispatch_world_snap] 批量关系保存完成")

        # 保存世界记忆 - 重大事件摘要
        event_summary = resp_json.get("event_summary", "")
        if event_summary:
            debug_log(f"[_dispatch_world_snap] 保存世界记忆: 长度={len(event_summary)}")
            self.save_memory("world_global_history", event_summary)

        # 批量剧情向量入库
        plot_entries = resp_json.get("plot_entries", [])
        if isinstance(plot_entries, list):
            debug_log(f"[_dispatch_world_snap] 批量剧情入库: {len(plot_entries)}条")
            for entry in plot_entries:
                content = entry.get("content", "")
                meta = entry.get("meta", {})
                if content:
                    # 补充 area 信息
                    if "area" not in meta:
                        meta["area"] = current_area
                    self.insert_plot_vector(content=content, meta=meta)
            debug_log(f"[_dispatch_world_snap] 批量剧情入库完成")

    # ================================================================
    # 生命周期管理
    # ================================================================

    def close(self) -> None:
        """关闭所有客户端连接"""
        # 关闭 CouchDB 客户端
        if self._couch_client:
            try:
                self._couch_client.close()
                debug_log("CouchDB 连接已关闭")
            except Exception as e:
                warn_log(f"关闭 CouchDB 连接时出错: {e}")
            finally:
                self._couch_client = None

        # 关闭 Hindsight 记忆库连接
        for bank_id, store in self._memory_stores.items():
            try:
                store.close()
                debug_log(f"Hindsight 记忆库连接已关闭: {bank_id}")
            except Exception as e:
                warn_log(f"关闭 Hindsight 记忆库连接时出错: bank_id={bank_id}, 错误: {e}")
        self._memory_stores.clear()

        info_log("GMStorage 已关闭")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False
