"""
Search Episode Skill - 查询相似剧情技能

根据用户输入文本和历史聊天内容，从 Qdrant 向量数据库查询相似的小说剧情片段。

前置条件:
    pip install qdrant-client transformers torch
    启动 Qdrant 服务
    已使用 vectorize_novel.py 将小说剧情向量化并存入 Qdrant

用法:
    from skills.search_episode import search_similar_episodes

    results = search_similar_episodes(
        query="我想修炼炼丹术",
        conversation_history=messages,
        top_k=3,
    )
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import httpx
    import torch
    from transformers import AutoModel, AutoTokenizer
    from qdrant_client import QdrantClient
    _HAS_DEPS = True
except ImportError as _import_err:
    _HAS_DEPS = False
    _IMPORT_ERROR = str(_import_err)
    # torch 未安装时提供占位类型，避免类型注解 NameError
    torch = None

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

def _load_qdrant_config() -> Dict[str, Any]:
    """从 config.yaml 加载 Qdrant 配置"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config.yaml",
    )
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("qdrant", {})
    except Exception as e:
        error_log(f"加载 Qdrant 配置失败: {e}")
        return {}


_qdrant_cfg = _load_qdrant_config()
DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", _qdrant_cfg.get("url", "http://localhost:6333"))
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", _qdrant_cfg.get("collection", "episode"))

_DEFAULT_MODEL_DIR = Path.home() / ".cache" / "modelscope" / "hub" / "models"
DEFAULT_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    str(_DEFAULT_MODEL_DIR / "Qwen" / "Qwen3-Embedding-0.6B"),
)

# 全局单例缓存
_embedding_client: Optional[Any] = None
_qdrant_client: Optional[Any] = None


# ───────────────────────────────────────────────
# Embedding 客户端
# ───────────────────────────────────────────────

