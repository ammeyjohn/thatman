#!/usr/bin/env python3
"""
世界种子初始化脚本

功能：
1. 读取 docs/ 目录下的世界观与配置文档
2. 将内容按层级（## / ### / 列表项）细粒度解析为结构化世界记忆
3. 通过 hindsight_memory 模块写入 hindsight 世界记忆库

细粒度拆分策略：
- 二级标题 (##) 作为章节记忆
- 三级标题 (###) 作为子章节记忆
- 每个列表项 (- / 1. ) 作为独立知识点种子
- 每个层级保留父级上下文，确保语义完整

前置条件：
    pip install hindsight-client
    启动 Hindsight 服务 (见 hindsight_memory.py 顶部注释)

用法：
    python init_world_seed.py [--bank world] [--base-url http://localhost:8888] [--clear]
"""

import os
import sys
import re
import argparse
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# 将 agents 目录加入路径，复用 hindsight_memory 模块
AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

from hindsight_memory import HindsightMemoryStore


# ───────────────────────────────────────────────
# 配置
# ───────────────────────────────────────────────

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

# 文档 -> 记忆上下文标签映射
DOC_CONTEXT_MAP = {
    "世界观.md": "world_lore",
    "world_config.md": "world_environment",
    "guild_config.md": "guild_system",
    "npc_config.md": "npc_system",
    "item_config.md": "item_system",
    "skill_config.md": "skill_system",
    "task_config.md": "task_system",
    "level_config.md": "level_system",
    "game_manual.md": "game_manual",
}

# 世界 bank 的 mission 描述
WORLD_MISSION = (
    "《青墟灵修志》世界记忆库。存储上古劫后遗落修仙世界的完整设定，"
    "包括世界起源、修行体系、势力阵营、生灵角色、资源物产、规则法则等。"
    "用于支撑 AI 多智能体自主演化与动态剧情生成。"
)

# 世界 bank 的性格配置（更偏向严谨、务实，保证设定一致性）
WORLD_DISPOSITION = {
    "skepticism": 4,
    "literalism": 4,
    "empathy": 2,
}


# ───────────────────────────────────────────────
# 细粒度文档解析
# ───────────────────────────────────────────────

def extract_list_items(text: str, parent_heading: str = "") -> List[Dict[str, str]]:
    """
    从文本中提取列表项（- 或 数字. 开头），每个列表项作为独立记忆。
    返回: [{"title": str, "body": str, "parent": str}]
    """
    items = []
    lines = text.splitlines()
    i = 0
    current_title = ""
    current_body_lines = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 匹配列表项开头: "- " 或 "1. " 等
        is_list_item = bool(re.match(r"^[-*]\s+", stripped)) or bool(re.match(r"^\d+\.\s+", stripped))

        if is_list_item:
            # 保存上一个列表项
            if current_title:
                items.append({
                    "title": current_title,
                    "body": "\n".join(current_body_lines).strip(),
                    "parent": parent_heading,
                })
            # 提取标题（列表项第一行）
            # 去掉列表标记
            title_text = re.sub(r"^[-*\d]+\.\s*", "", stripped)
            current_title = title_text
            current_body_lines = []
        elif stripped and current_title:
            # 属于当前列表项的续行（缩进内容）
            current_body_lines.append(line)
        elif stripped and not current_title:
            # 非列表项的普通段落，跳过（由上层处理）
            pass

        i += 1

    # 保存最后一个列表项
    if current_title:
        items.append({
            "title": current_title,
            "body": "\n".join(current_body_lines).strip(),
            "parent": parent_heading,
        })

    return items


