"""
Layout Generator - 面板布局生成模块

调用 Qwen3-Coder-Next-Q4 模型，根据角色/世界数据动态生成面板展示布局。
生成时参考旧布局，进行增量更新，确保风格符合 DESIGN.md 规范。
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List

import httpx
import yaml
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from gm_storage import GMStorage
from gm_logger import debug_log, info_log, warn_log, error_log

# 配置日志
logger = logging.getLogger(__name__)


class LayoutGenerator:
    """面板布局生成器，调用 LLM 动态生成面板布局"""

    def __init__(self, config: Dict[str, Any], storage: GMStorage):
        """
       初始化 LayoutGenerator

        Args:
            config: 配置字典
            storage: GMStorage 实例
        """
        self.config = config
        self.storage = storage

        # 保存布局生成模型配置（不创建常驻实例，避免 httpx.Client 线程安全问题）
        layout_cfg = config.get("layout_model", {})
        self._layout_api_base = os.getenv("GM_LAYOUT_API_BASE", layout_cfg.get("api_base", "http://localhost:7777/v1"))
        self._layout_api_key = os.getenv("GM_LAYOUT_API_KEY", layout_cfg.get("api_key", "not-needed"))
        self._layout_model_name = os.getenv("GM_LAYOUT_MODEL_NAME", layout_cfg.get("model_name", "Qwen3-Coder-Next-Q4"))
        self._layout_temperature = float(os.getenv("GM_LAYOUT_TEMPERATURE", layout_cfg.get("temperature", 0.3)))
        self._layout_max_tokens = int(os.getenv("GM_LAYOUT_MAX_TOKENS", layout_cfg.get("max_tokens", 4096)))

        # 加载布局生成 system prompt
        self.system_prompt: str = ""
        self._load_system_prompt()

        info_log("LayoutGenerator 初始化完成")

    def _create_layout_llm(self) -> ChatOpenAI:
        """创建新的布局生成模型实例（每次请求创建，避免 httpx.Client 线程安全问题）"""
        http_client = httpx.Client(
            limits=httpx.Limits(max_keepalive_connections=0),
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
        )
        llm = ChatOpenAI(
            base_url=self._layout_api_base,
            api_key=self._layout_api_key,
            model=self._layout_model_name,
            temperature=self._layout_temperature,
            max_tokens=self._layout_max_tokens,
            http_client=http_client,
        )
        llm._httpx_client = http_client
        return llm

    def _close_llm(self, llm: ChatOpenAI) -> None:
        """安全关闭 LLM 实例内部的 httpx.Client"""
        try:
            httpx_client = getattr(llm, '_httpx_client', None)
            if httpx_client is not None:
                httpx_client.close()
                llm._httpx_client = None
        except Exception as e:
            warn_log(f"关闭布局模型 httpx.Client 时出错: {e}")

    def _load_system_prompt(self) -> None:
        """加载布局生成 system prompt"""
        prompt_path = Path(__file__).parent / "prompts" / "layout_system.md"
        if prompt_path.exists():
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    self.system_prompt = f.read()
                debug_log(f"加载布局 system prompt: {prompt_path}")
            except Exception as e:
                error_log(f"加载布局 system prompt 失败: {e}")
                self.system_prompt = "你是面板布局生成器，根据数据生成面板HTML代码。"
        else:
            warn_log(f"布局 system prompt 文件不存在: {prompt_path}")
            self.system_prompt = "你是面板布局生成器，根据数据生成面板HTML代码。"

    def generate_layout(
        self,
        uid: str,
        panel_type: str,
        current_data: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成面板布局

        流程：读取旧布局 -> 构建提示 -> 调用 LLM -> 提取 HTML -> 保存 -> 返回

        Args:
            uid: 玩家唯一标识
            panel_type: 面板类型，"character" 或 "world"
            current_data: 当前角色或世界数据
            game_context: 游戏上下文信息，包含最近事件、角色记忆、世界记忆、世界快照等

        Returns:
            生成结果字典，包含 panel_type、layout、version
        """
        info_log(f"开始生成布局: uid={uid}, panel_type={panel_type}")
        debug_log(f"[generate_layout] 当前数据字段: {list(current_data.keys()) if isinstance(current_data, dict) else 'not_dict'}")

        try:
            # 1. 读取旧布局
            old_layout = {}
            if self.storage:
                old_layout = self.storage.couch_get_layout(uid, panel_type)
                if old_layout:
                    # 移除 CouchDB 内部字段
                    old_layout.pop("_id", None)
                    old_layout.pop("_rev", None)
                    old_layout.pop("uid", None)
                    old_layout.pop("panel_type", None)
                    old_layout.pop("created_at", None)
                    old_layout.pop("updated_at", None)
                    old_layout_html = old_layout.get('layout', '')
                    debug_log(f"[generate_layout] 读取旧布局成功: HTML长度={len(old_layout_html) if isinstance(old_layout_html, str) else 'not_str'}")
                else:
                    debug_log("[generate_layout] 无旧布局")

            # 2. 构建提示
            messages = self._build_layout_prompt(panel_type, old_layout, current_data, game_context)
            debug_log(f"[generate_layout] 构建提示完成: messages数={len(messages)}")

            # 3. 调用 LLM
            layout_llm = self._create_layout_llm()
            try:
                langchain_messages = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "system":
                        langchain_messages.append(SystemMessage(content=content))
                    else:
                        langchain_messages.append(HumanMessage(content=content))

                # 日志输出调用内容（原始 JSON 格式）
                messages_json = json.dumps(messages, ensure_ascii=False)
                debug_log(f"[generate_layout] 请求消息(JSON): {messages_json[:3000]}{'...' if len(messages_json) > 3000 else ''}")

                debug_log("[generate_layout] 开始调用 LLM")
                ai_message = layout_llm.invoke(langchain_messages)
                content = ai_message.content if hasattr(ai_message, "content") else str(ai_message)
                debug_log(f"[generate_layout] LLM 响应完成: content长度={len(content)}")
                debug_log(f"[generate_layout] LLM 响应内容: {content[:2000]}{'...' if len(content) > 2000 else ''}")
            finally:
                self._close_llm(layout_llm)

            # 4. 提取 HTML
            layout_html = self._extract_html(content)
            if not layout_html:
                warn_log("布局生成结果为空或无有效 HTML")
                return {"panel_type": panel_type, "layout": "", "version": ""}

            debug_log(f"[generate_layout] HTML 提取成功: 长度={len(layout_html)}")

            # 5. 保存到 CouchDB
            version = uuid.uuid4().hex[:8]
            layout_doc = {
                "layout": layout_html,
                "version": version,
            }

            if self.storage:
                self.storage.couch_save_layout(uid, panel_type, layout_doc)
                info_log(f"布局保存成功: uid={uid}, panel_type={panel_type}, version={version}")

            # 6. 返回结果
            return {
                "panel_type": panel_type,
                "layout": layout_html,
                "version": version,
            }

        except Exception as e:
            error_log(f"生成布局异常: uid={uid}, panel_type={panel_type}, 错误: {e}")
            return {"panel_type": panel_type, "layout": "", "version": "", "error": str(e)}

    def _build_layout_prompt(
        self,
        panel_type: str,
        old_layout: Dict[str, Any],
        current_data: Dict[str, Any],
        game_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """
        构建布局生成请求的 messages

        Args:
            panel_type: 面板类型
            old_layout: 旧布局数据
            current_data: 当前角色/世界数据
            game_context: 游戏上下文信息，包含最近事件、角色记忆、世界记忆、世界快照等

        Returns:
            消息列表
        """
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
        ]

        # 构建用户提示
        user_parts = []

        # 面板类型
        user_parts.append(f"请生成【{panel_type}】面板的布局。")

        # 当前数据
        if current_data:
            # 过滤掉空值字段
            filtered_data = {}
            for key, value in current_data.items():
                if value is not None and value != "" and value != 0 and value != [] and value != {}:
                    filtered_data[key] = value

            if filtered_data:
                user_parts.append(f"\n当前数据：\n{json.dumps(filtered_data, ensure_ascii=False, indent=2)}")

        # 游戏上下文信息
        if game_context:
            context_parts = []

            # 最近游戏事件
            recent_events = game_context.get("recent_events")
            if recent_events:
                events_text = recent_events if isinstance(recent_events, str) else json.dumps(recent_events, ensure_ascii=False, indent=2)
                context_parts.append(f"【最近游戏事件】\n{events_text}")

            # 角色记忆
            character_memories = game_context.get("character_memories")
            if character_memories:
                memory_text = character_memories if isinstance(character_memories, str) else json.dumps(character_memories, ensure_ascii=False, indent=2)
                context_parts.append(f"【角色记忆】\n{memory_text}")

            # 世界记忆
            world_memories = game_context.get("world_memories")
            if world_memories:
                memory_text = world_memories if isinstance(world_memories, str) else json.dumps(world_memories, ensure_ascii=False, indent=2)
                context_parts.append(f"【世界记忆】\n{memory_text}")

            # 世界快照
            world_snapshot = game_context.get("world_snapshot")
            if world_snapshot:
                context_parts.append(f"【世界快照】\n{json.dumps(world_snapshot, ensure_ascii=False, indent=2)}")

            if context_parts:
                user_parts.append("\n" + "\n".join(context_parts))
                debug_log(f"[build_layout_prompt] 添加游戏上下文信息: {len(context_parts)}项")

        # 旧布局参考
        if old_layout and old_layout.get("layout"):
            old_layout_html = old_layout["layout"]
            if isinstance(old_layout_html, str) and old_layout_html.strip():
                user_parts.append(f"\n旧布局 HTML 参考（保留仍有效的结构，仅调整变化部分）：\n{old_layout_html}")

        # 生成指令
        user_parts.append("\n请根据以上信息生成新的面板 HTML 代码。注意：当前数据中不存在的字段不要在布局中显示，所有动态值通过 JS 从 window.__LAYOUT_DATA__ 读取。")
        if game_context:
            user_parts.append("请结合游戏上下文和当前数据，生成最能反映当前游戏状态的面板布局。布局应突出当前最重要的信息，如角色当前状态、所处环境、正在发生的事件等。")

        messages.append({"role": "user", "content": "\n".join(user_parts)})

        debug_log(f"[build_layout_prompt] 用户提示长度: {len(messages[-1]['content'])}")

        return messages

    def _extract_html(self, content: str) -> str:
        """
        从 LLM 返回内容中提取 HTML 代码

        支持以下格式：
        1. 纯 HTML 代码
        2. markdown 代码块包裹的 HTML（```html ... ```）

        Args:
            content: LLM 返回的文本内容

        Returns:
            提取出的 HTML 代码字符串，失败返回空字符串
        """
        if not content or not content.strip():
            warn_log("LLM 返回内容为空")
            return ""

        text = content.strip()

        # 尝试提取 markdown 代码块中的 HTML
        if "```html" in text:
            start = text.find("```html") + len("```html")
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + len("```")
            # 跳过可能的语言标识行（如 html、htm 等）
            first_newline = text.find("\n", start)
            if first_newline > start and first_newline - start < 20:
                start = first_newline + 1
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        # 验证是否包含 HTML 标签
        if "<" in text and ">" in text:
            debug_log("HTML 代码提取成功")
            return text
        else:
            warn_log(f"LLM 返回内容不包含有效 HTML: {content[:200]}")
            return ""


# ================================================================
# 全局实例缓存（单例模式）
# ================================================================

_layout_generator: Optional[LayoutGenerator] = None


def get_layout_generator(config: Dict[str, Any], storage: GMStorage) -> LayoutGenerator:
    """
    获取 LayoutGenerator 单例

    Args:
        config: 配置字典
        storage: GMStorage 实例

    Returns:
        LayoutGenerator 实例
    """
    global _layout_generator
    if _layout_generator is None:
        _layout_generator = LayoutGenerator(config, storage)
    return _layout_generator
