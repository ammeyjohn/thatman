"""
Game Master - GM 主控类，负责游戏整体流程编排

管理双模型 LLM 连接（chat_model / world_model），
编排玩家聊天与世界演化的完整流程，
包括预拉数据、消息拼装、工具调用循环、落库分发。
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import yaml
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from gm_storage import GMStorage
from gm_tools import get_all_tools, match_and_execute_tool

# 配置日志
logger = logging.getLogger(__name__)


def debug_log(message: str):
    """输出 DEBUG 级别日志（灰色）"""
    logger.debug(message)
    print(f"\033[90m[DEBUG] {message}\033[0m")


def info_log(message: str):
    """输出 INFO 级别日志（白色）"""
    logger.info(message)
    print(f"\033[97m[INFO] {message}\033[0m")


def warn_log(message: str):
    """输出 WARN 级别日志（黄色）"""
    logger.warning(message)
    print(f"\033[93m[WARN] {message}\033[0m")


def error_log(message: str):
    """输出 ERROR 级别日志（红色）"""
    logger.error(message)
    print(f"\033[91m[ERROR] {message}\033[0m")


class GameMaster:
    """GM 主控类，负责游戏整体流程编排"""

    # 工具调用最大循环次数，防止无限循环
    MAX_TOOL_LOOP = 10

    def __init__(self):
        """初始化 GameMaster"""
        # 1. 加载配置
        self.config: Dict[str, Any] = {}
        self._load_config()

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

        从 config.yaml 的 gm.chat_model 段读取配置，
        支持环境变量覆盖。
        """
        gm_cfg = self.config.get("gm", {})
        chat_cfg = gm_cfg.get("chat_model", {})

        api_base = os.getenv("GM_CHAT_API_BASE", chat_cfg.get("api_base", "http://localhost:8080/v1"))
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

        从 config.yaml 的 gm.world_model 段读取配置，
        支持环境变量覆盖。
        初始化失败时回退到 chat_model。
        """
        gm_cfg = self.config.get("gm", {})
        world_cfg = gm_cfg.get("world_model", {})

        api_base = os.getenv("GM_WORLD_API_BASE", world_cfg.get("api_base", "http://localhost:8081/v1"))
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
        memory_text = ""
        plot_text = ""

        try:
            # 拉取记忆
            if self.storage:
                memory_text = self.storage.recall_all_memory(uid, user_input)
                debug_log(f"预拉记忆完成: uid={uid}, 长度={len(memory_text)}")
            else:
                warn_log("storage 未初始化，跳过记忆拉取")
        except Exception as e:
            error_log(f"预拉记忆失败: uid={uid}, 错误: {e}")

        try:
            # 拉取剧情向量
            if self.storage:
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
                debug_log(f"预拉剧情完成: uid={uid}, 长度={len(plot_text)}")
            else:
                warn_log("storage 未初始化，跳过剧情拉取")
        except Exception as e:
            error_log(f"预拉剧情失败: uid={uid}, 错误: {e}")

        return memory_text, plot_text

    def build_messages(
        self,
        uid: str,
        user_input: str,
        current_area: str,
        session_history: List[Dict[str, str]],
        memory_text: str,
        plot_text: str,
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

        Returns:
            拼装好的 messages 列表
        """
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
        ]

        # 追加前端本地短时对话
        if session_history:
            messages.extend(session_history)

        # 追加角色编号、当前区域、历史记忆
        messages.append({
            "role": "system",
            "content": (
                f"【角色编号】{uid}\n"
                f"【当前区域】{current_area}\n"
                f"【角色&世界历史记忆】：{memory_text}"
            ),
        })

        # 追加相关过往剧情片段
        messages.append({
            "role": "system",
            "content": f"【相关过往剧情片段】：{plot_text}",
        })

        # 追加用户输入
        messages.append({"role": "user", "content": user_input})

        debug_log(f"消息拼装完成: uid={uid}, 消息数={len(messages)}")
        return messages

    def llm_chat_loop(self, messages: List[Dict[str, str]], llm: ChatOpenAI) -> Dict[str, Any]:
        """
        工具调用循环逻辑

        调用 LLM，如果返回包含 tool_calls 则执行工具并继续循环，
        直到 LLM 不再返回 tool_calls 或达到最大循环次数。

        Args:
            messages: 消息列表
            llm: 使用的 LLM 实例

        Returns:
            解析后的 JSON 字典

        Raises:
            RuntimeError: LLM 超过最大循环次数仍未返回结果
        """
        if not llm:
            error_log("LLM 实例为空，无法调用")
            return {"dialog": "系统异常，请稍后重试。", "player_update": {}, "ui_config": {}, "save_flag": ""}

        if not self.storage:
            error_log("storage 未初始化，工具无法执行")
            return {"dialog": "系统异常，存储层不可用。", "player_update": {}, "ui_config": {}, "save_flag": ""}

        # 绑定工具
        llm_with_tools = llm.bind_tools(self.tools)

        # 转换消息为 LangChain 格式
        langchain_messages = self._convert_messages(messages)

        for loop_count in range(self.MAX_TOOL_LOOP):
            debug_log(f"LLM 调用循环第 {loop_count + 1} 次")

            try:
                ai_message = llm_with_tools.invoke(langchain_messages)
            except Exception as e:
                error_log(f"LLM 调用失败: {e}")
                return {"dialog": "大模型调用异常，请稍后重试。", "player_update": {}, "ui_config": {}, "save_flag": ""}

            # 检查是否有工具调用
            tool_calls = getattr(ai_message, "tool_calls", None)

            if not tool_calls:
                # 无工具调用，尝试解析文本为 JSON
                content = ai_message.content if hasattr(ai_message, "content") else str(ai_message)
                debug_log(f"LLM 返回纯文本，长度={len(content)}")
                return self._parse_json_response(content)

            # 有工具调用，逐个执行
            debug_log(f"LLM 返回 {len(tool_calls)} 个工具调用")

            # 将 AIMessage 追加到消息列表
            langchain_messages.append(ai_message)

            for tool_call in tool_calls:
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

                info_log(f"执行工具: {tool_name}, 参数: {json.dumps(tool_args, ensure_ascii=False)[:200]}")

                # 执行工具
                try:
                    result = match_and_execute_tool(tool_name, tool_args, self.storage)
                    debug_log(f"工具执行结果: {result[:200]}")
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
        return {"dialog": "系统处理超时，请稍后重试。", "player_update": {}, "ui_config": {}, "save_flag": ""}

    def handle_chat(
        self,
        uid: str,
        user_input: str,
        current_area: str,
        session_history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """
        玩家聊天完整串行流程入口（req_type=chat）

        流程：pre_context -> build_messages -> llm_chat_loop -> 解析 -> save_dispatcher -> 返回

        Args:
            uid: 玩家唯一标识
            user_input: 用户输入文本
            current_area: 当前区域
            session_history: 前端本地短时对话历史

        Returns:
            {"dialog": ..., "player_update": ..., "ui_config": ...}
        """
        info_log(f"处理玩家聊天: uid={uid}, area={current_area}, input={user_input[:50]}...")

        try:
            # 1. 预拉外围数据
            memory_text, plot_text = self.pre_context(uid, user_input)

            # 2. 拼装消息
            messages = self.build_messages(
                uid=uid,
                user_input=user_input,
                current_area=current_area,
                session_history=session_history,
                memory_text=memory_text,
                plot_text=plot_text,
            )

            # 3. 调用 LLM 循环（使用 chat_model）
            resp_json = self.llm_chat_loop(messages, self.chat_model)

            # 4. 提取字段
            dialog = resp_json.get("dialog", "")
            player_update = resp_json.get("player_update", {})
            ui_config = resp_json.get("ui_config", {})
            save_flag = resp_json.get("save_flag", "")

            # 5. 落库分发
            if self.storage and save_flag:
                try:
                    self.storage.save_dispatcher(save_flag, uid, current_area, resp_json)
                    info_log(f"落库完成: uid={uid}, flag={save_flag}")
                except Exception as e:
                    error_log(f"落库分发失败: uid={uid}, flag={save_flag}, 错误: {e}")

            # 6. 返回结果（不暴露 save_flag 给前端）
            return {
                "dialog": dialog,
                "player_update": player_update,
                "ui_config": ui_config,
            }

        except Exception as e:
            error_log(f"处理玩家聊天异常: uid={uid}, 错误: {e}")
            return {
                "dialog": "系统处理异常，请稍后重试。",
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

        try:
            # 1. 获取世界演化 prompt
            gm_cfg = self.config.get("gm", {})
            world_tick_cfg = gm_cfg.get("world_tick", {})
            world_tick_prompt = world_tick_cfg.get("prompt", "请根据当前世界状态，推演世界变化。")

            # 2. 构建消息
            messages: List[Dict[str, str]] = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": world_tick_prompt},
            ]

            # 3. 调用 LLM 循环（使用 world_model，回退到 chat_model）
            llm = self.world_model or self.chat_model
            resp_json = self.llm_chat_loop(messages, llm)

            # 4. 落库分发（save_flag 应为 "world_snap"）
            save_flag = resp_json.get("save_flag", "")
            if self.storage and save_flag:
                try:
                    # 世界演化使用空 uid 和空 area
                    self.storage.save_dispatcher(save_flag, "", "world", resp_json)
                    info_log(f"世界演化落库完成: flag={save_flag}")
                except Exception as e:
                    error_log(f"世界演化落库失败: flag={save_flag}, 错误: {e}")

            # 5. 返回结果
            info_log("世界演化任务完成")
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
            return {"dialog": "", "player_update": {}, "ui_config": {}, "save_flag": ""}

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
                return {"dialog": content, "player_update": {}, "ui_config": {}, "save_flag": ""}
        except json.JSONDecodeError as e:
            warn_log(f"LLM 返回 JSON 解析失败: {e}, 原始内容: {content[:200]}")
            # JSON 解析失败，将原始文本作为 dialog 返回
            return {"dialog": content, "player_update": {}, "ui_config": {}, "save_flag": ""}


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
