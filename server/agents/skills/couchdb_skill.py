"""
CouchDB Skill - CouchDB 读写技能

封装 CouchDB 的玩家、实体、关系、世界快照的读写操作，
供 LLM function calling 或其他模块直接调用。

用法:
    from skills.couchdb_skill import (
        couch_get_player, couch_save_player,
        couch_get_entity, couch_save_entity,
        couch_get_link, couch_save_link,
        couch_get_last_world_snap, couch_save_world_snap,
    )

    # 查询玩家
    player = couch_get_player("uid_001")

    # 保存玩家
    couch_save_player("uid_001", {"name": "张三", "level": 5})
"""

import os
import uuid
import logging
from typing import Dict, Any, Optional

import httpx
import yaml

# 配置日志
logger = logging.getLogger(__name__)


def debug_log(message: str):
    """输出 DEBUG 级别日志（灰色）"""
    logger.debug(message)
    print(f"\033[90m[DEBUG] {message}\033[0m")


def info_log(message: str):
    """输出 INFO 级别日志（白色）"""
    logger.info(message)
    print(f"\033[97m[INFO] {message}\033[0m")


def warn_log(message: str):
    """输出 WARN 级别日志（黄色）"""
    logger.warning(message)
    print(f"\033[93m[WARN] {message}\033[0m")


def error_log(message: str):
    """输出 ERROR 级别日志（红色）"""
    logger.error(message)
    print(f"\033[91m[ERROR] {message}\033[0m")


# ───────────────────────────────────────────────
# 配置加载
# ───────────────────────────────────────────────

