"""
《青墟灵修志》GM控制中枢Agent
负责游戏世界的实时生成、进程推进与动态演化

核心职责：
1. 解析用户输入，识别专属指令
2. 管理长短期记忆（Hindsight）
3. 多轮迭代处理复杂请求
4. 协调数据查询与保存
5. 生成符合修仙世界观的动态内容
"""

import os
import sys
import json
import re
from typing import Optional, List, Dict, Any, Callable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# 添加server目录到路径以导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import llm_config

from llm_client import LLMClient, get_llm_client, load_system_prompt
from hindsight_memory import HindsightMemoryStore


class CommandType(Enum):
    """用户指令类型"""
    STATUS = "/状态"          # 展示角色当前状态
    EQUIPMENT = "/装备"       # 展示装备信息
    INVENTORY = "/物品"       # 展示背包物品
    EVENTS = "/事件"          # 展示当前可进行的事件
    HISTORY = "/历史"         # 展示角色历史记录
    ALL = "/全部"             # 展示所有面板信息
    UNKNOWN = "unknown"       # 未知指令


@dataclass
class PlayerState:
    """玩家状态数据"""
    name: str = ""
    realm: str = "凡人"           # 境界
    level: int = 0                # 层级
    exp: int = 0                  # 修为
    max_exp: int = 100            # 修为上限
    location: str = "起始之地"     # 当前位置
    world_year: str = "青墟历元年" # 世界纪年
    health: int = 100             # 生命值
    mana: int = 100               # 法力值
    mood: str = "平静"            # 心境
    unlocked_panels: List[str] = field(default_factory=list)  # 已解锁面板


@dataclass
class GMResponse:
    """GM响应结构"""
    content: str                    # 响应内容（JSON字符串或纯文本）
    is_json: bool                   # 是否为JSON格式
    command_type: Optional[CommandType] = None  # 识别的指令类型
    memories_used: List[Dict] = field(default_factory=list)  # 使用的记忆
    iteration_count: int = 0        # 迭代次数
    metadata: Dict[str, Any] = field(default_factory=dict)   # 元数据


