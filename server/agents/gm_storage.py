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
import threading
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

# 复用 search_episode 的 QdrantClient
from skills.search_episode import (
    _get_qdrant_client,
)

# 配置日志
logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────
# OpenAI Embedding 客户端
# ───────────────────────────────────────────────

class OpenAIEmbeddingClient:
    """基于 OpenAI 兼容 API 的 Embedding 客户端（线程安全）"""

    def __init__(
        self,
        api_base: str,
        api_key: str = "not-needed",
        model_name: str = "",
        max_tokens: int = 4096,
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._max_tokens = max_tokens
        self._vector_size: Optional[int] = None
        # 线程本地存储，避免多线程共享 httpx.Client 导致连接池损坏
        self._local = threading.local()
        info_log(f"OpenAI Embedding 客户端初始化: model={model_name}, api_base={api_base}")

    @property
    def _client(self) -> httpx.Client:
        """获取当前线程的 httpx.Client（线程安全）"""
        client = getattr(self._local, 'client', None)
        if client is None:
            client = httpx.Client(
                base_url=self._api_base,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(max_keepalive_connections=0),
            )
            self._local.client = client
        return client

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        调用 OpenAI 兼容的 /embeddings 接口生成向量

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        if not texts:
            return []

        try:
            resp = self._client.post(
                "embeddings",
                json={
                    "model": self._model_name,
                    "input": texts,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            embeddings = []
            # 按 index 排序确保顺序一致
            for item in sorted(data.get("data", []), key=lambda x: x.get("index", 0)):
                embeddings.append(item.get("embedding", []))

            # 缓存向量维度
            if embeddings and self._vector_size is None:
                self._vector_size = len(embeddings[0])

            return embeddings

        except Exception as e:
            error_log(f"OpenAI Embedding 调用失败: {e}")
            # 返回零向量占位
            fallback_size = self._vector_size or 1024
            return [[0.0] * fallback_size] * len(texts)

    @property
    def vector_size(self) -> int:
        """获取向量维度"""
        if self._vector_size is not None:
            return self._vector_size
        # 首次调用时通过空查询获取维度
        try:
            result = self.embed(["test"])
            if result and result[0]:
                self._vector_size = len(result[0])
                return self._vector_size
        except Exception:
            pass
        return 1024


# 全局单例缓存
_openai_embedding_client: Optional[OpenAIEmbeddingClient] = None


def _get_openai_embedding_client(config: dict) -> Optional[OpenAIEmbeddingClient]:
    """获取全局单例 OpenAIEmbeddingClient（懒加载）"""
    global _openai_embedding_client
    if _openai_embedding_client is None:
        try:
            emb_cfg = config.get("embedding_model", {})
            api_base = emb_cfg.get("api_base", "http://localhost:8888/v1")
            api_key = emb_cfg.get("api_key", "not-needed")
            model_name = emb_cfg.get("model_name", "")
            max_tokens = int(emb_cfg.get("max_tokens", 4096))

            if not model_name:
                warn_log("embedding_model.model_name 未配置，无法初始化 Embedding 客户端")
                return None

            _openai_embedding_client = OpenAIEmbeddingClient(
                api_base=api_base,
                api_key=api_key,
                model_name=model_name,
                max_tokens=max_tokens,
            )
        except Exception as e:
            error_log(f"初始化 OpenAIEmbeddingClient 失败: {e}")
            return None
    return _openai_embedding_client


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
        couch_cfg = config.get("couchdb", {})
        self._couch_url: str = couch_cfg.get("url", "http://localhost:5984").rstrip("/")
        self._couch_db_prefix: str = couch_cfg.get("db_prefix", "game_")
        self._couch_user: str = couch_cfg.get("user", "admin")
        self._couch_password: str = couch_cfg.get("password", "password")

        # CouchDB 数据库名
        self._db_players: str = f"{self._couch_db_prefix}players"
        self._db_users: str = f"{self._couch_db_prefix}users"
        self._db_entities: str = f"{self._couch_db_prefix}entities"
        self._db_links: str = f"{self._couch_db_prefix}links"
        self._db_world_snaps: str = f"{self._couch_db_prefix}world_snaps"
        self._db_chat_history: str = f"{self._couch_db_prefix}chat_history"
        self._db_layouts: str = f"{self._couch_db_prefix}layouts"
        self._db_world_time: str = f"{self._couch_db_prefix}world_time"
        self._db_weather: str = f"{self._couch_db_prefix}weather"
        self._db_action_definitions: str = f"{self._couch_db_prefix}action_definitions"
        self._db_key_events: str = f"{self._couch_db_prefix}key_events"

        # 初始化 CouchDB httpx 客户端（线程本地存储，避免多线程共享导致连接池损坏）
        self._couch_local = threading.local()

        # 确保 CouchDB 数据库存在
        self._ensure_couch_dbs()

        # ── Qdrant 配置 ──
        qdrant_cfg = config.get("qdrant", {})
        self._qdrant_collection: str = qdrant_cfg.get("collection", "episode")

        # ── Hindsight 配置 ──
        hindsight_cfg = config.get("hindsight", {})
        self._hindsight_base_url: str = hindsight_cfg.get(
            "base_url", "http://localhost:9998"
        )
        self._hindsight_api_key: Optional[str] = hindsight_cfg.get("api_key")

        # Hindsight 记忆库实例缓存
        self._memory_stores: Dict[str, HindsightMemoryStore] = {}

        info_log("GMStorage 初始化完成")

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
        client = getattr(self._couch_local, 'client', None)
        if client is None:
            client = httpx.Client(
                base_url=self._couch_url,
                auth=(self._couch_user, self._couch_password),
                headers={"Content-Type": "application/json"},
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=0),
            )
            self._couch_local.client = client
        return client

    def _ensure_couch_dbs(self) -> None:
        """确保 CouchDB 所需数据库存在，不存在则创建"""
        db_names = [
            self._db_players,
            self._db_users,
            self._db_entities,
            self._db_links,
            self._db_world_snaps,
            self._db_chat_history,
            self._db_layouts,
            self._db_world_time,
            self._db_weather,
            self._db_action_definitions,
            self._db_key_events,
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

        # 为 chat_history 创建 Mango 索引（uid + timestamp），支持排序查询
        self._ensure_chat_history_index()

    def _ensure_chat_history_index(self) -> None:
        """确保 chat_history 数据库有 uid+timestamp 的 Mango 索引"""
        try:
            # 升序索引（uid 等值查询时，同一 uid 下按 timestamp 升序排列）
            index_doc_asc = {
                "index": {
                    "fields": ["uid", "timestamp"]
                },
                "name": "uid-timestamp-asc-index",
                "type": "json"
            }
            resp = self._couch_request(
                "POST",
                f"/{self._db_chat_history}/_index",
                json_data=index_doc_asc,
            )
            if resp.status_code in (200, 201):
                debug_log("chat_history 索引创建/已存在: uid-timestamp-asc-index")
            else:
                warn_log(f"chat_history 升序索引创建失败: 状态码={resp.status_code}, 响应={resp.text[:200]}")
        except Exception as e:
            error_log(f"chat_history 索引创建异常: {e}")

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
    # CouchDB 用户操作
    # ================================================================

    def couch_get_user(self, username: str) -> dict:
        """
        通过用户名查询用户记录

        使用 Mango 查询在 users 数据库中查找匹配的 username 文档。

        Args:
            username: 用户名

        Returns:
            用户数据字典，失败返回空字典
        """
        try:
            body = {
                "selector": {"username": username},
                "limit": 1,
            }
            resp = self._couch_request(
                "POST",
                f"/{self._db_users}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                if docs:
                    debug_log(f"查询用户成功: {username}")
                    return docs[0]
                else:
                    debug_log(f"用户不存在: {username}")
                    return {}
            else:
                warn_log(f"查询用户失败: {username}, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"查询用户异常: {username}, 错误: {e}")
            return {}

    def couch_save_user(self, username: str, user_data: dict) -> dict:
        """
        保存用户记录，使用 username 作为文档 ID

        如果文档已存在，自动携带 _rev 进行更新。

        Args:
            username: 用户名，同时作为文档 ID
            user_data: 用户数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            # 先查询现有文档获取 _rev
            resp = self._couch_request("GET", f"/{self._db_users}/{username}")
            if resp.status_code == 200:
                existing = resp.json()
                if "_rev" in existing:
                    user_data["_rev"] = existing["_rev"]
            elif resp.status_code != 404:
                warn_log(f"查询用户文档失败: {username}, 状态码: {resp.status_code}")

            resp = self._couch_request("PUT", f"/{self._db_users}/{username}", json_data=user_data)
            if resp.status_code in (201, 202):
                info_log(f"保存用户记录成功: {username}")
                return resp.json()
            else:
                warn_log(f"保存用户记录失败: {username}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存用户记录异常: {username}, 错误: {e}")
            return {}

    def couch_get_user_by_uid(self, uid: str) -> dict:
        """
        通过 uid 查询用户记录

        使用 Mango 查询在 users 数据库中查找匹配的 uid 文档。

        Args:
            uid: 用户唯一标识

        Returns:
            用户数据字典，失败返回空字典
        """
        try:
            body = {
                "selector": {"uid": uid},
                "limit": 1,
            }
            resp = self._couch_request(
                "POST",
                f"/{self._db_users}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                if docs:
                    debug_log(f"通过 uid 查询用户成功: {uid}")
                    return docs[0]
                else:
                    debug_log(f"uid 对应用户不存在: {uid}")
                    return {}
            else:
                warn_log(f"通过 uid 查询用户失败: {uid}, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"通过 uid 查询用户异常: {uid}, 错误: {e}")
            return {}

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

    # ================================================================
    # CouchDB 动作定义操作
    # ================================================================

    def couch_get_action_definition(self, action_id: str) -> dict:
        """
        获取动作类型定义

        Args:
            action_id: 动作唯一标识

        Returns:
            动作定义数据字典，失败返回空字典
        """
        try:
            resp = self._couch_request("GET", f"/{self._db_action_definitions}/{action_id}")
            if resp.status_code == 200:
                data = resp.json()
                debug_log(f"获取动作定义成功: {action_id}")
                return data
            elif resp.status_code == 404:
                debug_log(f"动作定义不存在: {action_id}")
                return {}
            else:
                warn_log(f"获取动作定义失败: {action_id}, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"获取动作定义异常: {action_id}, 错误: {e}")
            return {}

    def couch_save_action_definition(self, action_id: str, data: dict) -> dict:
        """
        保存动作类型定义（新增或更新）

        Args:
            action_id: 动作唯一标识
            data: 动作定义数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            existing = self.couch_get_action_definition(action_id)
            if existing and "_rev" in existing:
                data["_rev"] = existing["_rev"]

            resp = self._couch_request("PUT", f"/{self._db_action_definitions}/{action_id}", json_data=data)
            if resp.status_code in (201, 202):
                info_log(f"保存动作定义成功: {action_id}")
                return resp.json()
            else:
                warn_log(f"保存动作定义失败: {action_id}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存动作定义异常: {action_id}, 错误: {e}")
            return {}

    def couch_list_action_definitions(self, category: str = "") -> list:
        """
        列出所有动作类型定义

        Args:
            category: 类别过滤，为空则返回所有

        Returns:
            动作定义列表
        """
        try:
            selector: Dict[str, Any] = {}
            if category:
                selector["category"] = category

            body = {
                "selector": selector,
                "limit": 1000,
            }

            resp = self._couch_request(
                "POST",
                f"/{self._db_action_definitions}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                debug_log(f"列出动作定义: category={category}, 找到 {len(docs)} 条")
                return docs
            else:
                warn_log(f"列出动作定义失败: 状态码: {resp.status_code}")
                return []
        except Exception as e:
            error_log(f"列出动作定义异常: 错误: {e}")
            return []

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

    def couch_find_entity_by_name(self, name: str, entity_type: str = "") -> list:
        """
        按名称查询实体，返回匹配的文档列表

        Args:
            name: 实体名称
            entity_type: 实体类型过滤，为空则不过滤

        Returns:
            匹配的实体文档列表
        """
        try:
            selector: Dict[str, Any] = {"name": name}
            if entity_type:
                selector["entity_type"] = entity_type

            body = {
                "selector": selector,
                "limit": 10,
            }

            resp = self._couch_request(
                "POST",
                f"/{self._db_entities}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                debug_log(f"按名称查询实体: name={name}, type={entity_type}, 找到 {len(docs)} 条")
                return docs
            else:
                warn_log(f"按名称查询实体失败: name={name}, 状态码: {resp.status_code}")
                return []
        except Exception as e:
            error_log(f"按名称查询实体异常: name={name}, 错误: {e}")
            return []

    def save_entities_from_chat(self, uid: str, current_area: str, entities: list) -> int:
        """
        将聊天中出现的实体自动保存到数据库

        - 按名称+类型去重，已存在则跳过
        - 将 entities 格式转换为 entity_data 格式
        - 自动生成 entity_id
        - 保存实体数据到 CouchDB
        - 保存世界记忆

        Args:
            uid: 玩家唯一标识
            current_area: 当前地域
            entities: LLM 响应中的 entities 数组

        Returns:
            新增实体数量
        """
        if not entities:
            return 0

        # entities type 到 entity_type 的映射
        type_mapping = {
            "character": "npc",
            "place": "area",
            "weapon": "equip",
            "technique": "technique",
            "item": "treasure",
        }

        # detail 字段到 attr 的提取映射
        attr_keys = {
            "character": "realm",
            "place": "spirit_level",
            "weapon": "grade",
            "technique": "grade",
            "item": "grade",
        }

        new_count = 0

        for entity in entities:
            if not isinstance(entity, dict):
                continue

            name = entity.get("name", "")
            entity_type_raw = entity.get("type", "")
            desc = entity.get("desc", "")
            detail = entity.get("detail", {})

            if not name or not entity_type_raw:
                continue

            entity_type = type_mapping.get(entity_type_raw, entity_type_raw)

            # 去重：按名称+类型查询是否已存在
            existing = self.couch_find_entity_by_name(name, entity_type)
            if existing:
                debug_log(f"实体已存在，跳过: name={name}, type={entity_type}")
                continue

            # 生成唯一 entity_id
            entity_id = f"entity_{uuid.uuid4().hex[:12]}"

            # 从 detail 中提取 attr
            attr_key = attr_keys.get(entity_type_raw, "")
            attr_value = detail.get(attr_key, "") if detail and attr_key else ""

            # 构建实体数据
            entity_data = {
                "entity_type": entity_type,
                "name": name,
                "base_info": desc,
                "attr": attr_value,
                "birth_story": "",
                "belong_area": current_area,
                "source": "chat",
            }

            # 保留 detail 原始数据
            if detail and isinstance(detail, dict):
                entity_data["detail"] = detail

            # 保存实体
            debug_log(f"[save_entities_from_chat] 保存实体: id={entity_id}, name={name}, type={entity_type}")
            self.couch_save_entity(entity_id, entity_data)
            new_count += 1

            # 保存世界记忆
            try:
                self.save_memory("world_global_history", f"新实体出现：{name}（类型：{entity_type}）{desc}")
            except Exception as e:
                warn_log(f"保存实体世界记忆失败: name={name}, 错误: {e}")

        if new_count > 0:
            info_log(f"实体自动持久化完成: uid={uid}, 新增={new_count}/{len(entities)}")

        return new_count

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
    # 布局操作
    # ================================================================

    def couch_get_layout(self, uid: str, panel_type: str) -> dict:
        """
        获取指定用户的面板布局

        Args:
            uid: 玩家唯一标识
            panel_type: 面板类型，"character" 或 "world"

        Returns:
            布局数据字典，失败返回空字典
        """
        try:
            doc_id = f"layout_{uid}_{panel_type}"
            resp = self._couch_request("GET", f"/{self._db_layouts}/{doc_id}")
            if resp.status_code == 200:
                data = resp.json()
                debug_log(f"获取布局成功: uid={uid}, panel_type={panel_type}")
                return data
            elif resp.status_code == 404:
                debug_log(f"布局不存在: uid={uid}, panel_type={panel_type}")
                return {}
            else:
                warn_log(f"获取布局失败: uid={uid}, panel_type={panel_type}, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"获取布局异常: uid={uid}, panel_type={panel_type}, 错误: {e}")
            return {}

    def couch_save_layout(self, uid: str, panel_type: str, layout_data: dict) -> dict:
        """
        保存/更新面板布局

        如果布局已存在，自动携带 _rev 进行更新。

        Args:
            uid: 玩家唯一标识
            panel_type: 面板类型，"character" 或 "world"
            layout_data: 布局数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            doc_id = f"layout_{uid}_{panel_type}"

            # 先查询现有文档获取 _rev
            existing = self.couch_get_layout(uid, panel_type)
            if existing and "_rev" in existing:
                layout_data["_rev"] = existing["_rev"]

            # 设置元数据
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            layout_data["_id"] = doc_id
            layout_data["uid"] = uid
            layout_data["panel_type"] = panel_type
            if "created_at" not in layout_data and not existing:
                layout_data["created_at"] = now
            layout_data["updated_at"] = now

            resp = self._couch_request("PUT", f"/{self._db_layouts}/{doc_id}", json_data=layout_data)
            if resp.status_code in (201, 202):
                info_log(f"保存布局成功: uid={uid}, panel_type={panel_type}")
                return resp.json()
            else:
                warn_log(f"保存布局失败: uid={uid}, panel_type={panel_type}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存布局异常: uid={uid}, panel_type={panel_type}, 错误: {e}")
            return {}

    # ================================================================
    # 世界时间操作
    # ================================================================

    def couch_get_world_time(self) -> dict:
        """
        获取世界时间状态

        文档 ID 固定为 'world_time_state'。

        Returns:
            时间状态字典，失败返回空字典
        """
        try:
            resp = self._couch_request("GET", f"/{self._db_world_time}/world_time_state")
            if resp.status_code == 200:
                data = resp.json()
                debug_log("获取世界时间状态成功")
                return data
            elif resp.status_code == 404:
                debug_log("世界时间状态不存在，首次初始化")
                return {}
            else:
                warn_log(f"获取世界时间状态失败, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"获取世界时间状态异常: {e}")
            return {}

    def couch_save_world_time(self, time_data: dict) -> dict:
        """
        保存世界时间状态

        文档 ID 固定为 'world_time_state'，自动携带 _rev 进行更新。
        遇到 409 冲突时会自动重试（最多 3 次）。

        Args:
            time_data: 时间状态数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            # 确保文档 ID 正确
            time_data["_id"] = "world_time_state"

            for attempt in range(3):
                # 先查询现有文档获取 _rev
                resp = self._couch_request("GET", f"/{self._db_world_time}/world_time_state")
                if resp.status_code == 200:
                    existing = resp.json()
                    if "_rev" in existing:
                        time_data["_rev"] = existing["_rev"]
                elif resp.status_code != 404:
                    warn_log(f"查询世界时间文档失败, 状态码: {resp.status_code}")

                resp = self._couch_request(
                    "PUT",
                    f"/{self._db_world_time}/world_time_state",
                    json_data=time_data,
                )
                if resp.status_code in (201, 202):
                    info_log("保存世界时间状态成功")
                    return resp.json()
                if resp.status_code == 409 and attempt < 2:
                    warn_log(f"保存世界时间状态冲突，第 {attempt + 1} 次重试...")
                    continue

                warn_log(f"保存世界时间状态失败, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存世界时间状态异常: {e}")
            return {}

    # ================================================================
    # 聊天记录操作
    # ================================================================

    def couch_get_weather(self) -> dict:
        """
        获取天气状态

        文档 ID 固定为 'weather_state'。

        Returns:
            天气状态字典，失败返回空字典
        """
        try:
            resp = self._couch_request("GET", f"/{self._db_weather}/weather_state")
            if resp.status_code == 200:
                data = resp.json()
                debug_log("获取天气状态成功")
                return data
            elif resp.status_code == 404:
                debug_log("天气状态不存在，首次初始化")
                return {}
            else:
                warn_log(f"获取天气状态失败, 状态码: {resp.status_code}")
                return {}
        except Exception as e:
            error_log(f"获取天气状态异常: {e}")
            return {}

    def couch_save_weather(self, weather_data: dict) -> dict:
        """
        保存天气状态

        文档 ID 固定为 'weather_state'，自动携带 _rev 进行更新。
        遇到 409 冲突时会自动重试（最多 3 次）。

        Args:
            weather_data: 天气状态数据

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            # 确保文档 ID 正确
            weather_data["_id"] = "weather_state"

            for attempt in range(3):
                # 先查询现有文档获取 _rev
                resp = self._couch_request("GET", f"/{self._db_weather}/weather_state")
                if resp.status_code == 200:
                    existing = resp.json()
                    if "_rev" in existing:
                        weather_data["_rev"] = existing["_rev"]
                elif resp.status_code != 404:
                    warn_log(f"查询天气文档失败, 状态码: {resp.status_code}")

                resp = self._couch_request(
                    "PUT",
                    f"/{self._db_weather}/weather_state",
                    json_data=weather_data,
                )
                if resp.status_code in (201, 202):
                    info_log("保存天气状态成功")
                    return resp.json()
                if resp.status_code == 409 and attempt < 2:
                    warn_log(f"保存天气状态冲突，第 {attempt + 1} 次重试...")
                    continue

                warn_log(f"保存天气状态失败, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存天气状态异常: {e}")
            return {}

    def save_chat_message(
        self,
        uid: str,
        sender: str,
        content: str,
        timestamp: int,
        actions: Optional[list] = None,
        player_update: Optional[dict] = None,
        ui_config: Optional[dict] = None,
        game_date: Optional[str] = None,
        game_shichen: Optional[str] = None,
        location: Optional[str] = None,
        weather: Optional[str] = None,
        weather_desc: Optional[str] = None,
        spirit_tide: Optional[bool] = None,
        doc_id: Optional[str] = None,
        entities: Optional[list] = None,
    ) -> dict:
        """
        保存单条聊天消息到 thatman_chat_history

        Args:
            uid: 玩家唯一标识
            sender: 发送者，"player" 或 "npc"
            content: 消息内容
            timestamp: 消息时间戳（毫秒）
            actions: 建议动作列表（仅 NPC 消息）
            player_update: 玩家数据变更（仅 NPC 消息）
            ui_config: UI 配置变更（仅 NPC 消息）
            game_date: 游戏日期，如"天元三千六百年·正月初一"
            game_shichen: 游戏时辰，如"卯时·清晨"
            location: 当前地点
            weather: 天气，如"晴朗"
            weather_desc: 天气描述，如"微风"
            spirit_tide: 灵潮状态
            doc_id: 可选，指定文档 ID，不传则自动生成
            entities: 实体列表（仅 NPC 消息）

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            if not doc_id:
                doc_id = f"msg_{timestamp}_{uuid.uuid4().hex[:8]}"
            doc = {
                "_id": doc_id,
                "uid": uid,
                "sender": sender,
                "content": content,
                "timestamp": timestamp,
            }
            if actions:
                doc["actions"] = actions
            if player_update:
                doc["player_update"] = player_update
            if ui_config:
                doc["ui_config"] = ui_config
            if game_date:
                doc["game_date"] = game_date
            if game_shichen:
                doc["game_shichen"] = game_shichen
            if location:
                doc["location"] = location
            if weather:
                doc["weather"] = weather
            if weather_desc:
                doc["weather_desc"] = weather_desc
            if spirit_tide is not None:
                doc["spirit_tide"] = spirit_tide
            if entities:
                doc["entities"] = entities

            resp = self._couch_request("PUT", f"/{self._db_chat_history}/{doc_id}", json_data=doc)
            if resp.status_code in (201, 202):
                debug_log(f"保存聊天消息成功: uid={uid}, sender={sender}")
                return resp.json()
            else:
                warn_log(f"保存聊天消息失败: uid={uid}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存聊天消息异常: uid={uid}, 错误: {e}")
            return {}

    def get_chat_history(self, uid: str, limit: int = 100, before_timestamp: Optional[int] = None) -> list:
        """
        获取用户聊天历史（支持分页）

        Args:
            uid: 玩家唯一标识
            limit: 返回消息数量上限
            before_timestamp: 获取此时间戳之前的消息（用于分页加载更早记录）

        Returns:
            聊天消息列表，按时间升序排列（从早到晚），失败返回空列表
        """
        try:
            selector: Dict[str, Any] = {"uid": uid}
            if before_timestamp:
                selector["timestamp"] = {"$lt": before_timestamp}

            # 不在查询中指定 sort，避免 json 索引的 sort 字段必须完全匹配索引的限制
            # CouchDB 仍会使用 uid-timestamp-asc-index 进行 selector 筛选
            # 返回结果在同一 uid 下天然按 timestamp 升序排列，在 Python 中截取即可
            body = {
                "selector": selector,
                "limit": 10000,
            }

            resp = self._couch_request(
                "POST",
                f"/{self._db_chat_history}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                # 反转为降序（最新的在前），截取前 limit 条
                docs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                docs = docs[:limit]
                # 再反转为升序（时间从早到晚，适合前端展示）
                docs.reverse()
                info_log(f"获取聊天历史成功: uid={uid}, 数量={len(docs)}, before_timestamp={before_timestamp}")
                return docs
            else:
                warn_log(f"获取聊天历史失败: uid={uid}, 状态码: {resp.status_code}, 响应={resp.text[:200]}")
                return []
        except Exception as e:
            error_log(f"获取聊天历史异常: uid={uid}, 错误: {e}")
            return []

    def delete_chat_message(self, uid: str, message_id: str):
        """
        删除单条聊天消息

        Args:
            uid: 玩家唯一标识
            message_id: 消息文档ID（对应 CouchDB 的 _id）

        Returns:
            True 表示删除成功
            "not_found" 表示消息不存在
            "forbidden" 表示消息不属于该用户
            False 表示其他失败
        """
        try:
            # 先查询该消息，确认存在且属于该用户
            resp = self._couch_request("GET", f"/{self._db_chat_history}/{message_id}")
            if resp.status_code == 404:
                warn_log(f"查询消息失败: uid={uid}, message_id={message_id}, 状态码: 404")
                return "not_found"
            if resp.status_code != 200:
                warn_log(f"查询消息失败: uid={uid}, message_id={message_id}, 状态码: {resp.status_code}")
                return False

            doc = resp.json()
            if doc.get("uid") != uid:
                warn_log(f"消息不属于该用户: uid={uid}, message_id={message_id}")
                return "forbidden"

            rev = doc.get("_rev")
            del_resp = self._couch_request(
                "DELETE",
                f"/{self._db_chat_history}/{message_id}?rev={rev}",
            )
            if del_resp.status_code in (200, 202):
                info_log(f"删除聊天消息成功: uid={uid}, message_id={message_id}")
                return True
            else:
                warn_log(f"删除聊天消息失败: uid={uid}, message_id={message_id}, 状态码: {del_resp.status_code}")
                return False
        except Exception as e:
            error_log(f"删除聊天消息异常: uid={uid}, message_id={message_id}, 错误: {e}")
            return False

    def clear_chat_history(self, uid: str) -> bool:
        """
        清除用户聊天历史

        Args:
            uid: 玩家唯一标识

        Returns:
            True 表示清除成功，False 表示失败
        """
        try:
            # 先查询所有该用户的消息
            body = {
                "selector": {"uid": uid},
                "limit": 1000,
            }
            resp = self._couch_request(
                "POST",
                f"/{self._db_chat_history}/_find",
                json_data=body,
            )
            if resp.status_code != 200:
                warn_log(f"查询聊天历史失败: uid={uid}, 状态码: {resp.status_code}")
                return False

            docs = resp.json().get("docs", [])
            if not docs:
                debug_log(f"无聊天历史需要清除: uid={uid}")
                return True

            # 批量删除
            deleted = 0
            for doc in docs:
                del_resp = self._couch_request(
                    "DELETE",
                    f"/{self._db_chat_history}/{doc['_id']}?rev={doc['_rev']}",
                )
                if del_resp.status_code in (200, 202):
                    deleted += 1

            info_log(f"清除聊天历史完成: uid={uid}, 删除={deleted}/{len(docs)}")
            return True
        except Exception as e:
            error_log(f"清除聊天历史异常: uid={uid}, 错误: {e}")
            return False

    # ================================================================
    # Qdrant 剧情向量操作
    # ================================================================

    def search_plot_vector(self, query: str, top_k: int = 3) -> list:
        """
        语义检索过往剧情

        复用 search_episode 的 QdrantClient，使用 OpenAI 兼容 Embedding API。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            相似剧情列表，每项包含 content 和 score，失败返回空列表
        """
        try:
            embedding_client = _get_openai_embedding_client(self.config)
            if not embedding_client:
                warn_log("OpenAIEmbeddingClient 未初始化，无法检索剧情向量")
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

        复用 search_episode 的 QdrantClient，使用 OpenAI 兼容 Embedding API。

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

            embedding_client = _get_openai_embedding_client(self.config)
            if not embedding_client:
                warn_log("OpenAIEmbeddingClient 未初始化，无法入库剧情向量")
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
            # 先获取现有文档，进行增量合并，避免覆盖其他字段
            existing = self.couch_get_player(uid)
            if existing and "_id" in existing:
                merged = {**existing, **player_update}
                # 移除 CouchDB 内部字段，避免冲突
                merged.pop("_id", None)
                merged.pop("_rev", None)
                self.couch_save_player(uid, merged)
            else:
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
    # 关键事件操作
    # ================================================================

    def couch_save_key_event(self, uid: str, event_data: dict) -> dict:
        """
        保存关键事件

        Args:
            uid: 玩家唯一标识
            event_data: 事件数据，包含 title, description, status 等

        Returns:
            CouchDB 写入响应，失败返回空字典
        """
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            event_id = event_data.get("_id") or f"event_{uuid.uuid4().hex[:12]}"
            event_data["_id"] = event_id
            event_data["uid"] = uid
            if "created_at" not in event_data:
                event_data["created_at"] = now
            event_data["updated_at"] = now

            # 检查是否已存在（更新场景）
            existing_resp = self._couch_request("GET", f"/{self._db_key_events}/{event_id}")
            if existing_resp.status_code == 200:
                existing = existing_resp.json()
                if "_rev" in existing:
                    event_data["_rev"] = existing["_rev"]
                # 保留原始 created_at
                if "created_at" in existing and "created_at" not in event_data:
                    event_data["created_at"] = existing["created_at"]

            resp = self._couch_request("PUT", f"/{self._db_key_events}/{event_id}", json_data=event_data)
            if resp.status_code in (201, 202):
                info_log(f"保存关键事件成功: uid={uid}, event_id={event_id}")
                return resp.json()
            else:
                warn_log(f"保存关键事件失败: uid={uid}, event_id={event_id}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
                return {}
        except Exception as e:
            error_log(f"保存关键事件异常: uid={uid}, 错误: {e}")
            return {}

    def couch_get_key_events(self, uid: str, status: str = "") -> list:
        """
        获取用户的关键事件列表

        Args:
            uid: 玩家唯一标识
            status: 事件状态过滤，"ongoing" 或 "completed"，为空则返回所有

        Returns:
            事件列表，按 created_at 降序排列（最新在前），失败返回空列表
        """
        try:
            selector: Dict[str, Any] = {"uid": uid}
            if status:
                selector["status"] = status

            body = {
                "selector": selector,
                "limit": 1000,
            }

            resp = self._couch_request(
                "POST",
                f"/{self._db_key_events}/_find",
                json_data=body,
            )
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("docs", [])
                # 按 created_at 降序排列（最新在前）
                docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                info_log(f"获取关键事件成功: uid={uid}, status={status}, 数量={len(docs)}")
                return docs
            else:
                warn_log(f"获取关键事件失败: uid={uid}, 状态码: {resp.status_code}")
                return []
        except Exception as e:
            error_log(f"获取关键事件异常: uid={uid}, 错误: {e}")
            return []

    def couch_delete_key_event(self, uid: str, event_id: str):
        """
        删除关键事件

        Args:
            uid: 玩家唯一标识
            event_id: 事件文档 ID

        Returns:
            True 表示删除成功
            "not_found" 表示事件不存在
            "forbidden" 表示事件不属于该用户
            False 表示其他失败
        """
        try:
            # 先查询该事件，确认存在且属于该用户
            resp = self._couch_request("GET", f"/{self._db_key_events}/{event_id}")
            if resp.status_code == 404:
                warn_log(f"查询关键事件失败: uid={uid}, event_id={event_id}, 状态码: 404")
                return "not_found"
            if resp.status_code != 200:
                warn_log(f"查询关键事件失败: uid={uid}, event_id={event_id}, 状态码: {resp.status_code}")
                return False

            doc = resp.json()
            if doc.get("uid") != uid:
                warn_log(f"关键事件不属于该用户: uid={uid}, event_id={event_id}")
                return "forbidden"

            rev = doc.get("_rev")
            del_resp = self._couch_request(
                "DELETE",
                f"/{self._db_key_events}/{event_id}?rev={rev}",
            )
            if del_resp.status_code in (200, 202):
                info_log(f"删除关键事件成功: uid={uid}, event_id={event_id}")
                return True
            else:
                warn_log(f"删除关键事件失败: uid={uid}, event_id={event_id}, 状态码: {del_resp.status_code}")
                return False
        except Exception as e:
            error_log(f"删除关键事件异常: uid={uid}, event_id={event_id}, 错误: {e}")
            return False

    # ================================================================
    # 生命周期管理
    # ================================================================

    def close(self) -> None:
        """关闭所有客户端连接"""
        # 关闭当前线程的 CouchDB 客户端
        client = getattr(self._couch_local, 'client', None)
        if client:
            try:
                client.close()
                debug_log("CouchDB 连接已关闭")
            except Exception as e:
                warn_log(f"关闭 CouchDB 连接时出错: {e}")
            finally:
                self._couch_local.client = None

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
