"""
Memory Skill - 长效记忆技能

封装 Hindsight 记忆库的读写操作，支持个人记忆和世界记忆的合并召回与保存。

用法:
    from skills.memory_skill import recall_all_memory, save_memory

    # 召回记忆
    memory_text = recall_all_memory("uid_001", "灵潮")

    # 保存记忆
    save_memory("user_uid_001", "玩家在青墟山突破筑基期")
    save_memory("world_global_history", "灵潮爆发，灵气浓度骤增")
"""

import os
import logging
from typing import Dict, Any, Optional

import yaml

try:
    from hindsight_memory import HindsightMemoryStore, get_memory_store
    _HAS_HINDSIGHT = True
except ImportError as _import_err:
    _HAS_HINDSIGHT = False
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
# 配置加载
# ───────────────────────────────────────────────

def _load_hindsight_config() -> Dict[str, Any]:
    """从 config.yaml 加载 Hindsight 配置"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config.yaml",
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("gm", {}).get("hindsight", {})
    except Exception as e:
        error_log(f"加载 Hindsight 配置失败: {e}")
        return {}


# ───────────────────────────────────────────────
# 全局记忆库实例缓存
# ───────────────────────────────────────────────

_memory_stores: Dict[str, HindsightMemoryStore] = {}
_hindsight_base_url: str = "http://localhost:8888"
_hindsight_api_key: Optional[str] = None
_config_loaded: bool = False


def _ensure_config() -> None:
    """确保 Hindsight 配置已加载"""
    global _hindsight_base_url, _hindsight_api_key, _config_loaded
    if _config_loaded:
        return

    cfg = _load_hindsight_config()
    _hindsight_base_url = cfg.get("base_url", "http://localhost:8888")
    _hindsight_api_key = cfg.get("api_key")
    _config_loaded = True
    info_log(f"Hindsight 配置加载完成: base_url={_hindsight_base_url}")


def _get_memory_store(bank_id: str) -> Optional[HindsightMemoryStore]:
    """获取或创建 Hindsight 记忆库实例（带缓存）"""
    if not _HAS_HINDSIGHT:
        error_log(f"缺少 hindsight_memory 模块: {_IMPORT_ERROR}")
        return None

    _ensure_config()

    if bank_id in _memory_stores:
        return _memory_stores[bank_id]

    try:
        store = get_memory_store(
            bank_id=bank_id,
            base_url=_hindsight_base_url,
            api_key=_hindsight_api_key,
        )
        _memory_stores[bank_id] = store
        debug_log(f"Hindsight 记忆库实例创建成功: {bank_id}")
        return store
    except Exception as e:
        error_log(f"Hindsight 记忆库实例创建失败: {bank_id}, 错误: {e}")
        return None


# ================================================================
# ⑤ 长效记忆
# ================================================================

def recall_all_memory(uid: str, query: str) -> Dict[str, Any]:
    """
    合并召回个人记忆和世界记忆，返回与查询相关的记忆内容

    个人记忆使用 bank_id = f"user_{uid}"，
    世界记忆使用 bank_id = "world"，
    合并两者结果并格式化为文本。

    Args:
        uid: 玩家唯一标识
        query: 记忆检索查询文本

    Returns:
        记忆召回结果:
        {
            "success": True/False,
            "uid": "uid_001",
            "query": "灵潮",
            "memory_text": "格式化的记忆文本",
            "error": "错误信息（如果有）"
        }
    """
    if not _HAS_HINDSIGHT:
        error_msg = f"缺少 hindsight_memory 模块: {_IMPORT_ERROR}"
        error_log(error_msg)
        return {"success": False, "uid": uid, "query": query, "memory_text": "", "error": error_msg}

    parts = []

    # ── 个人记忆 ──
    user_bank_id = f"user_{uid}"
    user_store = _get_memory_store(user_bank_id)
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
    world_store = _get_memory_store("world")
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

    memory_text = "\n".join(parts)
    if memory_text:
        info_log(f"合并召回记忆成功: uid={uid}, query={query}")
    else:
        debug_log(f"未召回相关记忆: uid={uid}, query={query}")

    return {
        "success": bool(memory_text),
        "uid": uid,
        "query": query,
        "memory_text": memory_text,
        "error": "" if memory_text else "未召回相关记忆",
    }


def save_memory(namespace: str, summary: str) -> Dict[str, Any]:
    """
    保存记忆，namespace 为 user_{uid} 或 world_global_history

    namespace 格式：
    - user_{uid}: 保存到玩家个人记忆库
    - world_global_history: 保存到世界全局记忆库

    Args:
        namespace: 记忆命名空间，如 user_{uid} 或 world_global_history
        summary: 记忆摘要内容

    Returns:
        保存结果字典:
        {
            "success": True/False,
            "namespace": "user_uid_001",
            "error": "错误信息（如果有）"
        }
    """
    if not _HAS_HINDSIGHT:
        error_msg = f"缺少 hindsight_memory 模块: {_IMPORT_ERROR}"
        error_log(error_msg)
        return {"success": False, "namespace": namespace, "error": error_msg}

    try:
        if not summary or not summary.strip():
            warn_log("记忆摘要为空，跳过保存")
            return {"success": False, "namespace": namespace, "error": "记忆摘要为空"}

        # world_global_history 映射到 world bank
        bank_id = "world" if namespace == "world_global_history" else namespace

        store = _get_memory_store(bank_id)
        if not store:
            warn_log(f"记忆库不可用: {bank_id}")
            return {"success": False, "namespace": namespace, "error": f"记忆库不可用: {bank_id}"}

        success = store.retain(
            content=summary.strip(),
            context="gm_event",
        )
        if success:
            info_log(f"记忆保存成功: namespace={namespace}, content={summary[:50]}")
            return {"success": True, "namespace": namespace, "error": ""}
        else:
            warn_log(f"记忆保存返回失败: namespace={namespace}")
            return {"success": False, "namespace": namespace, "error": "记忆保存返回失败"}

    except Exception as e:
        error_log(f"记忆保存异常: namespace={namespace}, 错误: {e}")
        return {"success": False, "namespace": namespace, "error": str(e)}


if __name__ == "__main__":
    # 测试代码
    info_log("测试 memory_skill...")

    # 测试召回记忆
    info_log("\n测试 recall_all_memory:")
    result = recall_all_memory("uid_001", "灵潮")
    print(f"  success={result['success']}, memory_text={result.get('memory_text', '')[:100]}")

    # 测试保存记忆
    info_log("\n测试 save_memory:")
    result = save_memory("user_uid_test", "测试记忆内容")
    print(f"  success={result['success']}, error={result.get('error', '')}")

    # 测试保存世界记忆
    info_log("\n测试 save_memory (world):")
    result = save_memory("world_global_history", "世界事件测试")
    print(f"  success={result['success']}, error={result.get('error', '')}")
