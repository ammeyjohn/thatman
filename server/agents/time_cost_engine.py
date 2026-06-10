"""
TimeCostEngine - 耗时计算引擎

后端自动计算动作的实际耗时，根据玩家功法、丹药buff、法宝、修为境界、环境灵气等
计算耗时缩减或增加。

修正上限：总修正不超过基础耗时的 ±70%
"""

import random
from typing import Dict, Any, List, Optional

from gm_logger import debug_log, info_log, warn_log, error_log
from action_definition_manager import ActionDefinitionManager, get_action_definition_manager


# 境界等级映射（用于计算修为差距）
_REALM_LEVELS = {
    "引气入体": 1,
    "炼气期": 2,
    "筑基期": 3,
    "金丹期": 4,
    "元婴期": 5,
    "化神期": 6,
    "炼虚期": 7,
    "合体期": 8,
    "大乘期": 9,
    "渡劫期": 10,
}


def _get_realm_level(realm: str) -> int:
    """获取境界等级数值"""
    for key, level in _REALM_LEVELS.items():
        if key in realm:
            return level
    return 1


class TimeCostEngine:
    """耗时计算引擎"""

    # 修正上限
    MAX_MODIFIER_FACTOR = 0.70

    def __init__(self, action_def_manager: ActionDefinitionManager = None):
        """
        初始化耗时计算引擎

        Args:
            action_def_manager: 动作定义管理器实例
        """
        self._action_def_manager = action_def_manager or get_action_definition_manager()

    def calculate(
        self,
        action_id: str,
        player_data: Dict[str, Any],
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        计算动作的实际耗时

        Args:
            action_id: 动作类型ID
            player_data: 玩家数据字典
            context: 上下文数据（环境灵气、天气、地点buff等）

        Returns:
            {
                "base_time": 180,           # 基础耗时（分钟）
                "final_time": 135,          # 最终耗时（分钟）
                "modifiers": [             # 所有生效的修正项
                    {"source": "...", "factor": -0.15, "minutes": -27},
                ],
                "total_factor": -0.25,      # 总修正比例
            }
        """
        context = context or {}

        # 1. 获取动作定义
        if self._action_def_manager:
            definition = self._action_def_manager.get_action_definition(action_id)
        else:
            definition = None

        if not definition:
            # 未知动作类型，返回默认耗时 0
            warn_log(f"未知动作类型: {action_id}，无法计算耗时")
            return {
                "base_time": 0,
                "final_time": 0,
                "modifiers": [],
                "total_factor": 0.0,
            }

        # 2. 计算基础耗时（在 min~max 范围内取随机值，或取中间值）
        base_time_cost = definition.get("base_time_cost", {"min": 0, "max": 0})
        min_time = base_time_cost.get("min", 0)
        max_time = base_time_cost.get("max", 0)

        if min_time == 0 and max_time == 0:
            # 即时行为
            return {
                "base_time": 0,
                "final_time": 0,
                "modifiers": [],
                "total_factor": 0.0,
            }

        base_time = random.randint(min_time, max_time)

        # 3. 收集所有修正因子
        modifiers: List[Dict[str, Any]] = []
        time_modifiers = definition.get("time_modifiers", {})

        # 3.1 功法修正
        if time_modifiers.get("realm_factor", False):
            technique_mod = self._calc_technique_modifier(player_data)
            if technique_mod:
                modifiers.append(technique_mod)

        # 3.2 丹药buff修正
        buff_mod = self._calc_buff_modifier(player_data)
        if buff_mod:
            modifiers.append(buff_mod)

        # 3.3 法宝修正
        equip_mod = self._calc_equipment_modifier(player_data)
        if equip_mod:
            modifiers.append(equip_mod)

        # 3.4 修为境界修正
        if time_modifiers.get("realm_factor", False):
            realm_mod = self._calc_realm_modifier(player_data, definition)
            if realm_mod:
                modifiers.append(realm_mod)

        # 3.5 环境灵气修正（仅修炼类）
        if time_modifiers.get("spirit_concentration_factor", False):
            spirit_mod = self._calc_spirit_concentration_modifier(context)
            if spirit_mod:
                modifiers.append(spirit_mod)

        # 3.6 天气修正（仅赶路/探索类）
        if time_modifiers.get("weather_factor", False):
            weather_mod = self._calc_weather_modifier(context)
            if weather_mod:
                modifiers.append(weather_mod)

        # 3.7 地点buff修正
        location_mod = self._calc_location_buff_modifier(context)
        if location_mod:
            modifiers.append(location_mod)

        # 4. 计算总修正（限制在 ±70%）
        total_factor = sum(m["factor"] for m in modifiers)
        total_factor = max(-self.MAX_MODIFIER_FACTOR, min(self.MAX_MODIFIER_FACTOR, total_factor))

        # 5. 计算最终耗时
        final_time = int(base_time * (1 + total_factor))
        final_time = max(1, final_time)  # 至少1分钟

        # 6. 重新计算各修正项对应的分钟数（基于 base_time）
        for m in modifiers:
            m["minutes"] = round(base_time * m["factor"])

        result = {
            "base_time": base_time,
            "final_time": final_time,
            "modifiers": modifiers,
            "total_factor": round(total_factor, 4),
        }

        debug_log(
            f"耗时计算: action={action_id}, base={base_time}, final={final_time}, "
            f"factor={total_factor:.2%}, modifiers={len(modifiers)}"
        )

        return result

    def _calc_technique_modifier(self, player_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算功法对耗时的修正"""
        techniques = player_data.get("techniques", [])
        if not techniques:
            return None

        best_factor = 0.0
        best_source = ""

        for tech in techniques:
            if not isinstance(tech, dict):
                continue
            effect = tech.get("effect", {})
            if not isinstance(effect, dict):
                continue
            time_reduction = effect.get("time_reduction", 0)
            if time_reduction and time_reduction > 0:
                factor = -time_reduction
                if factor < best_factor:  # 更负 = 更好的缩减
                    best_factor = factor
                    best_source = tech.get("name", "未知功法")

        if best_factor < 0:
            return {
                "source": f"功法《{best_source}》",
                "factor": best_factor,
                "minutes": 0,  # 会在主函数中重新计算
            }
        return None

    def _calc_buff_modifier(self, player_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算丹药buff对耗时的修正"""
        buffs = player_data.get("active_buffs", [])
        if not buffs:
            return None

        best_factor = 0.0
        best_source = ""

        for buff in buffs:
            if not isinstance(buff, dict):
                continue
            effect = buff.get("effect", {})
            if not isinstance(effect, dict):
                continue
            time_reduction = effect.get("time_reduction", 0)
            if time_reduction and time_reduction > 0:
                factor = -time_reduction
                if factor < best_factor:
                    best_factor = factor
                    best_source = buff.get("name", "未知丹药")

        if best_factor < 0:
            return {
                "source": f"丹药效果【{best_source}】",
                "factor": best_factor,
                "minutes": 0,
            }
        return None

    def _calc_equipment_modifier(self, player_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算法宝对耗时的修正"""
        equipment = player_data.get("equipment", [])
        if not equipment:
            return None

        best_factor = 0.0
        best_source = ""

        for equip in equipment:
            if not isinstance(equip, dict):
                continue
            effect = equip.get("effect", {})
            if not isinstance(effect, dict):
                continue
            time_reduction = effect.get("time_reduction", 0)
            if time_reduction and time_reduction > 0:
                factor = -time_reduction
                if factor < best_factor:
                    best_factor = factor
                    best_source = equip.get("name", "未知法宝")

        if best_factor < 0:
            return {
                "source": f"法宝【{best_source}】",
                "factor": best_factor,
                "minutes": 0,
            }
        return None

    def _calc_realm_modifier(
        self, player_data: Dict[str, Any], definition: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """计算修为境界对耗时的修正"""
        realm = player_data.get("realm", "")
        level = player_data.get("level", 0)
        action_difficulty = definition.get("difficulty", 1)

        if not realm:
            return None

        realm_level = _get_realm_level(realm)
        # 境界等级 + 阶段等级（初期/中期/后期/巅峰）粗略估计
        stage_bonus = 0
        realm_stage = player_data.get("realm_stage", "")
        if "巅峰" in realm_stage:
            stage_bonus = 0.8
        elif "后期" in realm_stage:
            stage_bonus = 0.6
        elif "中期" in realm_stage:
            stage_bonus = 0.3
        elif "初期" in realm_stage:
            stage_bonus = 0.0

        total_realm_score = realm_level + stage_bonus + (level / 100)

        # 差距计算
        diff = total_realm_score - action_difficulty

        if diff >= 3:
            factor = -0.30
            desc = "修为远超行为难度"
        elif diff >= 1:
            factor = -0.15
            desc = "修为高于行为难度"
        elif diff >= -1:
            factor = 0.0
            desc = "修为与行为难度相当"
        elif diff >= -3:
            factor = 0.20
            desc = "修为低于行为难度"
        else:
            factor = 0.50
            desc = "修为远低于行为难度"

        if factor == 0.0:
            return None

        return {
            "source": f"修为境界（{realm}{realm_stage}）{desc}",
            "factor": factor,
            "minutes": 0,
        }

    def _calc_spirit_concentration_modifier(
        self, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """计算环境灵气浓度对耗时的修正"""
        spirit_concentration = context.get("spirit_concentration", "")
        if not spirit_concentration:
            # 尝试从天气服务获取
            spirit_tide = context.get("spirit_tide", False)
            spirit_tide_intensity = context.get("spirit_tide_intensity", 0)
            if spirit_tide and spirit_tide_intensity > 0:
                factor = -0.10 * spirit_tide_intensity
                return {
                    "source": f"灵潮涌动（强度{spirit_tide_intensity}）",
                    "factor": max(-0.50, factor),
                    "minutes": 0,
                }
            return None

        # 根据灵气浓度描述判断
        concentration_map = {
            "浓郁": -0.30,
            "浓厚": -0.25,
            "充沛": -0.20,
            "中等": -0.10,
            "稀薄": 0.10,
            "枯竭": 0.30,
        }

        factor = 0.0
        source = ""
        for key, val in concentration_map.items():
            if key in spirit_concentration:
                factor = val
                source = f"灵气浓度{key}"
                break

        if factor == 0.0:
            return None

        return {
            "source": source,
            "factor": factor,
            "minutes": 0,
        }

    def _calc_weather_modifier(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算天气对耗时的修正"""
        weather = context.get("weather", "")
        if not weather:
            return None

        weather_map = {
            "暴雨": 0.30,
            "大雪": 0.30,
            "雷雨": 0.25,
            "狂风": 0.20,
            "小雨": 0.10,
            "小雪": 0.10,
            "雾": 0.15,
            "晴朗": -0.05,
        }

        factor = 0.0
        source = ""
        for key, val in weather_map.items():
            if key in weather:
                factor = val
                source = f"天气：{key}"
                break

        if factor == 0.0:
            return None

        return {
            "source": source,
            "factor": factor,
            "minutes": 0,
        }

    def _calc_location_buff_modifier(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """计算地点buff对耗时的修正"""
        location_buffs = context.get("location_buffs", [])
        if not location_buffs:
            return None

        best_factor = 0.0
        best_source = ""

        for buff in location_buffs:
            if not isinstance(buff, dict):
                continue
            buff_type = buff.get("type", "")
            buff_value = buff.get("value", 0)

            if buff_type in ("spirit_array", "spirit_vein", "聚灵阵", "灵脉"):
                factor = -buff_value
                if factor < best_factor:
                    best_factor = factor
                    best_source = buff.get("name", buff_type)

        if best_factor < 0:
            return {
                "source": f"地点加持【{best_source}】",
                "factor": best_factor,
                "minutes": 0,
            }
        return None


# ───────────────────────────────────────────────
# 全局单例引用
# ───────────────────────────────────────────────

_time_cost_engine_instance: Optional["TimeCostEngine"] = None


def set_time_cost_engine(instance: "TimeCostEngine"):
    """设置全局 TimeCostEngine 实例"""
    global _time_cost_engine_instance
    _time_cost_engine_instance = instance


def get_time_cost_engine() -> Optional["TimeCostEngine"]:
    """获取全局 TimeCostEngine 实例"""
    return _time_cost_engine_instance
