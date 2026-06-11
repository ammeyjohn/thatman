"""
Action Definition Skill - 动作类型定义管理技能

封装 ActionDefinitionManager 的操作，供 LLM 通过 function calling 调用。
支持创建/更新、查询、列出动作类型定义。

用法:
    from skills.action_definition import create_action_definition, get_action_definition, list_action_definitions

    # 创建动作定义
    result = create_action_definition(definition={...})

    # 查询动作定义
    result = get_action_definition(action_id="meditate_depth")

    # 列出所有动作定义
    result = list_action_definitions(category="修炼")
"""

import logging
from typing import Dict, Any, Optional

from action_definition_manager import get_action_definition_manager

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


def create_action_definition(definition: Dict[str, Any]) -> Dict[str, Any]:
    """
    创建或更新动作类型定义

    当玩家执行一个全新类型的动作时，使用此工具保存新动作的定义，供后续复用。

    Args:
        definition: 动作定义对象，必须包含：
            - action_id: 唯一标识
            - name: 显示名称
            - category: 类别
            - base_time_cost: {"min": x, "max": y}
            - difficulty: 难度1-10
            - restrictions: {forbidden_operations, allowed_operations, allow_interrupt, interrupt_penalty}
            - time_modifiers: {realm_factor, spirit_concentration_factor, weather_factor}
            - description: 描述

    Returns:
        包含 success, action_id, definition 的字典
    """
    action_mgr = get_action_definition_manager()
    if not action_mgr:
        error_msg = "动作定义管理器未初始化"
        error_log(error_msg)
        return {"success": False, "error": error_msg}

    try:
        result = action_mgr.create_or_update_action(definition)
        info_log(f"动作定义已创建/更新: {definition.get('action_id', 'unknown')}")
        return {"success": True, "action_id": result.get("action_id"), "definition": result}
    except ValueError as e:
        warn_log(f"动作定义参数无效: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        error_log(f"创建动作定义失败: {e}")
        return {"success": False, "error": str(e)}


def get_action_definition(action_id: str) -> Dict[str, Any]:
    """
    查询指定动作类型的完整定义，包括耗时、约束规则、中断策略等

    Args:
        action_id: 动作唯一标识，如 meditate_depth, combat, move_region 等

    Returns:
        包含 success, action_id, definition 的字典
    """
    action_mgr = get_action_definition_manager()
    if not action_mgr:
        error_msg = "动作定义管理器未初始化"
        error_log(error_msg)
        return {"success": False, "action_id": action_id, "error": error_msg}

    result = action_mgr.get_action_definition(action_id)
    if result:
        debug_log(f"获取动作定义成功: {action_id}")
        return {"success": True, "action_id": action_id, "definition": result}
    else:
        warn_log(f"动作定义不存在: {action_id}")
        return {"success": False, "action_id": action_id, "error": f"动作定义不存在: {action_id}"}


def list_action_definitions(category: str = "") -> Dict[str, Any]:
    """
    列出所有已定义的动作类型，可按类别过滤

    用于了解游戏中有哪些动作类型及其规则。

    Args:
        category: 类别过滤，如 修炼/战斗/移动/采集/炼制/休息/社交/即时，为空返回所有

    Returns:
        包含 success, total, definitions 的字典
    """
    action_mgr = get_action_definition_manager()
    if not action_mgr:
        error_msg = "动作定义管理器未初始化"
        error_log(error_msg)
        return {"success": False, "total": 0, "definitions": [], "error": error_msg}

    result = action_mgr.list_action_definitions(category)
    info_log(f"列出动作定义: category={category or '全部'}, 共 {len(result)} 个")
    return {"success": True, "total": len(result), "definitions": result}


if __name__ == "__main__":
    # 测试代码
    info_log("测试 action_definition skill...")

    # 测试列出所有动作定义
    info_log("\n测试 list_action_definitions:")
    result = list_action_definitions()
    print(f"  success={result['success']}, total={result.get('total', 0)}")

    # 测试查询特定动作定义
    info_log("\n测试 get_action_definition:")
    result = get_action_definition("meditate_depth")
    print(f"  success={result['success']}, action_id={result.get('action_id', '')}")

    # 测试创建动作定义
    info_log("\n测试 create_action_definition:")
    test_def = {
        "action_id": "test_action",
        "name": "测试动作",
        "category": "测试",
        "base_time_cost": {"min": 10, "max": 20},
        "difficulty": 1,
        "restrictions": {
            "forbidden_operations": ["move"],
            "allowed_operations": ["chat"],
            "allow_interrupt": True,
            "interrupt_penalty": "none",
        },
        "time_modifiers": {
            "realm_factor": False,
            "spirit_concentration_factor": False,
            "weather_factor": False,
        },
        "description": "测试用动作定义",
    }
    result = create_action_definition(test_def)
    print(f"  success={result['success']}, action_id={result.get('action_id', '')}")