def _load_couchdb_config() -> Dict[str, Any]:
    """从 config.yaml 加载 CouchDB 配置"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config.yaml",
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("couchdb", {})
    except Exception as e:
        error_log(f"加载 CouchDB 配置失败: {e}")
        return {}


# ───────────────────────────────────────────────
# 全局单例 CouchDB 客户端
# ───────────────────────────────────────────────

_couch_client: Optional[httpx.Client] = None
_couch_db_prefix: str = "game_"
_db_players: str = "game_players"
_db_entities: str = "game_entities"
_db_links: str = "game_links"
_db_world_snaps: str = "game_world_snaps"


def _get_couch_client() -> Optional[httpx.Client]:
    """获取全局单例 CouchDB HTTP 客户端（懒加载）"""
    global _couch_client, _couch_db_prefix
    global _db_players, _db_entities, _db_links, _db_world_snaps

    if _couch_client is not None:
        return _couch_client

    cfg = _load_couchdb_config()
    url = cfg.get("url", "http://localhost:5984").rstrip("/")
    user = cfg.get("user", "admin")
    password = cfg.get("password", "password")
    _couch_db_prefix = cfg.get("db_prefix", "game_")

    _db_players = f"{_couch_db_prefix}players"
    _db_entities = f"{_couch_db_prefix}entities"
    _db_links = f"{_couch_db_prefix}links"
    _db_world_snaps = f"{_couch_db_prefix}world_snaps"

    try:
        _couch_client = httpx.Client(
            base_url=url,
            auth=(user, password),
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        # 测试连接
        resp = _couch_client.get("/")
        if resp.status_code == 200:
            info_log(f"CouchDB 连接成功: {url}")
            _ensure_dbs()
        else:
            warn_log(f"CouchDB 连接异常: 状态码 {resp.status_code}")
    except Exception as e:
        error_log(f"连接 CouchDB 失败: {e}")
        _couch_client = None

    return _couch_client


def _ensure_dbs() -> None:
    """确保 CouchDB 所需数据库存在"""
    client = _couch_client
    if not client:
        return

    db_names = [_db_players, _db_entities, _db_links, _db_world_snaps]
    for db_name in db_names:
        try:
            resp = client.head(f"/{db_name}")
            if resp.status_code == 404:
                resp = client.put(f"/{db_name}")
                if resp.status_code in (201, 202):
                    info_log(f"CouchDB 数据库已创建: {db_name}")
                else:
                    warn_log(f"CouchDB 数据库创建失败: {db_name}, 状态码: {resp.status_code}")
            else:
                debug_log(f"CouchDB 数据库已存在: {db_name}")
        except Exception as e:
            error_log(f"检查/创建 CouchDB 数据库失败: {db_name}, 错误: {e}")


def _couch_request(method: str, path: str, *, json_data: Optional[dict] = None) -> Optional[httpx.Response]:
    """发送 CouchDB HTTP 请求"""
    client = _get_couch_client()
    if not client:
        return None
    try:
        return client.request(method=method, url=path, json=json_data)
    except Exception as e:
        error_log(f"CouchDB 请求失败: {method} {path}, 错误: {e}")
        return None


# ================================================================
# ① 玩家数据 (CouchDB)
# ================================================================

def couch_get_player(uid: str) -> Dict[str, Any]:
    """
    查询玩家全档案，返回玩家的完整数据

    Args:
        uid: 玩家唯一标识

    Returns:
        包含玩家数据的字典:
        {
            "success": True/False,
            "uid": "uid_001",
            "data": {...},
            "error": "错误信息（如果有）"
        }
    """
    try:
        resp = _couch_request("GET", f"/{_db_players}/{uid}")
        if resp is None:
            return {"success": False, "uid": uid, "data": {}, "error": "CouchDB 客户端不可用"}
        if resp.status_code == 200:
            data = resp.json()
            debug_log(f"获取玩家数据成功: {uid}")
            return {"success": True, "uid": uid, "data": data, "error": ""}
        elif resp.status_code == 404:
            warn_log(f"玩家不存在: {uid}")
            return {"success": False, "uid": uid, "data": {}, "error": f"玩家不存在: {uid}"}
        else:
            warn_log(f"获取玩家数据失败: {uid}, 状态码: {resp.status_code}")
            return {"success": False, "uid": uid, "data": {}, "error": f"请求失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"获取玩家数据异常: {uid}, 错误: {e}")
        return {"success": False, "uid": uid, "data": {}, "error": str(e)}


def couch_save_player(uid: str, data: dict) -> Dict[str, Any]:
    """
    保存玩家变更数据，新增或更新玩家档案

    如果文档已存在，自动携带 _rev 进行更新。

    Args:
        uid: 玩家唯一标识
        data: 玩家变更后的完整数据

    Returns:
        保存结果字典:
        {
            "success": True/False,
            "uid": "uid_001",
            "rev": "文档版本号",
            "error": "错误信息（如果有）"
        }
    """
    try:
        # 先查询现有文档获取 _rev
        existing = couch_get_player(uid)
        if existing.get("success") and "_rev" in existing.get("data", {}):
            data["_rev"] = existing["data"]["_rev"]

        resp = _couch_request("PUT", f"/{_db_players}/{uid}", json_data=data)
        if resp is None:
            return {"success": False, "uid": uid, "rev": "", "error": "CouchDB 客户端不可用"}
        if resp.status_code in (201, 202):
            result = resp.json()
            info_log(f"保存玩家数据成功: {uid}")
            return {"success": True, "uid": uid, "rev": result.get("rev", ""), "error": ""}
        else:
            warn_log(f"保存玩家数据失败: {uid}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
            return {"success": False, "uid": uid, "rev": "", "error": f"保存失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"保存玩家数据异常: {uid}, 错误: {e}")
        return {"success": False, "uid": uid, "rev": "", "error": str(e)}


# ================================================================
# ② 全局实体：NPC / 地点 / 法宝 / 宗门 (CouchDB 统一 entity 库)
# ================================================================

def couch_get_entity(entity_id: str) -> Dict[str, Any]:
    """
    按实体ID查询实体详情，如NPC、装备、区域等

    Args:
        entity_id: 实体唯一标识

    Returns:
        包含实体数据的字典:
        {
            "success": True/False,
            "entity_id": "npc_001",
            "data": {...},
            "error": "错误信息（如果有）"
        }
    """
    try:
        resp = _couch_request("GET", f"/{_db_entities}/{entity_id}")
        if resp is None:
            return {"success": False, "entity_id": entity_id, "data": {}, "error": "CouchDB 客户端不可用"}
        if resp.status_code == 200:
            data = resp.json()
            debug_log(f"获取实体数据成功: {entity_id}")
            return {"success": True, "entity_id": entity_id, "data": data, "error": ""}
        elif resp.status_code == 404:
            warn_log(f"实体不存在: {entity_id}")
            return {"success": False, "entity_id": entity_id, "data": {}, "error": f"实体不存在: {entity_id}"}
        else:
            warn_log(f"获取实体数据失败: {entity_id}, 状态码: {resp.status_code}")
            return {"success": False, "entity_id": entity_id, "data": {}, "error": f"请求失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"获取实体数据异常: {entity_id}, 错误: {e}")
        return {"success": False, "entity_id": entity_id, "data": {}, "error": str(e)}


def couch_save_entity(entity_id: str, entity_data: dict) -> Dict[str, Any]:
    """
    新增或修改实体数据

    如果文档已存在，自动携带 _rev 进行更新。

    Args:
        entity_id: 实体唯一标识
        entity_data: 实体变更后的完整数据

    Returns:
        保存结果字典:
        {
            "success": True/False,
            "entity_id": "npc_001",
            "rev": "文档版本号",
            "error": "错误信息（如果有）"
        }
    """
    try:
        # 先查询现有文档获取 _rev
        existing = couch_get_entity(entity_id)
        if existing.get("success") and "_rev" in existing.get("data", {}):
            entity_data["_rev"] = existing["data"]["_rev"]

        resp = _couch_request("PUT", f"/{_db_entities}/{entity_id}", json_data=entity_data)
        if resp is None:
            return {"success": False, "entity_id": entity_id, "rev": "", "error": "CouchDB 客户端不可用"}
        if resp.status_code in (201, 202):
            result = resp.json()
            info_log(f"保存实体数据成功: {entity_id}")
            return {"success": True, "entity_id": entity_id, "rev": result.get("rev", ""), "error": ""}
        else:
            warn_log(f"保存实体数据失败: {entity_id}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
            return {"success": False, "entity_id": entity_id, "rev": "", "error": f"保存失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"保存实体数据异常: {entity_id}, 错误: {e}")
        return {"success": False, "entity_id": entity_id, "rev": "", "error": str(e)}


# ================================================================
# ③ 关联关系：师徒 / 仇敌 / 入宗 / 领地 (CouchDB link 库)
# ================================================================

def couch_get_link(target_id: str, rel_type: str = "") -> Dict[str, Any]:
    """
    查询指定目标ID和关系类型的关联关系

    使用 CouchDB Mango 查询，查找 from_id 或 to_id 等于 target_id 的关系文档。

    Args:
        target_id: 目标实体ID
        rel_type: 关系类型过滤，如 owns、belongs_to、located_in 等，为空则返回所有关系

    Returns:
        关联关系查询结果:
        {
            "success": True/False,
            "target_id": "npc_001",
            "rel_type": "owns",
            "total": 3,
            "docs": [...],
            "error": "错误信息（如果有）"
        }
    """
    try:
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

        resp = _couch_request("POST", f"/{_db_links}/_find", json_data=body)
        if resp is None:
            return {"success": False, "target_id": target_id, "rel_type": rel_type, "total": 0, "docs": [], "error": "CouchDB 客户端不可用"}
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("docs", [])
            debug_log(f"查询关联关系成功: target_id={target_id}, rel_type={rel_type}, 找到 {len(docs)} 条")
            return {"success": True, "target_id": target_id, "rel_type": rel_type, "total": len(docs), "docs": docs, "error": ""}
        else:
            warn_log(f"查询关联关系失败: target_id={target_id}, 状态码: {resp.status_code}")
            return {"success": False, "target_id": target_id, "rel_type": rel_type, "total": 0, "docs": [], "error": f"请求失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"查询关联关系异常: target_id={target_id}, 错误: {e}")
        return {"success": False, "target_id": target_id, "rel_type": rel_type, "total": 0, "docs": [], "error": str(e)}


def couch_save_link(from_id: str, to_id: str, rel_type: str, desc: str) -> Dict[str, Any]:
    """
    新增两个实体之间的关系

    Args:
        from_id: 关系起点实体ID
        to_id: 关系终点实体ID
        rel_type: 关系类型，如 owns、belongs_to、located_in 等
        desc: 关系描述

    Returns:
        保存结果字典:
        {
            "success": True/False,
            "from_id": "npc_001",
            "to_id": "item_001",
            "rel_type": "owns",
            "rev": "文档版本号",
            "error": "错误信息（如果有）"
        }
    """
    try:
        link_doc = {
            "from_id": from_id,
            "to_id": to_id,
            "rel_type": rel_type,
            "desc": desc,
        }

        resp = _couch_request("POST", f"/{_db_links}", json_data=link_doc)
        if resp is None:
            return {"success": False, "from_id": from_id, "to_id": to_id, "rel_type": rel_type, "rev": "", "error": "CouchDB 客户端不可用"}
        if resp.status_code in (201, 202):
            result = resp.json()
            info_log(f"保存关联关系成功: {from_id} --[{rel_type}]--> {to_id}")
            return {"success": True, "from_id": from_id, "to_id": to_id, "rel_type": rel_type, "rev": result.get("rev", ""), "error": ""}
        else:
            warn_log(f"保存关联关系失败: {from_id}->{to_id}, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
            return {"success": False, "from_id": from_id, "to_id": to_id, "rel_type": rel_type, "rev": "", "error": f"保存失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"保存关联关系异常: {from_id}->{to_id}, 错误: {e}")
        return {"success": False, "from_id": from_id, "to_id": to_id, "rel_type": rel_type, "rev": "", "error": str(e)}


# ================================================================
# ④ 世界快照（定时演化专用）
# ================================================================

def couch_get_last_world_snap() -> Dict[str, Any]:
    """
    获取上一轮世界存档快照

    按 created_at 降序取最新一条世界快照。

    Returns:
        世界快照数据:
        {
            "success": True/False,
            "data": {...},
            "error": "错误信息（如果有）"
        }
    """
    try:
        body = {
            "selector": {},
            "sort": [{"created_at": "desc"}],
            "limit": 1,
        }

        resp = _couch_request("POST", f"/{_db_world_snaps}/_find", json_data=body)
        if resp is None:
            return {"success": False, "data": {}, "error": "CouchDB 客户端不可用"}
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get("docs", [])
            if docs:
                debug_log("获取最新世界快照成功")
                return {"success": True, "data": docs[0], "error": ""}
            else:
                warn_log("世界快照为空")
                return {"success": False, "data": {}, "error": "世界快照为空"}
        else:
            warn_log(f"获取最新世界快照失败, 状态码: {resp.status_code}")
            return {"success": False, "data": {}, "error": f"请求失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"获取最新世界快照异常: {e}")
        return {"success": False, "data": {}, "error": str(e)}


def couch_save_world_snap(snap_data: dict) -> Dict[str, Any]:
    """
    保存新的世界快照存档

    使用自动生成的 UUID 作为文档 ID。

    Args:
        snap_data: 世界快照数据

    Returns:
        保存结果字典:
        {
            "success": True/False,
            "doc_id": "snap_xxxx",
            "rev": "文档版本号",
            "error": "错误信息（如果有）"
        }
    """
    try:
        doc_id = f"snap_{uuid.uuid4().hex[:12]}"
        resp = _couch_request("PUT", f"/{_db_world_snaps}/{doc_id}", json_data=snap_data)
        if resp is None:
            return {"success": False, "doc_id": doc_id, "rev": "", "error": "CouchDB 客户端不可用"}
        if resp.status_code in (201, 202):
            result = resp.json()
            info_log(f"保存世界快照成功: {doc_id}")
            return {"success": True, "doc_id": doc_id, "rev": result.get("rev", ""), "error": ""}
        else:
            warn_log(f"保存世界快照失败, 状态码: {resp.status_code}, 响应: {resp.text[:200]}")
            return {"success": False, "doc_id": doc_id, "rev": "", "error": f"保存失败, 状态码: {resp.status_code}"}
    except Exception as e:
        error_log(f"保存世界快照异常: {e}")
        return {"success": False, "doc_id": "", "rev": "", "error": str(e)}


if __name__ == "__main__":
    # 测试代码
    info_log("测试 couchdb_skill...")

    # 测试获取玩家
    info_log("\n测试 couch_get_player:")
    result = couch_get_player("uid_001")
    print(f"  success={result['success']}, error={result.get('error', '')}")

    # 测试保存玩家
    info_log("\n测试 couch_save_player:")
    result = couch_save_player("uid_test", {"name": "测试玩家", "level": 1})
    print(f"  success={result['success']}, rev={result.get('rev', '')}")

    # 测试获取实体
    info_log("\n测试 couch_get_entity:")
    result = couch_get_entity("npc_001")
    print(f"  success={result['success']}, error={result.get('error', '')}")

    # 测试保存实体
    info_log("\n测试 couch_save_entity:")
    result = couch_save_entity("npc_test", {"name": "测试NPC", "type": "npc"})
    print(f"  success={result['success']}, rev={result.get('rev', '')}")

    # 测试查询关联
    info_log("\n测试 couch_get_link:")
    result = couch_get_link("npc_test", "owns")
    print(f"  success={result['success']}, total={result.get('total', 0)}")

    # 测试保存关联
    info_log("\n测试 couch_save_link:")
    result = couch_save_link("npc_test", "item_test", "owns", "持有测试物品")
    print(f"  success={result['success']}, rev={result.get('rev', '')}")

    # 测试获取世界快照
    info_log("\n测试 couch_get_last_world_snap:")
    result = couch_get_last_world_snap()
    print(f"  success={result['success']}, error={result.get('error', '')}")

    # 测试保存世界快照
    info_log("\n测试 couch_save_world_snap:")
    result = couch_save_world_snap({"world_state": "测试", "created_at": "2026-01-01T00:00:00Z"})
    print(f"  success={result['success']}, doc_id={result.get('doc_id', '')}")