if _HAS_DEPS:
    class EmbeddingClient:
        """基于 Qwen3-Embedding 本地模型的 Embedding 客户端"""

        def __init__(
            self,
            model_name: str = DEFAULT_MODEL_NAME,
            device: Optional[str] = None,
            max_length: int = 512,
        ):
            if not _HAS_DEPS:
                raise RuntimeError(f"缺少必要依赖: {_IMPORT_ERROR}")

            self.model_name = model_name
            self.max_length = max_length

            # 自动选择设备
            if device:
                self.device = torch.device(device)
            elif torch.backends.mps.is_available():
                self.device = torch.device("mps")
            elif torch.cuda.is_available():
                self.device = torch.device("cuda")
            else:
                self.device = torch.device("cpu")

            info_log(f"加载 Embedding 模型: {model_name}")
            info_log(f"使用设备: {self.device}")

            self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
            self.model.to(self.device)
            self.model.eval()

            self._vector_size = self.model.config.hidden_size
            info_log(f"向量维度: {self._vector_size}")

        def _last_token_pooling(
            self,
            last_hidden_state: torch.Tensor,
            attention_mask: torch.Tensor,
        ) -> torch.Tensor:
            """Last token pooling：取每个序列最后一个非 padding token 的隐藏状态。"""
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_state.shape[0]
            pooled = last_hidden_state[
                torch.arange(batch_size, device=last_hidden_state.device),
                sequence_lengths,
            ]
            return pooled

        @torch.no_grad()
        def embed(self, texts: List[str]) -> List[List[float]]:
            """批量生成 embedding。"""
            if not texts:
                return []

            try:
                inputs = self.tokenizer(
                    texts,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                outputs = self.model(**inputs)
                pooled = self._last_token_pooling(
                    outputs.last_hidden_state, inputs["attention_mask"]
                )
                normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
                return normalized.cpu().tolist()
            except Exception as e:
                error_log(f"Embedding 生成失败: {e}")
                return [[0.0] * self._vector_size] * len(texts)

        @property
        def vector_size(self) -> int:
            """获取向量维度"""
            return self._vector_size
else:
    class EmbeddingClient:  # type: ignore[no-redef]
        """占位类，torch 未安装时使用"""

        def __init__(self, *args, **kwargs):
            raise RuntimeError(f"缺少必要依赖，无法使用 EmbeddingClient: {_IMPORT_ERROR}")

        @property
        def vector_size(self) -> int:
            return 0


def _get_embedding_client() -> Optional[EmbeddingClient]:
    """获取全局单例 EmbeddingClient（懒加载）"""
    global _embedding_client
    if _embedding_client is None:
        try:
            _embedding_client = EmbeddingClient(model_name=DEFAULT_MODEL_NAME)
        except Exception as e:
            error_log(f"初始化 EmbeddingClient 失败: {e}")
            return None
    return _embedding_client


def _get_qdrant_client() -> Optional[Any]:
    """获取全局单例 QdrantClient（懒加载）"""
    global _qdrant_client
    if _qdrant_client is None:
        try:
            # 禁用 HTTP 连接池 keepalive，避免长时间空闲后复用已断开的连接导致挂起
            _qdrant_client = QdrantClient(
                url=DEFAULT_QDRANT_URL,
                limits=httpx.Limits(max_keepalive_connections=0),
            )
            # 测试连接
            _qdrant_client.get_collections()
            info_log(f"Qdrant 连接成功: {DEFAULT_QDRANT_URL}")
        except Exception as e:
            error_log(f"连接 Qdrant 失败: {e}")
            return None
    return _qdrant_client


# ───────────────────────────────────────────────
# 查询构建与搜索
# ───────────────────────────────────────────────

def _build_enhanced_query(
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    构建增强查询文本。

    结合当前查询和最近对话历史，构建更全面的查询内容。

    Args:
        query: 当前用户查询
        conversation_history: 对话历史消息列表

    Returns:
        增强后的查询字符串
    """
    if not conversation_history:
        return query.strip()

    # 取最近 3 轮对话（最多 6 条消息）
    recent = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history

    parts = [query.strip()]

    for msg in recent:
        content = msg.get("content", "").strip()
        if len(content) > 10:
            # 限制长度避免查询过长
            parts.append(content[:150])

    # 去重并用空格拼接
    seen = set()
    unique_parts = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique_parts.append(p)

    return " ".join(unique_parts)


def search_similar_episodes(
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    top_k: int = 5,
    collection_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    根据用户输入和历史聊天内容，从 Qdrant 查询相似的剧情片段。

    Args:
        query: 用户输入的查询文本
        conversation_history: 对话历史消息列表，格式为 [{"role": "user", "content": "..."}, ...]
        top_k: 返回的相似剧情数量，默认 5
        collection_name: Qdrant 集合名称，默认使用环境变量或 "episode"

    Returns:
        搜索结果字典，格式如下:
        {
            "success": True/False,
            "query": "增强后的查询文本",
            "total": 3,
            "episodes": [
                {
                    "content": "剧情片段内容",
                    "score": 0.92,
                }
            ],
            "error": "错误信息（如果有）"
        }
    """
    if not _HAS_DEPS:
        error_msg = f"缺少必要依赖，请安装: pip install qdrant-client transformers torch。详情: {_IMPORT_ERROR}"
        error_log(error_msg)
        return {
            "success": False,
            "query": query,
            "total": 0,
            "episodes": [],
            "error": error_msg,
        }

    query = query.strip() if query else ""
    if not query:
        return {
            "success": False,
            "query": "",
            "total": 0,
            "episodes": [],
            "error": "查询文本不能为空",
        }

    # 1. 构建增强查询
    enhanced_query = _build_enhanced_query(query, conversation_history)
    debug_log(f"增强查询文本: {enhanced_query[:200]}...")

    # 2. 获取 EmbeddingClient 并生成向量
    embedding_client = _get_embedding_client()
    if not embedding_client:
        return {
            "success": False,
            "query": enhanced_query,
            "total": 0,
            "episodes": [],
            "error": "Embedding 客户端初始化失败",
        }

    try:
        embeddings = embedding_client.embed([enhanced_query])
        vector = embeddings[0]
        # 检查零向量
        if all(v == 0.0 for v in vector):
            return {
                "success": False,
                "query": enhanced_query,
                "total": 0,
                "episodes": [],
                "error": "Embedding 生成失败（零向量）",
            }
    except Exception as e:
        error_log(f"生成查询向量失败: {e}")
        return {
            "success": False,
            "query": enhanced_query,
            "total": 0,
            "episodes": [],
            "error": f"生成查询向量失败: {e}",
        }

    # 3. 连接 Qdrant 并搜索
    qdrant_client = _get_qdrant_client()
    if not qdrant_client:
        return {
            "success": False,
            "query": enhanced_query,
            "total": 0,
            "episodes": [],
            "error": "Qdrant 客户端连接失败",
        }

    coll = collection_name or DEFAULT_COLLECTION

    try:
        search_result = qdrant_client.query_points(
            collection_name=coll,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
    except Exception as e:
        error_log(f"Qdrant 搜索失败: {e}")
        return {
            "success": False,
            "query": enhanced_query,
            "total": 0,
            "episodes": [],
            "error": f"Qdrant 搜索失败: {e}",
        }

    # 4. 整理结果（query_points 返回 QueryResponse，points 在 .points 属性中）
    points = search_result.points if hasattr(search_result, "points") else search_result
    episodes = []
    for point in points:
        payload = point.payload or {}
        episodes.append({
            "content": payload.get("content", ""),
            "score": float(point.score) if point.score is not None else 0.0,
        })

    info_log(f"剧情检索完成: 找到 {len(episodes)} 条相似剧情")
    for i, ep in enumerate(episodes, 1):
        preview = ep["content"][:80].replace("\n", " ") if ep["content"] else ""
        debug_log(f"  [{i}] score={ep['score']:.4f} {preview}...")

    return {
        "success": True,
        "query": enhanced_query,
        "total": len(episodes),
        "episodes": episodes,
        "error": "",
    }


def format_episodes_as_context(
    search_result: Dict[str, Any],
    max_chars: int = 2048,
) -> str:
    """
    将搜索结果格式化为 LLM 可用的上下文字符串。

    Args:
        search_result: search_similar_episodes 的返回结果
        max_chars: 最大字符数限制

    Returns:
        格式化的上下文字符串
    """
    if not search_result.get("success"):
        return ""

    episodes = search_result.get("episodes", [])
    if not episodes:
        return ""

    parts = ["【参考剧情】"]
    total_chars = len(parts[0])

    for i, ep in enumerate(episodes, 1):
        content = ep.get("content", "").strip()
        if not content:
            continue

        entry = f"{i}. {content}"
        if total_chars + len(entry) + 2 > max_chars:
            parts.append(f"...（还有 {len(episodes) - i + 1} 条剧情未展示）")
            break

        parts.append(entry)
        total_chars += len(entry) + 2

    return "\n".join(parts)


if __name__ == "__main__":
    # 测试代码
    info_log("测试 search_episode skill...")

    # 测试查询
    test_query = "修炼突破境界"
    test_history = [
        {"role": "user", "content": "我在山洞中闭关修炼了三天"},
        {"role": "assistant", "content": "你感到体内灵气涌动，似乎即将突破"},
        {"role": "user", "content": "我想尝试冲击筑基期"},
    ]

    result = search_similar_episodes(
        query=test_query,
        conversation_history=test_history,
        top_k=3,
    )

    if result["success"]:
        info_log(f"查询成功: {result['total']} 条结果")
        for ep in result["episodes"]:
            print(f"  [score={ep['score']:.4f}] {ep['content'][:100]}...")

        # 测试格式化
        context = format_episodes_as_context(result)
        info_log("格式化上下文:")
        print(context)
    else:
        error_log(f"查询失败: {result['error']}")
