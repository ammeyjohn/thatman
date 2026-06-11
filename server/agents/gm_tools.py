"""
GM Tools - Game Master 全量工具函数定义
提供 LLM function calling 所需的 JSON Schema 以及工具匹配与执行逻辑。
工具 Schema 从 skills/skills.json 加载，支持外部配置化管理。
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

# 复用 gm_logger 的 debug 开关控制日志函数
from gm_logger import debug_log, info_log, warn_log, error_log

# 导入 read_doc 和 find_skill 模块
from skills.read_doc import read_doc as _read_doc, list_available_docs as _list_available_docs, search_doc_content as _search_doc_content
from skills.find_skill import list_all_skills as _list_all_skills, search_skill as _search_skill, get_skill_info as _get_skill_info
from skills.character_status_skill import update_character_status as _update_character_status
from skills.karma_skill import (
    record_karma as _record_karma,
    get_karma_status as _get_karma_status,
    judge_karma as _judge_karma,
    get_karma_bonds as _get_karma_bonds,
    resolve_karma as _resolve_karma,
)
from action_definition_manager import get_action_definition_manager

# 配置日志
logger = logging.getLogger(__name__)


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
            tool_schemas = skill.get("tool_schemas")
            if tool_schemas and isinstance(tool_schemas, list):
                tools.extend(tool_schemas)

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

        # ---- 文档读取操作 ----
        if tool_name == "read_doc":
            filename = tool_args["filename"]
            result = _read_doc(filename)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "list_available_docs":
            result = _list_available_docs()
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "search_doc_content":
            keyword = tool_args["keyword"]
            result = _search_doc_content(keyword)
            return json.dumps(result, ensure_ascii=False)

        # ---- 技能查找操作 ----
        if tool_name == "list_all_skills":
            include_details = tool_args.get("include_details", True)
            result = _list_all_skills(include_details)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "search_skill":
            keyword = tool_args["keyword"]
            search_in_description = tool_args.get("search_in_description", True)
            result = _search_skill(keyword, search_in_description)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "get_skill_info":
            skill_name = tool_args["skill_name"]
            result = _get_skill_info(skill_name)
            return json.dumps(result, ensure_ascii=False)

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

        # ---- 动作定义操作 ----
        if tool_name == "create_action_definition":
            definition = tool_args.get("definition", {})
            action_mgr = get_action_definition_manager()
            if not action_mgr:
                return json.dumps({"error": "动作定义管理器未初始化"}, ensure_ascii=False)
            try:
                result = action_mgr.create_or_update_action(definition)
                return json.dumps({"success": True, "action_id": result.get("action_id"), "definition": result}, ensure_ascii=False)
            except Exception as e:
                error_log(f"创建动作定义失败: {e}")
                return json.dumps({"error": f"创建动作定义失败: {e}"}, ensure_ascii=False)

        if tool_name == "get_action_definition":
            action_id = tool_args.get("action_id", "")
            action_mgr = get_action_definition_manager()
            if not action_mgr:
                return json.dumps({"error": "动作定义管理器未初始化"}, ensure_ascii=False)
            result = action_mgr.get_action_definition(action_id)
            if result:
                return json.dumps({"success": True, "action_id": action_id, "definition": result}, ensure_ascii=False)
            else:
                return json.dumps({"success": False, "action_id": action_id, "error": "动作定义不存在"}, ensure_ascii=False)

        if tool_name == "list_action_definitions":
            category = tool_args.get("category", "")
            action_mgr = get_action_definition_manager()
            if not action_mgr:
                return json.dumps({"error": "动作定义管理器未初始化"}, ensure_ascii=False)
            result = action_mgr.list_action_definitions(category)
            return json.dumps({"success": True, "total": len(result), "definitions": result}, ensure_ascii=False)

        # ---- 角色状态更新操作 ----
        if tool_name == "update_character_status":
            uid = tool_args.get("uid", "")
            updates = tool_args.get("updates", {})
            if not uid:
                return json.dumps({"success": False, "error": "uid 不能为空"}, ensure_ascii=False)
            if not updates:
                return json.dumps({"success": False, "error": "updates 不能为空"}, ensure_ascii=False)
            result = _update_character_status(uid=uid, updates=updates, storage=storage)
            return json.dumps(result, ensure_ascii=False)

        # ---- 因果业力操作 ----
        if tool_name == "record_karma":
            uid = tool_args.get("uid", "")
            karma_type = tool_args.get("karma_type", "")
            target_id = tool_args.get("target_id", "")
            target_name = tool_args.get("target_name", "")
            description = tool_args.get("description", "")
            karma_value = tool_args.get("karma_value", 0)
            if not uid:
                return json.dumps({"success": False, "error": "uid 不能为空"}, ensure_ascii=False)
            result = _record_karma(
                uid=uid, karma_type=karma_type, target_id=target_id,
                target_name=target_name, description=description,
                karma_value=karma_value, storage=storage,
            )
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "get_karma_status":
            uid = tool_args.get("uid", "")
            if not uid:
                return json.dumps({"success": False, "error": "uid 不能为空"}, ensure_ascii=False)
            result = _get_karma_status(uid=uid, storage=storage)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "judge_karma":
            uid = tool_args.get("uid", "")
            action_description = tool_args.get("action_description", "")
            context = tool_args.get("context", "")
            if not uid:
                return json.dumps({"success": False, "error": "uid 不能为空"}, ensure_ascii=False)
            if not action_description:
                return json.dumps({"success": False, "error": "action_description 不能为空"}, ensure_ascii=False)
            result = _judge_karma(uid=uid, action_description=action_description, context=context, storage=storage)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "get_karma_bonds":
            uid = tool_args.get("uid", "")
            if not uid:
                return json.dumps({"success": False, "error": "uid 不能为空"}, ensure_ascii=False)
            result = _get_karma_bonds(uid=uid, storage=storage)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "resolve_karma":
            uid = tool_args.get("uid", "")
            target_id = tool_args.get("target_id", "")
            resolution_type = tool_args.get("resolution_type", "")
            if not uid:
                return json.dumps({"success": False, "error": "uid 不能为空"}, ensure_ascii=False)
            if not target_id:
                return json.dumps({"success": False, "error": "target_id 不能为空"}, ensure_ascii=False)
            if not resolution_type:
                return json.dumps({"success": False, "error": "resolution_type 不能为空"}, ensure_ascii=False)
            result = _resolve_karma(uid=uid, target_id=target_id, resolution_type=resolution_type, storage=storage)
            return json.dumps(result, ensure_ascii=False)

        # 未知工具
        warn_log(f"未知工具名称: {tool_name}")
        return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    except KeyError as e:
        error_log(f"工具 {tool_name} 缺少必需参数: {e}")
        return json.dumps({"error": f"缺少必需参数: {e}"}, ensure_ascii=False)
    except Exception as e:
        error_log(f"工具 {tool_name} 执行失败: {e}")
        return json.dumps({"error": f"工具执行失败: {e}"}, ensure_ascii=False)
