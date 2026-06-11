"""
CombatManager - 切磋/斗法管理器

管理修仙世界中玩家间的切磋与斗法。
战斗为非实时回合制：双方提交行动后，由 AI GM 仲裁生成战斗描述。

用法:
    from combat_manager import get_combat_manager

    mgr = get_combat_manager()
    mgr.create_combat("uid_001", "uid_002")
    mgr.accept_combat("uid_002", "combat_xxx")
    mgr.execute_action("uid_001", "combat_xxx", "挥剑攻击")
"""

import json
import time
import uuid
import threading
from typing import Dict, Any, Optional, List

from gm_logger import debug_log, info_log, error_log


class CombatManager:
    """切磋/斗法管理器"""

    # 战斗最大回合数，防止无限循环
    MAX_ROUNDS = 30

    def __init__(self):
        """初始化切磋管理器"""
        self._active_combats: Dict[str, Dict[str, Any]] = {}
        # uid -> combat_id 映射，快速查找玩家当前参与的战斗
        self._player_combat_map: Dict[str, str] = {}
        # 当前回合已提交行动的玩家 uid 集合（每回合重置）
        # combat_id -> set of uid
        self._round_actions_submitted: Dict[str, set] = {}
        self._lock = threading.Lock()
        info_log("CombatManager 初始化完成")

    # ================================================================
    # 公开接口
    # ================================================================

    def create_combat(self, uid: str, target_uid: str) -> Dict[str, Any]:
        """
        发起切磋挑战

        Args:
            uid: 发起者 uid
            target_uid: 被挑战者 uid

        Returns:
            战斗数据字典
        """
        if uid == target_uid:
            return {"error": "不能与自己切磋"}

        with self._lock:
            # 检查发起者是否已在战斗中
            if uid in self._player_combat_map:
                existing_id = self._player_combat_map[uid]
                existing = self._active_combats.get(existing_id, {})
                if existing.get("status") in ("pending", "active"):
                    return {"error": "你已在一场切磋中，请先完成或退出当前战斗"}

            # 检查被挑战者是否已在战斗中
            if target_uid in self._player_combat_map:
                existing_id = self._player_combat_map[target_uid]
                existing = self._active_combats.get(existing_id, {})
                if existing.get("status") in ("pending", "active"):
                    return {"error": "对方已在一场切磋中，请稍后再试"}

            # 获取双方角色名
            challenger_name = self._get_player_name(uid)
            defender_name = self._get_player_name(target_uid)

            if not defender_name:
                return {"error": "目标玩家不存在"}

            # 创建战斗
            combat_id = f"combat_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            now = time.time()

            combat_data = {
                "combat_id": combat_id,
                "challenger_uid": uid,
                "defender_uid": target_uid,
                "challenger_name": challenger_name,
                "defender_name": defender_name,
                "status": "pending",
                "round": 1,
                "actions": [],
                "result": "",
                "created_at": now,
            }

            self._active_combats[combat_id] = combat_data
            self._player_combat_map[uid] = combat_id
            self._player_combat_map[target_uid] = combat_id
            self._round_actions_submitted[combat_id] = set()

        # 推送挑战通知给被挑战者
        self._notify_player(target_uid, "combat_challenge", {
            "combat_id": combat_id,
            "challenger_uid": uid,
            "challenger_name": challenger_name,
            "message": f"{challenger_name} 向你发起了切磋挑战！",
        })

        # 推送确认给发起者
        self._notify_player(uid, "combat_created", {
            "combat_id": combat_id,
            "defender_uid": target_uid,
            "defender_name": defender_name,
            "message": f"你向 {defender_name} 发起了切磋挑战，等待对方应战。",
        })

        info_log(f"切磋挑战已发起: {challenger_name}({uid}) -> {defender_name}({target_uid}), combat_id={combat_id}")

        return {
            "combat_id": combat_id,
            "challenger_uid": uid,
            "defender_uid": target_uid,
            "challenger_name": challenger_name,
            "defender_name": defender_name,
            "status": "pending",
            "message": f"已向 {defender_name} 发起切磋挑战",
        }

    def accept_combat(self, uid: str, combat_id: str) -> Dict[str, Any]:
        """
        接受切磋挑战

        Args:
            uid: 接受者 uid（必须是被挑战者）
            combat_id: 战斗 ID

        Returns:
            战斗数据字典
        """
        with self._lock:
            combat = self._active_combats.get(combat_id)
            if not combat:
                return {"error": "切磋不存在"}

            if combat["status"] != "pending":
                return {"error": f"切磋状态异常，当前状态: {combat['status']}"}

            if uid != combat["defender_uid"]:
                return {"error": "只有被挑战者才能接受挑战"}

            # 更新战斗状态
            combat["status"] = "active"
            combat["accepted_at"] = time.time()
            # 重置回合行动提交记录
            self._round_actions_submitted[combat_id] = set()

            challenger_uid = combat["challenger_uid"]
            defender_uid = combat["defender_uid"]
            challenger_name = combat["challenger_name"]
            defender_name = combat["defender_name"]

        # 通知发起者：挑战已被接受
        self._notify_player(challenger_uid, "combat_accepted", {
            "combat_id": combat_id,
            "defender_name": defender_name,
            "message": f"{defender_name} 接受了你的切磋挑战！战斗开始！",
        })

        # 通知接受者：战斗开始
        self._notify_player(defender_uid, "combat_started", {
            "combat_id": combat_id,
            "challenger_name": challenger_name,
            "message": f"你接受了 {challenger_name} 的切磋挑战！战斗开始！",
        })

        info_log(f"切磋已开始: {challenger_name} vs {defender_name}, combat_id={combat_id}")

        return {
            "combat_id": combat_id,
            "status": "active",
            "round": 1,
            "message": f"切磋开始！你与 {challenger_name} 的战斗正式打响！",
        }

    def execute_action(self, uid: str, combat_id: str, action: str) -> Dict[str, Any]:
        """
        执行战斗行动

        记录玩家行动，如果双方都提交了当前回合行动，
        则调用 LLM 生成战斗描述和结果。

        Args:
            uid: 行动玩家 uid
            combat_id: 战斗 ID
            action: 行动描述（如"挥剑攻击"、"施展火球术"等）

        Returns:
            行动结果字典
        """
        if not action or not action.strip():
            return {"error": "行动描述不能为空"}

        with self._lock:
            combat = self._active_combats.get(combat_id)
            if not combat:
                return {"error": "切磋不存在"}

            if combat["status"] != "active":
                return {"error": f"切磋未在进行中，当前状态: {combat['status']}"}

            if uid not in (combat["challenger_uid"], combat["defender_uid"]):
                return {"error": "你不在这场切磋中"}

            # 检查该玩家本回合是否已提交行动
            submitted = self._round_actions_submitted.get(combat_id, set())
            if uid in submitted:
                return {"error": "你本回合已提交行动，请等待对方行动"}

            # 记录行动
            current_round = combat["round"]
            action_record = {
                "uid": uid,
                "action": action.strip(),
                "round": current_round,
                "timestamp": time.time(),
            }
            combat["actions"].append(action_record)
            submitted.add(uid)
            self._round_actions_submitted[combat_id] = submitted

            player_name = combat["challenger_name"] if uid == combat["challenger_uid"] else combat["defender_name"]
            opponent_uid = combat["defender_uid"] if uid == combat["challenger_uid"] else combat["challenger_uid"]
            opponent_name = combat["defender_name"] if uid == combat["challenger_uid"] else combat["challenger_name"]

            # 通知对手：对方已行动
            self._notify_player(opponent_uid, "combat_action_submitted", {
                "combat_id": combat_id,
                "player_name": player_name,
                "action": action.strip(),
                "round": current_round,
                "message": f"{player_name} 已提交第 {current_round} 回合行动，等待你行动。",
            })

            # 检查双方是否都已提交行动
            both_submitted = (combat["challenger_uid"] in submitted
                             and combat["defender_uid"] in submitted)

            if not both_submitted:
                debug_log(f"切磋行动已记录: {player_name}({uid}) 第{current_round}回合, 等待对方行动, combat_id={combat_id}")
                return {
                    "combat_id": combat_id,
                    "round": current_round,
                    "action_recorded": True,
                    "message": f"你使出了「{action.strip()}」，等待 {opponent_name} 行动...",
                }

        # 双方都已提交，调用 LLM 仲裁
        debug_log(f"双方行动已提交，开始 LLM 仲裁: combat_id={combat_id}, round={current_round}")
        return self._resolve_round(combat_id, current_round)

    def flee_combat(self, uid: str, combat_id: str) -> Dict[str, Any]:
        """
        逃跑退出战斗

        Args:
            uid: 逃跑玩家 uid
            combat_id: 战斗 ID

        Returns:
            逃跑结果字典
        """
        with self._lock:
            combat = self._active_combats.get(combat_id)
            if not combat:
                return {"error": "切磋不存在"}

            if combat["status"] not in ("pending", "active"):
                return {"error": f"切磋已结束，当前状态: {combat['status']}"}

            if uid not in (combat["challenger_uid"], combat["defender_uid"]):
                return {"error": "你不在这场切磋中"}

            player_name = combat["challenger_name"] if uid == combat["challenger_uid"] else combat["defender_name"]
            opponent_uid = combat["defender_uid"] if uid == combat["challenger_uid"] else combat["challenger_uid"]
            opponent_name = combat["defender_name"] if uid == combat["challenger_uid"] else combat["challenger_name"]

            # 更新战斗状态
            combat["status"] = "fled"
            combat["result"] = f"{player_name} 逃离了战斗，{opponent_name} 获胜"
            combat["fled_by"] = uid
            combat["fled_at"] = time.time()

            # 清理玩家战斗映射
            challenger_uid = combat["challenger_uid"]
            defender_uid = combat["defender_uid"]
            self._player_combat_map.pop(challenger_uid, None)
            self._player_combat_map.pop(defender_uid, None)
            self._round_actions_submitted.pop(combat_id, None)

        # 通知对手
        self._notify_player(opponent_uid, "combat_fled", {
            "combat_id": combat_id,
            "fled_name": player_name,
            "winner_name": opponent_name,
            "message": f"{player_name} 逃离了战斗，你获得了胜利！",
        })

        # 通知逃跑者
        self._notify_player(uid, "combat_fled", {
            "combat_id": combat_id,
            "fled_name": player_name,
            "message": f"你逃离了与 {opponent_name} 的战斗。",
        })

        info_log(f"玩家逃离切磋: {player_name}({uid}), combat_id={combat_id}")

        return {
            "combat_id": combat_id,
            "status": "fled",
            "message": f"你逃离了与 {opponent_name} 的战斗。",
        }

    def get_combat_info(self, uid: str) -> Dict[str, Any]:
        """
        获取玩家当前战斗状态

        Args:
            uid: 玩家 uid

        Returns:
            战斗信息字典
        """
        with self._lock:
            combat_id = self._player_combat_map.get(uid)
            if not combat_id:
                return {"in_combat": False, "message": "你当前没有参与任何切磋"}

            combat = self._active_combats.get(combat_id)
            if not combat:
                # 数据不一致，清理映射
                self._player_combat_map.pop(uid, None)
                return {"in_combat": False, "message": "你当前没有参与任何切磋"}

            # 判断玩家角色
            is_challenger = uid == combat["challenger_uid"]
            opponent_uid = combat["defender_uid"] if is_challenger else combat["challenger_uid"]
            opponent_name = combat["defender_name"] if is_challenger else combat["challenger_name"]
            player_name = combat["challenger_name"] if is_challenger else combat["defender_name"]

            # 检查本回合是否已提交行动
            submitted = self._round_actions_submitted.get(combat_id, set())
            has_submitted = uid in submitted

            # 获取当前回合的行动
            current_round = combat["round"]
            round_actions = [
                a for a in combat["actions"]
                if a["round"] == current_round
            ]

            return {
                "in_combat": True,
                "combat_id": combat_id,
                "status": combat["status"],
                "round": current_round,
                "is_challenger": is_challenger,
                "player_name": player_name,
                "opponent_uid": opponent_uid,
                "opponent_name": opponent_name,
                "has_submitted_action": has_submitted,
                "current_round_actions": round_actions,
                "result": combat.get("result", ""),
                "created_at": combat.get("created_at", 0),
            }

    # ================================================================
    # LLM 仲裁
    # ================================================================

    def _resolve_round(self, combat_id: str, round_num: int) -> Dict[str, Any]:
        """
        仲裁一个回合：双方行动都已提交，调用 LLM 生成战斗描述

        Args:
            combat_id: 战斗 ID
            round_num: 回合数

        Returns:
            回合结果字典
        """
        with self._lock:
            combat = self._active_combats.get(combat_id)
            if not combat:
                return {"error": "切磋不存在"}

            # 提取当前回合双方行动
            round_actions = [a for a in combat["actions"] if a["round"] == round_num]
            challenger_action = ""
            defender_action = ""
            for a in round_actions:
                if a["uid"] == combat["challenger_uid"]:
                    challenger_action = a["action"]
                elif a["uid"] == combat["defender_uid"]:
                    defender_action = a["action"]

            challenger_name = combat["challenger_name"]
            defender_name = combat["defender_name"]
            all_actions = combat["actions"]

        # 构建 LLM prompt
        prompt = self._build_combat_prompt(
            challenger_name, defender_name,
            challenger_action, defender_action,
            round_num, all_actions,
        )

        # 调用 LLM
        llm_result = self._call_llm_for_combat(prompt)

        if "error" in llm_result:
            # LLM 调用失败，使用简单仲裁
            llm_result = {
                "description": f"第{round_num}回合：{challenger_name}使出「{challenger_action}」，{defender_name}以「{defender_action}」应对，双方你来我往，战况激烈。",
                "is_over": False,
                "winner": "",
            }

        with self._lock:
            combat = self._active_combats.get(combat_id)
            if not combat:
                return {"error": "切磋不存在"}

            # 记录回合结果
            round_result = {
                "round": round_num,
                "challenger_action": challenger_action,
                "defender_action": defender_action,
                "description": llm_result.get("description", ""),
                "is_over": llm_result.get("is_over", False),
                "winner": llm_result.get("winner", ""),
            }

            if "round_results" not in combat:
                combat["round_results"] = []
            combat["round_results"].append(round_result)

            is_over = llm_result.get("is_over", False)
            winner = llm_result.get("winner", "")

            if is_over or round_num >= self.MAX_ROUNDS:
                # 战斗结束
                if winner:
                    combat["result"] = f"{winner} 获得了胜利！"
                else:
                    combat["result"] = "双方旗鼓相当，切磋以平局收场"
                combat["status"] = "completed"
                combat["completed_at"] = time.time()

                # 清理玩家映射
                challenger_uid = combat["challenger_uid"]
                defender_uid = combat["defender_uid"]
                self._player_combat_map.pop(challenger_uid, None)
                self._player_combat_map.pop(defender_uid, None)
                self._round_actions_submitted.pop(combat_id, None)

                # 通知双方战斗结束
                self._notify_player(challenger_uid, "combat_completed", {
                    "combat_id": combat_id,
                    "round": round_num,
                    "description": round_result["description"],
                    "result": combat["result"],
                    "winner": winner,
                    "message": combat["result"],
                })
                self._notify_player(defender_uid, "combat_completed", {
                    "combat_id": combat_id,
                    "round": round_num,
                    "description": round_result["description"],
                    "result": combat["result"],
                    "winner": winner,
                    "message": combat["result"],
                })

                info_log(f"切磋结束: {challenger_name} vs {defender_name}, 结果: {combat['result']}, combat_id={combat_id}")

                return {
                    "combat_id": combat_id,
                    "round": round_num,
                    "description": round_result["description"],
                    "is_over": True,
                    "result": combat["result"],
                    "winner": winner,
                }
            else:
                # 进入下一回合
                combat["round"] = round_num + 1
                self._round_actions_submitted[combat_id] = set()

                # 通知双方回合结果
                challenger_uid = combat["challenger_uid"]
                defender_uid = combat["defender_uid"]

                self._notify_player(challenger_uid, "combat_round_result", {
                    "combat_id": combat_id,
                    "round": round_num,
                    "next_round": round_num + 1,
                    "description": round_result["description"],
                    "message": f"第{round_num}回合结束，进入第{round_num + 1}回合，请提交你的行动。",
                })
                self._notify_player(defender_uid, "combat_round_result", {
                    "combat_id": combat_id,
                    "round": round_num,
                    "next_round": round_num + 1,
                    "description": round_result["description"],
                    "message": f"第{round_num}回合结束，进入第{round_num + 1}回合，请提交你的行动。",
                })

                info_log(f"切磋回合结束: {challenger_name} vs {defender_name}, 第{round_num}回合, combat_id={combat_id}")

                return {
                    "combat_id": combat_id,
                    "round": round_num,
                    "next_round": round_num + 1,
                    "description": round_result["description"],
                    "is_over": False,
                    "message": f"第{round_num}回合结束，进入第{round_num + 1}回合",
                }

    def _build_combat_prompt(
        self,
        challenger_name: str,
        defender_name: str,
        challenger_action: str,
        defender_action: str,
        round_num: int,
        all_actions: List[Dict[str, Any]],
    ) -> str:
        """
        构建 LLM 战斗仲裁 prompt

        Args:
            challenger_name: 挑战者名称
            defender_name: 防守者名称
            challenger_action: 挑战者本回合行动
            defender_action: 防守者本回合行动
            round_num: 当前回合数
            all_actions: 所有回合行动记录

        Returns:
            prompt 字符串
        """
        # 构建战斗历史
        history_lines = []
        for a in all_actions:
            name = challenger_name if a["uid"] == all_actions[0]["uid"] and a["round"] == all_actions[0]["round"] else ""
            # 简化：按行动顺序列出
            pass

        # 只保留当前回合之前的行动作为历史
        prev_actions = [a for a in all_actions if a["round"] < round_num]
        history_text = ""
        if prev_actions:
            history_parts = []
            for a in prev_actions:
                # 通过 uid 判断是哪一方
                # 由于没有直接关联，在 prompt 中简化处理
                history_parts.append(f"回合{a['round']}: {a['action']}")
            history_text = "\n".join(history_parts)

        prompt = f"""你是一位修仙世界的战斗裁判，负责仲裁两位修士之间的切磋战斗。

## 战斗信息
- 挑战者: {challenger_name}
- 防守者: {defender_name}
- 当前回合: 第{round_num}回合

## 本回合行动
- {challenger_name} 使出: 「{challenger_action}」
- {defender_name} 使出: 「{defender_action}」
"""

        if history_text:
            prompt += f"""
## 之前回合的行动记录
{history_text}
"""

        prompt += """
## 要求
请根据双方行动，生成一段精彩的修仙战斗描述，并判断本回合是否分出胜负。

请以 JSON 格式返回，包含以下字段：
- "description": 本回合的战斗描述（100-200字，修仙风格，生动精彩）
- "is_over": 战斗是否结束（boolean，通常为 false，只在明显分出胜负时为 true）
- "winner": 获胜者名称（如果 is_over 为 true 则填写获胜者名字，否则为空字符串）

注意：
1. 切磋以交流为主，不要轻易判定一方落败，通常需要3-5回合才能分出胜负
2. 战斗描述要有修仙世界的韵味，包含灵力波动、法术碰撞等元素
3. 双方实力相近，胜负取决于战术和行动的巧妙程度
4. 第1-2回合 is_over 应为 false
5. 第3回合起可以根据行动合理性考虑是否结束
"""
        return prompt

    def _call_llm_for_combat(self, prompt: str) -> Dict[str, Any]:
        """
        调用 LLM 进行战斗仲裁

        Args:
            prompt: 战斗仲裁 prompt

        Returns:
            LLM 返回的战斗结果字典
        """
        llm = None
        try:
            from game_master import get_game_master
            gm = get_game_master()
            llm = gm._create_chat_llm()

            messages = [
                {"role": "system", "content": "你是一位修仙世界的战斗裁判，负责仲裁切磋战斗。请始终以 JSON 格式回复。"},
                {"role": "user", "content": prompt},
            ]

            debug_log(f"[CombatManager] 调用 LLM 仲裁战斗, prompt长度={len(prompt)}")

            response = llm.chat.completions.create(
                model=getattr(llm, '_gm_model_name', 'Qwen3.6-35B-A3B'),
                messages=messages,
                temperature=0.8,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content or ""
            debug_log(f"[CombatManager] LLM 仲裁响应: {content[:500]}")

            # 解析 JSON
            result = json.loads(content)

            # 校验必要字段
            if "description" not in result:
                result["description"] = "双方你来我往，战况激烈。"
            if "is_over" not in result:
                result["is_over"] = False
            if "winner" not in result:
                result["winner"] = ""

            return result

        except json.JSONDecodeError as e:
            error_log(f"[CombatManager] LLM 响应 JSON 解析失败: {e}")
            return {"error": f"JSON 解析失败: {e}"}
        except Exception as e:
            error_log(f"[CombatManager] LLM 仲裁调用失败: {e}")
            return {"error": str(e)}
        finally:
            # 安全关闭 LLM client
            if llm:
                try:
                    if hasattr(llm, 'close'):
                        llm.close()
                except Exception as e:
                    debug_log(f"[CombatManager] 关闭 LLM client 时出错: {e}")

    # ================================================================
    # 辅助方法
    # ================================================================

    def _get_player_name(self, uid: str) -> str:
        """
        获取玩家角色名

        Args:
            uid: 玩家 uid

        Returns:
            角色名，获取失败返回空字符串
        """
        try:
            from gm_storage import GMStorage
            import yaml
            from pathlib import Path

            config_path = Path(__file__).parent.parent / "config.yaml"
            config = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}

            storage = GMStorage(config)
            player = storage.couch_get_player(uid)
            if player:
                return player.get("name", "")
        except Exception as e:
            error_log(f"[CombatManager] 获取玩家名称失败: uid={uid}, 错误: {e}")

        return ""

    def _notify_player(self, uid: str, event_type: str, data: Dict[str, Any]) -> None:
        """
        通过 EventBus 推送战斗通知给指定玩家

        Args:
            uid: 目标玩家 uid
            event_type: 事件类型
            data: 事件数据
        """
        try:
            from event_bus import get_event_bus
            bus = get_event_bus()
            bus.publish_to_uid(uid, event_type, data)
        except Exception as e:
            error_log(f"[CombatManager] 推送战斗通知失败: uid={uid}, event={event_type}, 错误: {e}")


# ================================================================
# 全局单例
# ================================================================

_combat_manager_instance: Optional[CombatManager] = None
_instance_lock = threading.Lock()


def get_combat_manager() -> CombatManager:
    """
    获取 CombatManager 单例实例

    Returns:
        CombatManager 实例
    """
    global _combat_manager_instance
    if _combat_manager_instance is None:
        with _instance_lock:
            if _combat_manager_instance is None:
                _combat_manager_instance = CombatManager()
                info_log("CombatManager 单例初始化完成")
    return _combat_manager_instance