def split_markdown_hierarchical(text: str) -> List[Dict[str, Any]]:
    """
    按层级拆分 Markdown 文档：
    1. 先按 ## 切分大章节
    2. 每个章节内按 ### 切分子章节
    3. 每个子章节内提取列表项作为独立知识点
    4. 无列表项的段落保留为段落记忆

    返回的记忆块包含层级上下文，确保语义完整。
    """
    memories = []

    # 按 ## 切分大章节
    chapter_pattern = r"(?=^##\s+)"
    chapter_parts = re.split(chapter_pattern, text, flags=re.MULTILINE)

    for chapter in chapter_parts:
        chapter = chapter.strip()
        if not chapter:
            continue

        chapter_lines = chapter.splitlines()
        chapter_heading = chapter_lines[0].lstrip("#").strip() if chapter_lines else "未命名章节"
        chapter_body = "\n".join(chapter_lines[1:]).strip()

        if not chapter_body:
            continue

        # 检查章节内是否有 ### 子标题
        sub_pattern = r"(?=^###\s+)"
        sub_parts = re.split(sub_pattern, chapter_body, flags=re.MULTILINE)

        if len(sub_parts) <= 1:
            # 没有子标题，整个章节作为一块，同时提取列表项
            # 1) 章节总览记忆
            memories.append({
                "type": "chapter_overview",
                "heading": chapter_heading,
                "content": chapter_body,
                "parent": "",
            })
            # 2) 提取列表项作为独立种子
            list_items = extract_list_items(chapter_body, parent_heading=chapter_heading)
            for item in list_items:
                content = f"【{chapter_heading} - {item['title']}】\n{item['body']}" if item['body'] else f"【{chapter_heading} - {item['title']}】"
                memories.append({
                    "type": "list_item",
                    "heading": item["title"],
                    "content": content,
                    "parent": chapter_heading,
                })
        else:
            # 有子标题，按子标题拆分
            for sub in sub_parts:
                sub = sub.strip()
                if not sub:
                    continue

                sub_lines = sub.splitlines()
                sub_heading = sub_lines[0].lstrip("#").strip() if sub_lines else "未命名子章节"
                sub_body = "\n".join(sub_lines[1:]).strip()

                if not sub_body:
                    continue

                # 1) 子章节总览记忆
                memories.append({
                    "type": "subchapter_overview",
                    "heading": sub_heading,
                    "content": f"【{chapter_heading} - {sub_heading}】\n{sub_body}",
                    "parent": chapter_heading,
                })

                # 2) 提取列表项作为独立种子
                list_items = extract_list_items(sub_body, parent_heading=f"{chapter_heading} - {sub_heading}")
                for item in list_items:
                    content = f"【{chapter_heading} - {sub_heading} - {item['title']}】\n{item['body']}" if item['body'] else f"【{chapter_heading} - {sub_heading} - {item['title']}】"
                    memories.append({
                        "type": "list_item",
                        "heading": item["title"],
                        "content": content,
                        "parent": f"{chapter_heading} - {sub_heading}",
                    })

    return memories


def read_doc(filepath: Path) -> Optional[str]:
    """读取文档内容，文件不存在返回 None"""
    if not filepath.exists():
        print(f"\033[33m[WARN] 文档不存在，跳过: {filepath}\033[0m")
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"\033[33m[WARN] 读取文档失败 {filepath}: {e}\033[0m")
        return None


# ───────────────────────────────────────────────
# 种子数据生成
# ───────────────────────────────────────────────

def build_seed_memories() -> List[Dict[str, Any]]:
    """
    扫描 docs/ 目录，解析所有配置文档，生成细粒度结构化记忆列表。
    返回列表元素: {"content": str, "context": str, "metadata": dict}
    """
    memories: List[Dict[str, Any]] = []

    for filename, context_tag in DOC_CONTEXT_MAP.items():
        filepath = DOCS_DIR / filename
        raw_text = read_doc(filepath)
        if raw_text is None:
            continue

        # 使用细粒度层级拆分
        blocks = split_markdown_hierarchical(raw_text)

        if not blocks:
            # 兜底：如果没有解析到任何块，整篇作为一个记忆
            memories.append({
                "content": raw_text.strip(),
                "context": context_tag,
                "metadata": {"source": filename, "heading": "全文", "type": "full_doc"},
            })
            continue

        for block in blocks:
            memories.append({
                "content": block["content"],
                "context": context_tag,
                "metadata": {
                    "source": filename,
                    "heading": block["heading"],
                    "parent": block.get("parent", ""),
                    "type": block.get("type", "unknown"),
                },
            })

    return memories


# ───────────────────────────────────────────────
# Hindsight 写入
# ───────────────────────────────────────────────

def init_world_bank(
    bank_id: str,
    base_url: str,
    api_key: Optional[str],
    clear: bool = False,
) -> HindsightMemoryStore:
    """初始化或获取世界记忆库"""
    store = HindsightMemoryStore(
        bank_id=bank_id,
        bank_name="青墟世界记忆库",
        base_url=base_url,
        api_key=api_key,
        short_term_window=6,
        auto_retain=False,
        mission=WORLD_MISSION,
        disposition=WORLD_DISPOSITION,
    )

    if clear:
        print(f"\033[36m[INFO] 清空现有世界记忆库 '{bank_id}'...\033[0m")
        store.clear_bank()
        # 重建 bank
        store._ensure_bank("青墟世界记忆库", WORLD_MISSION, WORLD_DISPOSITION)

    return store


