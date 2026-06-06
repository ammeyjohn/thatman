#!/usr/bin/env python3
"""
小说向量化工具

功能：
1. 从 story/ 目录逐个读取小说文本
2. 去除空行、卷标题、章节标题
3. 通过 Qwen3-Embedding-0.6B 本地模型生成向量
4. 存储到 Qdrant 向量数据库进行索引

预处理：
- 去除空行
- 去除卷标题（第X卷 XXX）
- 去除章节标题（第X章 XXX / 第X节 XXX / 第X回 XXX）

分块策略：
- 纯文本滑动窗口切分
- 优先在段落边界（换行符）处切分
- 相邻块保留 overlap 字符重叠，保证语义连贯

前置条件：
    pip install qdrant-client transformers torch
    启动 Qdrant 服务: docker compose -f docker/qdrant/docker-compose.yml up -d

用法：
    python vectorize_novel.py [--qdrant-url http://localhost:6333] [--model Qwen/Qwen3-Embedding-0.6B] [--collection novel] [--chunk-size 1024] [--dry-run]
"""

import re
import sys
import argparse
import uuid
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)


# ───────────────────────────────────────────────
# 配置
# ───────────────────────────────────────────────

STORY_DIR = Path(__file__).resolve().parent / "story"

# Embedding 模型默认本地路径
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "modelscope" / "hub" / "models"

# 卷标题正则：匹配 "第X卷 XXX" 等
VOLUME_PATTERN = re.compile(
    r"^第[零一二三四五六七八九十百千万\d]+卷\s*.*",
    re.MULTILINE,
)

# 章节标题正则：匹配 "第X章 XXX"、"第X节 XXX"、"第X回 XXX" 等
CHAPTER_PATTERN = re.compile(
    r"^第[零一二三四五六七八九十百千万\d]+[章节回]\s*.*",
    re.MULTILINE,
)


# ───────────────────────────────────────────────
# 日志
# ───────────────────────────────────────────────

def debug_log(msg: str):
    print(f"\033[90m[DEBUG] {msg}\033[0m")

def info_log(msg: str):
    print(f"\033[97m[INFO] {msg}\033[0m")

def warn_log(msg: str):
    print(f"\033[93m[WARN] {msg}\033[0m")

def error_log(msg: str):
    print(f"\033[91m[ERROR] {msg}\033[0m")


# ───────────────────────────────────────────────
# 小说读取与清洗
# ───────────────────────────────────────────────

def list_novels(story_dir: Path) -> List[Path]:
    """列出 story 目录下所有 .txt 小说文件"""
    if not story_dir.exists():
        error_log(f"小说目录不存在: {story_dir}")
        return []
    novels = sorted(story_dir.glob("*.txt"))
    return novels


def read_and_clean(filepath: Path) -> Optional[str]:
    """读取小说文件，去除空行、卷标题和章节标题"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        cleaned_lines = []
        removed_volumes = 0
        removed_chapters = 0
        for line in lines:
            stripped = line.strip()
            # 去除空行
            if not stripped:
                continue
            # 去除卷标题
            if VOLUME_PATTERN.match(stripped):
                removed_volumes += 1
                continue
            # 去除章节标题
            if CHAPTER_PATTERN.match(stripped):
                removed_chapters += 1
                continue
            cleaned_lines.append(line.rstrip("\n\r"))

        debug_log(f"{filepath.name}: 去除 {removed_volumes} 个卷标题, {removed_chapters} 个章节标题")
        return "\n".join(cleaned_lines)
    except Exception as e:
        error_log(f"读取小说失败 {filepath.name}: {e}")
        return None


# ───────────────────────────────────────────────
# 智能分块
# ───────────────────────────────────────────────

def chunk_novel(text: str, chunk_size: int = 1024, overlap: int = 128) -> List[Dict[str, Any]]:
    """
    对纯文本进行滑动窗口分块。

    策略：
    - 按 chunk_size 字符切分
    - 优先在段落边界（换行符）处切分
    - 相邻块保留 overlap 字符的重叠，保证语义连贯
    """
    if not text:
        return []

    chunks = []
    start = 0
    idx = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # 如果不是文本末尾，尝试在段落边界切分
        if end < text_len:
            # 往回找最近的换行符
            newline_pos = text.rfind("\n", start, end + 1)
            if newline_pos != -1 and newline_pos > start + chunk_size * 0.5:
                end = newline_pos

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "content": chunk_text,
                "chunk_idx": idx,
            })
            idx += 1

        if end >= text_len:
            break

        # 滑动窗口步进 = chunk_size - overlap
        start = max(start + 1, end - overlap)

    return chunks


# ───────────────────────────────────────────────
# Embedding 生成（Qwen3-Embedding 本地模型）
# ───────────────────────────────────────────────

class EmbeddingClient:
    """基于 Qwen3-Embedding 本地模型的 Embedding 客户端"""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-Embedding-0.6B",
        device: Optional[str] = None,
        batch_size: int = 32,
        max_length: int = 512,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
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

        # 获取向量维度
        self._vector_size = self.model.config.hidden_size
        info_log(f"向量维度: {self._vector_size}")

    def _last_token_pooling(
        self,
        last_hidden_state: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        Last token pooling：取每个序列最后一个非 padding token 的隐藏状态。

        Qwen3-Embedding 使用 last token pooling 策略。
        """
        # 找到每个序列中最后一个非 padding 位置
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_size = last_hidden_state.shape[0]
        pooled = last_hidden_state[
            torch.arange(batch_size, device=last_hidden_state.device),
            sequence_lengths,
        ]
        return pooled

    @torch.no_grad()
    def embed(self, texts: List[str]) -> List[List[float]]:
        """批量生成 embedding，自动分批"""
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            try:
                inputs = self.tokenizer(
                    batch,
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
                # L2 归一化
                normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
                all_embeddings.extend(normalized.cpu().tolist())

                debug_log(f"Embedding 批次 {i // self.batch_size + 1}: {len(batch)} 条")
            except Exception as e:
                error_log(f"Embedding 批次失败 ({i}-{i + len(batch)}): {e}")
                # 用零向量填充失败的批次
                all_embeddings.extend([[0.0] * self._vector_size] * len(batch))

        return all_embeddings

    @property
    def vector_size(self) -> int:
        """获取向量维度"""
        return self._vector_size


# ───────────────────────────────────────────────
# Qdrant 操作
# ───────────────────────────────────────────────

def ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
) -> bool:
    """确保 Qdrant 集合存在，不存在则创建"""
    try:
        collections = client.get_collections().collections
        names = [c.name for c in collections]
        if collection_name in names:
            info_log(f"Qdrant 集合已存在: {collection_name}")
            return True
    except Exception as e:
        warn_log(f"获取集合列表失败: {e}")

    try:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        info_log(f"创建 Qdrant 集合成功: {collection_name} (维度: {vector_size})")
        return True
    except Exception as e:
        error_log(f"创建集合失败: {e}")
        return False


