"""
Hindsight 记忆模块
使用 hindsight-client 访问 Hindsight 服务实现长期记忆

核心设计：
1. 使用 hindsight-client 连接 Hindsight API 服务
2. 对话内容通过 retain 存储到 hindsight memory bank
3. 通过 recall 检索相关记忆
4. 通过 reflect 生成基于记忆的回复

Hindsight 服务需要单独启动：
    pip install hindsight-api
    export OPENAI_API_KEY=sk-xxx
    export HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY
    hindsight-api

或使用 Docker：
    docker run -it --pull always --name hindsight --restart unless-stopped \\
        -p 8888:8888 -p 9999:9999 \\
        -e HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY \\
        -v $HOME/.hindsight-docker:/home/hindsight/.pg0 \\
        ghcr.io/vectorize-io/hindsight:latest
"""
import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from langchain.memory import ConversationBufferWindowMemory
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


try:
    from hindsight_client import Hindsight
    HINDSIGHT_AVAILABLE = True
except ImportError:
    HINDSIGHT_AVAILABLE = False


class HindsightMemoryStore:
    """
    Hindsight 记忆存储系统
    
    使用 hindsight-client 访问 Hindsight 服务：
    - retain: 存储记忆
    - recall: 检索记忆 (语义+关键词+图谱+时间)
    - reflect: 基于记忆生成回复
    """
    
    def __init__(
        self,
        bank_id: str = "default-agent",
        bank_name: Optional[str] = None,
        base_url: str = "http://localhost:8888",
        api_key: Optional[str] = None,
        short_term_window: int = 6,
        auto_retain: bool = True,
        mission: Optional[str] = None,
        disposition: Optional[Dict[str, int]] = None,
    ):
        """
        初始化 Hindsight 记忆存储
        
        Args:
            bank_id: Memory bank ID
            bank_name: Memory bank 显示名称
            base_url: Hindsight API 服务地址
            api_key: API 密钥（如需要）
            short_term_window: 短期记忆窗口大小
            auto_retain: 是否自动保存对话到 hindsight
            mission: Bank 的使命描述
            disposition: 性格配置 {skepticism, literalism, empathy} (1-5)
        """
        if not HINDSIGHT_AVAILABLE:
            raise ImportError(
                "hindsight-client 未安装。请运行: pip install hindsight-client\n"
                "Hindsight 服务需要单独启动，详见: https://hindsight.vectorize.io"
            )
        
        self.bank_id = bank_id
        self.base_url = base_url or os.getenv("HINDSIGHT_BASE_URL", "http://localhost:8888")
        self.api_key = api_key or os.getenv("HINDSIGHT_API_KEY")
        self.auto_retain = auto_retain
        
        # 初始化 hindsight client
        self.client = Hindsight(
            base_url=self.base_url,
            api_key=self.api_key,
        )
        
        # 创建或确认 memory bank
        self._ensure_bank(bank_name or bank_id, mission, disposition)
        
        # 短期记忆（用于构建上下文）
        self.short_term = ConversationBufferWindowMemory(
            k=short_term_window,
            return_messages=True,
            memory_key="history",
        )
    
    def _ensure_bank(
        self,
        name: str,
        mission: Optional[str] = None,
        disposition: Optional[Dict[str, int]] = None,
    ):
        """确保 memory bank 存在"""
        try:
            # 尝试创建 bank（如果已存在会返回已有 bank）
            self.client.create_bank(
                bank_id=self.bank_id,
                name=name,
                mission=mission or "AI assistant memory bank",
                disposition=disposition or {
                    "skepticism": 3,
                    "literalism": 2,
                    "empathy": 4,
                },
            )
        except Exception as e:
            # Bank 可能已存在，忽略错误
            print(f"\033[90m[DEBUG] Bank ensure: {e}\033[0m")
    
    def retain(
        self,
        content: str,
        context: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        document_id: Optional[str] = None,
    ) -> bool:
        """
        存储记忆到 hindsight
        
        Args:
            content: 记忆内容
            context: 上下文标签
            metadata: 元数据
            document_id: 文档 ID（用于关联相关记忆）
        """
        try:
            self.client.retain(
                bank_id=self.bank_id,
                content=content,
                context=context or "conversation",
                metadata=metadata or {},
                document_id=document_id,
            )
            return True
        except Exception as e:
            print(f"\033[33m[WARN] Hindsight retain 失败: {e}\033[0m")
            return False
    
    def retain_conversation(
        self,
        user_msg: str,
        ai_msg: str,
        context: str = "conversation",
    ) -> bool:
        """
        存储对话到 hindsight
        
        Args:
            user_msg: 用户消息
            ai_msg: AI 回复
            context: 上下文标签
        """
        # 同时保存到短期记忆
        self.short_term.save_context(
            {"input": user_msg},
            {"output": ai_msg}
        )
        
        if not self.auto_retain:
            return False
        
        # 存储到 hindsight
        content = f"用户: {user_msg}\nAI: {ai_msg}"
        return self.retain(content, context=context)
    
    def recall(
        self,
        query: str,
        types: Optional[List[str]] = None,
        budget: str = "mid",
        max_tokens: int = 4096,
    ) -> List[Dict[str, Any]]:
        """
        从 hindsight 检索记忆
        
        Args:
            query: 查询内容
            types: 记忆类型过滤 ["world", "experience", "observation"]
            budget: 搜索深度 "low"/"mid"/"high"
            max_tokens: 最大 token 数
            
        Returns:
            记忆列表，每项包含 text, type, entities, context 等
        """
        try:
            result = self.client.recall(
                bank_id=self.bank_id,
                query=query,
                types=types,
                budget=budget,
                max_tokens=max_tokens,
            )
            
            memories = []
            for r in result.results:
                memories.append({
                    "id": getattr(r, "id", ""),
                    "text": getattr(r, "text", ""),
                    "type": getattr(r, "type", ""),
                    "context": getattr(r, "context", ""),
                    "entities": getattr(r, "entities", []),
                    "mentioned_at": getattr(r, "mentioned_at", ""),
                })
            return memories
        except Exception as e:
            print(f"\033[33m[WARN] Hindsight recall 失败: {e}\033[0m")
            return []
    
    def reflect(self, query: str, budget: str = "mid", context: Optional[str] = None) -> Optional[str]:
        """
        使用 hindsight reflect 生成基于记忆的回复
        
        Args:
            query: 查询内容
            budget: 搜索深度
            context: 额外上下文
            
        Returns:
            生成的回复文本
        """
        try:
            answer = self.client.reflect(
                bank_id=self.bank_id,
                query=query,
                budget=budget,
                context=context or "",
            )
            return answer.text
        except Exception as e:
            print(f"\033[33m[WARN] Hindsight reflect 失败: {e}\033[0m")
            return None
    
    def get_short_term_history(self) -> List[Dict[str, str]]:
        """获取短期对话历史"""
        messages = self.short_term.load_memory_variables({}).get("history", [])
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
        return result
    
    def build_context(
        self,
        query: str,
        max_memories: int = 5,
        include_recent: bool = True,
    ) -> str:
        """
        构建记忆上下文
        
        使用 hindsight recall 检索相关记忆
        """
        parts = []
        
        # 1. 从 hindsight 检索相关记忆
        memories = self.recall(query, budget="mid")
        
        if memories:
            hindsight_text = "【已记住的信息】\n"
            for mem in memories[:max_memories]:
                text = mem.get("text", "")
                mem_type = mem.get("type", "")
                if text:
                    hindsight_text += f"• [{mem_type}] {text}\n"
            
            if hindsight_text != "【已记住的信息】\n":
                parts.append(hindsight_text)
        
        # 2. 最近对话（短期记忆）
        if include_recent:
            recent = self.get_short_term_history()
            if recent:
                recent_text = "【最近对话】\n"
                for msg in recent[-6:]:
                    role = "用户" if msg["role"] == "user" else "AI"
                    recent_text += f"{role}: {msg['content']}\n"
                parts.append(recent_text)
        
        return "\n".join(parts)
    
    def list_memories(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """列出 hindsight 中的所有记忆"""
        try:
            result = self.client.list_memories(
                bank_id=self.bank_id,
                limit=limit,
                offset=offset,
            )
            return {
                "total": getattr(result, "total", 0),
                "items": [
                    {
                        "text": getattr(item, "text", ""),
                        "type": getattr(item, "type", ""),
                        "context": getattr(item, "context", ""),
                    }
                    for item in getattr(result, "items", [])
                ],
            }
        except Exception as e:
            print(f"\033[33m[WARN] Hindsight list_memories 失败: {e}\033[0m")
            return {"total": 0, "items": []}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取 hindsight 记忆统计"""
        try:
            result = self.list_memories(limit=1)
            return {
                "bank_id": self.bank_id,
                "base_url": self.base_url,
                "total_memories": result.get("total", 0),
                "short_term_messages": len(self.get_short_term_history()),
            }
        except Exception as e:
            return {
                "bank_id": self.bank_id,
                "error": str(e),
            }
    
    def clear_short_term(self):
        """清空短期记忆"""
        self.short_term.clear()
    
    def clear_bank(self):
        """清空 hindsight bank（删除并重建）"""
        try:
            # 删除 bank
            self.client.delete_bank(bank_id=self.bank_id)
            # 重建
            self._ensure_bank(self.bank_id)
            print(f"\033[32m[INFO] Hindsight bank '{self.bank_id}' 已清空\033[0m")
        except Exception as e:
            print(f"\033[33m[WARN] 清空 bank 失败: {e}\033[0m")
    
    def close(self):
        """关闭 hindsight client"""
        if hasattr(self.client, "close"):
            self.client.close()


# 向后兼容的别名
class HindsightMemory(HindsightMemoryStore):
    """向后兼容的别名"""
    pass