class GameMaster:
    """
    《青墟灵修志》GM控制中枢

    核心功能：
    - 用户指令解析与响应
    - Hindsight长短期记忆管理
    - 多轮迭代内容生成
    - 数据查询与保存协调
    """

    # 系统提示词路径
    SYSTEM_PROMPT_PATH = "./prompts/system.md"

    def __init__(
        self,
        player_id: str,
        player_name: str = "",
        enable_memory: bool = True,
        max_iterations: int = 3,
    ):
        """
        初始化GM控制中枢

        Args:
            player_id: 玩家唯一标识
            player_name: 玩家名称
            enable_memory: 是否启用Hindsight记忆系统
            max_iterations: 最大迭代次数
        """
        self.player_id = player_id
        self.player_name = player_name or f"修士{player_id[:8]}"
        self.max_iterations = max_iterations

        # 从config加载 hindsight 配置
        self.hindsight_base_url = llm_config.hindsight_base_url
        self.hindsight_api_key = llm_config.hindsight_api_key

        # 初始化玩家状态
        self.player_state = PlayerState(name=self.player_name)

        # 加载系统提示词
        self.system_prompt = self._load_system_prompt()

        # 初始化LLM客户端
        self.llm = get_llm_client(
            streaming=False,
            auto_load_system_prompt=False,  # 我们手动管理系统提示词
            enable_memory=False,  # 我们手动管理记忆
        )

        # 初始化Hindsight记忆系统
        self.memory: Optional[HindsightMemoryStore] = None
        self.world_memory: Optional[HindsightMemoryStore] = None

        if enable_memory:
            self._init_memory_system(self.hindsight_base_url, self.hindsight_api_key)

        # 指令处理器映射
        self.command_handlers: Dict[CommandType, Callable] = {
            CommandType.STATUS: self._handle_status_command,
            CommandType.EQUIPMENT: self._handle_equipment_command,
            CommandType.INVENTORY: self._handle_inventory_command,
            CommandType.EVENTS: self._handle_events_command,
            CommandType.HISTORY: self._handle_history_command,
            CommandType.ALL: self._handle_all_command,
        }

        # 对话历史（短期记忆）
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 10

        print(f"\033[32m[INFO] GM控制中枢已初始化 - 玩家: {self.player_name}\033[0m")

    def _load_system_prompt(self) -> str:
        """加载系统提示词"""
        try:
            with open(self.SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"\033[33m[WARN] 加载系统提示词失败: {e}\033[0m")
            return "你是《青墟灵修志》修仙大世界的GM，负责游戏世界的实时生成与推进。"

    def _init_memory_system(self, base_url: str, api_key: Optional[str]):
        """初始化Hindsight记忆系统"""
        try:
            # 玩家个人记忆库
            self.memory = HindsightMemoryStore(
                bank_id=f"player-{self.player_id}",
                bank_name=f"{self.player_name}的记忆",
                base_url=base_url,
                api_key=api_key,
                short_term_window=6,
                auto_retain=True,
                mission=f"《青墟灵修志》玩家 {self.player_name} 的个人记忆库，记录修炼历程、人际关系、重要抉择",
                disposition={
                    "skepticism": 2,    # 较低怀疑度，相信玩家描述
                    "literalism": 3,    # 中等字面理解
                    "empathy": 4,       # 较高共情，理解玩家情感
                },
            )

            # 世界共享记忆库
            self.world_memory = HindsightMemoryStore(
                bank_id="world",
                bank_name="青墟世界记忆",
                base_url=base_url,
                api_key=api_key,
                short_term_window=4,
                auto_retain=False,  # 世界记忆需要手动管理
                mission="《青墟灵修志》世界共享知识库，存储世界历史、宗门势力、地域变迁、重大事件",
                disposition={
                    "skepticism": 3,
                    "literalism": 4,    # 较高字面理解，确保世界设定准确
                    "empathy": 2,
                },
            )

            print(f"\033[32m[INFO] Hindsight记忆系统已初始化\033[0m")
        except Exception as e:
            print(f"\033[33m[WARN] Hindsight记忆系统初始化失败: {e}\033[0m")
            self.memory = None
            self.world_memory = None

    def _parse_command(self, user_input: str) -> CommandType:
        """解析用户指令"""
        input_clean = user_input.strip()

        for cmd_type in CommandType:
            if cmd_type == CommandType.UNKNOWN:
                continue
            if input_clean.startswith(cmd_type.value):
                return cmd_type

        return CommandType.UNKNOWN

    def _build_system_context(self, query: str) -> str:
        """构建系统上下文（包含记忆）"""
        context_parts = [self.system_prompt]

        # 添加玩家状态信息
        state_info = f"""
【当前玩家状态】
- 姓名: {self.player_state.name}
- 境界: {self.player_state.realm}
- 层级: {self.player_state.level}
- 修为: {self.player_state.exp}/{self.player_state.max_exp}
- 位置: {self.player_state.location}
- 世界纪年: {self.player_state.world_year}
- 心境: {self.player_state.mood}
- 已解锁面板: {', '.join(self.player_state.unlocked_panels) if self.player_state.unlocked_panels else '无'}
"""
        context_parts.append(state_info)

        # 从Hindsight获取相关记忆
        memory_context = self._retrieve_memories(query)
        if memory_context:
            context_parts.append(f"\n【相关记忆】\n{memory_context}")

        # 添加近期对话历史
        if self.conversation_history:
            history_text = "\n【近期对话】\n"
            for msg in self.conversation_history[-6:]:
                role = "玩家" if msg["role"] == "user" else "GM"
                history_text += f"{role}: {msg['content'][:100]}...\n"
            context_parts.append(history_text)

        return "\n".join(context_parts)

    def _retrieve_memories(self, query: str) -> str:
        """从Hindsight检索相关记忆"""
        memory_parts = []

        # 从玩家记忆库检索
        if self.memory:
            try:
                player_memories = self.memory.recall(query, budget="mid", max_tokens=2048)
                if player_memories:
                    mem_text = "【个人经历】\n"
                    for mem in player_memories[:5]:
                        text = mem.get("text", "")
                        mem_type = mem.get("type", "")
                        if text:
                            mem_text += f"• [{mem_type}] {text[:150]}...\n"
                    memory_parts.append(mem_text)
            except Exception as e:
                print(f"\033[33m[WARN] 检索玩家记忆失败: {e}\033[0m")

        # 从世界记忆库检索
        if self.world_memory:
            try:
                world_memories = self.world_memory.recall(query, budget="mid", max_tokens=2048)
                if world_memories:
                    mem_text = "【世界知识】\n"
                    for mem in world_memories[:3]:
                        text = mem.get("text", "")
                        mem_type = mem.get("type", "")
                        if text:
                            mem_text += f"• [{mem_type}] {text[:150]}...\n"
                    memory_parts.append(mem_text)
            except Exception as e:
                print(f"\033[33m[WARN] 检索世界记忆失败: {e}\033[0m")

        return "\n\n".join(memory_parts)

    def _save_to_memory(self, user_input: str, response: str, context: str = "conversation"):
        """保存对话到Hindsight记忆"""
        if self.memory:
            try:
                self.memory.retain_conversation(user_input, response, context=context)
            except Exception as e:
                print(f"\033[33m[WARN] 保存记忆失败: {e}\033[0m")

    def _update_conversation_history(self, user_input: str, response: str):
        """更新对话历史"""
        self.conversation_history.append({"role": "user", "content": user_input})
        self.conversation_history.append({"role": "assistant", "content": response})

        # 保持历史记录在限制范围内
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-self.max_history * 2:]

    def _is_json_response_needed(self, user_input: str, command_type: CommandType) -> bool:
        """判断是否需要JSON格式响应"""
        # 指令查询通常需要结构化数据
        if command_type != CommandType.UNKNOWN:
            return True

        # 特定关键词触发JSON响应
        json_keywords = ["状态", "装备", "物品", "背包", "属性", "面板", "信息"]
        for keyword in json_keywords:
            if keyword in user_input:
                return True

        return False

    def _iterative_generate(
        self,
        user_input: str,
        system_context: str,
        require_json: bool,
    ) -> GMResponse:
        """
        多轮迭代生成内容

        迭代策略：
        1. 第一轮：生成初始内容
        2. 第二轮：检查并修正内容质量
        3. 第三轮：最终优化（如需要）
        """
        iteration = 0
        last_response = ""
        memories_used = []

        # 记录使用的记忆
        if self.memory:
            memories_used = self.memory.recall(user_input, budget="low")

        while iteration < self.max_iterations:
            iteration += 1

            # 构建迭代特定的提示词
            if iteration == 1:
                # 第一轮：初始生成
                prompt = self._build_first_iteration_prompt(
                    user_input, system_context, require_json
                )
            elif iteration == 2:
                # 第二轮：质量检查与修正
                prompt = self._build_second_iteration_prompt(
                    user_input, last_response, require_json
                )
            else:
                # 第三轮：最终优化
                prompt = self._build_third_iteration_prompt(
                    user_input, last_response, require_json
                )

            # 调用LLM生成
            messages = [
                {"role": "system", "content": system_context},
                {"role": "user", "content": prompt}
            ]

            try:
                response = self.llm.chat(messages, use_memory=False)
                last_response = response

                # 检查是否需要继续迭代
                if self._should_stop_iteration(response, iteration, require_json):
                    break

            except Exception as e:
                print(f"\033[31m[ERROR] 迭代 {iteration} 生成失败: {e}\033[0m")
                break

        # 处理最终响应
        is_json, processed_response = self._process_final_response(
            last_response, require_json
        )

        return GMResponse(
            content=processed_response,
            is_json=is_json,
            iteration_count=iteration,
            memories_used=memories_used,
        )

    def _build_first_iteration_prompt(
        self, user_input: str, system_context: str, require_json: bool
    ) -> str:
        """构建第一轮迭代提示词"""
        json_instruction = """
**重要**：你必须返回有效的JSON格式，格式如下：
{
    "narrative": "古风修仙叙事内容",
    "data": {
        "关键字段": "值"
    },
    "options": ["选项1", "选项2"],
    "time_passed": "消耗的游戏时间"
}
""" if require_json else ""

        return f"""
玩家输入: {user_input}

请根据上述信息和游戏规则，生成响应内容。
要求：
1. 遵循正统古风修仙文风，无现代词汇
2. 剧情逻辑自洽，符合当前玩家状态
3. 内容唯一，不重复模板
{json_instruction}

直接返回内容，不要添加额外说明。
"""

    def _build_second_iteration_prompt(
        self, user_input: str, last_response: str, require_json: bool
    ) -> str:
        """构建第二轮迭代提示词（质量检查）"""
        json_check = """
如果是JSON格式，请确保：
- 是有效的JSON格式
- 包含所有必要字段
- narrative字段有丰富古风描述
""" if require_json else ""

        return f"""
请检查并优化以下响应内容：

原始输入: {user_input}
当前响应: {last_response}

检查要点：
1. 是否符合古风修仙文风？
2. 是否有现代词汇或口语化表达？
3. 剧情逻辑是否自洽？
4. 是否与玩家当前状态一致？
{json_check}

如有问题请修正，如无问题请直接返回优化后的内容。
直接返回最终内容，不要添加检查说明。
"""

    def _build_third_iteration_prompt(
        self, user_input: str, last_response: str, require_json: bool
    ) -> str:
        """构建第三轮迭代提示词（最终优化）"""
        return f"""
请对以下内容进行最终润色：

原始输入: {user_input}
当前响应: {last_response}

优化要求：
1. 提升古风修仙氛围
2. 增强画面感和沉浸感
3. 确保用词精准、意境深远
4. 保持内容完整性和逻辑性

直接返回最终优化后的内容。
"""

    def _should_stop_iteration(self, response: str, iteration: int, require_json: bool) -> bool:
        """判断是否应停止迭代"""
        # 第一轮总是继续
        if iteration == 1:
            return False

        # 检查JSON有效性（如果需要JSON）
        if require_json and iteration >= 2:
            try:
                json.loads(response)
                # JSON有效，可以停止
                return True
            except json.JSONDecodeError:
                # JSON无效，需要继续迭代
                return iteration >= self.max_iterations

        # 检查内容质量指标
        quality_indicators = [
            len(response) >= 50,  # 内容足够长
            "【" not in response,  # 没有未处理的标记
            "TODO" not in response.upper(),  # 没有待办标记
        ]

        if all(quality_indicators):
            return True

        return iteration >= self.max_iterations

    def _process_final_response(self, response: str, require_json: bool) -> tuple[bool, str]:
        """处理最终响应"""
        if not require_json:
            return False, response.strip()

        # 尝试提取JSON
        try:
            # 查找JSON代码块
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                # 验证JSON有效性
                json.loads(json_str)
                return True, json_str.strip()

            # 尝试直接解析整个响应
            json.loads(response)
            return True, response.strip()
        except json.JSONDecodeError:
            # 不是有效的JSON，包装为JSON格式
            wrapped = json.dumps({
                "narrative": response,
                "data": {},
                "options": [],
                "time_passed": "片刻"
            }, ensure_ascii=False)
            return True, wrapped

    # ========== 指令处理器 ==========

    def _handle_status_command(self, user_input: str) -> GMResponse:
        """处理/状态指令"""
        data = {
            "name": self.player_state.name,
            "realm": self.player_state.realm,
            "level": self.player_state.level,
            "exp": self.player_state.exp,
            "max_exp": self.player_state.max_exp,
            "location": self.player_state.location,
            "world_year": self.player_state.world_year,
            "health": self.player_state.health,
            "mana": self.player_state.mana,
            "mood": self.player_state.mood,
        }

        narrative = f"""
【{self.player_state.name} 当前状态】

汝现处于{self.player_state.location}，时值{self.player_state.world_year}。

修为境界：{self.player_state.realm} {self.player_state.level}层
修为进度：{self.player_state.exp}/{self.player_state.max_exp}
生命状态：{self.player_state.health}/100
法力储备：{self.player_state.mana}/100
当前心境：{self.player_state.mood}
"""

        content = json.dumps({
            "narrative": narrative.strip(),
            "data": data,
            "type": "status"
        }, ensure_ascii=False)

        return GMResponse(content=content, is_json=True, command_type=CommandType.STATUS)

    def _handle_equipment_command(self, user_input: str) -> GMResponse:
        """处理/装备指令"""
        # 检查是否已解锁装备面板
        if "equipment" not in self.player_state.unlocked_panels:
            narrative = "汝尚未获得任何装备，无法查看装备信息。待获得首件法器后，此面板将自动开启。"
            data = {"unlocked": False, "equipment": []}
        else:
            narrative = "【装备面板】\n\n汝当前装备如下：\n（装备系统待完善）"
            data = {"unlocked": True, "equipment": []}

        content = json.dumps({
            "narrative": narrative,
            "data": data,
            "type": "equipment"
        }, ensure_ascii=False)

        return GMResponse(content=content, is_json=True, command_type=CommandType.EQUIPMENT)

    def _handle_inventory_command(self, user_input: str) -> GMResponse:
        """处理/物品指令"""
        if "inventory" not in self.player_state.unlocked_panels:
            narrative = "汝之储物袋空空如也，尚无物品可察。待获得首件宝物后，此面板将自动开启。"
            data = {"unlocked": False, "items": []}
        else:
            narrative = "【物品面板】\n\n汝之储物袋中有：\n（物品系统待完善）"
            data = {"unlocked": True, "items": []}

        content = json.dumps({
            "narrative": narrative,
            "data": data,
            "type": "inventory"
        }, ensure_ascii=False)

        return GMResponse(content=content, is_json=True, command_type=CommandType.INVENTORY)

    def _handle_events_command(self, user_input: str) -> GMResponse:
        """处理/事件指令"""
        narrative = """
【当前可参与事件】

1. 【修炼】于当前地点打坐修炼，吸纳天地灵气
2. 【探索】探查周遭环境，寻觅机缘
3. 【移动】前往其他地域
4. 【休憩】恢复身心状态

请述汝之所欲为。
"""

        data = {
            "events": [
                {"id": "cultivate", "name": "修炼", "desc": "打坐修炼，吸纳灵气"},
                {"id": "explore", "name": "探索", "desc": "探查环境，寻觅机缘"},
                {"id": "move", "name": "移动", "desc": "前往其他地域"},
                {"id": "rest", "name": "休憩", "desc": "恢复身心状态"},
            ]
        }

        content = json.dumps({
            "narrative": narrative.strip(),
            "data": data,
            "type": "events"
        }, ensure_ascii=False)

        return GMResponse(content=content, is_json=True, command_type=CommandType.EVENTS)

    def _handle_history_command(self, user_input: str) -> GMResponse:
        """处理/历史指令"""
        # 从Hindsight获取历史记忆
        history_items = []
        if self.memory:
            try:
                all_memories = self.memory.list_memories(limit=20)
                for item in all_memories.get("items", []):
                    history_items.append({
                        "text": item.get("text", ""),
                        "type": item.get("type", ""),
                        "context": item.get("context", "")
                    })
            except Exception as e:
                print(f"\033[33m[WARN] 获取历史记忆失败: {e}\033[0m")

        if not history_items:
            narrative = "【历史记录】\n\n汝之修仙之路方始，尚无重大事迹可载。"
        else:
            narrative = "【历史记录】\n\n汝之过往：\n"
            for i, item in enumerate(history_items[-10:], 1):
                text = item.get("text", "")[:50]
                narrative += f"\n{i}. {text}..."

        data = {"history": history_items}

        content = json.dumps({
            "narrative": narrative,
            "data": data,
            "type": "history"
        }, ensure_ascii=False)

        return GMResponse(content=content, is_json=True, command_type=CommandType.HISTORY)

    def _handle_all_command(self, user_input: str) -> GMResponse:
        """处理/全部指令"""
        # 组合所有面板信息
        status_resp = self._handle_status_command(user_input)
        equipment_resp = self._handle_equipment_command(user_input)
        inventory_resp = self._handle_inventory_command(user_input)
        events_resp = self._handle_events_command(user_input)
        history_resp = self._handle_history_command(user_input)

        # 解析JSON内容
        all_data = {
            "status": json.loads(status_resp.content),
            "equipment": json.loads(equipment_resp.content),
            "inventory": json.loads(inventory_resp.content),
            "events": json.loads(events_resp.content),
            "history": json.loads(history_resp.content),
        }

        narrative = f"""
【{self.player_state.name} - 完整面板】

═══ 状态 ═══
{all_data['status']['narrative']}

═══ 装备 ═══
{all_data['equipment']['narrative']}

═══ 物品 ═══
{all_data['inventory']['narrative']}

═══ 事件 ═══
{all_data['events']['narrative']}

═══ 历史 ═══
{all_data['history']['narrative']}
"""

        content = json.dumps({
            "narrative": narrative.strip(),
            "data": all_data,
            "type": "all"
        }, ensure_ascii=False)

        return GMResponse(content=content, is_json=True, command_type=CommandType.ALL)

    # ========== 公共API ==========

    def process(self, user_input: str) -> GMResponse:
        """
        处理用户输入的主入口

        Args:
            user_input: 用户输入内容

        Returns:
            GMResponse对象
        """
        if not user_input or not user_input.strip():
            return GMResponse(
                content=json.dumps({
                    "narrative": "汝欲何为？请述所求。",
                    "data": {},
                    "type": "error"
                }, ensure_ascii=False),
                is_json=True
            )

        # 1. 解析指令
        command_type = self._parse_command(user_input)

        # 2. 如果是已知指令，使用对应的处理器
        if command_type != CommandType.UNKNOWN:
            handler = self.command_handlers.get(command_type)
            if handler:
                response = handler(user_input)
                response.command_type = command_type

                # 保存到记忆
                self._save_to_memory(user_input, response.content, context=f"command:{command_type.value}")
                self._update_conversation_history(user_input, response.content)

                return response

        # 3. 普通对话，使用多轮迭代生成
        system_context = self._build_system_context(user_input)
        require_json = self._is_json_response_needed(user_input, command_type)

        response = self._iterative_generate(user_input, system_context, require_json)

        # 4. 保存到记忆和对话历史
        self._save_to_memory(user_input, response.content)
        self._update_conversation_history(user_input, response.content)

        return response

    def update_player_state(self, **kwargs):
        """更新玩家状态"""
        for key, value in kwargs.items():
            if hasattr(self.player_state, key):
                setattr(self.player_state, key, value)

                # 检查是否需要解锁面板
                if key == "realm" and value != "凡人":
                    if "status" not in self.player_state.unlocked_panels:
                        self.player_state.unlocked_panels.append("status")

    def add_world_memory(self, content: str, context: str = "world_event"):
        """添加世界记忆"""
        if self.world_memory:
            try:
                self.world_memory.retain(content, context=context)
            except Exception as e:
                print(f"\033[33m[WARN] 添加世界记忆失败: {e}\033[0m")

    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        stats = {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "conversation_history_count": len(self.conversation_history),
        }

        if self.memory:
            try:
                stats["player_memory"] = self.memory.get_stats()
            except Exception as e:
                stats["player_memory_error"] = str(e)

        if self.world_memory:
            try:
                stats["world_memory"] = self.world_memory.get_stats()
            except Exception as e:
                stats["world_memory_error"] = str(e)

        return stats

    def clear_memory(self, clear_short_term_only: bool = False):
        """清空记忆"""
        self.conversation_history = []

        if self.memory:
            if clear_short_term_only:
                self.memory.clear_short_term()
            else:
                self.memory.clear_bank()

    def close(self):
        """关闭GM控制中枢，释放资源"""
        if self.memory:
            self.memory.close()
        if self.world_memory:
            self.world_memory.close()


