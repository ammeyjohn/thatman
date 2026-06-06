"""
GM Tools - Game Master 全量工具函数定义
提供 LLM function calling 所需的 JSON Schema 以及工具匹配与执行逻辑。
工具 Schema 从 skills/skills.json 加载，支持外部配置化管理。
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

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


# skills.json 路径
_SKILLS_JSON_PATH = Path(__file__).parent / "skills" / "skills.json"


# ============================================================
# 从 skills.json 加载工具 Schema
# ============================================================

def _load_tools_from_json() -> List[Dict[str, Any]]:
    """
    从 skills/skills.json 加载工具 Schema 列表

    只加载包含 tool_schema 字段的 skill（即 GM 工具），
    将其 tool_schema 提取出来组成列表。

    Returns:
        工具 Schema 列表
    """
    if not _SKILLS_JSON_PATH.exists():
        error_log(f"skills.json 不存在: {_SKILLS_JSON_PATH}")
        return []

    try:
        with open(_SKILLS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        tools = []
        for skill in data.get("skills", []):
            tool_schema = skill.get("tool_schema")
            if tool_schema:
                tools.append(tool_schema)

        info_log(f"从 skills.json 加载 {len(tools)} 个工具 Schema")
        return tools

    except Exception as e:
        error_log(f"加载 skills.json 失败: {e}")
        return []


def get_all_tools() -> List[Dict[str, Any]]:
    """
    返回全量工具 JSON Schema 数组，供 LLM function calling 使用

    从 skills/skills.json 动态加载，支持外部配置化管理。

    Returns:
        工具定义列表
    """
    return _load_tools_from_json()


# ============================================================
# 工具匹配与执行
# ============================================================

def match_and_execute_tool(tool_name: str, tool_args: Dict[str, Any], storage) -> str:
    """
    根据工具名匹配并调用 storage 层对应方法，返回结果文本

    Args:
        tool_name: 工具函数名称
        tool_args: 工具调用参数字典
        storage: GMStorage 实例，提供底层数据操作方法

    Returns:
        工具执行结果的 JSON 字符串
    """
    try:
        debug_log(f"匹配工具: {tool_name}, 参数: {json.dumps(tool_args, ensure_ascii=False)}")

        # ---- CouchDB 玩家操作 ----
        if tool_name == "couch_get_player":
            uid = tool_args["uid"]
            result = storage.couch_get_player(uid)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "couch_save_player":
            uid = tool_args["uid"]
            data = tool_args["data"]
            result = storage.couch_save_player(uid, data)
            return json.dumps(result, ensure_ascii=False)

        # ---- CouchDB 实体操作 ----
        if tool_name == "couch_get_entity":
            entity_id = tool_args["entity_id"]
            result = storage.couch_get_entity(entity_id)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "couch_save_entity":
            entity_id = tool_args["entity_id"]
            entity_data = tool_args["entity_data"]
            result = storage.couch_save_entity(entity_id, entity_data)
            return json.dumps(result, ensure_ascii=False)

        # ---- CouchDB 关系操作 ----
        if tool_name == "couch_get_link":
            target_id = tool_args["target_id"]
            rel_type = tool_args["rel_type"]
            result = storage.couch_get_link(target_id, rel_type)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "couch_save_link":
            from_id = tool_args["from_id"]
            to_id = tool_args["to_id"]
            rel_type = tool_args["rel_type"]
            desc = tool_args["desc"]
            result = storage.couch_save_link(from_id, to_id, rel_type, desc)
            return json.dumps(result, ensure_ascii=False)

        # ---- CouchDB 世界快照操作 ----
        if tool_name == "couch_get_last_world_snap":
            result = storage.couch_get_last_world_snap()
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "couch_save_world_snap":
            snap_data = tool_args["snap_data"]
            result = storage.couch_save_world_snap(snap_data)
            return json.dumps(result, ensure_ascii=False)

        # ---- 记忆操作 ----
        if tool_name == "recall_all_memory":
            uid = tool_args["uid"]
            query = tool_args["query"]
            result = storage.recall_all_memory(uid, query)
            # recall_all_memory 返回 str，直接返回
            return result

        if tool_name == "save_memory":
            namespace = tool_args["namespace"]
            summary = tool_args["summary"]
            result = storage.save_memory(namespace, summary)
            return json.dumps({"success": result}, ensure_ascii=False)

        # ---- 剧情向量操作 ----
        if tool_name == "search_plot_vector":
            query = tool_args["query"]
            top_k = tool_args.get("top_k", 3)
            result = storage.search_plot_vector(query, top_k)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "insert_plot_vector":
            content = tool_args["content"]
            meta = tool_args["meta"]
            result = storage.insert_plot_vector(content, meta)
            return json.dumps({"success": result}, ensure_ascii=False)

        # 未知工具
        warn_log(f"未知工具名称: {tool_name}")
        return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    except KeyError as e:
        error_log(f"工具 {tool_name} 缺少必需参数: {e}")
        return json.dumps({"error": f"缺少必需参数: {e}"}, ensure_ascii=False)
    except Exception as e:
        error_log(f"工具 {tool_name} 执行失败: {e}")
        return json.dumps({"error": f"工具执行失败: {e}"}, ensure_ascii=False)
