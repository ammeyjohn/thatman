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
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from gm_storage import GMStorage
from gm_tools import get_all_tools, match_and_execute_tool
from gm_logger import debug_log, info_log, warn_log, error_log, set_debug, is_debug

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
        self.chat_model: Optional[ChatOpenAI] = None
        self.world_model: Optional[ChatOpenAI] = None
        self._init_chat_model()
        self._init_world_model()

        # 3. 加载 GM system prompt
        self.system_prompt: str = ""
        self._load_system_prompt()

        # 4. 初始化 GMStorage 存储层
        self.storage: Optional[GMStorage] = None
        self._init_storage()

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
        初始化聊天模型（常驻，用于玩家聊天）

        从 config.yaml 的 chat_model 段读取配置，
        支持环境变量覆盖。
        """
        chat_cfg = self.config.get("chat_model", {})

        api_base = os.getenv("GM_CHAT_API_BASE", chat_cfg.get("api_base", "http://localhost:7778/v1"))
        api_key = os.getenv("GM_CHAT_API_KEY", chat_cfg.get("api_key", "not-needed"))
        model_name = os.getenv("GM_CHAT_MODEL_NAME", chat_cfg.get("model_name", "Qwen3.6-35B-A3B"))
        temperature = float(os.getenv("GM_CHAT_TEMPERATURE", chat_cfg.get("temperature", 0.65)))
        max_tokens = int(os.getenv("GM_CHAT_MAX_TOKENS", chat_cfg.get("max_tokens", 4096)))

        try:
            self.chat_model = ChatOpenAI(
                base_url=api_base,
                api_key=api_key,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
            info_log(f"聊天模型初始化成功 - 模型: {model_name}, API: {api_base}")
        except Exception as e:
            error_log(f"聊天模型初始化失败: {e}")
            raise

    def _init_world_model(self) -> None:
        """
        初始化世界模型（按需，用于世界演化）

        从 config.yaml 的 world_model 段读取配置，
        支持环境变量覆盖。
        初始化失败时回退到 chat_model。
        """
        world_cfg = self.config.get("world_model", {})

        api_base = os.getenv("GM_WORLD_API_BASE", world_cfg.get("api_base", "http://localhost:7779/v1"))
        api_key = os.getenv("GM_WORLD_API_KEY", world_cfg.get("api_key", "not-needed"))
        model_name = os.getenv("GM_WORLD_MODEL_NAME", world_cfg.get("model_name", "Qwen3.6-27B-MTP"))
        temperature = float(os.getenv("GM_WORLD_TEMPERATURE", world_cfg.get("temperature", 0.7)))
        max_tokens = int(os.getenv("GM_WORLD_MAX_TOKENS", world_cfg.get("max_tokens", 8192)))

        try:
            self.world_model = ChatOpenAI(
                base_url=api_base,
                api_key=api_key,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
            info_log(f"世界模型初始化成功 - 模型: {model_name}, API: {api_base}")
        except Exception as e:
            warn_log(f"世界模型初始化失败，回退到聊天模型: {e}")
            self.world_model = self.chat_model

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

    def _init_storage(self) -> None:
        """初始化 GMStorage 存储层"""
        try:
            self.storage = GMStorage(self.config)
            info_log("GMStorage 存储层初始化成功")
        except Exception as e:
            error_log(f"GMStorage 存储层初始化失败: {e}")
            self.storage = None

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

        # 追加角色编号、当前区域、历史记忆
        memory_section = (
            f"【角色编号】{uid}\n"
            f"【当前区域】{current_area}\n"
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

        debug_log(f"[build_messages] 完成: 总消息数={len(messages)}")
        return messages

    # JSON 重试最大次数
    MAX_JSON_RETRY = 2

    def llm_chat_loop(self, messages: List[Dict[str, str]], llm: ChatOpenAI) -> Dict[str, Any]:
        """
        工具调用循环逻辑

        调用 LLM，如果返回包含 tool_calls 则执行工具并继续循环，
        直到 LLM 不再返回 tool_calls 或达到最大循环次数。
        当 LLM 返回非 JSON 文本时，追加提示要求重新输出 JSON 格式，最多重试 MAX_JSON_RETRY 次。

        Args:
            messages: 消息列表
            llm: 使用的 LLM 实例

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

        # 绑定工具
        debug_log(f"[llm_chat_loop] Step1 绑定工具: tools数={len(self.tools)}")
        llm_with_tools = llm.bind_tools(self.tools)

        # 转换消息为 LangChain 格式
        debug_log("[llm_chat_loop] Step2 转换消息为LangChain格式")
        langchain_messages = self._convert_messages(messages)

        # JSON 重试计数器
        json_retry_count = 0

        for loop_count in range(self.MAX_TOOL_LOOP):
            debug_log(f"[llm_chat_loop] Step3 LLM调用循环第 {loop_count + 1}/{self.MAX_TOOL_LOOP} 次")

            try:
                ai_message = llm_with_tools.invoke(langchain_messages)
                debug_log(f"[llm_chat_loop] LLM响应成功: content长度={len(ai_message.content) if hasattr(ai_message, 'content') and ai_message.content else 0}")
            except Exception as e:
                error_log(f"LLM 调用失败: {e}")
                return {"dialog": "大模型调用异常，请稍后重试。", "actions": [], "player_update": {}, "ui_config": {}, "save_flag": ""}

            # 检查是否有工具调用
            tool_calls = getattr(ai_message, "tool_calls", None)

            if not tool_calls:
                # 无工具调用，尝试解析文本为 JSON
                content = ai_message.content if hasattr(ai_message, "content") else str(ai_message)
                debug_log(f"[llm_chat_loop] Step4 无工具调用，解析JSON响应: content长度={len(content)}")
                parsed = self._parse_json_response(content)

                # 检查是否解析失败（dialog 等于原始内容说明 JSON 解析失败）
                if parsed.get("__json_parse_failed__"):
                    parsed.pop("__json_parse_failed__", None)
                    if json_retry_count < self.MAX_JSON_RETRY:
                        json_retry_count += 1
                        warn_log(f"[llm_chat_loop] JSON解析失败，第 {json_retry_count}/{self.MAX_JSON_RETRY} 次重试")
                        # 追加 AI 回复和重试提示
                        langchain_messages.append(ai_message)
                        retry_prompt = (
                            "你上面的回复不是合法的JSON格式。请严格按照标准JSON格式重新输出，"
                            "包含 dialog、actions、player_update、ui_config、save_flag 字段。"
                            "将你上面的叙述内容放入 dialog 字段，禁止输出JSON以外的任何文字。"
                        )
                        langchain_messages.append(HumanMessage(content=retry_prompt))
                        continue
                    else:
                        warn_log(f"[llm_chat_loop] JSON重试已达上限 {self.MAX_JSON_RETRY} 次，使用回退结果")
                        return parsed

                return parsed

            # 有工具调用，逐个执行
            debug_log(f"[llm_chat_loop] Step4 收到 {len(tool_calls)} 个工具调用")

            # 将 AIMessage 追加到消息列表
            langchain_messages.append(ai_message)

            for idx, tool_call in enumerate(tool_calls):
                tool_call_id = tool_call.get("id", "") if isinstance(tool_call, dict) else getattr(tool_call, "id", "")
                function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}

                if isinstance(tool_call, dict):
                    tool_name = function.get("name", "")
                    tool_args_str = function.get("arguments", "{}")
                else:
                    tool_name = getattr(tool_call, "name", "") or getattr(function, "name", "")
                    tool_args_str = getattr(tool_call, "args", {}) if hasattr(tool_call, "args") else "{}"

                # 解析工具参数
                try:
                    if isinstance(tool_args_str, str):
                        tool_args = json.loads(tool_args_str)
                    elif isinstance(tool_args_str, dict):
                        tool_args = tool_args_str
                    else:
                        tool_args = {}
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
                from langchain_core.messages import ToolMessage
                langchain_messages.append(
                    ToolMessage(content=result, tool_call_id=tool_call_id)
                )

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

        流程：pre_context -> build_messages -> llm_chat_loop -> 解析 -> save_dispatcher -> 返回

        Args:
            uid: 玩家唯一标识
            user_input: 用户输入文本
            current_area: 当前区域
            session_history: 前端本地短时对话历史
            req_type: 请求类型，"chat" 为普通聊天，"tutorial" 为引导教程

        Returns:
            {"dialog": ..., "player_update": ..., "ui_config": ...}
        """
        info_log(f"处理玩家聊天: uid={uid}, area={current_area}, input={user_input}")
        debug_log(f"[handle_chat] Step0 入参: uid={uid}, area={current_area}, history轮数={len(session_history)}, input={user_input[:100]}")

        try:
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

            # 3. 调用 LLM 循环（使用 chat_model）
            debug_log(f"[handle_chat] Step3 开始LLM调用循环: model=chat_model")
            resp_json = self.llm_chat_loop(messages, self.chat_model)
            debug_log(f"[handle_chat] Step3 LLM循环结束: save_flag={resp_json.get('save_flag', '')}, dialog长度={len(resp_json.get('dialog', ''))}")

            # 4. 提取字段
            dialog = resp_json.get("dialog", "")
            actions = resp_json.get("actions", [])
            player_update = resp_json.get("player_update", {})
            ui_config = resp_json.get("ui_config", {})
            save_flag = resp_json.get("save_flag", "")
            debug_log(f"[handle_chat] Step4 字段提取: save_flag={save_flag}, actions={actions}, player_update字段={list(player_update.keys()) if player_update else '[]'}")

            # 5. 落库分发
            if self.storage and save_flag:
                debug_log(f"[handle_chat] Step5 开始落库分发: flag={save_flag}, uid={uid}")
                try:
                    self.storage.save_dispatcher(save_flag, uid, current_area, resp_json)
                    info_log(f"落库完成: uid={uid}, flag={save_flag}")
                    debug_log(f"[handle_chat] Step5 落库分发完成: flag={save_flag}")
                except Exception as e:
                    error_log(f"落库分发失败: uid={uid}, flag={save_flag}, 错误: {e}")
            else:
                debug_log(f"[handle_chat] Step5 跳过落库: save_flag={save_flag}, storage={'已初始化' if self.storage else '未初始化'}")

            # 6. 返回结果（不暴露 save_flag 给前端）
            debug_log(f"[handle_chat] Step6 返回结果: dialog长度={len(dialog)}, actions={actions}")
            return {
                "dialog": dialog,
                "actions": actions,
                "player_update": player_update,
                "ui_config": ui_config,
            }

        except Exception as e:
            error_log(f"处理玩家聊天异常: uid={uid}, 错误: {e}")
            return {
                "dialog": "系统处理异常，请稍后重试。",
                "actions": [],
                "player_update": {},
                "ui_config": {},
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

            # 3. 调用 LLM 循环（使用 world_model，回退到 chat_model）
            llm = self.world_model or self.chat_model
            model_name = "world_model" if self.world_model else "chat_model(fallback)"
            debug_log(f"[world_tick] Step3 开始LLM调用循环: model={model_name}")
            resp_json = self.llm_chat_loop(messages, llm)
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
                "dialog": "世界演化异常。",
                "player_update": {},
                "ui_config": {},
                "save_flag": "",
            }

    # ================================================================
    # 辅助方法
    # ================================================================

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
        "inventory": "背包",
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

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List:
        """
        将字典格式的消息列表转换为 LangChain 消息对象列表

        Args:
            messages: 字典格式的消息列表

        Returns:
            LangChain 消息对象列表
        """
        langchain_messages = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:  # user 或其他
                langchain_messages.append(HumanMessage(content=content))

        return langchain_messages

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

        try:
            result = json.loads(text)
            if isinstance(result, dict):
                debug_log("LLM 返回 JSON 解析成功")
                return result
            else:
                warn_log(f"LLM 返回 JSON 不是字典类型: {type(result)}")
                return {"dialog": content, "actions": [], "player_update": {}, "ui_config": {}, "save_flag": "", "__json_parse_failed__": True}
        except json.JSONDecodeError as e:
            warn_log(f"LLM 返回 JSON 解析失败: {e}, 原始内容: {content[:200]}")
            # JSON 解析失败，将原始文本作为 dialog 返回，标记解析失败供重试判断
            return {"dialog": content, "actions": [], "player_update": {}, "ui_config": {}, "save_flag": "", "__json_parse_failed__": True}

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

    def llm_chat_loop_stream(self, messages: List[Dict[str, str]], llm: ChatOpenAI) -> Generator[str, None, None]:
        """
        流式工具调用循环逻辑，以 SSE 事件格式 yield 数据

        调用 LLM，如果返回包含 tool_calls 则执行工具并继续循环，
        直到 LLM 不再返回 tool_calls 或达到最大循环次数。
        最终响应阶段，增量提取 dialog 并流式输出。

        Args:
            messages: 消息列表
            llm: 使用的 LLM 实例

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

        # 绑定工具
        debug_log(f"[llm_chat_loop_stream] Step1 绑定工具: tools数={len(self.tools)}")
        llm_with_tools = llm.bind_tools(self.tools)

        # 转换消息为 LangChain 格式
        debug_log("[llm_chat_loop_stream] Step2 转换消息为LangChain格式")
        langchain_messages = self._convert_messages(messages)

        # JSON 重试计数器
        json_retry_count = 0

        for loop_count in range(self.MAX_TOOL_LOOP):
            debug_log(f"[llm_chat_loop_stream] Step3 LLM调用循环第 {loop_count + 1}/{self.MAX_TOOL_LOOP} 次")

            try:
                # 使用流式调用
                full_chunk = None
                accumulated_content = ""
                prev_dialog = ""

                for chunk in llm_with_tools.stream(langchain_messages):
                    # 累积 chunk
                    if full_chunk is None:
                        full_chunk = chunk
                    else:
                        full_chunk = full_chunk + chunk

                    # 累积内容文本
                    if hasattr(chunk, 'content') and chunk.content:
                        accumulated_content += chunk.content

                        # 尝试增量提取 dialog
                        new_dialog = self._extract_dialog_from_partial_json(accumulated_content, prev_dialog)
                        if new_dialog:
                            prev_dialog += new_dialog
                            yield self._sse_event("dialog_delta", {"content": new_dialog})

            except Exception as e:
                error_log(f"LLM 流式调用失败: {e}")
                yield self._sse_event("error", {"message": f"大模型调用异常: {e}"})
                return

            # 检查是否有工具调用
            tool_calls = getattr(full_chunk, "tool_calls", None) if full_chunk else None

            if not tool_calls:
                # 无工具调用，解析完整 JSON
                content = full_chunk.content if full_chunk and hasattr(full_chunk, 'content') else ""
                debug_log(f"[llm_chat_loop_stream] Step4 无工具调用，解析JSON响应: content长度={len(content)}")
                resp_json = self._parse_json_response(content)

                # 检查是否解析失败，尝试重试
                if resp_json.get("__json_parse_failed__"):
                    resp_json.pop("__json_parse_failed__", None)
                    if json_retry_count < self.MAX_JSON_RETRY:
                        json_retry_count += 1
                        warn_log(f"[llm_chat_loop_stream] JSON解析失败，第 {json_retry_count}/{self.MAX_JSON_RETRY} 次重试")
                        # 追加 AI 回复和重试提示
                        if full_chunk:
                            langchain_messages.append(full_chunk)
                        retry_prompt = (
                            "你上面的回复不是合法的JSON格式。请严格按照标准JSON格式重新输出，"
                            "包含 dialog、actions、player_update、ui_config、save_flag 字段。"
                            "将你上面的叙述内容放入 dialog 字段，禁止输出JSON以外的任何文字。"
                        )
                        langchain_messages.append(HumanMessage(content=retry_prompt))
                        continue
                    else:
                        warn_log(f"[llm_chat_loop_stream] JSON重试已达上限 {self.MAX_JSON_RETRY} 次，使用回退结果")

                # 发送完整结果事件
                yield self._sse_event("result", {
                    "dialog": resp_json.get("dialog", ""),
                    "actions": resp_json.get("actions", []),
                    "player_update": resp_json.get("player_update", {}),
                    "ui_config": resp_json.get("ui_config", {}),
                    "save_flag": resp_json.get("save_flag", ""),
                })
                return

            # 有工具调用，逐个执行
            debug_log(f"[llm_chat_loop_stream] Step4 收到 {len(tool_calls)} 个工具调用")

            # 将 AIMessage 追加到消息列表
            langchain_messages.append(full_chunk)

            for idx, tool_call in enumerate(tool_calls):
                tool_call_id = tool_call.get("id", "") if isinstance(tool_call, dict) else getattr(tool_call, "id", "")
                function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}

                if isinstance(tool_call, dict):
                    tool_name = function.get("name", "")
                    tool_args_str = function.get("arguments", "{}")
                else:
                    tool_name = getattr(tool_call, "name", "") or getattr(function, "name", "")
                    tool_args_str = getattr(tool_call, "args", {}) if hasattr(tool_call, "args") else "{}"

                # 解析工具参数
                try:
                    if isinstance(tool_args_str, str):
                        tool_args = json.loads(tool_args_str)
                    elif isinstance(tool_args_str, dict):
                        tool_args = tool_args_str
                    else:
                        tool_args = {}
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
                from langchain_core.messages import ToolMessage
                langchain_messages.append(
                    ToolMessage(content=result, tool_call_id=tool_call_id)
                )

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

        流程：pre_context -> build_messages -> llm_chat_loop_stream -> 落库分发 -> done

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

            # 3. 流式调用 LLM 循环
            debug_log(f"[handle_chat_stream] Step3 开始LLM流式调用循环: model=chat_model")
            resp_json = {}
            for sse_event in self.llm_chat_loop_stream(messages, self.chat_model):
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

            # 4. 落库分发
            save_flag = resp_json.get("save_flag", "")
            if self.storage and save_flag:
                debug_log(f"[handle_chat_stream] Step4 开始落库分发: flag={save_flag}, uid={uid}")
                try:
                    self.storage.save_dispatcher(save_flag, uid, current_area, resp_json)
                    info_log(f"落库完成: uid={uid}, flag={save_flag}")
                except Exception as e:
                    error_log(f"落库分发失败: uid={uid}, flag={save_flag}, 错误: {e}")

            # 5. 发送完成事件
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
