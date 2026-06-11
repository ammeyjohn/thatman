"""
Karma Skill - 因果业力核心技能模块

提供因果业力记录、查询、善恶判定、因果羁绊、了结因果等功能，
供 LLM 通过 function calling 调用。

核心概念：
- 业力值(karma)：正值为善/功德，负值为恶/业障
- 因果类型：恩情(grace)、仇怨(enmity)、同门(fellowship)、知己(friendship)、契约(contract)、陌路(neutral)
- 善恶等级：1-5级，影响突破成功率和NPC态度
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from gm_logger import debug_log, info_log, warn_log, error_log
from skills.karma_validator import (
    validate_karma_change,
    validate_resolve_karma,
    get_karma_level,
    get_resolve_karma_value,
    KARMA_TYPE_RANGES,
)

logger = logging.getLogger(__name__)


def record_karma(
    uid: str,
    karma_type: str,
    target_id: str,
    target_name: str,
    description: str,
    karma_value: int,
    storage=None,
) -> Dict[str, Any]:
    """
    记录一条因果事件，更新玩家业力值

    Args:
        uid: 玩家唯一标识
        karma_type: 因果类型 (grace/enmity/fellowship/friendship/contract/neutral)
        target_id: 目标实体ID（NPC/宗门/法宝等）
        target_name: 目标名称
        description: 因果事件描述
        karma_value: 业力变化值（正=善，负=恶）
        storage: GMStorage 实例

    Returns:
        包含 success, uid, karma_value, karma_level 等的字典
    """
    if not uid:
        return {"success": False, "error": "uid 不能为空"}

    if not storage:
        return {"success": False, "error": "存储层不可用"}

    # 1. 获取当前玩家数据
    player_data = storage.couch_get_player(uid)
    if not player_data:
        return {"success": False, "error": f"玩家数据不存在: {uid}"}

    old_karma = player_data.get("karma", 0)

    # 2. 验证业力变更
    is_valid, reasons = validate_karma_change(old_karma, karma_value, karma_type, target_id)
    if not is_valid:
        return {
            "success": False,
            "uid": uid,
            "rejected": True,
            "reasons": reasons,
            "hint": "请根据拒绝原因调整业力值。单次变化不超过±50，因果类型与业力值方向需匹配。",
        }

    # 3. 计算新业力值和等级
    new_karma = old_karma + karma_value
    level_info = get_karma_level(new_karma)

    # 4. 保存因果记录
    record_data = {
        "uid": uid,
        "karma_type": karma_type,
        "target_id": target_id,
        "target_name": target_name,
        "description": description,
        "karma_value": karma_value,
        "karma_before": old_karma,
        "karma_after": new_karma,
        "resolved": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        storage.couch_save_karma_record(uid, record_data)
    except Exception as e:
        error_log(f"保存因果记录失败: uid={uid}, 错误: {e}")
        # 不阻断主流程，继续更新玩家业力

    # 5. 保存/更新因果羁绊（使用 link 系统）
    try:
        rel_type = f"karma_{karma_type}"
        storage.couch_save_link(uid, target_id, rel_type, description)
        debug_log(f"因果羁绊已记录: {uid} -> {target_id}, type={karma_type}")
    except Exception as e:
        error_log(f"保存因果羁绊失败: uid={uid}, 错误: {e}")

    # 6. 更新玩家业力数据
    try:
        player_data["karma"] = new_karma
        player_data["karma_level"] = level_info["level"]
        player_data["karma_title"] = level_info["title"]
        # 移除 CouchDB 内部字段
        player_data.pop("_id", None)
        player_data.pop("_rev", None)
        storage.couch_save_player(uid, player_data)
        info_log(f"玩家业力更新: uid={uid}, {old_karma}->{new_karma}, 等级={level_info['title']}")
    except Exception as e:
        error_log(f"更新玩家业力失败: uid={uid}, 错误: {e}")
        return {"success": False, "error": f"更新玩家业力失败: {e}"}

    # 7. 保存因果记忆到长效记忆
    try:
        memory_summary = f"因果事件：{description}（与{target_name}的{karma_type}关系，业力{'+'if karma_value>=0 else ''}{karma_value}）"
        storage.save_memory(f"user_{uid}", memory_summary)
    except Exception as e:
        error_log(f"保存因果记忆失败: uid={uid}, 错误: {e}")

    return {
        "success": True,
        "uid": uid,
        "karma_before": old_karma,
        "karma_change": karma_value,
        "karma_after": new_karma,
        "karma_level": level_info["level"],
        "karma_title": level_info["title"],
        "message": f"因果已记录：{description}，业力{'+'if karma_value>=0 else ''}{karma_value}，当前善恶等级：{level_info['title']}",
    }


def get_karma_status(uid: str, storage=None) -> Dict[str, Any]:
    """
    获取玩家业力总览

    Args:
        uid: 玩家唯一标识
        storage: GMStorage 实例

    Returns:
        包含业力值、善恶等级、因果记录、因果羁绊的字典
    """
    if not uid:
        return {"success": False, "error": "uid 不能为空"}

    if not storage:
        return {"success": False, "error": "存储层不可用"}

    # 1. 获取玩家业力数据
    player_data = storage.couch_get_player(uid)
    if not player_data:
        return {"success": False, "error": f"玩家数据不存在: {uid}"}

    karma = player_data.get("karma", 0)
    karma_level = player_data.get("karma_level", 3)
    karma_title = player_data.get("karma_title", "因果清净")

    # 2. 获取因果记录
    records = []
    try:
        records = storage.couch_get_karma_records(uid, limit=20)
    except Exception as e:
        error_log(f"获取因果记录失败: uid={uid}, 错误: {e}")

    # 3. 获取因果羁绊
    bonds = []
    try:
        bonds = storage.couch_get_karma_bonds(uid)
    except Exception as e:
        error_log(f"获取因果羁绊失败: uid={uid}, 错误: {e}")

    # 4. 统计因果类型分布
    type_stats = {}
    for record in records:
        kt = record.get("karma_type", "unknown")
        type_stats[kt] = type_stats.get(kt, 0) + 1

    return {
        "success": True,
        "uid": uid,
        "karma": karma,
        "karma_level": karma_level,
        "karma_title": karma_title,
        "total_records": len(records),
        "total_bonds": len(bonds),
        "type_stats": type_stats,
        "recent_records": records[:10],
        "bonds": bonds,
    }


def judge_karma(
    uid: str,
    action_description: str,
    context: str = "",
    storage=None,
) -> Dict[str, Any]:
    """
    善恶判定：根据行为描述和上下文，返回善恶判定结果

    此函数提供判定参考，GM（LLM）根据判定结果决定是否调用 record_karma

    Args:
        uid: 玩家唯一标识
        action_description: 行为描述
        context: 行为上下文
        storage: GMStorage 实例

    Returns:
        包含 judgment, suggested_karma_value, reason 的字典
    """
    if not uid:
        return {"success": False, "error": "uid 不能为空"}

    if not action_description:
        return {"success": False, "error": "行为描述不能为空"}

    # 获取当前业力状态
    current_karma = 0
    current_level = 3
    if storage:
        player_data = storage.couch_get_player(uid)
        if player_data:
            current_karma = player_data.get("karma", 0)
            current_level = player_data.get("karma_level", 3)

    # 善恶判定规则表（关键词匹配 + 建议值）
    judgment_rules = {
        # 恩情类善行
        "救": {"judgment": "善", "karma_type": "grace", "suggested_value": 30, "reason": "救助他人，结下恩情因果"},
        "帮助": {"judgment": "善", "karma_type": "grace", "suggested_value": 15, "reason": "施以援手，善行积德"},
        "赠": {"judgment": "善", "karma_type": "grace", "suggested_value": 20, "reason": "慷慨赠予，恩泽他人"},
        "传法": {"judgment": "善", "karma_type": "grace", "suggested_value": 30, "reason": "传授功法，大恩大德"},
        "护": {"judgment": "善", "karma_type": "grace", "suggested_value": 20, "reason": "守护他人，义举善行"},
        "治": {"judgment": "善", "karma_type": "grace", "suggested_value": 15, "reason": "救治伤病，悬壶济世"},
        # 仇怨类恶行
        "杀": {"judgment": "恶", "karma_type": "enmity", "suggested_value": -40, "reason": "杀戮生灵，结下仇怨"},
        "掠夺": {"judgment": "恶", "karma_type": "enmity", "suggested_value": -30, "reason": "掠夺他人财物，结怨"},
        "偷": {"judgment": "恶", "karma_type": "enmity", "suggested_value": -20, "reason": "窃取他人之物，损人利己"},
        "辱": {"judgment": "恶", "karma_type": "enmity", "suggested_value": -15, "reason": "羞辱他人，结怨"},
        "背叛": {"judgment": "恶", "karma_type": "enmity", "suggested_value": -40, "reason": "背叛信义，大恶"},
        # 中性行为
        "修炼": {"judgment": "中性", "karma_type": "neutral", "suggested_value": 0, "reason": "修行自身，无善恶因果"},
        "赶路": {"judgment": "中性", "karma_type": "neutral", "suggested_value": 0, "reason": "行走赶路，无因果"},
        "查看": {"judgment": "中性", "karma_type": "neutral", "suggested_value": 0, "reason": "观察了解，无因果"},
    }

    # 关键词匹配判定
    matched_rule = None
    for keyword, rule in judgment_rules.items():
        if keyword in action_description:
            matched_rule = rule
            break

    if matched_rule:
        judgment = matched_rule["judgment"]
        karma_type = matched_rule["karma_type"]
        suggested_value = matched_rule["suggested_value"]
        reason = matched_rule["reason"]
    else:
        # 未匹配到规则，返回中性判定
        judgment = "中性"
        karma_type = "neutral"
        suggested_value = 0
        reason = "行为未匹配善恶判定规则，需GM根据剧情判定"

    # 计算判定后的业力等级
    predicted_karma = current_karma + suggested_value
    predicted_level = get_karma_level(predicted_karma)

    return {
        "success": True,
        "uid": uid,
        "action_description": action_description,
        "judgment": judgment,
        "karma_type": karma_type,
        "suggested_karma_value": suggested_value,
        "reason": reason,
        "current_karma": current_karma,
        "current_karma_level": current_level,
        "predicted_karma": predicted_karma,
        "predicted_karma_level": predicted_level["level"],
        "predicted_karma_title": predicted_level["title"],
        "note": "此判定仅供参考，GM应根据剧情上下文决定是否记录因果及具体业力值",
    }


def get_karma_bonds(uid: str, storage=None) -> Dict[str, Any]:
    """
    获取玩家与NPC/实体的因果羁绊列表

    Args:
        uid: 玩家唯一标识
        storage: GMStorage 实例

    Returns:
        包含因果羁绊列表的字典
    """
    if not uid:
        return {"success": False, "error": "uid 不能为空"}

    if not storage:
        return {"success": False, "error": "存储层不可用"}

    bonds = []
    try:
        bonds = storage.couch_get_karma_bonds(uid)
    except Exception as e:
        error_log(f"获取因果羁绊失败: uid={uid}, 错误: {e}")
        return {"success": False, "error": f"获取因果羁绊失败: {e}"}

    return {
        "success": True,
        "uid": uid,
        "total": len(bonds),
        "bonds": bonds,
    }


def resolve_karma(
    uid: str,
    target_id: str,
    resolution_type: str,
    storage=None,
) -> Dict[str, Any]:
    """
    了结因果：恩报恩、仇复仇等，了结后业力变化

    Args:
        uid: 玩家唯一标识
        target_id: 因果羁绊的目标实体ID
        resolution_type: 了结方式 (repay/betray/revenge/forgive/part/reunite/deepen/fulfill/break)
        storage: GMStorage 实例

    Returns:
        包含了结结果和业力变化的字典
    """
    if not uid:
        return {"success": False, "error": "uid 不能为空"}

    if not target_id:
        return {"success": False, "error": "target_id 不能为空"}

    if not storage:
        return {"success": False, "error": "存储层不可用"}

    # 1. 查找因果羁绊
    bonds = []
    try:
        bonds = storage.couch_get_karma_bonds(uid)
    except Exception as e:
        error_log(f"查找因果羁绊失败: uid={uid}, 错误: {e}")

    target_bond = None
    for bond in bonds:
        if bond.get("target_id") == target_id:
            target_bond = bond
            break

    if not target_bond:
        return {"success": False, "error": f"未找到与 {target_id} 的因果羁绊"}

    bond_type = target_bond.get("bond_type", "").replace("karma_", "")

    # 2. 验证了结方式
    is_valid, reasons = validate_resolve_karma(bond_type, resolution_type)
    if not is_valid:
        return {"success": False, "error": "了结方式无效", "reasons": reasons}

    # 3. 计算了结业力变化
    karma_change = get_resolve_karma_value(bond_type, resolution_type)

    # 4. 更新玩家业力
    player_data = storage.couch_get_player(uid)
    if not player_data:
        return {"success": False, "error": f"玩家数据不存在: {uid}"}

    old_karma = player_data.get("karma", 0)
    new_karma = old_karma + karma_change
    level_info = get_karma_level(new_karma)

    player_data["karma"] = new_karma
    player_data["karma_level"] = level_info["level"]
    player_data["karma_title"] = level_info["title"]
    player_data.pop("_id", None)
    player_data.pop("_rev", None)

    try:
        storage.couch_save_player(uid, player_data)
    except Exception as e:
        error_log(f"更新玩家业力失败: uid={uid}, 错误: {e}")
        return {"success": False, "error": f"更新玩家业力失败: {e}"}

    # 5. 记录了结事件
    resolve_record = {
        "uid": uid,
        "karma_type": bond_type,
        "target_id": target_id,
        "target_name": target_bond.get("target_name", ""),
        "description": f"了结因果：{target_bond.get('bond_desc', '')}，方式：{resolution_type}",
        "karma_value": karma_change,
        "karma_before": old_karma,
        "karma_after": new_karma,
        "resolved": True,
        "resolution_type": resolution_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        storage.couch_save_karma_record(uid, resolve_record)
    except Exception as e:
        error_log(f"保存了结记录失败: uid={uid}, 错误: {e}")

    # 6. 保存记忆
    try:
        memory_summary = f"了结因果：与{target_bond.get('target_name', target_id)}的{bond_type}关系已了结（{resolution_type}），业力{'+'if karma_change>=0 else ''}{karma_change}"
        storage.save_memory(f"user_{uid}", memory_summary)
    except Exception as e:
        error_log(f"保存了结记忆失败: uid={uid}, 错误: {e}")

    info_log(f"因果了结: uid={uid}, target={target_id}, type={resolution_type}, karma_change={karma_change}")

    return {
        "success": True,
        "uid": uid,
        "target_id": target_id,
        "target_name": target_bond.get("target_name", ""),
        "bond_type": bond_type,
        "resolution_type": resolution_type,
        "karma_change": karma_change,
        "karma_before": old_karma,
        "karma_after": new_karma,
        "karma_level": level_info["level"],
        "karma_title": level_info["title"],
        "message": f"因果已了结：与{target_bond.get('target_name', '')}的{bond_type}关系，方式{resolution_type}，业力{'+'if karma_change>=0 else ''}{karma_change}",
    }
