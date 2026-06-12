"""
State Engine - 自动状态引擎

在每次对话回复后、保存数据前执行，根据时间推进和剧情事件
自动计算角色状态变化，包括自然恢复、疲劳累积、Buff过期、
伤势恢复、心神变化、环境效果等。
"""

import logging
import math
from typing import Dict, Any, Optional, List

from gm_logger import debug_log, info_log, warn_log, error_log

logger = logging.getLogger(__name__)

# ============================================================
# 自然恢复配置
# ============================================================

# 每游戏小时恢复比例（相对 max 值）
HEALTH_RECOVERY_RATE = 0.02      # 2%/小时
MANA_RECOVERY_RATE = 0.05        # 5%/小时
SPIRIT_RECOVERY_RATE = 0.03      # 3%/小时

# 疲劳恢复（每游戏小时减少）
FATIGUE_RECOVERY_REST = 5        # 休息时
FATIGUE_RECOVERY_SLEEP = 15      # 睡眠时

# 心神清明度恢复（每游戏小时增加）
CLARITY_RECOVERY_NORMAL = 3      # 平静环境
CLARITY_RECOVERY_MEDITATE = 5    # 修炼时

# ============================================================
# 疲劳累积配置（每游戏小时）
# ============================================================

FATIGUE_ACCUMULATION = {
    "chat": 1,
    "check_status": 0,
    "view_inventory": 0,
    "view_equipment": 0,
    "meditate_basic": 3,
    "meditate_depth": 4,
    "breakthrough": 15,
    "move_region": 4,
    "move_cross_region": 6,
    "gather": 4,
    "craft_pill": 5,
    "craft_equip": 5,
    "combat": 8,
    "rest": -5,
    "custom": 3,
}

# ============================================================
# 疲劳等级阈值
# ============================================================

FATIGUE_LEVELS = [
    (0, "refreshed"),
    (11, "normal"),
    (31, "tired"),
    (61, "exhausted"),
    (86, "collapsed"),
]

# ============================================================
# 心神情绪映射
# ============================================================

MOOD_MAP = {
    "calm": "平静",
    "focused": "专注",
    "anxious": "焦虑",
    "agitated": "烦躁",
    "enlightened": "顿悟",
}

VALID_MOODS = {"calm", "focused", "anxious", "agitated", "enlightened"}


