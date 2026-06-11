"""
Game Master - GM 主控类，负责游戏整体流程编排

管理双模型 LLM 连接（chat_model / world_model），
编排玩家聊天与世界演化的完整流程，
包括预拉数据、消息拼装、工具调用循环、落库分发。
"""

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Generator

import yaml
from openai import OpenAI

from gm_storage import GMStorage
from gm_tools import get_all_tools, match_and_execute_tool
from gm_logger import debug_log, info_log, warn_log, error_log, set_debug, is_debug
from action_definition_manager import ActionDefinitionManager, set_action_definition_manager, get_action_definition_manager
from time_cost_engine import TimeCostEngine, set_time_cost_engine

# 配置日志
logger = logging.getLogger(__name__)


class GameMaster:
    """GM 主控类，负责游戏整体流程编排"""

    # 工具调用最大循环次数，防止无限循环
    MAX_TOOL_LOOP = 10

    def __init__(self):
        """初始化 GameMaster"""
        # 1. 加载配置
        self.config: Dict[str, Any] = {}
        self._load_config()

        # 1.1 设置 debug 开关
        gm_cfg = self.config.get("gm", {})
        set_debug(gm_cfg.get("debug", True))
        debug_log("GM debug 模式已启用" if is_debug() else "GM debug 模式已关闭")

        # 2. 初始化双模型 LLM 连接
        self.chat_model: Optional[Any] = None
        self.world_model: Optional[Any] = None
        self._init_chat_model()
        self._init_world_model()

        # 3. 加载 GM system prompt 与 user prompt
        self.system_prompt: str = ""
        self._load_system_prompt()
        self.user_prompt: str = ""
        self._load_user_prompt()

        # 4. 初始化 GMStorage 存储层
        self.storage: Optional[GMStorage] = None
        self._init_storage()

        # 4.1 初始化动作定义管理器
        self.action_def_manager: Optional[ActionDefinitionManager] = None
        self._init_action_definition_manager()

        # 4.2 初始化耗时计算引擎
        self.time_cost_engine: Optional[TimeCostEngine] = None
        self._init_time_cost_engine()

        # 5. 加载全量 tools
        self.tools: List[Dict[str, Any]] = get_all_tools()

        info_log("GameMaster 初始化完成")

    # ================================================================
    # 初始化方法
    # ================================================================

    def _load_config(self) -> None:
        """加载配置文件"""
        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
                debug_log(f"加载配置文件: {config_path}")
            except Exception as e:
                error_log(f"加载配置文件失败: {e}")
                self.config = {}
        else:
            warn_log(f"配置文件不存在: {config_path}")
            self.config = {}

    def _init_chat_model(self) -> None:
        """
        初始化聊天模型配置（仅保存配置，实际实例按需创建）

        从 config.yaml 的 chat_model 段读取配置，
        支持环境变量覆盖。
        """
        chat_cfg = self.config.get("chat_model", {})
        self._chat_api_base = os.getenv("GM_CHAT_API_BASE", chat_cfg.get("api_base", "http://localhost:7778/v1"))
        self._chat_api_key = os.getenv("GM_CHAT_API_KEY", chat_cfg.get("api_key", "not-needed"))
        self._chat_model_name = os.getenv("GM_CHAT_MODEL_NAME", chat_cfg.get("model_name", "Qwen3.6-35B-A3B"))
        self._chat_temperature = float(os.getenv("GM_CHAT_TEMPERATURE", chat_cfg.get("temperature", 0.65)))
        self._chat_max_tokens = int(os.getenv("GM_CHAT_MAX_TOKENS", chat_cfg.get("max_tokens", 4096)))
        info_log(f"聊天模型配置加载完成 - 模型: {self._chat_model_name}, API: {self._chat_api_base}")

    def _create_chat_llm(self) -> OpenAI:
        """
        创建新的聊天模型实例（每次请求创建，避免 httpx.Client 线程安全问题）
        """
        client = OpenAI(
            base_url=self._chat_api_base,
            api_key=self._chat_api_key,
        )
        client._gm_model_name = self._chat_model_name
        client._gm_temperature = self._chat_temperature
        client._gm_max_tokens = self._chat_max_tokens
        return client

    def _init_world_model(self) -> None:
        """
        初始化世界模型配置（仅保存配置，实际实例按需创建）

        从 config.yaml 的 world_model 段读取配置，
        支持环境变量覆盖。
        """
        world_cfg = self.config.get("world_model", {})
        self._world_api_base = os.getenv("GM_WORLD_API_BASE", world_cfg.get("api_base", "http://localhost:7779/v1"))
        self._world_api_key = os.getenv("GM_WORLD_API_KEY", world_cfg.get("api_key", "not-needed"))
        self._world_model_name = os.getenv("GM_WORLD_MODEL_NAME", world_cfg.get("model_name", "Qwen3.6-27B-MTP"))
        self._world_temperature = float(os.getenv("GM_WORLD_TEMPERATURE", world_cfg.get("temperature", 0.7)))
        self._world_max_tokens = int(os.getenv("GM_WORLD_MAX_TOKENS", world_cfg.get("max_tokens", 8192)))
        info_log(f"世界模型配置加载完成 - 模型: {self._world_model_name}, API: {self._world_api_base}")

    def _create_world_llm(self) -> OpenAI:
        """
        创建新的世界模型实例（每次请求创建，避免 httpx.Client 线程安全问题）

        如果世界模型配置不可用，回退到聊天模型配置。
        """
        try:
            client = OpenAI(
                base_url=self._world_api_base,
                api_key=self._world_api_key,
            )
            client._gm_model_name = self._world_model_name
            client._gm_temperature = self._world_temperature
            client._gm_max_tokens = self._world_max_tokens
            return client
        except Exception as e:
            warn_log(f"创建世界模型实例失败，回退到聊天模型配置: {e}")
            return self._create_chat_llm()

    def _load_system_prompt(self) -> None:
        """加载 GM system prompt"""
        prompt_path = Path(__file__).parent / "prompts" / "gm_system.md"
        if prompt_path.exists():
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    self.system_prompt = f.read()
                debug_log(f"加载 GM system prompt: {prompt_path}")
                debug_log(f"GM system prompt 长度: {len(self.system_prompt)} 字符")
            except Exception as e:
                error_log(f"加载 GM system prompt 失败: {e}")
                self.system_prompt = "你是游戏GM，负责管理游戏世界。"
        else:
            warn_log(f"GM system prompt 文件不存在: {prompt_path}")
            self.system_prompt = "你是游戏GM，负责管理游戏世界。"

    def _load_user_prompt(self) -> None:
        """加载 GM user prompt（格式约束，追加在用户输入之后）"""
        prompt_path = Path(__file__).parent / "prompts" / "gm_user.md"
        if prompt_path.exists():
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    self.user_prompt = f.read()
                debug_log(f"加载 GM user prompt: {prompt_path}")
                debug_log(f"GM user prompt 长度: {len(self.user_prompt)} 字符")
            except Exception as e:
                error_log(f"加载 GM user prompt 失败: {e}")
                self.user_prompt = "请严格按照 JSON 格式返回，不要输出任何其他文字。"
        else:
            warn_log(f"GM user prompt 文件不存在: {prompt_path}")
            self.user_prompt = "请严格按照 JSON 格式返回，不要输出任何其他文字。"

    def _init_storage(self) -> None:
        """初始化 GMStorage 存储层"""
        try:
            self.storage = GMStorage(self.config)
            info_log("GMStorage 存储层初始化成功")
        except Exception as e:
            error_log(f"GMStorage 存储层初始化失败: {e}")
            self.storage = None

    def _init_action_definition_manager(self) -> None:
        """初始化动作定义管理器"""
        try:
            self.action_def_manager = ActionDefinitionManager(self.storage)
            set_action_definition_manager(self.action_def_manager)
            info_log("ActionDefinitionManager 初始化成功")
        except Exception as e:
            error_log(f"ActionDefinitionManager 初始化失败: {e}")
            self.action_def_manager = None

    def _init_time_cost_engine(self) -> None:
        """初始化耗时计算引擎"""
        try:
            self.time_cost_engine = TimeCostEngine(self.action_def_manager)
            set_time_cost_engine(self.time_cost_engine)
            info_log("TimeCostEngine 初始化成功")
        except Exception as e:
            error_log(f"TimeCostEngine 初始化失败: {e}")
            self.time_cost_engine = None

    # ================================================================
    # 核心方法
    # ================================================================

    def pre_context(self, uid: str, user_input: str) -> Tuple[str, str]:
        """
        预拉外围数据，返回 (memory_text, plot_text)

        Args:
            uid: 玩家唯一标识
            user_input: 用户输入文本

        Returns:
            (memory_text, plot_text) 元组
            - memory_text: 角色&世界历史记忆文本
            - plot_text: 相关过往剧情片段文本
        """
        debug_log(f"[pre_context] 开始预拉外围数据: uid={uid}, query={user_input[:80]}")
        memory_text = ""
        plot_text = ""

        try:
            # 拉取记忆
            if self.storage:
                debug_log(f"[pre_context] Step1 拉取记忆: uid={uid}")
                memory_text = self.storage.recall_all_memory(uid, user_input)
                debug_log(f"[pre_context] Step1 记忆拉取完成: 长度={len(memory_text)}")
            else:
                warn_log("storage 未初始化，跳过记忆拉取")
        except Exception as e:
            error_log(f"预拉记忆失败: uid={uid}, 错误: {e}")

        try:
            # 拉取剧情向量
            if self.storage:
                debug_log(f"[pre_context] Step2 拉取剧情向量: top_k=3")
                plot_results = self.storage.search_plot_vector(user_input, 3)
                if plot_results:
                    # 格式化为文本
                    parts = []
                    for i, item in enumerate(plot_results, 1):
                        content = item.get("content", "").strip()
                        score = item.get("score", 0.0)
                        if content:
                            parts.append(f"{i}. {content}")
                    plot_text = "\n".join(parts)
                debug_log(f"[pre_context] Step2 剧情拉取完成: 结果数={len(plot_results) if plot_results else 0}, 文本长度={len(plot_text)}")
            else:
                warn_log("storage 未初始化，跳过剧情拉取")
        except Exception as e:
            error_log(f"预拉剧情失败: uid={uid}, 错误: {e}")

        debug_log(f"[pre_context] 完成: memory长度={len(memory_text)}, plot长度={len(plot_text)}")
        return memory_text, plot_text

    def build_messages(
        self,
        uid: str,
        user_input: str,
        current_area: str,
        session_history: List[Dict[str, str]],
        memory_text: str,
        plot_text: str,
        req_type: str = "chat",
    ) -> List[Dict[str, str]]:
        """
        拼装 LLM messages 数组

        Args:
            uid: 玩家唯一标识
            user_input: 用户输入文本
            current_area: 当前区域
            session_history: 前端本地短时对话历史
            memory_text: 角色&世界历史记忆文本
            plot_text: 相关过往剧情片段文本
            req_type: 请求类型，"chat" 为普通聊天，"tutorial" 为引导教程

        Returns:
            拼装好的 messages 列表
        """
        debug_log(f"[build_messages] 开始拼装: uid={uid}, area={current_area}, history轮数={len(session_history)}")

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        debug_log(f"[build_messages] Step1 追加system prompt: 长度={len(self.system_prompt)}")

        # 追加前端本地短时对话
        if session_history:
            messages.extend(session_history)
            debug_log(f"[build_messages] Step2 追加session_history: {len(session_history)}条")
        else:
            debug_log("[build_messages] Step2 无session_history")

        # 追加角色档案信息
        player_data = {}
        if self.storage:
            try:
                player_data = self.storage.couch_get_player(uid)
            except Exception as e:
                error_log(f"获取玩家角色数据异常: uid={uid}, 错误: {e}")
                player_data = {}

        if player_data:
            character_text = self._format_character_profile(player_data)
            messages.append({
                "role": "system",
                "content": character_text,
            })
            debug_log(f"[build_messages] Step2.1 追加角色档案: 长度={len(character_text)}")
        else:
            warn_log(f"玩家角色数据为空，跳过角色信息注入: uid={uid}")
            debug_log("[build_messages] Step2.1 无角色数据，跳过角色信息注入")

        # 引导教程场景提示
        if req_type == "tutorial":
            tutorial_prompt = (
                "当前为新修士引导教程场景，请以引路仙灵的身份，逐步引导新修士了解青墟古域的世界观、"
                "基本操作、修炼入门之道。语气温和亲切，内容循序渐进，每次回复聚焦一个主题"
                "（如世界背景、修炼体系、操作指引等），并在末尾提供2-3个引导性建议动作供新修士选择。"
            )
            messages.append({
                "role": "system",
                "content": tutorial_prompt,
            })
            debug_log("[build_messages] Step2.2 追加引导教程场景提示")

        # 追加角色编号、当前区域、游戏时间、天气、历史记忆
        game_time_info = self._get_game_time_info()
        weather_info = self._get_weather_info()
        weather_str = f"{weather_info.get('weather', '未知')}·{weather_info.get('weather_desc', '未知')}"
        if weather_info.get('spirit_tide'):
            weather_str += f"，灵潮涌动（强度{weather_info.get('spirit_tide_intensity', 0)}）"
        memory_section = (
            f"【角色编号】{uid}\n"
            f"【当前区域】{current_area}\n"
            f"【游戏时间】{game_time_info}\n"
            f"【当前天气】{weather_str}\n"
            f"【角色&世界历史记忆】：{memory_text}"
        )
        messages.append({
            "role": "system",
            "content": memory_section,
        })
        debug_log(f"[build_messages] Step3 追加角色信息+记忆: 长度={len(memory_section)}")

        # 追加相关过往剧情片段
        plot_section = f"【相关过往剧情片段】：{plot_text}"
        messages.append({
            "role": "system",
            "content": plot_section,
        })
        debug_log(f"[build_messages] Step4 追加剧情片段: 长度={len(plot_section)}")

        # 追加用户输入
        messages.append({"role": "user", "content": user_input})
        debug_log(f"[build_messages] Step5 追加用户输入: 长度={len(user_input)}")

        # 追加 GM user prompt（格式约束，加载自 gm_user.md）
        messages.append({"role": "user", "content": self.user_prompt})
        debug_log(f"[build_messages] Step6 追加GM user prompt（格式约束）")

        debug_log(f"[build_messages] 完成: 总消息数={len(messages)}")
        return messages

    def llm_chat_loop(self, messages: List[Dict[str, str]], llm: OpenAI) -> Dict[str, Any]:
        """
        工具调用循环逻辑

        调用 LLM，如果返回包含 tool_calls 则执行工具并继续循环，
        直到 LLM 不再返回 tool_calls 或达到最大循环次数。
        LLM 返回非 JSON 文本时直接使用原始文本作为 dialog，不再重试生成。

        Args:
            messages: 消息列表
            llm: 使用的 LLM 实例 (OpenAI client)

        Returns:
            解析后的 JSON 字典

        Raises:
            RuntimeError: LLM 超过最大循环次数仍未返回结果
        """
        debug_log(f"[llm_chat_loop] 开始: messages数={len(messages)}, max_loop={self.MAX_TOOL_LOOP}")

        if not llm:
            error_log("LLM 实例为空，无法调用")
            return {"dialog": "系统异常，请稍后重试。", "actions": [], "player_update": {}, "ui_config": {}, "save_flag": ""}

        if not self.storage:
            error_log("storage 未初始化，工具无法执行")
            return {"dialog": "系统异常，存储层不可用。", "actions": [], "player_update": {}, "ui_config": {}, "save_flag": ""}

        # messages 已经是 OpenAI 格式，直接使用
        current_messages = list(messages)

        # 日志输出调用内容（原始 JSON 格式）
        messages_json = json.dumps(current_messages, ensure_ascii=False)
        debug_log(f"[llm_chat_loop] 请求消息(JSON): {messages_json[:3000]}{'...' if len(messages_json) > 3000 else ''}")

        for loop_count in range(self.MAX_TOOL_LOOP):
            debug_log(f"[llm_chat_loop] Step3 LLM调用循环第 {loop_count + 1}/{self.MAX_TOOL_LOOP} 次")

            try:
                response = llm.chat.completions.create(
                    model=getattr(llm, '_gm_model_name', self._chat_model_name),
                    messages=current_messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=getattr(llm, '_gm_temperature', 0.65),
                    max_tokens=getattr(llm, '_gm_max_tokens', 4096),
                    response_format={"type": "json_object"},
                )
                message = response.choices[0].message
                resp_content = message.content or ""
                debug_log(f"[llm_chat_loop] LLM响应成功: content长度={len(resp_content)}")
                debug_log(f"[llm_chat_loop] LLM响应内容: {resp_content[:2000]}{'...' if len(resp_content) > 2000 else ''}")
            except Exception as e:
                error_msg = str(e)
                # 检查是否是连接错误
                if "Connection error" in error_msg or "ConnectError" in error_msg or "connection" in error_msg.lower():
                    error_log(f"[Connection Error] LLM 连接失败")
                    error_log(f"  URL: {self._chat_api_base}")
                    error_log(f"  模型: {self._chat_model_name}")
                    error_log(f"  错误详情: {error_msg}")
                    return {
                        "dialog": f"连接大模型失败 - URL: {self._chat_api_base}, 模型: {self._chat_model_name}, 错误: {error_msg}",
                        "actions": [],
                        "player_update": {},
                        "ui_config": {},
                        "save_flag": ""
                    }
                else:
                    error_log(f"LLM 调用失败: {e}")
                    return {"dialog": f"大模型调用异常: {e}", "actions": [], "player_update": {}, "ui_config": {}, "save_flag": ""}

            # 检查是否有工具调用
            tool_calls = message.tool_calls

            if not tool_calls:
                # 无工具调用，尝试解析文本为 JSON
                content = message.content or ""
                debug_log(f"[llm_chat_loop] Step4 无工具调用，解析JSON响应: content长度={len(content)}")
                parsed = self._parse_json_response(content)
                return parsed

            # 有工具调用，逐个执行
            debug_log(f"[llm_chat_loop] Step4 收到 {len(tool_calls)} 个工具调用")

            # 将 assistant message 追加到消息列表
            current_messages.append({
                "role": "assistant",
                "content": resp_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            })

            for idx, tool_call in enumerate(tool_calls):
                tool_call_id = tool_call.id
                tool_name = tool_call.function.name
                tool_args_str = tool_call.function.arguments

                # 解析工具参数
                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError as e:
                    error_log(f"工具参数 JSON 解析失败: {e}")
                    tool_args = {}

                debug_log(f"[llm_chat_loop] Step4.{idx+1} 执行工具: {tool_name}, 参数预览={json.dumps(tool_args, ensure_ascii=False)[:150]}")
                info_log(f"执行工具: {tool_name}, 参数: {json.dumps(tool_args, ensure_ascii=False)[:200]}")

                # 执行工具
                try:
                    result = match_and_execute_tool(tool_name, tool_args, self.storage)
                    debug_log(f"[llm_chat_loop] Step4.{idx+1} 工具执行完成: {tool_name}, 结果长度={len(result)}")
                except Exception as e:
                    error_log(f"工具执行异常: {tool_name}, 错误: {e}")
                    result = json.dumps({"error": f"工具执行异常: {e}"}, ensure_ascii=False)

                # 构造工具结果消息追加到消息列表
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                })

        # 超过最大循环次数
        error_log(f"LLM 工具调用循环超过最大次数 {self.MAX_TOOL_LOOP}")
        return {"dialog": "系统处理超时，请稍后重试。", "actions": [], "player_update": {}, "ui_config": {}, "save_flag": ""}

    def handle_chat(
        self,
        uid: str,
        user_input: str,
        current_area: str,
        session_history: List[Dict[str, str]],
        req_type: str = "chat",
    ) -> Dict[str, Any]:
        """
        玩家聊天完整串行流程入口（req_type=chat）

        流程：忙碌检查 -> pre_context -> build_messages -> llm_chat_loop -> 解析 -> 耗时处理 -> save_dispatcher -> 返回

        Args:
            uid: 玩家唯一标识
            user_input: 用户输入文本
            current_area: 当前区域
            session_history: 前端本地短时对话历史
            req_type: 请求类型，"chat" 为普通聊天，"tutorial" 为引导教程

        Returns:
            {"dialog": ..., "player_update": ..., "ui_config": ..., "time_cost": ..., "busy_state": ...}
        """
        info_log(f"处理玩家聊天: uid={uid}, area={current_area}, input={user_input}")
        debug_log(f"[handle_chat] Step0 入参: uid={uid}, area={current_area}, history轮数={len(session_history)}, input={user_input[:100]}")

        try:
            # 0. 检查玩家动作约束状态
            busy_info = self._check_and_handle_busy(uid, user_input)
            if busy_info:
                return busy_info

            # 1. 预拉外围数据
            debug_log(f"[handle_chat] Step1 开始预拉外围数据: uid={uid}")
            memory_text, plot_text = self.pre_context(uid, user_input)
            debug_log(f"[handle_chat] Step1 预拉完成: memory长度={len(memory_text)}, plot长度={len(plot_text)}")

            # 2. 拼装消息
            debug_log(f"[handle_chat] Step2 开始拼装消息")
            messages = self.build_messages(
                uid=uid,
                user_input=user_input,
                current_area=current_area,
                session_history=session_history,
                memory_text=memory_text,
                plot_text=plot_text,
                req_type=req_type,
            )
            debug_log(f"[handle_chat] Step2 消息拼装完成: messages数={len(messages)}")

            # 3. 调用 LLM 循环（每次请求创建新实例，避免 httpx.Client 线程安全问题）
            debug_log(f"[handle_chat] Step3 开始LLM调用循环: model=chat_model")
            chat_llm = self._create_chat_llm()
            try:
                resp_json = self.llm_chat_loop(messages, chat_llm)
            finally:
                self._close_llm(chat_llm)
            debug_log(f"[handle_chat] Step3 LLM循环结束: save_flag={resp_json.get('save_flag', '')}, dialog长度={len(resp_json.get('dialog', ''))}")

            # 4. 提取字段
            dialog = resp_json.get("dialog", "")
            actions = resp_json.get("actions", [])
            player_update = resp_json.get("player_update", {})
            ui_config = resp_json.get("ui_config", {})
            save_flag = resp_json.get("save_flag", "")
            time_cost = resp_json.get("time_cost", 0)
            action_id = resp_json.get("action_id", "")
            debug_log(f"[handle_chat] Step4 字段提取: save_flag={save_flag}, time_cost={time_cost}, action_id={action_id}, actions={actions}, player_update字段={list(player_update.keys()) if player_update else '[]'}")

            # 5. 耗时处理：推进游戏时间 + 设置完整动作状态
            time_advance_info = None
            action_state = None
            time_cost_detail = None
            if time_cost and time_cost > 0:
                debug_log(f"[handle_chat] Step5 耗时处理: time_cost={time_cost}分钟, action_id={action_id}")
                # 构建上下文数据
                context = {
                    "weather": self._get_weather_info().get("weather", ""),
                    "spirit_tide": self._get_weather_info().get("spirit_tide", False),
                    "spirit_tide_intensity": self._get_weather_info().get("spirit_tide_intensity", 0),
                }
                # 获取玩家数据
                player_data = self.storage.couch_get_player(uid) if self.storage else {}
                time_advance_info, action_state, time_cost_detail = self._handle_time_cost(
                    uid=uid,
                    time_cost=time_cost,
                    action_desc=player_update.get("current_status", ""),
                    action_id=action_id,
                    player_data=player_data,
                    context=context,
                )
            else:
                debug_log(f"[handle_chat] Step5 跳过耗时处理: time_cost={time_cost}")

            # 6. 落库分发
            # 角色状态变更强制保存：player_update 非空时始终保存到数据库
            if self.storage and save_flag:
                debug_log(f"[handle_chat] Step6 开始落库分发: flag={save_flag}, uid={uid}")
                try:
                    self.storage.save_dispatcher(save_flag, uid, current_area, resp_json)
                    info_log(f"落库完成: uid={uid}, flag={save_flag}")
                    debug_log(f"[handle_chat] Step6 落库分发完成: flag={save_flag}")
                except Exception as e:
                    error_log(f"落库分发失败: uid={uid}, flag={save_flag}, 错误: {e}")
            elif self.storage and player_update:
                # save_flag 为空但有 player_update，强制保存角色状态
                debug_log(f"[handle_chat] Step6 强制保存角色状态: uid={uid}, player_update字段={list(player_update.keys())}")
                try:
                    self.storage.save_dispatcher("player_update", uid, current_area, resp_json)
                    info_log(f"强制保存角色状态完成: uid={uid}")
                except Exception as e:
                    error_log(f"强制保存角色状态失败: uid={uid}, 错误: {e}")
            else:
                debug_log(f"[handle_chat] Step6 跳过落库: save_flag={save_flag}, player_update为空")

            # 6.5 实体自动持久化（独立于 save_flag 机制）
            entities = resp_json.get("entities", [])
            if self.storage and entities:
                debug_log(f"[handle_chat] Step6.5 实体自动持久化: entities数={len(entities)}")
                try:
                    new_count = self.storage.save_entities_from_chat(uid, current_area, entities)
                    if new_count > 0:
                        info_log(f"实体自动持久化完成: uid={uid}, 新增={new_count}")
                except Exception as e:
                    error_log(f"实体自动持久化失败: uid={uid}, 错误: {e}")

            # 7. 返回结果（不暴露 save_flag 给前端）
            debug_log(f"[handle_chat] Step7 返回结果: dialog长度={len(dialog)}, actions={actions}, time_cost={time_cost}")
            result = {
                "dialog": dialog,
                "actions": actions,
                "player_update": player_update,
                "ui_config": ui_config,
                "time_cost": time_cost,
                "entities": entities,
            }
            if time_advance_info:
                result["time_advance"] = time_advance_info
            if action_state:
                result["action_state"] = action_state
            if time_cost_detail:
                result["time_cost_detail"] = time_cost_detail
            return result

        except Exception as e:
            error_log(f"处理玩家聊天异常: uid={uid}, 错误: {e}")
            return {
                "dialog": f"系统处理异常: {e}",
                "actions": [],
                "player_update": {},
                "ui_config": {},
                "time_cost": 0,
            }

    def world_tick_task(self) -> Dict[str, Any]:
        """
        定时世界演化流程入口（req_type=world_tick）

        流程：构建消息 -> llm_chat_loop（world_model）-> 解析 -> save_dispatcher -> 返回

        Returns:
            世界演化结果字典
        """
        info_log("开始世界演化任务...")
        debug_log("[world_tick] Step0 世界演化任务启动")

        try:
            # 1. 获取世界演化 prompt
            gm_cfg = self.config.get("gm", {})
            world_tick_cfg = gm_cfg.get("world_tick", {})
            world_tick_prompt = world_tick_cfg.get("prompt", "请根据当前世界状态，推演世界变化。")
            debug_log(f"[world_tick] Step1 获取演化prompt: 长度={len(world_tick_prompt)}")

            # 2. 构建消息
            messages: List[Dict[str, str]] = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": world_tick_prompt},
            ]
            debug_log(f"[world_tick] Step2 消息构建完成: messages数={len(messages)}")

            # 3. 调用 LLM 循环（每次请求创建新实例，避免 httpx.Client 线程安全问题）
            world_llm = self._create_world_llm()
            model_name = self._world_model_name
            debug_log(f"[world_tick] Step3 开始LLM调用循环: model={model_name}")
            try:
                resp_json = self.llm_chat_loop(messages, world_llm)
            finally:
                self._close_llm(world_llm)
            debug_log(f"[world_tick] Step3 LLM循环结束: save_flag={resp_json.get('save_flag', '')}")

            # 4. 落库分发（save_flag 应为 "world_snap"）
            save_flag = resp_json.get("save_flag", "")
            if self.storage and save_flag:
                debug_log(f"[world_tick] Step4 开始落库分发: flag={save_flag}")
                try:
                    # 世界演化使用空 uid 和空 area
                    self.storage.save_dispatcher(save_flag, "", "world", resp_json)
                    info_log(f"世界演化落库完成: flag={save_flag}")
                    debug_log(f"[world_tick] Step4 落库分发完成: flag={save_flag}")
                except Exception as e:
                    error_log(f"世界演化落库失败: flag={save_flag}, 错误: {e}")
            else:
                debug_log(f"[world_tick] Step4 跳过落库: save_flag={save_flag}")

            # 5. 返回结果
            info_log("世界演化任务完成")
            debug_log("[world_tick] Step5 世界演化任务完成")
            return resp_json

        except Exception as e:
            error_log(f"世界演化任务异常: {e}")
            return {
                "dialog": f"世界演化异常: {e}",
                "player_update": {},
                "ui_config": {},
                "save_flag": "",
            }

    # ================================================================
    # 辅助方法
    # ================================================================

    def _close_llm(self, llm: OpenAI) -> None:
        """
        安全关闭 LLM client

        每次请求创建的 OpenAI client 使用独立的连接池，
        请求结束后必须关闭以释放连接资源。
        """
        try:
            if hasattr(llm, 'close'):
                llm.close()
        except Exception as e:
            warn_log(f"关闭 LLM client 时出错: {e}")

    def _check_and_handle_busy(self, uid: str, user_input: str = "") -> Optional[Dict[str, Any]]:
        """
        检查玩家动作约束状态，如果当前动作禁止该操作则返回约束提示

        Args:
            uid: 玩家唯一标识
            user_input: 用户输入文本，用于识别操作类型

        Returns:
            约束提示响应字典，未受限时返回 None
        """
        try:
            from player_busy_manager import get_player_busy_manager
            busy_mgr = get_player_busy_manager()
            if not busy_mgr:
                return None

            # 检查是否有进行中的动作
            if not busy_mgr.has_active_action(uid):
                return None

            # 获取当前动作状态
            action_state = busy_mgr.get_action_state(uid)
            if not action_state:
                return None

            # 识别用户输入的操作类型
            operation = "unknown"
            if self.action_def_manager:
                operation = self.action_def_manager.recognize_operation(user_input)

            # 检查操作是否被允许
            allowed = busy_mgr.check_operation_allowed(uid, operation)
            if allowed:
                # 即时行为允许通过
                return None

            # 操作被禁止，返回约束提示
            action_name = action_state.get("action_name", "进行中")
            remaining = action_state.get("cooldown_remaining_seconds", 0)
            info_log(f"玩家操作被约束: uid={uid}, operation={operation}, action={action_name}, remaining={remaining}s")

            return {
                "dialog": f"你正在{action_name}之中，无法进行此操作。如需中断，请明确告知。",
                "actions": ["等待完成", "中断当前行为"],
                "player_update": {},
                "ui_config": {},
                "time_cost": 0,
                "action_state": action_state,
            }
        except Exception as e:
            error_log(f"检查动作约束异常: uid={uid}, 错误: {e}")
        return None

    def _handle_time_cost(
        self,
        uid: str,
        time_cost: int,
        action_desc: str,
        action_id: str = "",
        player_data: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
    ) -> tuple:
        """
        处理耗时行为：推进游戏时间 + 设置完整动作状态

        Args:
            uid: 玩家唯一标识
            time_cost: LLM 返回的参考游戏分钟数
            action_desc: 行为描述
            action_id: 动作类型ID
            player_data: 玩家数据字典
            context: 上下文数据（环境灵气、天气等）

        Returns:
            (time_advance_info, action_state, time_cost_detail) 元组
        """
        time_advance_info = None
        action_state = None
        time_cost_detail = None

        # 如果没有 action_id，尝试根据描述推断
        if not action_id and self.action_def_manager:
            operation = self.action_def_manager.recognize_operation(action_desc)
            if operation != "unknown":
                action_id = operation

        # 使用耗时计算引擎计算实际耗时
        if self.time_cost_engine and action_id:
            try:
                time_cost_detail = self.time_cost_engine.calculate(
                    action_id=action_id,
                    player_data=player_data or {},
                    context=context or {},
                )
                # 使用引擎计算的最终耗时替代 LLM 的参考值
                if time_cost_detail and time_cost_detail.get("final_time", 0) > 0:
                    time_cost = time_cost_detail["final_time"]
                    debug_log(f"耗时引擎覆盖: action={action_id}, 参考={time_cost} -> 计算={time_cost_detail['final_time']}")
            except Exception as e:
                error_log(f"耗时计算引擎异常: action={action_id}, 错误: {e}")
                time_cost_detail = None

        # 即时行为不设置动作状态
        if time_cost <= 0:
            return None, None, time_cost_detail

        # 推进游戏时间
        try:
            from world_time_service import get_world_time_service_instance
            wts = get_world_time_service_instance()
            if wts:
                time_advance_info = wts.advance_time_by_action(time_cost, action_desc)
                info_log(f"游戏时间已推进: uid={uid}, time_cost={time_cost}分钟, action={action_desc}")
        except Exception as e:
            error_log(f"推进游戏时间失败: uid={uid}, time_cost={time_cost}, 错误: {e}")

        # 设置完整动作状态
        try:
            from player_busy_manager import get_player_busy_manager
            busy_mgr = get_player_busy_manager()
            if busy_mgr and self.action_def_manager:
                definition = self.action_def_manager.get_action_definition(action_id)
                if definition:
                    restrictions = definition.get("restrictions", {})
                    action_name = definition.get("name", action_desc or "耗时行为")
                else:
                    restrictions = {}
                    action_name = action_desc or "耗时行为"

                # 获取当前游戏时间
                game_start_time = {}
                try:
                    from world_time_service import get_world_time_service_instance
                    wts = get_world_time_service_instance()
                    if wts:
                        ti = wts.get_current_time()
                        game_start_time = {
                            "date": ti.get("game_date", ""),
                            "hour": ti.get("game_hour", 0),
                            "minute": ti.get("game_minute", 0),
                        }
                except Exception:
                    pass

                base_time = time_cost_detail.get("base_time", time_cost) if time_cost_detail else time_cost
                modifiers = time_cost_detail.get("modifiers", []) if time_cost_detail else []

                action_state = busy_mgr.start_action(
                    uid=uid,
                    action_id=action_id or "unknown",
                    action_name=action_name,
                    base_time_cost=base_time,
                    final_time_cost=time_cost,
                    modifiers=modifiers,
                    game_start_time=game_start_time,
                    restrictions=restrictions,
                )
                info_log(f"玩家动作状态已设置: uid={uid}, action={action_id}, cooldown={action_state.get('cooldown_seconds', 0)}s")
        except Exception as e:
            error_log(f"设置动作状态失败: uid={uid}, 错误: {e}")

        return time_advance_info, action_state, time_cost_detail

    def _get_game_time_info(self) -> str:
        """
        获取当前游戏时间信息字符串

        Returns:
            格式化的游戏时间字符串，如"天元三千六百年·正月初一 卯时·清晨"
        """
        try:
            from world_time_service import get_world_time_service_instance
            wts = get_world_time_service_instance()
            if wts:
                time_info = wts.get_current_time()
                return f"{time_info.get('game_date', '未知')} {time_info.get('shichen_name', '')}·{time_info.get('shichen_period', '')}"
        except Exception as e:
            error_log(f"获取游戏时间信息失败: {e}")
        return "未知"

    def _get_weather_info(self) -> dict:
        """
        获取当前天气信息

        Returns:
            天气信息字典，包含 weather、weather_desc、spirit_tide
        """
        try:
            from weather_service import get_weather_service_instance
            ws = get_weather_service_instance()
            if ws:
                return ws.get_current_weather()
        except Exception as e:
            error_log(f"获取天气信息失败: {e}")
        return {"weather": "晴朗", "weather_desc": "微风", "spirit_tide": False}

    # 角色档案格式化时的已知字段列表（按展示顺序排列）
    _KNOWN_PROFILE_FIELDS = [
        "name", "realm", "realm_stage", "level",
        "health", "max_health", "mana", "max_mana",
        "spirit", "max_spirit",
        "current_location", "current_status", "clothing",
        "birth_date", "lifespan",
        "equipment", "inventory",
    ]

    # 字段中文标签映射
    _PROFILE_LABEL_MAP = {
        "name": "姓名",
        "realm": "境界",
        "realm_stage": "境界阶段",
        "level": "等级",
        "health": "生命",
        "max_health": "最大生命",
        "mana": "法力",
        "max_mana": "最大法力",
        "spirit": "神识",
        "max_spirit": "最大神识",
        "current_location": "当前位置",
        "current_status": "当前状态",
        "clothing": "衣着",
        "birth_date": "出生日期",
        "lifespan": "寿元",
        "equipment": "装备",
        "inventory": "储物袋",
    }

    # 需要排除的 CouchDB 内部字段
    _EXCLUDED_FIELDS = {"_id", "_rev"}

    def _format_character_profile(self, player_data: Dict[str, Any]) -> str:
        """
        将玩家数据格式化为角色档案结构化文本

        Args:
            player_data: 玩家数据字典

        Returns:
            格式化后的角色档案文本
        """
        lines = ["【角色档案】"]

        # 已知字段按顺序输出
        for field in self._KNOWN_PROFILE_FIELDS:
            value = player_data.get(field)
            if value is None or value == "" or value == []:
                continue

            label = self._PROFILE_LABEL_MAP.get(field, field)

            if field == "equipment" and isinstance(value, list):
                # 提取每个元素的 name 字段，用逗号连接
                names = [item.get("name", str(item)) for item in value if isinstance(item, dict)]
                if not names:
                    names = [str(item) for item in value]
                lines.append(f"{label}：{', '.join(names) if names else '无'}")
            elif field == "inventory" and isinstance(value, list):
                # 提取每个元素的 name 和 quantity，格式如"灵石x10, 丹药x3"
                inv_parts = []
                for item in value:
                    if isinstance(item, dict):
                        item_name = item.get("name", str(item))
                        quantity = item.get("quantity")
                        if quantity is not None:
                            inv_parts.append(f"{item_name}x{quantity}")
                        else:
                            inv_parts.append(item_name)
                    else:
                        inv_parts.append(str(item))
                lines.append(f"{label}：{', '.join(inv_parts) if inv_parts else '空'}")
            elif field in ("health", "max_health"):
                # 生命值合并为一行
                if field == "health":
                    max_val = player_data.get("max_health")
                    if max_val is not None:
                        lines.append(f"生命：{value}/{max_val}")
                    else:
                        lines.append(f"生命：{value}")
            elif field in ("mana", "max_mana"):
                if field == "mana":
                    max_val = player_data.get("max_mana")
                    if max_val is not None:
                        lines.append(f"法力：{value}/{max_val}")
                    else:
                        lines.append(f"法力：{value}")
            elif field in ("spirit", "max_spirit"):
                if field == "spirit":
                    max_val = player_data.get("max_spirit")
                    if max_val is not None:
                        lines.append(f"神识：{value}/{max_val}")
                    else:
                        lines.append(f"神识：{value}")
            elif field in ("max_health", "max_mana", "max_spirit"):
                # 已在 health/mana/spirit 中合并输出，跳过
                continue
            else:
                lines.append(f"{label}：{value}")

        # 收集已知字段名，用于后续排除
        known_set = set(self._KNOWN_PROFILE_FIELDS) | {"max_health", "max_mana", "max_spirit"}

        # 输出其他自定义字段
        for key, value in player_data.items():
            if key in self._EXCLUDED_FIELDS:
                continue
            if key in known_set:
                continue
            if value is None or value == "" or value == []:
                continue
            # 自定义字段直接用 key 作为标签
            if isinstance(value, (list, dict)):
                lines.append(f"{key}：{json.dumps(value, ensure_ascii=False)}")
            else:
                lines.append(f"{key}：{value}")

        return "\n".join(lines)

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        解析 LLM 返回的 JSON 文本

        尝试从返回文本中提取 JSON 对象，支持包含 markdown 代码块的情况。

        Args:
            content: LLM 返回的文本内容

        Returns:
            解析后的字典，解析失败返回默认结构
        """
        if not content or not content.strip():
            warn_log("LLM 返回内容为空")
            return {"dialog": "", "actions": [], "player_update": {}, "ui_config": {}, "save_flag": ""}

        # 尝试提取 markdown 代码块中的 JSON
        text = content.strip()
        if "```json" in text:
            start = text.find("```json") + len("```json")
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + len("```")
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        # 尝试解析 JSON，成功则直接使用，失败则将原始文本作为 dialog
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                debug_log("LLM 返回 JSON 解析成功")
                return result
        except json.JSONDecodeError:
            pass

        # 不是 JSON 格式，直接使用原始文本
        info_log(f"LLM 返回非 JSON 格式，直接使用原始文本: {content[:200]}")
        return {"dialog": content, "actions": [], "player_update": {}, "ui_config": {}, "save_flag": ""}

    def _extract_dialog_from_partial_json(self, accumulated: str, prev_dialog: str) -> str:
        """
        从部分 JSON 文本中增量提取 dialog 字段值

        Args:
            accumulated: 当前累积的完整文本
            prev_dialog: 之前已提取的 dialog 文本

        Returns:
            新增的 dialog 文本片段（不含之前已提取的部分）
        """
        # 尝试匹配 "dialog" 键及其字符串值
        # 匹配 "dialog"\s*:\s*" 后面的内容
        pattern = r'"dialog"\s*:\s*"'
        match = re.search(pattern, accumulated)
        if not match:
            return ""

        # 从 dialog 值开始位置
        value_start = match.end()
        remaining = accumulated[value_start:]

        # 提取字符串值（处理转义字符），找到结束引号
        dialog_chars = []
        i = 0
        while i < len(remaining):
            ch = remaining[i]
            if ch == '\\':
                # 转义字符，取下一个字符
                if i + 1 < len(remaining):
                    next_ch = remaining[i + 1]
                    escape_map = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', '/': '/'}
                    dialog_chars.append(escape_map.get(next_ch, next_ch))
                    i += 2
                else:
                    # 转义字符不完整，等待更多数据
                    break
            elif ch == '"':
                # 字符串结束
                break
            else:
                dialog_chars.append(ch)
                i += 1

        current_dialog = ''.join(dialog_chars)

        # 返回增量部分
        if len(current_dialog) > len(prev_dialog):
            return current_dialog[len(prev_dialog):]
        return ""

    def llm_chat_loop_stream(self, messages: List[Dict[str, str]], llm: OpenAI) -> Generator[str, None, None]:
        """
        流式工具调用循环逻辑，以 SSE 事件格式 yield 数据

        调用 LLM，如果返回包含 tool_calls 则执行工具并继续循环，
        直到 LLM 不再返回 tool_calls 或达到最大循环次数。
        最终响应阶段，增量提取 dialog 并流式输出。

        Args:
            messages: 消息列表
            llm: 使用的 LLM 实例 (OpenAI client)

        Yields:
            SSE 格式的事件字符串
        """
        debug_log(f"[llm_chat_loop_stream] 开始: messages数={len(messages)}, max_loop={self.MAX_TOOL_LOOP}")

        if not llm:
            error_log("LLM 实例为空，无法调用")
            yield self._sse_event("error", {"message": "LLM 实例为空"})
            return

        if not self.storage:
            error_log("storage 未初始化，工具无法执行")
            yield self._sse_event("error", {"message": "存储层不可用"})
            return

        current_messages = list(messages)

        # 日志输出调用内容（原始 JSON 格式）
        messages_json = json.dumps(current_messages, ensure_ascii=False)
        debug_log(f"[llm_chat_loop_stream] 请求消息(JSON): {messages_json[:3000]}{'...' if len(messages_json) > 3000 else ''}")

        for loop_count in range(self.MAX_TOOL_LOOP):
            debug_log(f"[llm_chat_loop_stream] Step3 LLM调用循环第 {loop_count + 1}/{self.MAX_TOOL_LOOP} 次")

            try:
                accumulated_content = ""
                prev_dialog = ""
                tool_calls_acc: Dict[int, Dict[str, Any]] = {}

                for chunk in llm.chat.completions.create(
                    model=getattr(llm, '_gm_model_name', self._chat_model_name),
                    messages=current_messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=getattr(llm, '_gm_temperature', 0.65),
                    max_tokens=getattr(llm, '_gm_max_tokens', 4096),
                    response_format={"type": "json_object"},
                    stream=True,
                ):
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    # 累积 content
                    if delta.content:
                        accumulated_content += delta.content
                        new_dialog = self._extract_dialog_from_partial_json(accumulated_content, prev_dialog)
                        if new_dialog:
                            prev_dialog += new_dialog
                            yield self._sse_event("dialog_delta", {"content": new_dialog})

                    # 累积 tool_calls
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.type:
                                tool_calls_acc[idx]["type"] = tc.type
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["function"]["arguments"] += tc.function.arguments

            except Exception as e:
                error_msg = str(e)
                # 检查是否是连接错误
                if "Connection error" in error_msg or "ConnectError" in error_msg or "connection" in error_msg.lower():
                    error_log(f"[Connection Error] LLM 流式连接失败")
                    error_log(f"  URL: {self._chat_api_base}")
                    error_log(f"  模型: {self._chat_model_name}")
                    error_log(f"  错误详情: {error_msg}")
                    yield self._sse_event("error", {
                        "message": f"连接大模型失败 - URL: {self._chat_api_base}, 模型: {self._chat_model_name}",
                        "detail": error_msg,
                        "url": self._chat_api_base,
                        "model": self._chat_model_name
                    })
                else:
                    error_log(f"LLM 流式调用失败: {e}")
                    yield self._sse_event("error", {"message": f"大模型调用异常: {e}", "detail": str(e)})
                return

            # 检查是否有工具调用
            if not tool_calls_acc:
                # 无工具调用，解析完整 JSON，非 JSON 则直接使用原始文本
                content = accumulated_content
                debug_log(f"[llm_chat_loop_stream] Step4 无工具调用，解析JSON响应: content长度={len(content)}")
                debug_log(f"[llm_chat_loop_stream] LLM完整响应内容: {content[:2000]}{'...' if len(content) > 2000 else ''}")
                resp_json = self._parse_json_response(content)

                # 发送完整结果事件
                yield self._sse_event("result", {
                    "dialog": resp_json.get("dialog", ""),
                    "entities": resp_json.get("entities", []),
                    "actions": resp_json.get("actions", []),
                    "player_update": resp_json.get("player_update", {}),
                    "ui_config": resp_json.get("ui_config", {}),
                    "save_flag": resp_json.get("save_flag", ""),
                })
                return

            # 有工具调用
            tool_calls_list = [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())]
            debug_log(f"[llm_chat_loop_stream] Step4 收到 {len(tool_calls_list)} 个工具调用")

            # 将 assistant message 追加到消息列表
            current_messages.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": tool_calls_list,
            })

            for idx, tool_call in enumerate(tool_calls_list):
                tool_call_id = tool_call["id"]
                tool_name = tool_call["function"]["name"]
                tool_args_str = tool_call["function"]["arguments"]

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError as e:
                    error_log(f"工具参数 JSON 解析失败: {e}")
                    tool_args = {}

                debug_log(f"[llm_chat_loop_stream] Step4.{idx+1} 执行工具: {tool_name}, 参数预览={json.dumps(tool_args, ensure_ascii=False)[:150]}")
                info_log(f"执行工具: {tool_name}, 参数: {json.dumps(tool_args, ensure_ascii=False)[:200]}")

                # 执行工具
                try:
                    result = match_and_execute_tool(tool_name, tool_args, self.storage)
                    debug_log(f"[llm_chat_loop_stream] Step4.{idx+1} 工具执行完成: {tool_name}, 结果长度={len(result)}")
                except Exception as e:
                    error_log(f"工具执行异常: {tool_name}, 错误: {e}")
                    result = json.dumps({"error": f"工具执行异常: {e}"}, ensure_ascii=False)

                # 构造工具结果消息追加到消息列表
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                })

        # 超过最大循环次数
        error_log(f"LLM 工具调用循环超过最大次数 {self.MAX_TOOL_LOOP}")
        yield self._sse_event("error", {"message": "系统处理超时，请稍后重试"})

    def _sse_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """
        构造 SSE 事件字符串

        Args:
            event_type: 事件类型
            data: 事件数据

        Returns:
            SSE 格式的事件字符串
        """
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def handle_chat_stream(
        self,
        uid: str,
        user_input: str,
        current_area: str,
        session_history: List[Dict[str, str]],
        req_type: str = "chat",
    ) -> Generator[str, None, None]:
        """
        玩家聊天流式串行流程入口（req_type=chat, stream=True）

        流程：忙碌检查 -> pre_context -> build_messages -> llm_chat_loop_stream -> 耗时处理 -> 落库分发 -> done

        Args:
            uid: 玩家唯一标识
            user_input: 用户输入文本
            current_area: 当前区域
            session_history: 前端本地短时对话历史
            req_type: 请求类型，"chat" 为普通聊天，"tutorial" 为引导教程

        Yields:
            SSE 格式的事件字符串
        """
        info_log(f"流式处理玩家聊天: uid={uid}, area={current_area}, input={user_input}")
        debug_log(f"[handle_chat_stream] Step0 入参: uid={uid}, area={current_area}, history轮数={len(session_history)}, input={user_input[:100]}")

        try:
            # 0. 检查玩家动作约束状态
            busy_info = self._check_and_handle_busy(uid, user_input)
            if busy_info:
                # 动作被约束，直接返回提示
                yield self._sse_event("result", {
                    "dialog": busy_info.get("dialog", ""),
                    "actions": busy_info.get("actions", []),
                    "player_update": busy_info.get("player_update", {}),
                    "ui_config": busy_info.get("ui_config", {}),
                    "save_flag": "",
                    "time_cost": 0,
                    "action_state": busy_info.get("action_state"),
                })
                yield self._sse_event("done", {})
                return

            # 1. 预拉外围数据
            debug_log(f"[handle_chat_stream] Step1 开始预拉外围数据: uid={uid}")
            memory_text, plot_text = self.pre_context(uid, user_input)
            debug_log(f"[handle_chat_stream] Step1 预拉完成: memory长度={len(memory_text)}, plot长度={len(plot_text)}")

            # 2. 拼装消息
            debug_log(f"[handle_chat_stream] Step2 开始拼装消息")
            messages = self.build_messages(
                uid=uid,
                user_input=user_input,
                current_area=current_area,
                session_history=session_history,
                memory_text=memory_text,
                plot_text=plot_text,
                req_type=req_type,
            )
            debug_log(f"[handle_chat_stream] Step2 消息拼装完成: messages数={len(messages)}")

            # 3. 流式调用 LLM 循环（每次请求创建新实例，避免 httpx.Client 线程安全问题）
            debug_log(f"[handle_chat_stream] Step3 开始LLM流式调用循环: model=chat_model")
            chat_llm = self._create_chat_llm()
            try:
                resp_json = {}
                for sse_event in self.llm_chat_loop_stream(messages, chat_llm):
                    yield sse_event
                    # 捕获 result 事件的数据用于后续落库
                    if sse_event.startswith("event: result"):
                        # 提取 data 行
                        for line in sse_event.split("\n"):
                            if line.startswith("data: "):
                                try:
                                    resp_json = json.loads(line[6:])
                                except json.JSONDecodeError:
                                    pass
            finally:
                self._close_llm(chat_llm)

            # 4. 耗时处理：推进游戏时间 + 设置完整动作状态
            time_cost = resp_json.get("time_cost", 0)
            action_id = resp_json.get("action_id", "")
            if time_cost and time_cost > 0:
                debug_log(f"[handle_chat_stream] Step4 耗时处理: time_cost={time_cost}分钟, action_id={action_id}")
                # 构建上下文数据
                context = {
                    "weather": self._get_weather_info().get("weather", ""),
                    "spirit_tide": self._get_weather_info().get("spirit_tide", False),
                    "spirit_tide_intensity": self._get_weather_info().get("spirit_tide_intensity", 0),
                }
                # 获取玩家数据
                player_data = self.storage.couch_get_player(uid) if self.storage else {}
                time_advance_info, action_state, time_cost_detail = self._handle_time_cost(
                    uid=uid,
                    time_cost=time_cost,
                    action_desc=resp_json.get("player_update", {}).get("current_status", ""),
                    action_id=action_id,
                    player_data=player_data,
                    context=context,
                )
                # 发送时间推进事件
                if time_advance_info:
                    yield self._sse_event("time_advance", time_advance_info)
                # 发送动作状态事件
                if action_state:
                    yield self._sse_event("action_state", action_state)
                # 发送耗时详情事件
                if time_cost_detail:
                    yield self._sse_event("time_cost_detail", time_cost_detail)
            else:
                debug_log(f"[handle_chat_stream] Step4 跳过耗时处理: time_cost={time_cost}")

            # 5. 落库分发
            # 角色状态变更强制保存：player_update 非空时始终保存到数据库
            save_flag = resp_json.get("save_flag", "")
            player_update = resp_json.get("player_update", {})
            if self.storage and save_flag:
                debug_log(f"[handle_chat_stream] Step5 开始落库分发: flag={save_flag}, uid={uid}")
                try:
                    self.storage.save_dispatcher(save_flag, uid, current_area, resp_json)
                    info_log(f"落库完成: uid={uid}, flag={save_flag}")
                except Exception as e:
                    error_log(f"落库分发失败: uid={uid}, flag={save_flag}, 错误: {e}")
            elif self.storage and player_update:
                # save_flag 为空但有 player_update，强制保存角色状态
                debug_log(f"[handle_chat_stream] Step5 强制保存角色状态: uid={uid}")
                try:
                    self.storage.save_dispatcher("player_update", uid, current_area, resp_json)
                    info_log(f"强制保存角色状态完成: uid={uid}")
                except Exception as e:
                    error_log(f"强制保存角色状态失败: uid={uid}, 错误: {e}")

            # 5.5 实体自动持久化（独立于 save_flag 机制）
            entities = resp_json.get("entities", [])
            if self.storage and entities:
                debug_log(f"[handle_chat_stream] Step5.5 实体自动持久化: entities数={len(entities)}")
                try:
                    new_count = self.storage.save_entities_from_chat(uid, current_area, entities)
                    if new_count > 0:
                        info_log(f"实体自动持久化完成: uid={uid}, 新增={new_count}")
                except Exception as e:
                    error_log(f"实体自动持久化失败: uid={uid}, 错误: {e}")

            # 6. 发送完成事件
            yield self._sse_event("done", {})

        except Exception as e:
            error_log(f"流式处理玩家聊天异常: uid={uid}, 错误: {e}")
            yield self._sse_event("error", {"message": f"系统处理异常: {e}"})


# ================================================================
# 全局实例缓存（单例模式）
# ================================================================

_game_master: Optional[GameMaster] = None


def get_game_master() -> GameMaster:
    """
    获取 GameMaster 单例

    Returns:
        GameMaster 实例
    """
    global _game_master
    if _game_master is None:
        _game_master = GameMaster()
    return _game_master
