"""
Character Status Skill - 角色状态更新技能

提供带验证限制的角色状态更新功能，供 LLM 通过 function calling 调用。
所有核心属性（境界、等级、生命值等）的修改必须通过此技能完成，
技能内部会对新旧状态进行比对验证，拒绝不合理的状态更新。
"""

import json
import logging
from typing import Dict, Any

from gm_logger import debug_log, info_log, warn_log, error_log
from character_status_validator import CharacterStatusValidator

logger = logging.getLogger(__name__)


def update_character_status(
    uid: str,
    updates: Dict[str, Any],
    storage=None,
) -> Dict[str, Any]:
    """
    更新角色核心属性状态（带验证限制）

    核心属性包括：realm、realm_stage、level、health、max_health、
    mana、max_mana、spirit、max_spirit、equipment、inventory。
    所有核心属性的修改必须通过此函数完成，函数内部会对新旧状态
    进行比对验证，拒绝不合理的状态更新（如等级跳跃、境界跨级等）。

    Args:
        uid: 玩家唯一标识
        updates: 待更新的状态字段字典，仅包含需要更新的字段。
            支持的字段：
            - realm: 境界名称（如"炼气期"、"筑基期"）
            - realm_stage: 境界阶段（"初期"/"中期"/"后期"/"巅峰"/"圆满"）
            - level: 等级（数字）
            - health: 当前生命值
            - max_health: 最大生命值
            - mana: 当前法力值
            - max_mana: 最大法力值
            - spirit: 当前神识值
            - max_spirit: 最大神识值
            - equipment: 装备列表
            - inventory: 背包物品列表
        storage: GMStorage 实例（由 gm_tools 传入）

    Returns:
        包含 success, uid, updates, rejected_fields, reasons 的字典
    """
    if not uid:
        return {"success": False, "error": "uid 不能为空"}

    if not updates or not isinstance(updates, dict):
        return {"success": False, "error": "updates 必须为非空字典"}

    if not storage:
        return {"success": False, "error": "存储层不可用"}

    # 1. 获取当前玩家数据
    old_status = storage.couch_get_player(uid)
    if not old_status:
        warn_log(f"玩家数据不存在: {uid}")
        return {"success": False, "error": f"玩家数据不存在: {uid}"}

    # 2. 验证更新
    is_valid, reasons = CharacterStatusValidator.validate(old_status, updates)

    if not is_valid:
        warn_log(f"角色状态更新被拒绝: uid={uid}, reasons={reasons}")
        return {
            "success": False,
            "uid": uid,
            "rejected_fields": list(updates.keys()),
            "reasons": reasons,
            "hint": "请根据拒绝原因调整状态更新值后重试。境界只能升一级，阶段只能升一级，等级单次增幅不超过10，属性上限变化不超过50%（突破时不超过200%）",
        }

    # 3. 执行增量合并保存
    try:
        # 合并数据
        merged = {**old_status, **updates}
        # 移除 CouchDB 内部字段
        merged.pop("_id", None)
        merged.pop("_rev", None)

        result = storage.couch_save_player(uid, merged)
        if result:
            info_log(f"角色状态更新成功: uid={uid}, 更新字段={list(updates.keys())}")
            return {
                "success": True,
                "uid": uid,
                "updated_fields": list(updates.keys()),
                "message": f"角色状态更新成功，已更新字段: {list(updates.keys())}",
            }
        else:
            error_log(f"角色状态保存失败: uid={uid}")
            return {"success": False, "error": "保存角色状态失败"}

    except Exception as e:
        error_log(f"角色状态更新异常: uid={uid}, 错误={e}")
        return {"success": False, "error": f"更新异常: {e}"}