def seed_world_memories(store: HindsightMemoryStore, memories: List[Dict[str, Any]]) -> int:
    """将记忆列表写入 hindsight，返回成功写入数量"""
    success_count = 0
    total = len(memories)

    print(f"\033[36m[INFO] 开始写入 {total} 条世界种子记忆...\033[0m")

    for i, mem in enumerate(memories, 1):
        ok = store.retain(
            content=mem["content"],
            context=mem["context"],
            metadata=mem.get("metadata", {}),
        )
        if ok:
            success_count += 1
            heading = mem.get("metadata", {}).get("heading", "")
            mem_type = mem.get("metadata", {}).get("type", "")
            print(f"\033[90m[DEBUG] ({i}/{total}) [{mem['context']}/{mem_type}] {heading[:40]}... OK\033[0m")
        else:
            print(f"\033[33m[WARN] ({i}/{total}) 写入失败: {mem.get('metadata', {}).get('heading', '')}\033[0m")

    return success_count


# ───────────────────────────────────────────────
# 主流程
# ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="初始化《青墟灵修志》世界种子到 hindsight 记忆库")
    parser.add_argument("--bank", default="world", help="hindsight memory bank ID (默认: world)")
    parser.add_argument("--base-url", default="http://localhost:8888", help="hindsight 服务地址")
    parser.add_argument("--api-key", default=None, help="hindsight API 密钥")
    parser.add_argument("--clear", action="store_true", help="清空已有记忆后重新写入")
    parser.add_argument("--dry-run", action="store_true", help="仅解析预览，不实际写入 hindsight")
    parser.add_argument("--preview-limit", type=int, default=5, help="干跑时预览的记忆条数 (默认: 5)")
    args = parser.parse_args()

    print("=" * 60)
    print("《青墟灵修志》世界种子初始化")
    print("=" * 60)
    print(f"文档目录: {DOCS_DIR}")
    print(f"目标 Bank: {args.bank}")
    print(f"Hindsight 地址: {args.base_url}")
    print(f"清空模式: {'是' if args.clear else '否'}")
    print(f"干跑模式: {'是' if args.dry_run else '否'}")
    print("-" * 60)

    # 1. 构建种子记忆
    memories = build_seed_memories()
    if not memories:
        print("\033[31m[ERROR] 未解析到任何记忆内容，请检查 docs/ 目录\033[0m")
        sys.exit(1)

    print(f"\033[32m[INFO] 成功解析 {len(memories)} 条记忆块\033[0m")

    # 按 context + type 统计
    ctx_stats: Dict[str, int] = {}
    type_stats: Dict[str, int] = {}
    for m in memories:
        ctx = m["context"]
        mem_type = m.get("metadata", {}).get("type", "unknown")
        ctx_stats[ctx] = ctx_stats.get(ctx, 0) + 1
        type_stats[mem_type] = type_stats.get(mem_type, 0) + 1

    print("\n按文档统计:")
    for ctx, count in sorted(ctx_stats.items()):
        print(f"  • {ctx}: {count} 条")

    print("\n按记忆类型统计:")
    for mem_type, count in sorted(type_stats.items(), key=lambda x: -x[1]):
        print(f"  • {mem_type}: {count} 条")

    if args.dry_run:
        limit = min(args.preview_limit, len(memories))
        print(f"\n\033[36m[DRY-RUN] 预览前 {limit} 条记忆内容:\033[0m")
        for mem in memories[:limit]:
            meta = mem.get("metadata", {})
            print(f"\n--- [{mem['context']}] [{meta.get('type', '')}] ---")
            print(f"heading: {meta.get('heading', '')}")
            print(f"parent: {meta.get('parent', '')}")
            print(f"content:\n{mem['content'][:400]}...")
        print(f"\n\033[36m[DRY-RUN] 干跑结束，共解析 {len(memories)} 条，未写入 hindsight\033[0m")
        sys.exit(0)

    # 2. 连接 hindsight 并写入
    try:
        store = init_world_bank(
            bank_id=args.bank,
            base_url=args.base_url,
            api_key=args.api_key,
            clear=args.clear,
        )
    except ImportError as e:
        print(f"\033[31m[ERROR] {e}\033[0m")
        sys.exit(1)
    except Exception as e:
        print(f"\033[31m[ERROR] 连接 hindsight 失败: {e}\033[0m")
        sys.exit(1)

    success = seed_world_memories(store, memories)

    # 3. 统计结果
    stats = store.get_stats()
    print("\n" + "=" * 60)
    print("初始化完成")
    print("=" * 60)
    print(f"成功写入: {success} / {len(memories)} 条")
    print(f"Bank 总记忆数: {stats.get('total_memories', 'N/A')}")
    print(f"Bank ID: {stats.get('bank_id', 'N/A')}")
    print("-" * 60)

    store.close()


if __name__ == "__main__":
    main()
