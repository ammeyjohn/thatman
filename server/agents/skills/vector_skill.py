"""
Vector Skill - Qdrant 剧情向量技能

封装 Qdrant 向量数据库的剧情检索和入库操作，
复用 search_episode 的 EmbeddingClient 和 QdrantClient。

用法:
    from skills.vector_skill import search_plot_vector, insert_plot_vector

    # 语义检索过往剧情
    results = search_plot_vector("灵潮爆发", top_k=3)

    # 剧情入库
    insert_plot_vector("灵潮爆发，灵气浓度骤增", {"type": "world_event", "area": "青墟"})
"""

import uuid
import logging
from typing import Dict, Any, Optional, List

# 复用 search_episode 的 EmbeddingClient 和 QdrantClient
from skills.search_episode import (
    _get_embedding_client,
    _get_qdrant_client,
    EmbeddingClient,
)

try:
    from qdrant_client.models import PointStruct
    _HAS_QDRANT = True
except ImportError as _import_err:
    _HAS_QDRANT = False
    _IMPORT_ERROR = str(_import_err)

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
# 默认配置
# ───────────────────────────────────────────────

import os

DEFAULT_QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "episode")


# ================================================================
# ⑥ Qdrant 剧情向量库
# ================================================================

def search_plot_vector(query: str, top_k: int = 3) -> Dict[str, Any]:
    """
    语义检索过往剧情，返回与查询最相似的剧情片段

    复用 search_episode 的 EmbeddingClient 和 QdrantClient。

    Args:
        query: 语义检索查询文本
        top_k: 返回最相似的 top_k 条结果，默认3

    Returns:
        检索结果字典:
        {
            "success": True/False,
            "query": "灵潮爆发",
            "total": 3,
            "episodes": [
                {"content": "剧情片段内容", "score": 0.92}
            ],
            "error": "错误信息（如果有）"
        }
    """
    if not _HAS_QDRANT:
        error_msg = f"缺少 qdrant_client 依赖: {_IMPORT_ERROR}"
        error_log(error_msg)
        return {"success": False, "query": query, "total": 0, "episodes": [], "error": error_msg}

    query = query.strip() if query else ""
    if not query:
        return {"success": False, "query": "", "total": 0, "episodes": [], "error": "查询文本不能为空"}

    # 1. 获取 EmbeddingClient 并生成向量
    embedding_client = _get_embedding_client()
    if not embedding_client:
        return {"success": False, "query": query, "total": 0, "episodes": [], "error": "EmbeddingClient 未初始化"}

    try:
        embeddings = embedding_client.embed([query])
        vector = embeddings[0]
        # 检查零向量
        if all(v == 0.0 for v in vector):
            return {"success": False, "query": query, "total": 0, "episodes": [], "error": "Embedding 生成失败（零向量）"}
    except Exception as e:
        error_log(f"生成查询向量失败: {e}")
        return {"success": False, "query": query, "total": 0, "episodes": [], "error": f"生成查询向量失败: {e}"}

    # 2. 连接 Qdrant 并搜索
    qdrant_client = _get_qdrant_client()
    if not qdrant_client:
        return {"success": False, "query": query, "total": 0, "episodes": [], "error": "QdrantClient 未连接"}

    try:
        search_result = qdrant_client.query_points(
            collection_name=DEFAULT_QDRANT_COLLECTION,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
    except Exception as e:
        error_log(f"Qdrant 搜索失败: {e}")
        return {"success": False, "query": query, "total": 0, "episodes": [], "error": f"Qdrant 搜索失败: {e}"}

    # 3. 整理结果
    points = search_result.points if hasattr(search_result, "points") else search_result
    episodes = []
    for point in points:
        payload = point.payload or {}
        episodes.append({
            "content": payload.get("content", ""),
            "score": float(point.score) if point.score is not None else 0.0,
        })

    info_log(f"剧情向量检索完成: query={query}, 找到 {len(episodes)} 条")

    return {
        "success": True,
        "query": query,
        "total": len(episodes),
        "episodes": episodes,
        "error": "",
    }


def insert_plot_vector(content: str, meta: dict) -> Dict[str, Any]:
    """
    将剧情内容入库，支持 NPC、装备、区域、阵营等类型

    复用 search_episode 的 EmbeddingClient 和 QdrantClient。

    Args:
        content: 剧情文本内容
        meta: 剧情元数据，包含 type(npc/equip/area/faction) 和 area(地域名)
              示例: {"type": "npc", "area": "青墟"}

    Returns:
        入库结果字典:
        {
            "success": True/False,
            "point_id": "向量点ID",
            "error": "错误信息（如果有）"
        }
    """
    if not _HAS_QDRANT:
        error_msg = f"缺少 qdrant_client 依赖: {_IMPORT_ERROR}"
        error_log(error_msg)
        return {"success": False, "point_id": "", "error": error_msg}

    if not content or not content.strip():
        warn_log("剧情内容为空，跳过入库")
        return {"success": False, "point_id": "", "error": "剧情内容为空"}

    # 1. 获取 EmbeddingClient 并生成向量
    embedding_client = _get_embedding_client()
    if not embedding_client:
        return {"success": False, "point_id": "", "error": "EmbeddingClient 未初始化"}

    try:
        embeddings = embedding_client.embed([content.strip()])
        vector = embeddings[0]
        # 检查零向量
        if all(v == 0.0 for v in vector):
            return {"success": False, "point_id": "", "error": "生成向量为零向量"}
    except Exception as e:
        error_log(f"生成向量失败: {e}")
        return {"success": False, "point_id": "", "error": f"生成向量失败: {e}"}

    # 2. 连接 Qdrant 并插入
    qdrant_client = _get_qdrant_client()
    if not qdrant_client:
        return {"success": False, "point_id": "", "error": "QdrantClient 未连接"}

    try:
        # 构建载荷
        payload = {
            "content": content.strip(),
            **meta,
        }

        # 生成唯一 ID
        point_id = uuid.uuid4().hex

        # 插入向量
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        )
        qdrant_client.upsert(
            collection_name=DEFAULT_QDRANT_COLLECTION,
            points=[point],
        )

        info_log(f"剧情向量入库成功: {content[:50]}")
        return {"success": True, "point_id": point_id, "error": ""}

    except Exception as e:
        error_log(f"剧情向量入库异常: {e}")
        return {"success": False, "point_id": "", "error": str(e)}


if __name__ == "__main__":
    # 测试代码
    info_log("测试 vector_skill...")

    # 测试检索
    info_log("\n测试 search_plot_vector:")
    result = search_plot_vector("灵潮爆发", top_k=3)
    print(f"  success={result['success']}, total={result.get('total', 0)}")
    for ep in result.get("episodes", []):
        print(f"  [score={ep['score']:.4f}] {ep['content'][:80]}...")

    # 测试入库
    info_log("\n测试 insert_plot_vector:")
    result = insert_plot_vector("灵潮爆发，灵气浓度骤增", {"type": "world_event", "area": "青墟"})
    print(f"  success={result['success']}, point_id={result.get('point_id', '')}")
