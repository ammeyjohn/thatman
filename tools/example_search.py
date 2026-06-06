#!/usr/bin/env python3
"""
Qdrant 相似文本搜索示例

功能：
1. 加载 Qwen3-Embedding 本地模型
2. 连接 Qdrant 向量数据库
3. 输入查询文本，生成 embedding 后在向量库中检索相似内容

前置条件：
    pip install qdrant-client transformers torch
    已运行 vectorize_novel.py 将小说向量写入 Qdrant

用法：
    python example_search.py --query "韩立修炼" [--limit 5]
    python example_search.py                    # 交互模式
"""

import argparse
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint

from vectorize_novel import EmbeddingClient, info_log, error_log, warn_log


# 默认配置
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "episode"
DEFAULT_MODEL = str(Path.home() / ".cache" / "modelscope" / "hub" / "models" / "Qwen" / "Qwen3-Embedding-0.6B")


def search_similar(
    query: str,
    embedding_client: EmbeddingClient,
    qdrant_client: QdrantClient,
    collection_name: str = DEFAULT_COLLECTION,
    limit: int = 5,
) -> list[ScoredPoint]:
    """
    在 Qdrant 中搜索与查询文本相似的向量。

    Args:
        query: 查询文本
        embedding_client: Embedding 模型客户端
        qdrant_client: Qdrant 客户端
        collection_name: 集合名称
        limit: 返回结果数量

    Returns:
        相似结果列表
    """
    info_log(f"查询文本: {query}")

    # 1. 生成查询向量
    embeddings = embedding_client.embed([query])
    query_vector = embeddings[0]

    # 2. 在 Qdrant 中搜索
    response = qdrant_client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=limit,
        with_payload=True,
    )

    return response.points


def print_results(results: list[ScoredPoint]) -> None:
    """格式化打印搜索结果"""
    if not results:
        print("\n未找到相似内容")
        return

    print(f"\n找到 {len(results)} 条相似结果:\n")
    print("=" * 60)

    for i, point in enumerate(results, 1):
        payload = point.payload or {}
        content = payload.get("content", "")
        source = payload.get("source", "未知来源")
        score = point.score

        print(f"\n[{i}] 相似度: {score:.4f} | 来源: {source}")
        print("-" * 40)
        # 截取前 300 字符展示
        preview = content[:300].replace("\n", " ")
        if len(content) > 300:
            preview += " ..."
        print(preview)

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Qdrant 相似文本搜索示例")
    parser.add_argument(
        "--query",
        default=None,
        help="查询文本，不指定则进入交互模式",
    )
    parser.add_argument(
        "--qdrant-url",
        default=DEFAULT_QDRANT_URL,
        help=f"Qdrant 服务地址 (默认: {DEFAULT_QDRANT_URL})",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"Qdrant 集合名称 (默认: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Embedding 模型路径 (默认: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="计算设备 (默认: 自动选择)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="返回结果数量 (默认: 5)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Qdrant 相似文本搜索")
    print("=" * 60)
    print(f"Qdrant 地址: {args.qdrant_url}")
    print(f"集合名称: {args.collection}")
    print(f"Embedding 模型: {args.model}")
    print(f"设备: {args.device or '自动'}")
    print(f"返回数量: {args.limit}")
    print("-" * 60)

    # 1. 加载 Embedding 模型
    try:
        embedding_client = EmbeddingClient(
            model_name=args.model,
            device=args.device,
            batch_size=1,
            max_length=512,
        )
    except Exception as e:
        error_log(f"加载 Embedding 模型失败: {e}")
        sys.exit(1)

    # 2. 连接 Qdrant
    try:
        qdrant_client = QdrantClient(url=args.qdrant_url)
        collection_info = qdrant_client.get_collection(args.collection)
        info_log(f"集合 '{args.collection}' 向量数: {collection_info.points_count}")
    except Exception as e:
        error_log(f"连接 Qdrant 失败: {e}")
        sys.exit(1)

    if args.query:
        # 单次查询模式
        results = search_similar(
            query=args.query,
            embedding_client=embedding_client,
            qdrant_client=qdrant_client,
            collection_name=args.collection,
            limit=args.limit,
        )
        print_results(results)
    else:
        # 交互模式
        print("\n进入交互模式，输入查询文本（输入 'quit' 退出）:\n")
        while True:
            try:
                query = input("\033[93m查询: \033[0m").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not query:
                continue
            if query.lower() in ("quit", "exit", "q"):
                print("再见！")
                break

            results = search_similar(
                query=query,
                embedding_client=embedding_client,
                qdrant_client=qdrant_client,
                collection_name=args.collection,
                limit=args.limit,
            )
            print_results(results)


if __name__ == "__main__":
    main()