class StateEngine:
    """自动状态引擎"""

    def process(
        self,
        uid: str,
        old_state: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        主处理函数：根据时间推进和上下文计算状态变化

        Args:
            uid: 玩家唯一标识
            old_state: 当前角色状态
            context: 上下文信息，包含：
                - time_cost: 本次行为消耗的游戏分钟数
                - action_id: 本次行为类型
                - weather: 天气信息
                - spirit_tide: 是否灵潮
                - spirit_tide_intensity: 灵潮强度
                - is_combat: 是否战斗中
                - is_resting: 是否休息中

        Returns:
            状态变更字典（仅包含需要更新的字段）
        """
        time_cost = context.get("time_cost", 0)
        if time_cost <= 0:
            debug_log(f"[StateEngine] 无时间消耗，跳过状态引擎: uid={uid}")
            return {}

        time_hours = time_cost / 60.0
        action_id = context.get("action_id", "chat")

        changes: Dict[str, Any] = {}

        # 1. 自然恢复
        recovery = self._calc_natural_recovery(old_state, time_hours, context)
        changes.update(recovery)

        # 2. 疲劳计算
        fatigue = self._calc_fatigue(old_state, time_hours, action_id, context)
        if fatigue:
            changes["fatigue"] = fatigue

        # 3. Buff 过期
        buffs = self._process_buff_expiry(old_state, time_cost)
        if buffs is not None:
            changes["active_buffs"] = buffs

        # 4. 伤势恢复
        injuries = self._process_injury_recovery(old_state, time_cost)
        if injuries is not None:
            changes["injuries"] = injuries

        # 5. 心神变化
        mental = self._calc_mental_state_changes(old_state, time_hours, context)
        if mental:
            changes["mental_state"] = mental

        # 6. 环境效果
        env = self._calc_environment_effects(old_state, time_hours, context)
        changes.update(env)

        if changes:
            info_log(
                f"[StateEngine] 状态引擎计算完成: uid={uid}, "
                f"变更字段={list(changes.keys())}, "
                f"time_cost={time_cost}分钟, action={action_id}"
            )
        else:
            debug_log(f"[StateEngine] 无状态变更: uid={uid}")

        return changes

    def _calc_natural_recovery(
        self,
        old_state: Dict[str, Any],
        time_hours: float,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        计算自然恢复

        规则：
        - health: max_health × 2%/小时（无重伤、非战斗中）
        - mana: max_mana × 5%/小时（非施法中）
        - spirit: max_spirit × 3%/小时（非消耗神识中）
        """
        changes: Dict[str, Any] = {}
        is_combat = context.get("is_combat", False)

        # 生命恢复
        health = old_state.get("health", 0)
        max_health = old_state.get("max_health", 0)
        if max_health > 0 and health < max_health and not is_combat:
            # 检查是否有重伤（重伤时不自然恢复）
            injuries = old_state.get("injuries", [])
            has_critical = any(
                isinstance(inj, dict) and inj.get("severity") == "critical"
                for inj in injuries
            )
            if not has_critical:
                recovery = int(max_health * HEALTH_RECOVERY_RATE * time_hours)
                new_health = min(health + recovery, max_health)
                if new_health != health:
                    changes["health"] = new_health
                    debug_log(
                        f"[StateEngine] 生命恢复: {health} → {new_health} "
                        f"(+{recovery}, {time_hours:.1f}小时)"
                    )

        # 法力恢复
        mana = old_state.get("mana", 0)
        max_mana = old_state.get("max_mana", 0)
        if max_mana > 0 and mana < max_mana:
            action_id = context.get("action_id", "")
            # 施法中不恢复
            is_casting = action_id in ("combat", "craft_pill", "craft_equip", "breakthrough")
            if not is_casting:
                recovery = int(max_mana * MANA_RECOVERY_RATE * time_hours)
                new_mana = min(mana + recovery, max_mana)
                if new_mana != mana:
                    changes["mana"] = new_mana
                    debug_log(
                        f"[StateEngine] 法力恢复: {mana} → {new_mana} "
                        f"(+{recovery}, {time_hours:.1f}小时)"
                    )

        # 神识恢复
        spirit = old_state.get("spirit", 0)
        max_spirit = old_state.get("max_spirit", 0)
        if max_spirit > 0 and spirit < max_spirit:
            action_id = context.get("action_id", "")
            is_consuming = action_id in ("combat", "breakthrough")
            if not is_consuming:
                recovery = int(max_spirit * SPIRIT_RECOVERY_RATE * time_hours)
                new_spirit = min(spirit + recovery, max_spirit)
                if new_spirit != spirit:
                    changes["spirit"] = new_spirit
                    debug_log(
                        f"[StateEngine] 神识恢复: {spirit} → {new_spirit} "
                        f"(+{recovery}, {time_hours:.1f}小时)"
                    )

        return changes

    def _calc_fatigue(
        self,
        old_state: Dict[str, Any],
        time_hours: float,
        action_id: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        计算疲劳变化

        规则：根据行为类型累积疲劳，休息时恢复
        """
        fatigue = old_state.get("fatigue")
        if fatigue is None:
            # 初始化疲劳度
            fatigue = {
                "value": 10,
                "level": "normal",
                "recovery_rate": FATIGUE_RECOVERY_REST,
                "accumulation_rate": FATIGUE_ACCUMULATION.get("chat", 1),
            }

        if not isinstance(fatigue, dict):
            warn_log(f"[StateEngine] 疲劳度数据格式异常: {type(fatigue)}")
            return None

        current_value = fatigue.get("value", 10)
        try:
            current_value = int(current_value)
        except (TypeError, ValueError):
            current_value = 10

        # 计算疲劳变化
        is_resting = context.get("is_resting", False) or action_id == "rest"
        if is_resting:
            # 休息时恢复疲劳
            change = -FATIGUE_RECOVERY_REST * time_hours
        else:
            # 根据行为类型累积疲劳
            rate = FATIGUE_ACCUMULATION.get(action_id, FATIGUE_ACCUMULATION["custom"])
            change = rate * time_hours

        new_value = max(0, min(100, int(current_value + change)))

        if new_value == current_value:
            return None

        # 计算疲劳等级
        new_level = self._get_fatigue_level(new_value)

        result = {
            "value": new_value,
            "level": new_level,
            "recovery_rate": fatigue.get("recovery_rate", FATIGUE_RECOVERY_REST),
            "accumulation_rate": FATIGUE_ACCUMULATION.get(action_id, 1),
        }

        debug_log(
            f"[StateEngine] 疲劳变化: {current_value} → {new_value} "
            f"({change:+.1f}, level={new_level}, action={action_id})"
        )

        return result

    def _process_buff_expiry(
        self,
        old_state: Dict[str, Any],
        time_cost_minutes: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        处理 Buff 过期

        规则：减少剩余时间，移除已过期 buff（remaining_minutes <= 0 且非永久）
        """
        buffs = old_state.get("active_buffs", [])
        if not buffs or not isinstance(buffs, list):
            return None

        changed = False
        new_buffs = []

        for buff in buffs:
            if not isinstance(buff, dict):
                new_buffs.append(buff)
                continue

            duration = buff.get("duration_minutes", -1)
            remaining = buff.get("remaining_minutes", -1)

            # 永久 buff 不处理
            if duration == -1 and remaining == -1:
                new_buffs.append(buff)
                continue

            # 减少剩余时间
            if remaining is not None:
                try:
                    new_remaining = int(remaining) - time_cost_minutes
                    if new_remaining <= 0:
                        # buff 已过期，移除
                        changed = True
                        debug_log(f"[StateEngine] Buff过期: {buff.get('name', '未知')}")
                        continue
                    else:
                        buff_copy = dict(buff)
                        buff_copy["remaining_minutes"] = new_remaining
                        new_buffs.append(buff_copy)
                        changed = True
                except (TypeError, ValueError):
                    new_buffs.append(buff)
            else:
                new_buffs.append(buff)

        if changed:
            return new_buffs
        return None

    def _process_injury_recovery(
        self,
        old_state: Dict[str, Any],
        time_cost_minutes: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        处理伤势恢复

        规则：减少剩余恢复时间，移除已恢复伤势
        """
        injuries = old_state.get("injuries", [])
        if not injuries or not isinstance(injuries, list):
            return None

        changed = False
        new_injuries = []

        for injury in injuries:
            if not isinstance(injury, dict):
                new_injuries.append(injury)
                continue

            remaining = injury.get("remaining_minutes")
            if remaining is not None:
                try:
                    new_remaining = int(remaining) - time_cost_minutes
                    if new_remaining <= 0:
                        # 伤势已恢复，移除
                        changed = True
                        debug_log(f"[StateEngine] 伤势恢复: {injury.get('name', '未知')}")
                        continue
                    else:
                        injury_copy = dict(injury)
                        injury_copy["remaining_minutes"] = new_remaining
                        new_injuries.append(injury_copy)
                        changed = True
                except (TypeError, ValueError):
                    new_injuries.append(injury)
            else:
                new_injuries.append(injury)

        if changed:
            return new_injuries
        return None

    def _calc_mental_state_changes(
        self,
        old_state: Dict[str, Any],
        time_hours: float,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        计算心神状态变化

        规则：
        - clarity: 平静环境 +3/小时，修炼时 +5/小时，战斗/焦虑 -5/小时
        - dao_heart: 缓慢恢复 +1/小时，重大事件可能大幅变化
        - mood: 根据上下文调整
        """
        mental = old_state.get("mental_state")
        if mental is None:
            # 初始化心神状态
            mental = {
                "clarity": 70,
                "mood": "calm",
                "dao_heart": 60,
            }

        if not isinstance(mental, dict):
            warn_log(f"[StateEngine] 心神状态数据格式异常: {type(mental)}")
            return None

        changes: Dict[str, Any] = {}
        action_id = context.get("action_id", "chat")
        is_combat = context.get("is_combat", False)

        # 清明度变化
        clarity = mental.get("clarity", 70)
        try:
            clarity = int(clarity)
        except (TypeError, ValueError):
            clarity = 70

        if is_combat or action_id == "combat":
            clarity_change = -5 * time_hours
        elif action_id in ("meditate_basic", "meditate_depth"):
            clarity_change = CLARITY_RECOVERY_MEDITATE * time_hours
        elif action_id == "breakthrough":
            clarity_change = -3 * time_hours
        elif action_id == "rest":
            clarity_change = CLARITY_RECOVERY_NORMAL * time_hours
        else:
            clarity_change = CLARITY_RECOVERY_NORMAL * time_hours * 0.5

        new_clarity = max(0, min(100, int(clarity + clarity_change)))
        if new_clarity != clarity:
            changes["clarity"] = new_clarity

        # 道心变化（缓慢恢复）
        dao_heart = mental.get("dao_heart", 60)
        try:
            dao_heart = int(dao_heart)
        except (TypeError, ValueError):
            dao_heart = 60

        if dao_heart < 80:
            dao_change = 1 * time_hours
            new_dao = min(100, int(dao_heart + dao_change))
            if new_dao != dao_heart:
                changes["dao_heart"] = new_dao

        # 情绪变化
        mood = mental.get("mood", "calm")
        if is_combat:
            new_mood = "focused"
        elif action_id in ("meditate_basic", "meditate_depth"):
            new_mood = "calm"
        elif action_id == "breakthrough":
            new_mood = "focused"
        elif action_id == "rest":
            new_mood = "calm"
        elif new_clarity < 30:
            new_mood = "anxious"
        elif new_clarity > 90:
            new_mood = "focused"
        else:
            new_mood = mood

        if new_mood != mood and new_mood in VALID_MOODS:
            changes["mood"] = new_mood

        if not changes:
            return None

        # 合并结果
        result = dict(mental)
        result.update(changes)
        return result

    def _calc_environment_effects(
        self,
        old_state: Dict[str, Any],
        time_hours: float,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        计算环境效果

        规则：
        - 灵潮：修炼时额外恢复法力 +2%/小时
        - 恶劣天气：疲劳累积 +1/小时
        - 高灵气区域：自然恢复 +50%
        """
        changes: Dict[str, Any] = {}
        spirit_tide = context.get("spirit_tide", False)
        spirit_tide_intensity = context.get("spirit_tide_intensity", 0)
        weather = context.get("weather", "晴朗")
        action_id = context.get("action_id", "chat")

        # 灵潮效果：修炼时额外恢复法力
        if spirit_tide and action_id in ("meditate_basic", "meditate_depth"):
            max_mana = old_state.get("max_mana", 0)
            current_mana = changes.get("mana", old_state.get("mana", 0))
            if max_mana > 0:
                bonus = int(max_mana * 0.02 * time_hours * (spirit_tide_intensity or 1))
                new_mana = min(current_mana + bonus, max_mana)
                changes["mana"] = new_mana
                debug_log(f"[StateEngine] 灵潮法力加成: +{bonus}")

        # 恶劣天气增加疲劳
        bad_weather = {"暴风雨", "雷暴", "大雪", "浓雾", "沙尘暴"}
        if weather in bad_weather:
            fatigue = old_state.get("fatigue")
            if fatigue and isinstance(fatigue, dict):
                current = changes.get("fatigue", fatigue)
                if isinstance(current, dict):
                    current_value = current.get("value", 0)
                    try:
                        current_value = int(current_value)
                    except (TypeError, ValueError):
                        current_value = 0
                    extra = int(1 * time_hours)
                    new_value = min(100, current_value + extra)
                    if new_value != current_value:
                        current = dict(current)
                        current["value"] = new_value
                        current["level"] = self._get_fatigue_level(new_value)
                        changes["fatigue"] = current

        return changes

    @staticmethod
    def _get_fatigue_level(value: int) -> str:
        """根据疲劳值获取等级"""
        for threshold, level in reversed(FATIGUE_LEVELS):
            if value >= threshold:
                return level
        return "refreshed"

    @staticmethod
    def calc_injury_penalties(injuries: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        计算伤势对属性上限的惩罚

        Args:
            injuries: 伤势列表

        Returns:
            惩罚字典 {"health_penalty": X, "mana_penalty": Y, "spirit_penalty": Z}
        """
        health_penalty = 0
        mana_penalty = 0
        spirit_penalty = 0

        for injury in injuries:
            if not isinstance(injury, dict):
                continue
            health_penalty += injury.get("health_penalty", 0)
            mana_penalty += injury.get("mana_penalty", 0)
            spirit_penalty += injury.get("spirit_penalty", 0)

        return {
            "health_penalty": health_penalty,
            "mana_penalty": mana_penalty,
            "spirit_penalty": spirit_penalty,
        }

    @staticmethod
    def get_effective_max_stats(state: Dict[str, Any]) -> Dict[str, int]:
        """
        获取考虑伤势惩罚后的有效属性上限

        Args:
            state: 角色状态

        Returns:
            有效上限字典 {"effective_max_health": X, "effective_max_mana": Y, "effective_max_spirit": Z}
        """
        max_health = state.get("max_health", 0)
        max_mana = state.get("max_mana", 0)
        max_spirit = state.get("max_spirit", 0)

        injuries = state.get("injuries", [])
        penalties = StateEngine.calc_injury_penalties(injuries)

        return {
            "effective_max_health": max(0, max_health - penalties["health_penalty"]),
            "effective_max_mana": max(0, max_mana - penalties["mana_penalty"]),
            "effective_max_spirit": max(0, max_spirit - penalties["spirit_penalty"]),
        }


# 全局单例
_state_engine: Optional[StateEngine] = None


def get_state_engine() -> StateEngine:
    """获取状态引擎单例"""
    global _state_engine
    if _state_engine is None:
        _state_engine = StateEngine()
        info_log("[StateEngine] 状态引擎初始化完成")
    return _state_engine
