"""
Character Status Validator - 角色状态验证模块

对角色状态更新进行合法性校验，防止不合理的状态变更。
验证规则基于 level_config.md 中的境界体系和属性成长规则。
"""

import logging
from typing import Dict, Any, List, Tuple, Optional

from gm_logger import debug_log, info_log, warn_log, error_log

logger = logging.getLogger(__name__)

# ============================================================
# 境界与阶段顺序定义
# ============================================================

# 人界境界顺序
HUMAN_REALMS = [
    "引气入体", "炼气期", "筑基期", "金丹期", "元婴期",
    "化神期", "炼虚期", "合体期", "大乘期", "渡劫期",
]

# 灵界境界顺序
SPIRIT_REALMS = [
    "地仙", "天仙", "金仙", "太乙金仙", "大罗金仙",
    "罗天上仙", "仙君", "仙帝",
]

# 仙界境界顺序
IMMORTAL_REALMS = [
    "凡仙", "灵仙", "真仙", "玄仙", "金仙", "太乙仙",
    "大罗仙", "仙王", "仙帝", "道祖",
]

# 完整境界顺序
REALM_ORDER = HUMAN_REALMS + SPIRIT_REALMS + IMMORTAL_REALMS

# 境界阶段顺序
REALM_STAGE_ORDER = ["初期", "中期", "后期", "巅峰", "圆满"]

# 需要验证的核心属性字段
CORE_STATUS_FIELDS = {
    "realm", "realm_stage", "level",
    "health", "max_health", "mana", "max_mana", "spirit", "max_spirit",
    "equipment", "inventory",
}

# ============================================================
# 验证配置
# ============================================================

# 单次 level 最大增幅
MAX_LEVEL_INCREMENT = 10

# 单次 max_health/max_mana/max_spirit 最大变化比例（相对旧值）
MAX_STAT_CHANGE_RATIO = 0.5

# 境界突破时 max 属性最大变化比例（放宽限制）
BREAKTHROUGH_MAX_STAT_CHANGE_RATIO = 2.0

# 单次装备增减上限
MAX_EQUIPMENT_CHANGE = 3

# 单次背包物品种类增减上限
MAX_INVENTORY_CHANGE = 5