# ========== 便捷函数 ==========

def create_game_master(
    player_id: str,
    player_name: str = "",
    enable_memory: bool = True,
) -> GameMaster:
    """
    创建GM控制中枢实例

    Args:
        player_id: 玩家唯一标识
        player_name: 玩家名称
        enable_memory: 是否启用记忆系统

    Returns:
        GameMaster实例
    """
    return GameMaster(
        player_id=player_id,
        player_name=player_name,
        enable_memory=enable_memory,
    )


# ========== 测试代码 ==========

if __name__ == "__main__":
    print("=" * 50)
    print("《青墟灵修志》GM控制中枢测试")
    print("=" * 50)

    # 创建GM控制中枢
    gm = create_game_master(
        player_id="test-player-001",
        player_name="测试修士",
        enable_memory=True,
    )

    # 测试指令
    test_inputs = [
        "/状态",
        "/事件",
        "你好，我想开始修炼",
        "我想探索周围的环境",
    ]

    for user_input in test_inputs:
        print(f"\n{'='*50}")
        print(f"玩家输入: {user_input}")
        print("-" * 50)

        response = gm.process(user_input)

        print(f"指令类型: {response.command_type}")
        print(f"JSON格式: {response.is_json}")
        print(f"迭代次数: {response.iteration_count}")
        print(f"响应内容:")

        if response.is_json:
            try:
                data = json.loads(response.content)
                print(json.dumps(data, ensure_ascii=False, indent=2))
            except:
                print(response.content)
        else:
            print(response.content)

    # 打印记忆统计
    print(f"\n{'='*50}")
    print("记忆统计:")
    stats = gm.get_memory_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    # 关闭
    gm.close()
    print("\n测试完成")
