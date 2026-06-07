"""
Hindsight Memory Store - 记忆库存储模块 (纯同步版本)

直接使用 httpx 同步客户端调用 Hindsight REST API，
避免 hindsight-client 内部 _run_async 导致的事件循环冲突。

前置条件:
    pip install httpx
    启动 Hindsight 服务 (默认端口 9998)

用法:
    from hindsight_memory import HindsightMemoryStore

    # 创建世界记忆库
    world_store = HindsightMemoryStore(
        bank_id="world",
        bank_name="青墟世界记忆库",
        base_url="http://localhost:9998",
    )

    # 存储记忆
    world_store.retain(
        content="青墟历三千零二十四年，灵潮爆发，灵气浓度骤增三倍",
        context="world_event",
        metadata={"year": 3024, "event_type": "灵潮"}
    )

    # 检索记忆
    memories = world_store.recall(
        query="灵潮事件",
        context="world_event",
        n=5
    )
"""

import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

import httpx

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


class HindsightMemoryStore:
    """
    Hindsight 记忆库存储类 (纯同步版本)

    直接使用 httpx 同步客户端调用 Hindsight REST API，
    避免 hindsight-client 内部 _run_async/asyncio 导致的事件循环冲突。
    """

    def __init__(
        self,
        bank_id: str,
        bank_name: Optional[str] = None,
        base_url: str = "http://localhost:9998",
        api_key: Optional[str] = None,
        short_term_window: int = 6,
        auto_retain: bool = False,
        mission: Optional[str] = None,
        disposition: Optional[Dict[str, int]] = None,
        timeout: float = 300.0,
    ):
        """
        初始化记忆库

        Args:
            bank_id: 记忆库唯一标识
            bank_name: 记忆库显示名称
            base_url: Hindsight 服务地址
            api_key: API 密钥（如需要）
            short_term_window: 短期记忆窗口大小
            auto_retain: 是否自动保留记忆
            mission: 记忆库任务描述（用于创建新库）
            disposition: 记忆库性格配置（用于创建新库）
            timeout: 请求超时时间（秒）
        """
        self.bank_id = bank_id
        self.bank_name = bank_name or bank_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.short_term_window = short_term_window
        self.auto_retain = auto_retain
        self.mission = mission
        self.disposition = disposition or {}
        self.timeout = timeout

        # 构建 HTTP 请求头
        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

        # 创建 httpx 同步客户端
        self._client: httpx.Client = httpx.Client(
            base_url=self.base_url,
            headers=self._headers,
            timeout=httpx.Timeout(timeout),
        )

        # 确保 bank 存在
        self._ensure_bank(self.bank_name, self.mission, self.disposition)
        info_log(f"Hindsight 记忆库连接成功 - Bank: {self.bank_id}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """
        发送同步 HTTP 请求

        Args:
            method: HTTP 方法
            path: API 路径
            json_data: JSON 请求体

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPStatusError: 当响应状态码非 2xx 时
        """
        response = self._client.request(
            method=method,
            url=path,
            json=json_data,
        )
        response.raise_for_status()
        return response

    def _ensure_bank(
        self,
        name: Optional[str] = None,
        mission: Optional[str] = None,
        disposition: Optional[Dict[str, int]] = None,
    ) -> bool:
        """
        确保记忆库存在，不存在则创建

        Args:
            name: 记忆库名称
            mission: 任务描述
            disposition: 性格配置

        Returns:
            True 表示成功
        """
        try:
            # 尝试获取现有 bank 配置
            self._request("GET", f"/v1/default/banks/{self.bank_id}/config")
            debug_log(f"记忆库已存在: {self.bank_id}")
            return True
        except Exception:
            # bank 不存在，创建新 bank
            try:
                body: Dict[str, Any] = {}
                if name:
                    body["name"] = name
                if mission:
                    body["mission"] = mission
                if disposition:
                    body["disposition_skepticism"] = disposition.get("skepticism")
                    body["disposition_literalism"] = disposition.get("literalism")
                    body["disposition_empathy"] = disposition.get("empathy")

                self._request("PUT", f"/v1/default/banks/{self.bank_id}", json_data=body)
                info_log(f"创建记忆库成功: {self.bank_id}")
                return True
            except Exception as e:
                error_log(f"确保记忆库存在时出错: {e}")
                raise

    def retain(
        self,
        content: str,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        存储记忆到 hindsight

        Args:
            content: 记忆内容
            context: 记忆上下文标签（如 "world_event", "character_history"）
            metadata: 附加元数据

        Returns:
            True 表示存储成功
        """
        if not content or not content.strip():
            warn_log("记忆内容为空，跳过存储")
            return False

        try:
            item: Dict[str, Any] = {
                "content": content.strip(),
                "context": context or "general",
            }
            if metadata:
                item["metadata"] = {k: str(v) for k, v in metadata.items()}

            body = {
                "items": [item],
                "async": False,
            }

            response = self._request(
                "POST",
                f"/v1/default/banks/{self.bank_id}/memories",
                json_data=body,
            )
            data = response.json()

            if data.get("success", False):
                debug_log(f"记忆存储成功 - context: {context}, content: {content[:50]}...")
                return True
            else:
                warn_log(f"记忆存储返回失败状态")
                return False
        except Exception as e:
            error_log(f"记忆存储失败: {e}")
            return False

    def recall(
        self,
        query: str,
        context: Optional[str] = None,
        n: int = 5,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        从 hindsight 检索记忆

        Args:
            query: 查询内容
            context: 上下文过滤（可选）
            n: 返回结果数量
            threshold: 相似度阈值（可选）

        Returns:
            记忆列表，每项包含 content, context, metadata, score
        """
        if not query or not query.strip():
            warn_log("查询内容为空")
            return []

        try:
            body: Dict[str, Any] = {
                "query": query.strip(),
                "budget": "mid",
                "max_tokens": 4096,
            }

            response = self._request(
                "POST",
                f"/v1/default/banks/{self.bank_id}/memories/recall",
                json_data=body,
            )
            data = response.json()

            memories = []
            results = data.get("results", [])
            # 限制返回数量
            results = results[:n] if n > 0 else results
            for i, result in enumerate(results):
                # 按返回顺序给递减分数（hindsight 已按相关度排序）
                score = 1.0 - (i * 0.05) if i < 10 else 0.5
                mem = {
                    "content": result.get("text", ""),
                    "context": result.get("context", ""),
                    "metadata": result.get("metadata", {}),
                    "score": score,
                }
                memories.append(mem)

            debug_log(f"记忆检索成功 - query: {query[:50]}..., 找到 {len(memories)} 条")
            return memories

        except Exception as e:
            error_log(f"记忆检索失败: {e}")
            return []

    def recall_with_history(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        n: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        结合对话历史检索相关记忆

        Args:
            query: 当前查询
            conversation_history: 对话历史
            context: 上下文过滤
            n: 返回结果数量

        Returns:
            相关记忆列表
        """
        # 构建增强查询：结合当前查询和对话历史
        enhanced_query = query
        if conversation_history:
            # 取最近3轮对话作为上下文
            recent_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
            history_text = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                for msg in recent_history
            ])
            enhanced_query = f"{query}\n\n对话上下文:\n{history_text}"

        return self.recall(enhanced_query, context=context, n=n)

    def get_recent_memories(
        self,
        context: Optional[str] = None,
        n: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        获取最近的记忆

        Args:
            context: 上下文过滤
            n: 返回数量

        Returns:
            最近记忆列表
        """
        try:
            params: Dict[str, Any] = {"limit": n, "offset": 0}
            if context:
                params["type"] = context

            response = self._client.request(
                method="GET",
                url=f"/v1/default/banks/{self.bank_id}/memories",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            result = []
            for mem in data.get("items", []):
                result.append({
                    "content": mem.get("content", ""),
                    "context": mem.get("context", ""),
                    "metadata": mem.get("metadata", {}),
                    "created_at": mem.get("created_at", ""),
                })

            return result

        except Exception as e:
            error_log(f"获取最近记忆失败: {e}")
            return []

    def delete_memory(self, memory_id: str) -> bool:
        """
        删除指定记忆

        注意：当前版本不支持删除单条记忆，
        如需清理请使用 clear_bank() 清空整个记忆库。

        Args:
            memory_id: 记忆 ID

        Returns:
            True 表示删除成功
        """
        warn_log("删除单条记忆在当前版本中不受支持，请使用 clear_bank() 清空记忆库")
        return False

    def clear_bank(self) -> bool:
        """
        清空整个记忆库（谨慎使用）

        Returns:
            True 表示清空成功
        """
        try:
            self._request("DELETE", f"/v1/default/banks/{self.bank_id}")
            info_log(f"记忆库已清空: {self.bank_id}")
            return True
        except Exception as e:
            error_log(f"清空记忆库失败: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        获取记忆库统计信息

        Returns:
            统计信息字典
        """
        try:
            # 获取 bank 配置
            response = self._request("GET", f"/v1/default/banks/{self.bank_id}/config")
            config_data = response.json()
            bank_name = ""
            if isinstance(config_data, dict):
                cfg = config_data.get("config", {})
                bank_name = cfg.get("name", "")

            # 获取记忆总数
            mem_response = self._client.request(
                method="GET",
                url=f"/v1/default/banks/{self.bank_id}/memories",
                params={"limit": 1},
            )
            mem_response.raise_for_status()
            mem_data = mem_response.json()
            total = mem_data.get("total", 0)

            return {
                "bank_id": self.bank_id,
                "bank_name": bank_name,
                "total_memories": total,
            }
        except Exception as e:
            error_log(f"获取统计信息失败: {e}")
            return {"bank_id": self.bank_id, "error": str(e)}

    def close(self) -> None:
        """关闭客户端连接"""
        if self._client:
            try:
                self._client.close()
                debug_log(f"Hindsight 连接已关闭: {self.bank_id}")
            except Exception as e:
                warn_log(f"关闭连接时出错: {e}")
            finally:
                self._client = None

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False


# ───────────────────────────────────────────────
# 便捷函数
# ───────────────────────────────────────────────

def get_memory_store(
    bank_id: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> HindsightMemoryStore:
    """
    获取或创建记忆库实例

    Args:
        bank_id: 记忆库 ID
        base_url: Hindsight 服务地址（默认从环境变量或配置读取）
        api_key: API 密钥

    Returns:
        HindsightMemoryStore 实例
    """
    if base_url is None:
        base_url = os.getenv("HINDSIGHT_BASE_URL", "http://localhost:9998")
    if api_key is None:
        api_key = os.getenv("HINDSIGHT_API_KEY")

    return HindsightMemoryStore(
        bank_id=bank_id,
        base_url=base_url,
        api_key=api_key,
    )


def get_world_memory_store(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> HindsightMemoryStore:
    """
    获取世界记忆库实例

    世界记忆库名称从配置中读取，默认 "world"

    Args:
        base_url: Hindsight 服务地址
        api_key: API 密钥

    Returns:
        HindsightMemoryStore 实例
    """
    import yaml
    config_path = Path(__file__).parent.parent / "config.yaml"
    world_bank = "world"

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            world_bank = config.get("hindsight", {}).get("world_bank", "world")
        except Exception:
            pass

    world_bank = os.getenv("WORLD_MEMORY_BANK", world_bank)

    return HindsightMemoryStore(
        bank_id=world_bank,
        bank_name="青墟世界记忆库",
        base_url=base_url or os.getenv("HINDSIGHT_BASE_URL", "http://localhost:9998"),
        api_key=api_key or os.getenv("HINDSIGHT_API_KEY"),
        mission=(
            "《青墟灵修志》世界记忆库。存储上古劫后遗落修仙世界的完整设定，"
            "包括世界起源、修行体系、势力阵营、生灵角色、资源物产、规则法则等。"
            "用于支撑 AI 多智能体自主演化与动态剧情生成。"
        ),
        disposition={
            "skepticism": 4,
            "literalism": 4,
            "empathy": 2,
        },
    )


def get_character_memory_store(
    character_id: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> HindsightMemoryStore:
    """
    获取角色记忆库实例

    Args:
        character_id: 角色唯一标识
        base_url: Hindsight 服务地址
        api_key: API 密钥

    Returns:
        HindsightMemoryStore 实例
    """
    return HindsightMemoryStore(
        bank_id=f"char_{character_id}",
        bank_name=f"角色 {character_id} 的记忆",
        base_url=base_url or os.getenv("HINDSIGHT_BASE_URL", "http://localhost:9998"),
        api_key=api_key or os.getenv("HINDSIGHT_API_KEY"),
        short_term_window=10,
        mission=f"角色 {character_id} 的个人记忆库，存储其经历、人际关系、成长历程等重要事件。",
        disposition={
            "skepticism": 3,
            "literalism": 3,
            "empathy": 5,
        },
    )


if __name__ == "__main__":
    # 测试代码
    info_log("测试 HindsightMemoryStore...")

    try:
        # 测试世界记忆库
        world_store = get_world_memory_store()
        stats = world_store.get_stats()
        info_log(f"世界记忆库统计: {stats}")

        # 测试存储
        test_content = "青墟历三千零二十四年，灵潮爆发，灵气浓度骤增三倍"
        success = world_store.retain(
            content=test_content,
            context="world_event",
            metadata={"year": 3024, "event_type": "灵潮"}
        )
        info_log(f"存储测试: {'成功' if success else '失败'}")

        # 测试检索
        memories = world_store.recall("灵潮", n=3)
        info_log(f"检索到 {len(memories)} 条记忆")
        for i, mem in enumerate(memories, 1):
            print(f"  {i}. [{mem['context']}] {mem['content'][:50]}... (score: {mem.get('score', 0):.3f})")

        world_store.close()

    except Exception as e:
        error_log(f"测试失败: {e}")