class CharacterStatusValidator:
    """角色状态验证器"""

    @staticmethod
    def validate(old_status: Dict[str, Any], updates: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        验证角色状态更新是否合法

        Args:
            old_status: 当前角色状态（旧值）
            updates: 待更新的字段（新值）

        Returns:
            (is_valid, reasons) - 是否合法，以及违规原因列表
        """
        reasons = []

        # 检查是否有境界变更
        realm_changed = "realm" in updates and updates["realm"] != old_status.get("realm", "")

        # 逐字段验证
        for field, new_value in updates.items():
            if field not in CORE_STATUS_FIELDS:
                continue

            old_value = old_status.get(field)

            field_reasons = CharacterStatusValidator._validate_field(
                field, old_value, new_value, old_status, updates, realm_changed
            )
            reasons.extend(field_reasons)

        is_valid = len(reasons) == 0
        if not is_valid:
            warn_log(f"角色状态验证失败: reasons={reasons}")
        else:
            debug_log("角色状态验证通过")

        return is_valid, reasons

    @staticmethod
    def _validate_field(
        field: str,
        old_value: Any,
        new_value: Any,
        old_status: Dict[str, Any],
        updates: Dict[str, Any],
        realm_changed: bool,
    ) -> List[str]:
        """验证单个字段"""
        reasons = []

        if field == "realm":
            reasons = CharacterStatusValidator._validate_realm(old_value, new_value)
        elif field == "realm_stage":
            reasons = CharacterStatusValidator._validate_realm_stage(
                old_value, new_value, realm_changed, old_status, updates
            )
        elif field == "level":
            reasons = CharacterStatusValidator._validate_level(old_value, new_value)
        elif field in ("health", "mana", "spirit"):
            max_field = f"max_{field}"
            max_value = updates.get(max_field, old_status.get(max_field, 0))
            reasons = CharacterStatusValidator._validate_current_stat(
                field, old_value, new_value, max_value
            )
        elif field in ("max_health", "max_mana", "max_spirit"):
            reasons = CharacterStatusValidator._validate_max_stat(
                field, old_value, new_value, realm_changed
            )
        elif field == "equipment":
            reasons = CharacterStatusValidator._validate_equipment(old_value, new_value)
        elif field == "inventory":
            reasons = CharacterStatusValidator._validate_inventory(old_value, new_value)

        return reasons

    @staticmethod
    def _validate_realm(old_realm: Optional[str], new_realm: str) -> List[str]:
        """
        验证境界变更

        规则：新境界必须是旧境界的下一个，或与旧境界相同（不变）
        """
        if not new_realm:
            return ["境界值不能为空"]

        # 旧境界为空（首次设置），允许
        if not old_realm:
            debug_log(f"首次设置境界: {new_realm}")
            return []

        if new_realm == old_realm:
            return []

        # 检查新境界是否在合法顺序中
        if new_realm not in REALM_ORDER:
            return [f"未知境界: {new_realm}，合法境界列表: {REALM_ORDER}"]

        if old_realm not in REALM_ORDER:
            warn_log(f"旧境界不在已知列表中: {old_realm}，跳过境界顺序验证")
            return []

        old_idx = REALM_ORDER.index(old_realm)
        new_idx = REALM_ORDER.index(new_realm)

        # 只允许升一级
        if new_idx != old_idx + 1:
            next_realm = REALM_ORDER[old_idx + 1] if old_idx + 1 < len(REALM_ORDER) else "已至最高境界"
            return [
                f"境界跳跃不合法: 不能从「{old_realm}」直接变为「{new_realm}」，"
                f"只能升一级至「{next_realm}」"
            ]

        return []

    @staticmethod
    def _validate_realm_stage(
        old_stage: Optional[str],
        new_stage: str,
        realm_changed: bool,
        old_status: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> List[str]:
        """
        验证境界阶段变更

        规则：
        - 境界突破时（realm 变化），阶段应重置为"初期"
        - 同境界内，阶段只能升一级或不变
        """
        if not new_stage:
            return ["境界阶段值不能为空"]

        if new_stage not in REALM_STAGE_ORDER:
            return [f"未知境界阶段: {new_stage}，合法阶段: {REALM_STAGE_ORDER}"]

        # 境界突破时，阶段应重置为"初期"
        if realm_changed:
            if new_stage != "初期":
                return [
                    f"境界突破时，阶段应重置为「初期」，当前设置为「{new_stage}」"
                ]
            return []

        # 同境界内阶段变更
        if not old_stage:
            debug_log(f"首次设置境界阶段: {new_stage}")
            return []

        if new_stage == old_stage:
            return []

        if old_stage not in REALM_STAGE_ORDER:
            warn_log(f"旧阶段不在已知列表中: {old_stage}，跳过阶段顺序验证")
            return []

        old_idx = REALM_STAGE_ORDER.index(old_stage)
        new_idx = REALM_STAGE_ORDER.index(new_stage)

        # 阶段只能升一级（阶段满后应突破境界）
        if new_idx != old_idx + 1:
            next_stage = REALM_STAGE_ORDER[old_idx + 1] if old_idx + 1 < len(REALM_STAGE_ORDER) else "应突破境界"
            return [
                f"境界阶段跳跃不合法: 不能从「{old_stage}」直接变为「{new_stage}」，"
                f"只能升一级至「{next_stage}」"
            ]

        return []

    @staticmethod
    def _validate_level(old_level: Optional[int], new_level: int) -> List[str]:
        """
        验证等级变更

        规则：等级不可减少，单次增幅不超过 MAX_LEVEL_INCREMENT
        """
        try:
            new_level = int(new_level)
        except (TypeError, ValueError):
            return [f"等级值必须为数字: {new_level}"]

        if new_level < 0:
            return [f"等级不能为负数: {new_level}"]

        if old_level is None:
            debug_log(f"首次设置等级: {new_level}")
            return []

        try:
            old_level = int(old_level)
        except (TypeError, ValueError):
            warn_log(f"旧等级值异常: {old_level}，跳过等级验证")
            return []

        if new_level < old_level:
            return [f"等级不可减少: {old_level} → {new_level}"]

        increment = new_level - old_level
        if increment > MAX_LEVEL_INCREMENT:
            return [
                f"等级增幅过大: {old_level} → {new_level}（增幅 {increment}），"
                f"单次最大增幅为 {MAX_LEVEL_INCREMENT}"
            ]

        return []

    @staticmethod
    def _validate_current_stat(
        field: str,
        old_value: Optional[int],
        new_value: int,
        max_value: int,
    ) -> List[str]:
        """
        验证当前属性值（health/mana/spirit）

        规则：0 ≤ 新值 ≤ max 值
        """
        field_names = {"health": "生命值", "mana": "法力值", "spirit": "神识值"}
        field_name = field_names.get(field, field)

        try:
            new_value = int(new_value)
        except (TypeError, ValueError):
            return [f"{field_name}必须为数字: {new_value}"]

        try:
            max_value = int(max_value) if max_value is not None else 0
        except (TypeError, ValueError):
            max_value = 0

        if new_value < 0:
            return [f"{field_name}不能为负数: {new_value}"]

        if max_value > 0 and new_value > max_value:
            return [
                f"{field_name}不能超过上限: {new_value} > {max_value}（max_{field}）"
            ]

        return []

    @staticmethod
    def _validate_max_stat(
        field: str,
        old_value: Optional[int],
        new_value: int,
        realm_changed: bool,
    ) -> List[str]:
        """
        验证最大属性值（max_health/max_mana/max_spirit）

        规则：
        - 新值必须 > 0
        - 普通变更：变化幅度不超过旧值的 MAX_STAT_CHANGE_RATIO
        - 境界突破：放宽至 BREAKTHROUGH_MAX_STAT_CHANGE_RATIO
        """
        field_names = {
            "max_health": "生命上限",
            "max_mana": "法力上限",
            "max_spirit": "神识上限",
        }
        field_name = field_names.get(field, field)

        try:
            new_value = int(new_value)
        except (TypeError, ValueError):
            return [f"{field_name}必须为数字: {new_value}"]

        if new_value <= 0:
            return [f"{field_name}必须大于0: {new_value}"]

        if old_value is None:
            debug_log(f"首次设置{field_name}: {new_value}")
            return []

        try:
            old_value = int(old_value)
        except (TypeError, ValueError):
            warn_log(f"旧{field_name}值异常: {old_value}，跳过验证")
            return []

        if old_value <= 0:
            return []

        # 计算变化比例
        change_ratio = abs(new_value - old_value) / old_value

        # 境界突破时放宽限制
        max_ratio = BREAKTHROUGH_MAX_STAT_CHANGE_RATIO if realm_changed else MAX_STAT_CHANGE_RATIO

        if change_ratio > max_ratio:
            max_allowed = int(old_value * (1 + max_ratio))
            min_allowed = int(old_value * (1 - max_ratio))
            return [
                f"{field_name}变化幅度过大: {old_value} → {new_value}（变化 {change_ratio:.0%}），"
                f"{'境界突破时最大' if realm_changed else '普通变更最大'}"
                f"允许变化 {max_ratio:.0%}，合法范围 [{min_allowed}, {max_allowed}]"
            ]

        return []

    @staticmethod
    def _validate_equipment(old_equipment: Optional[list], new_equipment: list) -> List[str]:
        """
        验证装备变更

        规则：单次增减装备数量不超过 MAX_EQUIPMENT_CHANGE
        """
        if not isinstance(new_equipment, list):
            return [f"装备数据必须为数组: {type(new_equipment)}"]

        if old_equipment is None:
            debug_log(f"首次设置装备: {len(new_equipment)}件")
            return []

        if not isinstance(old_equipment, list):
            warn_log("旧装备数据格式异常，跳过装备数量验证")
            return []

        change_count = abs(len(new_equipment) - len(old_equipment))
        if change_count > MAX_EQUIPMENT_CHANGE:
            return [
                f"装备变更数量过大: {len(old_equipment)} → {len(new_equipment)}（变化 {change_count}件），"
                f"单次最多变更 {MAX_EQUIPMENT_CHANGE} 件"
            ]

        return []

    @staticmethod
    def _validate_inventory(old_inventory: Optional[list], new_inventory: list) -> List[str]:
        """
        验证背包变更

        规则：单次增减物品种类不超过 MAX_INVENTORY_CHANGE
        """
        if not isinstance(new_inventory, list):
            return [f"背包数据必须为数组: {type(new_inventory)}"]

        if old_inventory is None:
            debug_log(f"首次设置背包: {len(new_inventory)}种物品")
            return []

        if not isinstance(old_inventory, list):
            warn_log("旧背包数据格式异常，跳过背包数量验证")
            return []

        change_count = abs(len(new_inventory) - len(old_inventory))
        if change_count > MAX_INVENTORY_CHANGE:
            return [
                f"背包物品种类变更过大: {len(old_inventory)} → {len(new_inventory)}（变化 {change_count}种），"
                f"单次最多变更 {MAX_INVENTORY_CHANGE} 种"
            ]

        return []

    @staticmethod
    def sanitize_updates(old_status: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        清洗更新数据：对可截断的字段进行截断处理，移除不合法的拒绝型字段

        对于拒绝型字段（realm、realm_stage、level、max_*、equipment、inventory）：
        验证失败则移除该字段

        对于截断型字段（health、mana、spirit）：
        超出范围时截断到合法范围

        Args:
            old_status: 当前角色状态
            updates: 待更新的字段

        Returns:
            清洗后的更新数据
        """
        sanitized = dict(updates)
        realm_changed = "realm" in sanitized and sanitized["realm"] != old_status.get("realm", "")

        fields_to_remove = []

        for field, new_value in list(sanitized.items()):
            if field not in CORE_STATUS_FIELDS:
                continue

            if field in ("health", "mana", "spirit"):
                # 截断型字段
                max_field = f"max_{field}"
                max_value = sanitized.get(max_field, old_status.get(max_field, 0)) if max_field in sanitized else old_status.get(max_field, 0)
                try:
                    new_value = int(new_value)
                    max_value = int(max_value) if max_value else 0
                    if new_value < 0:
                        sanitized[field] = 0
                        warn_log(f"截断 {field}: {new_value} → 0")
                    elif max_value > 0 and new_value > max_value:
                        sanitized[field] = max_value
                        warn_log(f"截断 {field}: {new_value} → {max_value}")
                except (TypeError, ValueError):
                    fields_to_remove.append(field)
            else:
                # 拒绝型字段：验证失败则移除
                old_value = old_status.get(field)
                reasons = CharacterStatusValidator._validate_field(
                    field, old_value, new_value, old_status, sanitized, realm_changed
                )
                if reasons:
                    fields_to_remove.append(field)
                    warn_log(f"移除不合法字段 {field}: {reasons}")

        for field in fields_to_remove:
            del sanitized[field]

        return sanitized
