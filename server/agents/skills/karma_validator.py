"""
Karma Validator - 业力变更验证器

验证业力变更的合理性，防止不合理的业力值修改。
规则：
- 单次业力变化不超过 ±50
- 因果记录必须有对应的 target_id
- 同一因果事件不可重复记录
"""

import logging
from typing import Dict, Any, Tuple, List

from gm_logger import debug_log, info_log, warn_log, error_log

logger = logging.getLogger(__name__)

# 单次业力变化最大绝对值
MAX_KARMA_CHANGE = 50

# 有效的因果类型
VALID_KARMA_TYPES = {"grace", "enmity", "fellowship", "friendship", "contract", "neutral"}

# 因果类型对应业力值范围
KARMA_TYPE_RANGES = {
    "grace": (10, 50),       # 恩情：+10~+50
    "enmity": (-50, -10),    # 仇怨：-50~-10
    "fellowship": (-15, 15), # 同门：-15~+15
    "friendship": (-40, 30), # 知己：-40~+30
    "contract": (-30, 20),   # 契约：-30~+20
    "neutral": (0, 0),       # 陌路：0
}

# 善恶等级定义
KARMA_LEVELS = [
    {"level": 1, "min": -999999, "max": -200, "title": "罪孽深重"},
    {"level": 2, "min": -199, "max": -100, "title": "业障缠身"},
    {"level": 3, "min": -99, "max": 99, "title": "因果清净"},
    {"level": 4, "min": 100, "max": 199, "title": "善行卓著"},
    {"level": 5, "min": 200, "max": 999999, "title": "功德圆满"},
]


def get_karma_level(karma_value: int) -> Dict[str, Any]:
    """
    根据业力值计算善恶等级

    Args:
        karma_value: 业力值

    Returns:
        包含 level 和 title 的字典
    """
    for kl in KARMA_LEVELS:
        if kl["min"] <= karma_value <= kl["max"]:
            return {"level": kl["level"], "title": kl["title"]}
    # 默认返回等级3
    return {"level": 3, "title": "因果清净"}


def validate_karma_change(
    old_karma: int,
    karma_value: int,
    karma_type: str,
    target_id: str,
) -> Tuple[bool, List[str]]:
    """
    验证业力变更是否合理

    Args:
        old_karma: 变更前的业力值
        karma_value: 本次业力变化值（正=善，负=恶）
        karma_type: 因果类型
        target_id: 目标实体ID

    Returns:
        (is_valid, reasons) 元组
        is_valid: 是否通过验证
        reasons: 拒绝原因列表（验证通过时为空）
    """
    reasons = []

    # 1. 验证因果类型
    if karma_type not in VALID_KARMA_TYPES:
        reasons.append(f"无效的因果类型: {karma_type}，有效类型: {', '.join(VALID_KARMA_TYPES)}")

    # 2. 验证目标ID
    if not target_id or not target_id.strip():
        reasons.append("因果记录必须有对应的 target_id")

    # 3. 验证单次业力变化范围
    if abs(karma_value) > MAX_KARMA_CHANGE:
        reasons.append(f"单次业力变化 {karma_value} 超出最大值 ±{MAX_KARMA_CHANGE}")

    # 4. 验证因果类型与业力值方向是否匹配
    if karma_type in KARMA_TYPE_RANGES:
        min_val, max_val = KARMA_TYPE_RANGES[karma_type]
        if karma_value < min_val or karma_value > max_val:
            reasons.append(
                f"因果类型 '{karma_type}' 的业力值范围应为 {min_val}~{max_val}，"
                f"当前值 {karma_value} 超出范围"
            )

    # 5. 验证业力值类型
    if not isinstance(karma_value, (int, float)):
        reasons.append(f"业力值必须为数字，当前类型: {type(karma_value).__name__}")

    is_valid = len(reasons) == 0
    if not is_valid:
        warn_log(f"业力变更验证失败: karma_value={karma_value}, karma_type={karma_type}, reasons={reasons}")
    else:
        debug_log(f"业力变更验证通过: karma_value={karma_value}, karma_type={karma_type}")

    return is_valid, reasons


def validate_resolve_karma(
    bond_type: str,
    resolution_type: str,
) -> Tuple[bool, List[str]]:
    """
    验证因果了结是否合理

    Args:
        bond_type: 因果羁绊类型
        resolution_type: 了结方式

    Returns:
        (is_valid, reasons) 元组
    """
    reasons = []

    valid_resolutions = {
        "grace": ["repay", "betray"],        # 恩情：报恩/忘恩
        "enmity": ["revenge", "forgive"],     # 仇怨：复仇/宽恕
        "fellowship": ["part", "reunite"],    # 同门：分别/重聚
        "friendship": ["betray", "deepen"],   # 知己：背叛/加深
        "contract": ["fulfill", "break"],     # 契约：履约/违约
    }

    if bond_type not in valid_resolutions:
        reasons.append(f"无效的因果羁绊类型: {bond_type}")
    elif resolution_type not in valid_resolutions.get(bond_type, []):
        reasons.append(
            f"因果类型 '{bond_type}' 不支持了结方式 '{resolution_type}'，"
            f"有效方式: {', '.join(valid_resolutions[bond_type])}"
        )

    is_valid = len(reasons) == 0
    return is_valid, reasons


def get_resolve_karma_value(bond_type: str, resolution_type: str) -> int:
    """
    根据因果了结方式计算业力变化

    Args:
        bond_type: 因果羁绊类型
        resolution_type: 了结方式

    Returns:
        业力变化值
    """
    # 了结因果的业力变化规则
    resolve_karma_map = {
        ("grace", "repay"): 15,       # 报恩：+15
        ("grace", "betray"): -30,     # 忘恩负义：-30
        ("enmity", "revenge"): 10,    # 复仇（了结仇怨）：+10（了结因果本身是善）
        ("enmity", "forgive"): 25,    # 宽恕：+25（大善）
        ("fellowship", "part"): 0,    # 分别：0
        ("fellowship", "reunite"): 5, # 重聚：+5
        ("friendship", "betray"): -35,# 背叛知己：-35
        ("friendship", "deepen"): 10, # 加深友谊：+10
        ("contract", "fulfill"): 10,  # 履约：+10
        ("contract", "break"): -20,   # 违约：-20
    }
    return resolve_karma_map.get((bond_type, resolution_type), 0)