def upsert_chunks(
    client: QdrantClient,
    collection_name: str,
    chunks: List[Dict[str, Any]],
    embeddings: List[List[float]],
    novel_name: str,
) -> int:
    """将分块和向量写入 Qdrant"""
    points = []
    for chunk, vector in zip(chunks, embeddings):
        # 跳过零向量（embedding 失败的块）
        if all(v == 0.0 for v in vector):
            continue

        point_id = str(uuid.uuid4())
        payload = {
            "content": chunk.get("content", ""),
        }
        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload=payload,
            )
        )

    if not points:
        warn_log("没有有效的向量点可写入")
        return 0

    # 分批 upsert
    batch_size = 100
    success_count = 0
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        try:
            client.upsert(collection_name=collection_name, points=batch)
            success_count += len(batch)
            debug_log(f"Upsert 批次 {i // batch_size + 1}: {len(batch)} 点")
        except Exception as e:
            error_log(f"Upsert 批次失败 ({i}-{i + len(batch)}): {e}")

    return success_count


# ───────────────────────────────────────────────
# 主流程
# ───────────────────────────────────────────────

def process_novel(
    filepath: Path,
    embedding_client: EmbeddingClient,
    qdrant_client: QdrantClient,
    collection_name: str,
    chunk_size: int,
    overlap: int,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    处理单本小说：读取 -> 清洗 -> 分块 -> 向量化 -> 写入 Qdrant

    返回: (分块数, 成功写入数)
    """
    novel_name = filepath.stem
    info_log(f"开始处理小说: {novel_name}")

    # 1. 读取并清洗
    text = read_and_clean(filepath)
    if text is None:
        return 0, 0

    text_len = len(text)
    info_log(f"  清洗后文本长度: {text_len:,} 字符")

    # 2. 分块
    chunks = chunk_novel(text, chunk_size=chunk_size, overlap=overlap)
    info_log(f"  分块数: {len(chunks)}")

    if not chunks:
        warn_log(f"  小说分块为空，跳过: {novel_name}")
        return 0, 0

    # 统计分块信息
    chunk_lengths = [len(c["content"]) for c in chunks]
    info_log(f"  分块长度 - 最小: {min(chunk_lengths)}, 最大: {max(chunk_lengths)}, 平均: {sum(chunk_lengths) // len(chunk_lengths)}")

    if dry_run:
        # 预览前3个分块
        for i, chunk in enumerate(chunks[:3]):
            preview = chunk["content"][:150].replace("\n", " ")
            debug_log(f"  分块[{i}] {preview}...")
        if len(chunks) > 3:
            debug_log(f"  ... 还有 {len(chunks) - 3} 个分块")
        return len(chunks), 0

    # 3. 生成 embedding
    texts = [chunk["content"] for chunk in chunks]
    info_log(f"  生成 Embedding ({len(texts)} 条)...")
    embeddings = embedding_client.embed(texts)
    info_log(f"  Embedding 完成，向量维度: {embedding_client.vector_size}")

    # 4. 确保 Qdrant 集合存在
    ensure_collection(qdrant_client, collection_name, embedding_client.vector_size)

    # 5. 写入 Qdrant
    info_log(f"  写入 Qdrant...")
    success_count = upsert_chunks(
        qdrant_client, collection_name, chunks, embeddings, novel_name
    )
    info_log(f"  写入完成: {success_count}/{len(chunks)} 条")

    return len(chunks), success_count


def main():
    parser = argparse.ArgumentParser(description="小说向量化工具 - 将小说分块向量化并存入 Qdrant")
    parser.add_argument(
        "files",
        nargs="*",
        default=None,
        help="要向量化的小说文件路径（支持多个），不指定则扫描 story-dir 下所有 .txt",
    )
    parser.add_argument(
        "--story-dir",
        default=str(STORY_DIR),
        help=f"小说目录，当未指定 files 时扫描此目录 (默认: {STORY_DIR})",
    )
    parser.add_argument(
        "--qdrant-url",
        default="http://localhost:6333",
        help="Qdrant 服务地址 (默认: http://localhost:6333)",
    )
    parser.add_argument(
        "--model",
        default=str(DEFAULT_MODEL_DIR / "Qwen" / "Qwen3-Embedding-0.6B"),
        help=f"Embedding 模型路径或名称 (默认: {DEFAULT_MODEL_DIR / 'Qwen' / 'Qwen3-Embedding-0.6B'})",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="计算设备 (默认: 自动选择 mps > cuda > cpu)",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=512,
        help="Tokenizer 最大序列长度 (默认: 512)",
    )
    parser.add_argument(
        "--collection",
        default="episode",
        help="Qdrant 集合名称 (默认: episode)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024,
        help="分块最大字符数 (默认: 1024)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=128,
        help="分块重叠字符数 (默认: 128)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Embedding 批次大小 (默认: 32)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅解析分块预览，不实际生成向量和写入",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("小说向量化工具")
    print("=" * 60)
    print(f"Qdrant 地址: {args.qdrant_url}")
    print(f"Embedding 模型: {args.model}")
    print(f"设备: {args.device or '自动'}")
    print(f"集合名称: {args.collection}")
    print(f"分块大小: {args.chunk_size} 字符")
    print(f"分块重叠: {args.overlap} 字符")
    print(f"干跑模式: {'是' if args.dry_run else '否'}")
    print("-" * 60)

    # 1. 收集小说文件
    if args.files:
        # 从命令行参数直接获取文件路径
        novels = []
        for f in args.files:
            p = Path(f).resolve()
            if p.is_file():
                novels.append(p)
            else:
                warn_log(f"文件不存在，跳过: {f}")
        if not novels:
            error_log("指定的文件均不存在")
            sys.exit(1)
    else:
        # 扫描 story-dir 目录
        story_dir = Path(args.story_dir)
        novels = list_novels(story_dir)
        if not novels:
            error_log(f"未在 {story_dir} 下找到任何小说文件 (.txt)")
            sys.exit(1)

    info_log(f"待处理 {len(novels)} 本小说:")
    for n in novels:
        size_mb = n.stat().st_size / (1024 * 1024)
        info_log(f"  • {n.name} ({size_mb:.1f} MB)")

    # 2. 初始化 Embedding 客户端（非干跑模式才加载模型）
    embedding_client = None
    if not args.dry_run:
        try:
            embedding_client = EmbeddingClient(
                model_name=args.model,
                device=args.device,
                batch_size=args.batch_size,
                max_length=args.max_length,
            )
        except Exception as e:
            error_log(f"加载 Embedding 模型失败: {e}")
            sys.exit(1)

    # 3. 初始化 Qdrant 客户端
    try:
        qdrant_client = QdrantClient(url=args.qdrant_url)
        qdrant_client.get_collections()
        info_log("Qdrant 连接成功")
    except Exception as e:
        if args.dry_run:
            warn_log(f"Qdrant 连接失败 (干跑模式可忽略): {e}")
            qdrant_client = None
        else:
            error_log(f"Qdrant 连接失败: {e}")
            sys.exit(1)

    # 4. 逐本处理
    total_chunks = 0
    total_upserted = 0

    for i, novel_path in enumerate(novels, 1):
        info_log(f"\n[{i}/{len(novels)}] 处理: {novel_path.name}")
        print("-" * 40)

        chunks_count, upserted_count = process_novel(
            filepath=novel_path,
            embedding_client=embedding_client,
            qdrant_client=qdrant_client,
            collection_name=args.collection,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            dry_run=args.dry_run,
        )

        total_chunks += chunks_count
        total_upserted += upserted_count

    # 5. 统计结果
    print("\n" + "=" * 60)
    print("向量化完成")
    print("=" * 60)
    print(f"处理小说数: {len(novels)}")
    print(f"总分块数: {total_chunks}")
    if not args.dry_run:
        print(f"成功写入: {total_upserted} 条")
        try:
            collection_info = qdrant_client.get_collection(args.collection)
            print(f"集合向量数: {collection_info.points_count}")
            print(f"向量维度: {collection_info.config.params.vectors.size}")
            print(f"距离度量: {collection_info.config.params.vectors.distance}")
        except Exception:
            pass
    else:
        print("干跑模式，未实际写入")
    print("-" * 60)


if __name__ == "__main__":
    main()
