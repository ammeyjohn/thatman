"""
世界种子初始化工具 - 生成青墟大世界完整种子数据

读取 docs/ 目录下的世界设定文档，构建基础世界种子，
通过 Qwen3.6-27B 大模型润色扩充，生成丰富的世界事实描述，
并保存到 Hindsight 记忆库和 CouchDB 数据库中。

生成的世界种子包括：
- 大陆/地域（凡人界、修行界四大域、上古秘境）
- 宗门势力（正道、邪道、中立、灵族）
- 物品资源（天材地宝、丹药、符箓、阵法材料）
- 法宝装备（攻击类、防御类、辅助类）
- 功法武技（心法、身法、攻击、防御、辅助）
- 典型NPC（宗主、长老、弟子、散修、灵族等）

用法:
    python init_world_seed.py [--skip-llm] [--skip-save] [--verbose]
"""

import os
import sys
import json
import uuid
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

import yaml
import httpx

# ───────────────────────────────────────────────
# 日志配置
# ───────────────────────────────────────────────

logger = logging.getLogger(__name__)


def debug_log(message: str):
    logger.debug(message)
    print(f"\033[90m[DEBUG] {message}\033[0m")


def info_log(message: str):
    logger.info(message)
    print(f"\033[97m[INFO] {message}\033[0m")


def warn_log(message: str):
    logger.warning(message)
    print(f"\033[93m[WARN] {message}\033[0m")


def error_log(message: str):
    logger.error(message)
    print(f"\033[91m[ERROR] {message}\033[0m")


def success_log(message: str):
    print(f"\033[92m[OK] {message}\033[0m")


# ───────────────────────────────────────────────
# 项目路径
# ───────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
SERVER_DIR = PROJECT_ROOT / "server"
DOCS_DIR = PROJECT_ROOT / "docs"
CONFIG_PATH = SERVER_DIR / "config.yaml"

# 将 server/agents 加入模块搜索路径
sys.path.insert(0, str(SERVER_DIR / "agents"))


# ───────────────────────────────────────────────
# 配置加载
# ───────────────────────────────────────────────

def load_config() -> dict:
    """加载 config.yaml 配置"""
    if not CONFIG_PATH.exists():
        error_log(f"配置文件不存在: {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    info_log(f"配置加载成功: {CONFIG_PATH}")
    return config


# ───────────────────────────────────────────────
# 文档读取
# ───────────────────────────────────────────────

DOC_FILES = {
    "world_config.md": "世界基础设定",
    "game_manual.md": "游戏手册",
    "level_config.md": "境界属性配置",
    "item_config.md": "物品资源配置",
    "skill_config.md": "功法配置",
    "npc_config.md": "NPC角色配置",
    "guild_config.md": "宗门势力配置",
    "task_config.md": "任务等级配置",
    "世界观.md": "世界观设定",
}


def read_doc(filename: str) -> str:
    """读取文档内容"""
    filepath = DOCS_DIR / filename
    if not filepath.exists():
        warn_log(f"文档不存在: {filename}")
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def read_all_docs() -> Dict[str, str]:
    """读取所有世界设定文档"""
    docs = {}
    for filename in DOC_FILES:
        content = read_doc(filename)
        if content:
            docs[filename] = content
    info_log(f"已读取 {len(docs)} 个世界设定文档")
    return docs


# ───────────────────────────────────────────────
# LLM 调用
# ───────────────────────────────────────────────

class LLMClient:
    """OpenAI 兼容接口客户端，用于调用 Qwen3.6-27B 大模型"""

    def __init__(self, api_base: str, api_key: str, model_name: str,
                 temperature: float = 0.7, max_tokens: int = 8192):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = httpx.Client(
            base_url=self.api_base,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            timeout=httpx.Timeout(300.0),
        )

    def chat(self, system_prompt: str, user_prompt: str,
             response_format: Optional[dict] = None) -> str:
        """
        调用 LLM 生成文本

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            response_format: 响应格式，如 {"type": "json_object"}

        Returns:
            LLM 生成的文本
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        body: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": 0.85,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
        }

        if response_format:
            body["response_format"] = response_format

        try:
            resp = self._client.post("/chat/completions", json=body)
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            # Qwen3 模型思考模式：reasoning_content 为思考过程，content 为最终输出
            # 当 content 为空时，可能思考内容中包含实际输出
            content = message.get("content", "") or ""
            reasoning = message.get("reasoning_content", "") or ""
            # 输出原始返回内容用于调试
            if content.strip():
                debug_log(f"LLM content 返回（前200字）: {content}")
            else:
                debug_log("LLM content 为空")
            if reasoning.strip():
                debug_log(f"LLM reasoning_content 返回（前200字）: {reasoning}")
            # 如果 content 为空但 reasoning 不为空，尝试从 reasoning 中提取
            if not content.strip() and reasoning.strip():
                debug_log("Qwen3 思考模式：content 为空，从 reasoning_content 提取")
                content = reasoning
            return content.strip()
        except Exception as e:
            error_log(f"LLM 调用失败: {e}")
            return ""

    def chat_json(self, system_prompt: str, user_prompt: str) -> Optional[dict]:
        """调用 LLM 并解析 JSON 响应，自动兼容不支持 response_format 的模型"""
        # 第一次尝试：带 response_format
        raw = self.chat(system_prompt, user_prompt, response_format={"type": "json_object"})
        if raw:
            result = self._parse_json_response(raw)
            if result is not None:
                return result
            warn_log("带 response_format 返回非有效 JSON，尝试不带 response_format 重试")

        # 第二次尝试：不带 response_format（兼容 llama.cpp 等不支持该参数的模型）
        # 在 prompt 中显式要求 JSON 输出
        json_hint_prompt = user_prompt + "\n\n【重要】请严格输出 JSON 格式，不要输出任何其他文字。"
        raw = self.chat(system_prompt, json_hint_prompt)
        if raw:
            return self._parse_json_response(raw)

        return None

    @staticmethod
    def _parse_json_response(raw: str) -> Optional[dict]:
        """从 LLM 响应中解析 JSON"""
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 尝试提取 JSON 数组块
        import re
        arr_match = re.search(r'\[[\s\S]*\]', raw)
        if arr_match:
            try:
                result = json.loads(arr_match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        # 尝试提取 JSON 对象块
        obj_match = re.search(r'\{[\s\S]*\}', raw)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError:
                pass
        # 尝试提取 markdown 代码块中的 JSON
        code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if code_match:
            try:
                return json.loads(code_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        return None

    def close(self):
        if self._client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ───────────────────────────────────────────────
# CouchDB 存储
# ───────────────────────────────────────────────

class CouchDBStore:
    """CouchDB 存储客户端，用于保存实体和关联关系"""

    def __init__(self, url: str, db_prefix: str, user: str, password: str):
        self._url = url.rstrip("/")
        self._db_prefix = db_prefix
        self._db_entities = f"{db_prefix}entities"
        self._db_links = f"{db_prefix}links"
        self._db_world_snaps = f"{db_prefix}world_snaps"
        self._client = httpx.Client(
            base_url=self._url,
            auth=(user, password),
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(30.0),
        )
        self._ensure_dbs()

    def _ensure_dbs(self):
        """确保数据库存在"""
        for db_name in [self._db_entities, self._db_links, self._db_world_snaps]:
            try:
                resp = self._client.head(f"/{db_name}")
                if resp.status_code == 404:
                    resp = self._client.put(f"/{db_name}")
                    if resp.status_code in (201, 202):
                        info_log(f"CouchDB 数据库已创建: {db_name}")
            except Exception as e:
                error_log(f"检查/创建 CouchDB 数据库失败: {db_name}, 错误: {e}")

    def save_entity(self, entity_id: str, entity_data: dict) -> bool:
        """保存实体（新增或更新）"""
        try:
            # 查询现有文档获取 _rev
            existing = self._get_entity(entity_id)
            if existing and "_rev" in existing:
                entity_data["_rev"] = existing["_rev"]

            resp = self._client.put(
                f"/{self._db_entities}/{entity_id}", json=entity_data
            )
            if resp.status_code in (201, 202):
                debug_log(f"保存实体成功: {entity_id}")
                return True
            else:
                warn_log(f"保存实体失败: {entity_id}, 状态码: {resp.status_code}")
                return False
        except Exception as e:
            error_log(f"保存实体异常: {entity_id}, 错误: {e}")
            return False

    def _get_entity(self, entity_id: str) -> dict:
        """获取实体"""
        try:
            resp = self._client.get(f"/{self._db_entities}/{entity_id}")
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception:
            return {}

    def save_link(self, from_id: str, to_id: str, rel_type: str, desc: str) -> bool:
        """保存关联关系"""
        try:
            link_doc = {
                "from_id": from_id,
                "to_id": to_id,
                "rel_type": rel_type,
                "desc": desc,
            }
            resp = self._client.post(f"/{self._db_links}", json=link_doc)
            if resp.status_code in (201, 202):
                debug_log(f"保存关联成功: {from_id} --[{rel_type}]--> {to_id}")
                return True
            else:
                warn_log(f"保存关联失败: {from_id}->{to_id}, 状态码: {resp.status_code}")
                return False
        except Exception as e:
            error_log(f"保存关联异常: {from_id}->{to_id}, 错误: {e}")
            return False

    def save_world_snap(self, snap_data: dict) -> bool:
        """保存世界快照"""
        try:
            doc_id = f"snap_{uuid.uuid4().hex[:12]}"
            resp = self._client.put(
                f"/{self._db_world_snaps}/{doc_id}", json=snap_data
            )
            if resp.status_code in (201, 202):
                info_log(f"保存世界快照成功: {doc_id}")
                return True
            else:
                warn_log(f"保存世界快照失败, 状态码: {resp.status_code}")
                return False
        except Exception as e:
            error_log(f"保存世界快照异常: {e}")
            return False

    def close(self):
        if self._client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ───────────────────────────────────────────────
# Hindsight 记忆库存储
# ───────────────────────────────────────────────

class HindsightStore:
    """Hindsight 记忆库客户端，用于存储世界事实记忆"""

    def __init__(self, base_url: str, api_key: Optional[str] = None,
                 bank_id: str = "world"):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._bank_id = bank_id
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=httpx.Timeout(300.0),
        )
        self._ensure_bank()

    def _ensure_bank(self):
        """确保记忆库存在"""
        try:
            self._client.get(f"/v1/default/banks/{self._bank_id}/config")
            debug_log(f"记忆库已存在: {self._bank_id}")
        except Exception:
            try:
                body = {
                    "name": "青墟世界记忆库",
                    "mission": (
                        "《青墟灵修志》世界记忆库。存储上古劫后遗落修仙世界的完整设定，"
                        "包括世界起源、修行体系、势力阵营、生灵角色、资源物产、规则法则等。"
                        "用于支撑 AI 多智能体自主演化与动态剧情生成。"
                    ),
                    "disposition_skepticism": 4,
                    "disposition_literalism": 4,
                    "disposition_empathy": 2,
                }
                self._client.put(f"/v1/default/banks/{self._bank_id}", json=body)
                info_log(f"创建记忆库成功: {self._bank_id}")
            except Exception as e:
                error_log(f"确保记忆库存在时出错: {e}")
                raise

    def retain(self, content: str, context: str = "world_lore",
               metadata: Optional[dict] = None, retries: int = 1) -> bool:
        """存储记忆"""
        if not content or not content.strip():
            return False
        try:
            item: Dict[str, Any] = {
                "content": content.strip(),
                "context": context,
            }
            if metadata:
                item["metadata"] = {k: str(v) for k, v in metadata.items()}

            # 优先使用异步模式，避免 Hindsight LLM 后端不可用时阻塞
            body = {"items": [item], "async": True}
            resp = self._client.post(
                f"/v1/default/banks/{self._bank_id}/memories", json=body
            )

            # 如果异步模式返回 500，回退到同步模式重试
            if resp.status_code == 500 and retries > 0:
                debug_log(f"异步存储失败，回退同步模式重试: {content}")
                body["async"] = False
                resp = self._client.post(
                    f"/v1/default/banks/{self._bank_id}/memories", json=body
                )

            resp.raise_for_status()
            data = resp.json()
            return data.get("success", False)
        except httpx.HTTPStatusError as e:
            # 500 错误通常是 Hindsight LLM 后端不可用，给出明确提示
            if e.response.status_code == 500:
                detail = ""
                try:
                    detail = e.response.json().get("detail", "")
                except Exception:
                    pass
                if "APIConnectionError" in detail:
                    warn_log(f"记忆存储失败（Hindsight LLM 后端不可用）: {content}")
                else:
                    warn_log(f"记忆存储失败（500）: {detail}")
            else:
                error_log(f"记忆存储失败: {e}")
            return False
        except Exception as e:
            error_log(f"记忆存储失败: {e}")
            return False

    def retain_batch(self, items: List[Dict[str, Any]]) -> int:
        """批量存储记忆"""
        success_count = 0
        for item in items:
            content = item.get("content", "")
            context = item.get("context", "world_lore")
            metadata = item.get("metadata")
            if self.retain(content, context, metadata):
                success_count += 1
        return success_count

    def close(self):
        if self._client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ───────────────────────────────────────────────
# 世界种子数据定义
# ───────────────────────────────────────────────

def build_area_entities() -> List[dict]:
    """构建地域实体数据"""
    areas = [
        # ── 凡人界 ──
        {
            "id": "area_mortal",
            "entity_type": "area",
            "name": "凡人界",
            "base_info": "凡人王朝聚集地，灵气稀薄，仅少数低阶散修游荡。以凡人农耕、王朝统治为主，是修士入世历练、感悟红尘的场所。",
            "attr": "灵气等级:普通灵气 | 适用境界:引气~筑基 | 核心功能:入世历练、感悟红尘",
            "birth_story": "上古大劫后，凡人界因灵脉断裂而灵气稀薄，逐渐成为凡人聚居之地。少数低阶散修在此游荡，以凡人方式生活，偶有修士来此感悟红尘。",
            "belong_area": "青墟大世界",
            "scenes": [
                {"name": "永安城", "desc": "凡人界最大城池，人口百万，商贾云集，偶有散修在此摆摊售卖低阶丹药"},
                {"name": "青柳镇", "desc": "永安城外小镇，民风淳朴，镇外有低阶灵草零星生长"},
                {"name": "落霞村", "desc": "偏远山村，村后山林中有废弃洞府，偶有散修路过借宿"},
                {"name": "天水坊市", "desc": "凡人界唯一的修士坊市，低阶丹药、灵草、凡器交易之地"},
                {"name": "苍梧山", "desc": "凡人界最高山脉，山巅有残破灵脉，偶有引气期修士在此修炼"},
            ],
        },
        # ── 青云古域 ──
        {
            "id": "area_qingyun",
            "entity_type": "area",
            "name": "青云古域",
            "base_info": "正统宗门聚集地，灵气充裕，灵脉完整度最高，主流修士聚集地，风气偏平和，重古法传承。",
            "attr": "灵气等级:精纯灵气 | 阵营倾向:正道 | 核心特征:正统宗门聚集，灵脉完整，风气平和",
            "birth_story": "上古大劫中，青云古域因地处灵脉交汇核心，受劫难波及较小，灵脉虽有断裂但根基尚存。劫后正道修士汇聚于此，重建宗门，守护灵脉，逐渐成为修行界正道核心。",
            "belong_area": "修行界",
            "scenes": [
                {"name": "青云主峰", "desc": "青云宗所在，先天灵脉贯穿山体，山顶常年灵雾缭绕，仙鹤盘旋"},
                {"name": "丹霞灵谷", "desc": "丹霞门所在，谷中灵药遍地，丹炉日夜不息，药香飘散百里"},
                {"name": "玄清道观", "desc": "玄清观所在，道观隐于云雾之中，符箓阁藏有万卷道经"},
                {"name": "论道台", "desc": "青云古域中心广场，正道修士定期论道之所，石台刻有上古道纹"},
                {"name": "灵石矿脉", "desc": "青云古域东部山脉，灵石矿脉绵延百里，由三大宗门共同守护"},
                {"name": "青云坊市", "desc": "修行界最大坊市，各类功法、丹药、法宝均可在此交易"},
                {"name": "试炼秘谷", "desc": "青云古域西部深谷，宗门弟子试炼之地，谷中有低阶妖兽出没"},
            ],
        },
        # ── 荒古野域 ──
        {
            "id": "area_huanggu",
            "entity_type": "area",
            "name": "荒古野域",
            "base_info": "无主之地，灵脉残缺但机缘众多，妖兽横行，邪修盘踞，是散修、亡命修士寻宝、历练、厮杀的场所。",
            "attr": "灵气等级:普通灵气 | 阵营倾向:中立/混乱 | 核心特征:无主之地，妖兽横行，机缘众多",
            "birth_story": "上古大劫中，荒古野域是万族大战的核心战场，灵脉断裂最为严重，但战场上古遗迹遍布，天材地宝时有现世，引得无数修士冒险深入。",
            "belong_area": "修行界",
            "scenes": [
                {"name": "万骨荒原", "desc": "上古战场遗迹，遍地白骨与残破法器，偶有上古残魂游荡，凶险异常"},
                {"name": "迷雾深林", "desc": "常年浓雾笼罩的原始森林，妖兽横行，灵草遍地，散修寻宝圣地"},
                {"name": "断崖秘洞", "desc": "悬崖峭壁间的隐秘洞窟，据传有上古修士遗留的洞府，藏有古法残卷"},
                {"name": "黑风兽巢", "desc": "黑风兽域核心，高阶妖兽盘踞，灵兽内丹、兽骨、兽皮产出地"},
                {"name": "散修集市", "desc": "荒古野域边缘的临时集市，无规则约束，弱肉强食"},
                {"name": "陨星湖", "desc": "上古陨石坠落形成的湖泊，湖底有星辰铁矿脉，但湖中有水妖守护"},
            ],
        },
        # ── 幽寒邪域 ──
        {
            "id": "area_youhan",
            "entity_type": "area",
            "name": "幽寒邪域",
            "base_info": "邪修核心地盘，灵气阴冷，充斥戾气，修士多走捷径修行，掠夺他人修为与资源，与青云古域势同水火。",
            "attr": "灵气等级:精纯灵气（阴冷） | 阵营倾向:邪道 | 核心特征:邪修核心，充斥戾气，捷径修行",
            "birth_story": "上古大劫后，幽寒邪域因地下阴脉汇聚，灵气阴冷浓郁，吸引大批邪修聚集。邪修以掠夺他人修为为生，逐渐形成以血影教为首的邪道势力。",
            "belong_area": "修行界",
            "scenes": [
                {"name": "血影魔宫", "desc": "血影教总坛，阴气冲天，血池遍布，教主闭关之所"},
                {"name": "骨傀深渊", "desc": "骨傀门所在，深渊中白骨堆积如山，骨傀游荡，阴风阵阵"},
                {"name": "幽月毒谷", "desc": "幽月谷所在，谷中遍植毒草，月夜时毒雾弥漫，百毒不侵者方可进入"},
                {"name": "血祭台", "desc": "邪修血祭修炼之地，台上残留血迹斑斑，令人不寒而栗"},
                {"name": "邪修黑市", "desc": "幽寒邪域地下交易市场，血修材料、邪功秘典均可在此交易"},
                {"name": "阴魂涧", "desc": "阴气汇聚的深涧，亡魂游荡，邪修在此炼制魂器"},
            ],
        },
        # ── 云岑灵境 ──
        {
            "id": "area_yuncen",
            "entity_type": "area",
            "name": "云岑灵境",
            "base_info": "中立区域，草木精怪、灵兽聚集地，灵气纯净，不喜人类修士干预，仅接纳心境平和、不嗜杀之人。",
            "attr": "灵气等级:精纯灵气（纯净） | 阵营倾向:灵族 | 核心特征:草木精怪聚集，灵气纯净，不喜杀伐",
            "birth_story": "云岑灵境是上古大劫中少数未受波及的区域，灵脉完好，灵气纯净。劫后草木精怪在此聚集，以自然之道修行，守护栖息地，不与人类修士来往。",
            "belong_area": "修行界",
            "scenes": [
                {"name": "万木灵心", "desc": "云岑灵境核心，千年古树参天，灵气纯净如水，灵族长老议事之所"},
                {"name": "碧泉灵池", "desc": "灵泉汇聚的天然灵池，池水可修复道心，灵族圣物"},
                {"name": "灵草花海", "desc": "无边灵草花海，灵药遍地，灵蝶飞舞，人间仙境"},
                {"name": "灵兽栖谷", "desc": "灵兽栖息的山谷，灵兽与精怪和谐共处，外人难以进入"},
                {"name": "古树集市", "desc": "灵族与人类修士的唯一交易点，仅心境平和者可进入"},
            ],
        },
        # ── 上古秘境 ──
        {
            "id": "area_ancient_realm",
            "entity_type": "area",
            "name": "上古秘境",
            "base_info": "上古大能遗留之地，时空错乱，随机现世、转瞬闭合，藏有上古典籍、天材地宝，但危机重重。",
            "attr": "灵气等级:先天灵气/上古灵气 | 出现规则:随机现世，转瞬闭合 | 核心产出:上古典籍、天材地宝、道韵",
            "birth_story": "上古大劫中，部分大能以自身道韵封印洞府，形成独立空间。这些空间随天地灵潮波动而随机现世，内藏上古传承，但时空扭曲，危机四伏。",
            "belong_area": "青墟大世界",
            "scenes": [
                {"name": "太虚遗迹", "desc": "上古太虚道人洞府，藏有《太虚道心诀》残卷，时空扭曲，时间流速为外界十倍"},
                {"name": "雷罚古域", "desc": "上古雷修大能遗留之地，雷属性灵气浓郁，藏有上古雷法传承"},
                {"name": "混沌裂隙", "desc": "空间乱流汇聚之地，极度危险，但偶有上古灵宝碎片随空间乱流飘出"},
                {"name": "道韵石壁", "desc": "刻有上古道纹的石壁，感悟道韵可加速悟道，但石壁会自行崩解"},
            ],
        },
    ]
    return areas


def build_faction_entities() -> List[dict]:
    """构建宗门势力实体数据"""
    factions = [
        # ── 正道宗门 ──
        {
            "id": "faction_qingyun",
            "entity_type": "faction",
            "name": "青云宗",
            "base_info": "青云古域核心宗门，修行界最具影响力的正道势力。坚守上古正统古法，护持灵脉，传承正道修行理念。宗门坐拥先天灵脉，弟子五千余人。",
            "attr": "等级:顶级 | 灵脉:先天灵脉 | 宗主境界:大乘期 | 弟子规模:5000+ | 阵营:正道",
            "birth_story": "上古大劫后，正道修士青云子于灵脉交汇处开宗立派，以守护灵脉、传承古法为宗门根基。历经万年传承，青云宗成为修行界正道核心，门下弟子遍布修行界。",
            "belong_area": "青云古域",
            "faction_type": "正道",
            "hierarchy": ["宗主", "长老团", "执法堂", "内门弟子", "外门弟子", "杂役弟子"],
        },
        {
            "id": "faction_danxia",
            "entity_type": "faction",
            "name": "丹霞门",
            "base_info": "以炼丹闻名的正道宗门，门下弟子多精于丹道，灵药资源丰富。与青云宗交好，互为盟友。",
            "attr": "等级:一流 | 灵脉:灵脉 | 掌门境界:炼虚期 | 弟子规模:2000+ | 阵营:正道",
            "birth_story": "丹霞门始祖丹霞真人原为散修炼丹师，偶得上古丹方残卷，悟出独门炼丹之法，遂开宗立派。门下弟子以丹道入道，炼丹术冠绝修行界。",
            "belong_area": "青云古域",
            "faction_type": "正道",
            "hierarchy": ["掌门", "丹道长老", "药园执事", "内门弟子", "外门弟子"],
        },
        {
            "id": "faction_xuanqing",
            "entity_type": "faction",
            "name": "玄清观",
            "base_info": "以符箓、道法见长的正道宗门，心境修炼为宗门特色。观中藏有万卷道经，符箓术独步修行界。",
            "attr": "等级:一流 | 灵脉:灵脉 | 掌门境界:炼虚期 | 弟子规模:2000+ | 阵营:正道",
            "birth_story": "玄清观始祖玄清道人以上古符箓残卷悟道，开创符箓修行体系。观中符箓阁藏有上古道经万卷，是修行界符箓术的传承圣地。",
            "belong_area": "青云古域",
            "faction_type": "正道",
            "hierarchy": ["观主", "符道长老", "执法道长", "内门弟子", "外门弟子"],
        },
        # ── 邪道势力 ──
        {
            "id": "faction_xueying",
            "entity_type": "faction",
            "name": "血影教",
            "base_info": "幽寒邪域核心势力，擅长血修功法，嗜杀成性。以掠夺他人修为、资源为生，与正道势不两立。",
            "attr": "等级:顶级 | 灵脉:先天灵脉（阴脉） | 教主境界:大乘期 | 教徒规模:3000+ | 阵营:邪道",
            "birth_story": "血影教始祖血影老祖原为正道修士，因资质有限无法突破，转而修炼血修邪法，以掠夺他人修为突破境界。后被正道围剿，逃入幽寒邪域建立血影教。",
            "belong_area": "幽寒邪域",
            "faction_type": "邪道",
            "hierarchy": ["教主", "护法", "舵主", "教徒"],
        },
        {
            "id": "faction_gukui",
            "entity_type": "faction",
            "name": "骨傀门",
            "base_info": "以炼制骨傀、掠夺神魂为生的邪道势力。门下修士以亡者骸骨炼制骨傀，驱使骨傀战斗，令人闻风丧胆。",
            "attr": "等级:一流 | 灵脉:灵脉（阴脉） | 门主境界:炼虚期 | 教徒规模:1500+ | 阵营:邪道",
            "birth_story": "骨傀门始祖为上古遗族中的骨修，掌握上古骨修秘法。劫后收徒传法，以炼制骨傀为生，逐渐成为幽寒邪域第二大势力。",
            "belong_area": "幽寒邪域",
            "faction_type": "邪道",
            "hierarchy": ["门主", "骨修长老", "傀师", "门徒"],
        },
        {
            "id": "faction_youyue",
            "entity_type": "faction",
            "name": "幽月谷",
            "base_info": "擅长毒术的邪道势力，隐蔽性极强。谷中遍植毒草，月夜时毒雾弥漫，百毒不侵者方可进入。",
            "attr": "等级:二流 | 灵脉:灵脉（残缺） | 谷主境界:化神期 | 教徒规模:500+ | 阵营:邪道",
            "birth_story": "幽月谷始祖幽月仙子原为丹霞门弟子，因修炼毒丹被逐出师门，后自创毒修功法，建立幽月谷。谷中弟子以毒入道，炼制各类毒丹、毒器。",
            "belong_area": "幽寒邪域",
            "faction_type": "邪道",
            "hierarchy": ["谷主", "毒修长老", "药师", "谷众"],
        },
        # ── 灵族势力 ──
        {
            "id": "faction_yuncen_spirit",
            "entity_type": "faction",
            "name": "云岑灵族",
            "base_info": "云岑灵境核心族群，草木精怪为主。遵循自然之道修行，不参与人类阵营争斗，守护栖息地。",
            "attr": "等级:一流 | 灵脉:先天灵脉（纯净） | 族长境界:炼虚期 | 族群规模:1000+ | 阵营:灵族",
            "birth_story": "上古大劫后，云岑灵境未受波及，草木精怪在此繁衍生息，以自然之道修行。灵族长老掌权，共同守护栖息地，不与人类修士来往。",
            "belong_area": "云岑灵境",
            "faction_type": "灵族",
            "hierarchy": ["族长", "长老", "灵使", "族众"],
        },
        {
            "id": "faction_heifeng_beast",
            "entity_type": "faction",
            "name": "黑风兽域",
            "base_info": "荒古野域妖兽族群，实力强悍。以肉身为修，低阶妖兽靠本能行动，高阶妖兽可化形人言。",
            "attr": "等级:二流 | 灵脉:灵脉（残缺） | 兽王境界:化神期 | 族群规模:500+ | 阵营:灵族",
            "birth_story": "荒古野域妖兽以上古灵气残余修炼，历经千年形成族群。兽王统率族群，守护领地，偶与人类修士冲突。",
            "belong_area": "荒古野域",
            "faction_type": "灵族",
            "hierarchy": ["兽王", "领主", "头领", "兽群"],
        },
    ]
    return factions


def build_npc_entities() -> List[dict]:
    """构建典型NPC实体数据"""
    npcs = [
        # ── 青云宗 ──
        {
            "id": "npc_qingyun_zongzhu",
            "entity_type": "npc",
            "name": "云无极",
            "base_info": "青云宗宗主，大乘期修士，先天雷灵根。修心悟道、济世安邦，以守护灵脉、传承古法为己任。道心稳固，修为深不可测，是修行界正道的精神领袖。",
            "attr": "境界:大乘期圆满 | 灵根:先天雷灵根 | 心境:悲悯济世 | 身份:青云宗宗主 | 寿元:11500年",
            "birth_story": "云无极幼年为凡人孤儿，被青云宗长老收养，觉醒先天雷灵根。修行百年突破金丹，三百年元婴，千年化神，五千年炼虚合体，八千年大乘悟道。一生坚守正道，守护灵脉，被修行界尊为'青云道尊'。",
            "belong_area": "青云古域",
            "spirit_root": "先天雷灵根",
            "realm": "大乘期圆满",
            "personality": "悲悯济世",
            "identity": "青云宗宗主",
        },
        {
            "id": "npc_qingyun_zhifa",
            "entity_type": "npc",
            "name": "铁面真人",
            "base_info": "青云宗执法堂首席，合体期修士，变异金火灵根。执法如山，铁面无私，维护宗门秩序。外冷内热，对弟子严厉但关爱有加。",
            "attr": "境界:合体期后期 | 灵根:变异金火灵根 | 心境:严谨务实 | 身份:执法堂首席 | 寿元:7200年",
            "birth_story": "铁面真人原名金烈，出身寒微，凭变异灵根入青云宗外门。因执法公正、战力出众，逐步晋升为执法堂首席。一生斩杀邪修无数，被尊为'铁面判官'。",
            "belong_area": "青云古域",
            "spirit_root": "变异金火灵根",
            "realm": "合体期后期",
            "personality": "严谨务实",
            "identity": "执法堂首席",
        },
        {
            "id": "npc_qingyun_neimen",
            "entity_type": "npc",
            "name": "苏瑶",
            "base_info": "青云宗内门弟子，金丹期修士，先天水灵根。性情温和，擅长丹道，是丹霞门交流弟子。与同门关系融洽，常在丹药阁研习炼丹之术。",
            "attr": "境界:金丹期中期 | 灵根:先天水灵根 | 心境:仁善谦和 | 身份:内门弟子 | 寿元:650年",
            "birth_story": "苏瑶出身修行世家，自幼灵根觉醒，十岁入青云宗外门，十五岁晋升内门。师从丹道长老，炼丹天赋出众，是宗门年轻一代的炼丹天才。",
            "belong_area": "青云古域",
            "spirit_root": "先天水灵根",
            "realm": "金丹期中期",
            "personality": "仁善谦和",
            "identity": "内门弟子",
        },
        {
            "id": "npc_qingyun_waimen",
            "entity_type": "npc",
            "name": "林风",
            "base_info": "青云宗外门弟子，筑基期修士，杂灵根。资质平庸但心性坚韧，勤奋修炼，渴望晋升内门。为人正直，乐于助人，在同门中口碑极好。",
            "attr": "境界:筑基期初期 | 灵根:杂灵根 | 心境:执念深重 | 身份:外门弟子 | 寿元:420年",
            "birth_story": "林风出身凡人村落，偶得散修指点引气入体，后入青云宗外门。资质虽平庸，但心性坚韧，日夜苦修不辍，终在三十岁前筑基成功，是外门弟子中的佼佼者。",
            "belong_area": "青云古域",
            "spirit_root": "杂灵根",
            "realm": "筑基期初期",
            "personality": "执念深重",
            "identity": "外门弟子",
        },
        # ── 丹霞门 ──
        {
            "id": "npc_danxia_zhangmen",
            "entity_type": "npc",
            "name": "药尘子",
            "base_info": "丹霞门掌门，炼虚期修士，变异木火灵根。炼丹术冠绝修行界，掌握多种上古丹方残卷。性情随和，对丹道痴迷，常闭关数月炼丹。",
            "attr": "境界:炼虚期中期 | 灵根:变异木火灵根 | 心境:淡然出世 | 身份:丹霞门掌门 | 寿元:4800年",
            "birth_story": "药尘子原名陈药，出身药农之家，自幼与灵草为伴。入丹霞门后展现惊人炼丹天赋，百年内掌握宗门所有丹方，后游历修行界收集上古丹方残卷，炼丹术登峰造极。",
            "belong_area": "青云古域",
            "spirit_root": "变异木火灵根",
            "realm": "炼虚期中期",
            "personality": "淡然出世",
            "identity": "丹霞门掌门",
        },
        # ── 玄清观 ──
        {
            "id": "npc_xuanqing_guanzhu",
            "entity_type": "npc",
            "name": "清虚道人",
            "base_info": "玄清观观主，炼虚期修士，先天金灵根。符箓术独步修行界，掌握上古符箓秘法。心境高深，不喜纷争，常在观中闭关悟道。",
            "attr": "境界:炼虚期初期 | 灵根:先天金灵根 | 心境:淡然出世 | 身份:玄清观观主 | 寿元:5100年",
            "birth_story": "清虚道人出身道修世家，自幼修习符箓之术。入玄清观后以上古符箓残卷悟道，开创数种新型符箓，被尊为'符道宗师'。",
            "belong_area": "青云古域",
            "spirit_root": "先天金灵根",
            "realm": "炼虚期初期",
            "personality": "淡然出世",
            "identity": "玄清观观主",
        },
        # ── 血影教 ──
        {
            "id": "npc_xueying_jiaozhu",
            "entity_type": "npc",
            "name": "血魔尊者",
            "base_info": "血影教教主，大乘期修士，变异血灵根。修炼血修邪法，以掠夺他人修为突破境界。心性扭曲，手段狠辣，是修行界邪道的精神领袖。",
            "attr": "境界:大乘期初期 | 灵根:变异血灵根 | 心境:阴鸷狠厉 | 身份:血影教教主 | 寿元:11200年",
            "birth_story": "血魔尊者原名萧血，原为青云宗外门弟子，因资质有限无法突破，偷学血修邪法被逐出师门。逃入幽寒邪域后以血修之法突破境界，建立血影教，发誓覆灭青云宗。",
            "belong_area": "幽寒邪域",
            "spirit_root": "变异血灵根",
            "realm": "大乘期初期",
            "personality": "阴鸷狠厉",
            "identity": "血影教教主",
        },
        {
            "id": "npc_xueying_hufa",
            "entity_type": "npc",
            "name": "厉魂",
            "base_info": "血影教左护法，炼虚期修士，杂灵根。修炼魂修邪法，擅长搜魂夺魄。对教主忠心耿耿，是血影教最可怕的杀手。",
            "attr": "境界:炼虚期初期 | 灵根:杂灵根 | 心境:阴鸷狠厉 | 身份:血影教左护法 | 寿元:5300年",
            "birth_story": "厉魂原为散修，因被正道修士追杀而投奔血影教。修炼魂修邪法后实力大增，成为教主最信任的护法，执行过无数次暗杀任务。",
            "belong_area": "幽寒邪域",
            "spirit_root": "杂灵根",
            "realm": "炼虚期初期",
            "personality": "阴鸷狠厉",
            "identity": "血影教左护法",
        },
        # ── 散修 ──
        {
            "id": "npc_sanxiu_xunbao",
            "entity_type": "npc",
            "name": "寻宝散人",
            "base_info": "荒古野域知名散修，元婴期修士，杂灵根。擅长寻宝探秘，掌握多种小众古法，对上古遗迹了如指掌。性格随性洒脱，恩怨分明。",
            "attr": "境界:元婴期后期 | 灵根:杂灵根 | 心境:随性洒脱 | 身份:寻宝散修 | 寿元:1350年",
            "birth_story": "寻宝散人原名秦宝，出身凡人商贾之家，因偶得上古藏宝图而踏入修行之路。多年游历荒古野域，寻得上古遗迹数处，掌握多种小众古法，是散修中的传奇人物。",
            "belong_area": "荒古野域",
            "spirit_root": "杂灵根",
            "realm": "元婴期后期",
            "personality": "随性洒脱",
            "identity": "寻宝散修",
        },
        {
            "id": "npc_sanxiu_yinshi",
            "entity_type": "npc",
            "name": "无名老者",
            "base_info": "隐居荒古野域深处的高阶散修，化神期修士，先天土灵根。不问世事，偶有缘者可得其指点。道心高深，修为深不可测。",
            "attr": "境界:化神期巅峰 | 灵根:先天土灵根 | 心境:淡然出世 | 身份:隐世修士 | 寿元:2900年",
            "birth_story": "无名老者原为青云宗太上长老，因道心瓶颈退隐，隐居荒古野域深处。修为高深但从不现身，偶有缘者路过其洞府，可得一二指点。",
            "belong_area": "荒古野域",
            "spirit_root": "先天土灵根",
            "realm": "化神期巅峰",
            "personality": "淡然出世",
            "identity": "隐世修士",
        },
        # ── 灵族 ──
        {
            "id": "npc_yuncen_zuzhang",
            "entity_type": "npc",
            "name": "碧梧长老",
            "base_info": "云岑灵族大长老，炼虚期修士，千年梧桐化形。性情温和但护短，守护灵族栖息地不遗余力。掌握自然道法，与天地共鸣。",
            "attr": "境界:炼虚期初期 | 灵根:先天木灵根 | 心境:仁善谦和 | 身份:灵族大长老 | 寿元:5000年",
            "birth_story": "碧梧长老原为云岑灵境千年梧桐，吸收天地灵气千年化形。化形后以自然之道修行，成为灵族大长老，守护灵族栖息地。",
            "belong_area": "云岑灵境",
            "spirit_root": "先天木灵根",
            "realm": "炼虚期初期",
            "personality": "仁善谦和",
            "identity": "灵族大长老",
        },
        {
            "id": "npc_heifeng_shouwang",
            "entity_type": "npc",
            "name": "黑风兽王",
            "base_info": "黑风兽域兽王，化神期修士，上古黑风虎血脉。肉身强悍，已化形人言。守护兽域领地，不主动招惹人类，但若领地被犯则暴怒反击。",
            "attr": "境界:化神期中期 | 灵根:先天风灵根 | 心境:孤傲桀骜 | 身份:兽域兽王 | 寿元:2800年",
            "birth_story": "黑风兽王为上古黑风虎后裔，继承上古血脉，修炼千年化形。统率黑风兽域妖兽族群，守护领地，与人类修士偶有冲突。",
            "belong_area": "荒古野域",
            "spirit_root": "先天风灵根",
            "realm": "化神期中期",
            "personality": "孤傲桀骜",
            "identity": "兽域兽王",
        },
    ]
    return npcs


def build_item_entities() -> List[dict]:
    """构建物品资源实体数据（天材地宝、丹药、符箓、阵法材料）"""
    items = [
        # ── 天材地宝 - 草木类 ──
        {
            "id": "item_lingcao_qingwen",
            "entity_type": "item",
            "name": "青纹灵草",
            "base_info": "筑基期常用灵草，叶面有青色纹路，灵气充盈。可炼制灵丹，灵力恢复+20%。",
            "attr": "品级:良品 | 类型:草木类 | 用途:炼制灵丹 | 对应境界:筑基期",
            "birth_story": "青纹灵草生长于灵脉附近，吸收精纯灵气百年方可成熟。叶面青纹为灵气凝聚而成，纹路越清晰品质越高。",
            "belong_area": "青云古域",
            "item_type": "天材地宝",
            "item_sub_type": "草木类",
            "grade": "良品",
        },
        {
            "id": "item_lingcao_ziheche",
            "entity_type": "item",
            "name": "紫河车草",
            "base_info": "金丹期珍稀灵草，通体紫色，可修复道心。炼制上品丹药的核心材料，极为稀有。",
            "attr": "品级:上品 | 类型:草木类 | 用途:修复道心、炼制上品丹药 | 对应境界:金丹期",
            "birth_story": "紫河车草仅生长于先天灵脉附近，千年方开一花。花谢后结出紫色果实，蕴含修复道心之力，是金丹期修士梦寐以求的灵药。",
            "belong_area": "青云古域",
            "item_type": "天材地宝",
            "item_sub_type": "草木类",
            "grade": "上品",
        },
        {
            "id": "item_lingcao_jiuzhuan",
            "entity_type": "item",
            "name": "九转还魂草",
            "base_info": "极品灵草，传说可起死回生。仅存于上古秘境深处，千年一遇。炼制极品丹药的核心材料。",
            "attr": "品级:极品 | 类型:草木类 | 用途:起死回生、炼制极品丹药 | 对应境界:元婴期",
            "birth_story": "九转还魂草为上古灵草，传说由上古大能以道韵培育而成。大劫后仅存数株于秘境深处，千年一开花，花谢即枯，需在开花瞬间采摘方有药效。",
            "belong_area": "上古秘境",
            "item_type": "天材地宝",
            "item_sub_type": "草木类",
            "grade": "极品",
        },
        # ── 天材地宝 - 矿石类 ──
        {
            "id": "item_ore_xuantie",
            "entity_type": "item",
            "name": "玄铁",
            "base_info": "筑基期常用矿石，硬度极高，可炼制灵器。是修行界最常见的炼器材料之一。",
            "attr": "品级:良品 | 类型:矿石类 | 用途:炼制灵器 | 对应境界:筑基期",
            "birth_story": "玄铁产于灵脉矿脉深处，经灵气千年浸润而成。硬度远超凡铁，是炼制灵器的基础材料。",
            "belong_area": "青云古域",
            "item_type": "天材地宝",
            "item_sub_type": "矿石类",
            "grade": "良品",
        },
        {
            "id": "item_ore_xingchen",
            "entity_type": "item",
            "name": "星辰铁",
            "base_info": "极品矿石，蕴含星辰之力，可炼制极品法宝。仅存于陨星湖底，极为稀有。",
            "attr": "品级:极品 | 类型:矿石类 | 用途:炼制极品法宝 | 对应境界:元婴期",
            "birth_story": "星辰铁为上古陨石坠落时，陨石核心与地脉灵气融合而成。蕴含星辰之力，是炼制极品法宝的顶级材料，仅存于陨星湖底。",
            "belong_area": "荒古野域",
            "item_type": "天材地宝",
            "item_sub_type": "矿石类",
            "grade": "极品",
        },
        # ── 丹药 ──
        {
            "id": "item_pill_huiling",
            "entity_type": "item",
            "name": "回灵丹",
            "base_info": "炼气期常用丹药，可恢复灵力10%。价格低廉，是低阶修士必备之物。",
            "attr": "品级:凡丹 | 类型:丹药 | 用途:灵力恢复 | 效果:灵力恢复10% | 对应境界:炼气期",
            "birth_story": "回灵丹是最基础的丹药，以甘草灵草为主料炼制。炼制简单，价格低廉，是低阶修士日常消耗量最大的丹药。",
            "belong_area": "青云古域",
            "item_type": "丹药",
            "item_sub_type": "灵力补充",
            "grade": "凡丹",
        },
        {
            "id": "item_pill_zhuji",
            "entity_type": "item",
            "name": "筑基丹",
            "base_info": "辅助筑基突破的灵丹，可提升筑基成功率。是炼气期修士突破筑基的关键丹药，价格昂贵。",
            "attr": "品级:灵丹 | 类型:丹药 | 用途:突破辅助 | 效果:筑基成功率+20% | 对应境界:筑基期",
            "birth_story": "筑基丹以上品灵草为主料，辅以灵液、药引炼制。丹霞门掌握最纯正的筑基丹配方，是修行界筑基丹的主要供应者。",
            "belong_area": "青云古域",
            "item_type": "丹药",
            "item_sub_type": "突破辅助",
            "grade": "灵丹",
        },
        {
            "id": "item_pill_huashen",
            "entity_type": "item",
            "name": "化神丹",
            "base_info": "辅助化神突破的仙丹，可修复道心、提升突破成功率。配方残缺，仅丹霞门掌握完整配方。",
            "attr": "品级:仙丹 | 类型:丹药 | 用途:突破辅助、修复道心 | 效果:化神成功率+15%，道心修复 | 对应境界:元婴期",
            "birth_story": "化神丹配方源自上古，大劫后残缺不全。丹霞门掌门药尘子游历修行界，收集残卷拼凑出完整配方，但炼制成功率仍不足三成。",
            "belong_area": "青云古域",
            "item_type": "丹药",
            "item_sub_type": "突破辅助",
            "grade": "仙丹",
        },
        # ── 符箓 ──
        {
            "id": "item_talisman_huodan",
            "entity_type": "item",
            "name": "火弹符",
            "base_info": "炼气期基础攻击符箓，释放火球攻击目标。伤害+10%，价格低廉，低阶修士常用。",
            "attr": "品级:凡品符 | 类型:符箓 | 用途:攻击 | 效果:火属性攻击，伤害+10% | 对应境界:炼气期",
            "birth_story": "火弹符是最基础的攻击符箓，以凡品符纸、符墨绘制。玄清观弟子入门即学，是修士自保的基础手段。",
            "belong_area": "青云古域",
            "item_type": "符箓",
            "item_sub_type": "攻击类",
            "grade": "凡品符",
        },
        {
            "id": "item_talisman_jingang",
            "entity_type": "item",
            "name": "金刚符",
            "base_info": "筑基期防御符箓，可形成护体金光。防御+20%，持续1时辰，是筑基修士保命符箓。",
            "attr": "品级:良品符 | 类型:符箓 | 用途:防御 | 效果:防御+20%，持续1时辰 | 对应境界:筑基期",
            "birth_story": "金刚符以良品符纸、符墨绘制，需注入灵力激活。激活后形成金色护罩，可抵御筑基期修士的全力一击。",
            "belong_area": "青云古域",
            "item_type": "符箓",
            "item_sub_type": "防御类",
            "grade": "良品符",
        },
    ]
    return items


def build_equipment_entities() -> List[dict]:
    """构建法宝装备实体数据"""
    equipments = [
        # ── 武器 ──
        {
            "id": "equip_qingfeng_sword",
            "entity_type": "equip",
            "name": "青锋剑",
            "base_info": "筑基期灵器飞剑，剑身青光流转，附带风属性灵性。攻击+25%，可御剑飞行，是青云宗内门弟子标配。",
            "attr": "品级:灵器 | 类型:攻击类/飞剑 | 效果:攻击+25%，风属性 | 认主要求:灵力注入 | 对应境界:筑基期",
            "birth_story": "青锋剑为青云宗炼器师以玄铁为主料，辅以风属性灵石炼制。剑身轻灵，适合筑基期修士御剑飞行，是青云宗内门弟子的标配法器。",
            "belong_area": "青云古域",
            "equip_type": "weapon",
            "grade": "灵器",
        },
        {
            "id": "equip_tianlei_sword",
            "entity_type": "equip",
            "name": "天雷剑",
            "base_info": "元婴期仙器飞剑，蕴含雷属性灵智，与修士心意相通。攻击+50%，附带雷属性麻痹效果，极为稀有。",
            "attr": "品级:仙器 | 类型:攻击类/飞剑 | 效果:攻击+50%，雷属性麻痹 | 认主要求:神识烙印 | 对应境界:元婴期",
            "birth_story": "天雷剑以上古雷修遗留的雷灵石为核心，辅以星辰铁炼制。剑灵初生，可自主引导雷属性攻击，是元婴期修士梦寐以求的仙器。",
            "belong_area": "上古秘境",
            "equip_type": "weapon",
            "grade": "仙器",
        },
        # ── 防具 ──
        {
            "id": "equip_xuanwu_shield",
            "entity_type": "equip",
            "name": "玄武盾",
            "base_info": "金丹期灵器护盾，可形成玄武虚影护体。防御+30%，反弹10%伤害，是金丹期修士的强力防御法器。",
            "attr": "品级:灵器 | 类型:防御类/护盾 | 效果:防御+30%，反弹10% | 认主要求:灵力注入 | 对应境界:金丹期",
            "birth_story": "玄武盾以玄铁与水属性灵石炼制，激活后形成玄武虚影护体。防御力出众，是金丹期修士的强力防御法器。",
            "belong_area": "青云古域",
            "equip_type": "armor",
            "grade": "灵器",
        },
        {
            "id": "equip_jinguang_armor",
            "entity_type": "equip",
            "name": "金光战甲",
            "base_info": "元婴期仙器铠甲，金光护体，刀枪不入。防御+50%，吸收30%伤害，是元婴期修士的顶级防御仙器。",
            "attr": "品级:仙器 | 类型:防御类/铠甲 | 效果:防御+50%，吸收30%伤害 | 认主要求:神识烙印 | 对应境界:元婴期",
            "birth_story": "金光战甲以上古金属性灵石为核心炼制，金光流转，坚不可摧。是元婴期修士的顶级防御仙器，极为稀有。",
            "belong_area": "上古秘境",
            "equip_type": "armor",
            "grade": "仙器",
        },
        # ── 辅助类 ──
        {
            "id": "equip_chuwu_bag",
            "entity_type": "equip",
            "name": "储物袋",
            "base_info": "筑基期辅助法器，内含独立空间，可储存物品。空间大小与注入灵力成正比，是修士必备法器。",
            "attr": "品级:灵器 | 类型:辅助类/储物 | 效果:独立储物空间 | 认主要求:灵力注入 | 对应境界:筑基期",
            "birth_story": "储物袋以空间属性灵石为核心炼制，内含独立空间。是修士日常必备法器，空间大小与注入灵力成正比。",
            "belong_area": "青云古域",
            "equip_type": "accessory",
            "grade": "灵器",
        },
        {
            "id": "equip_juling_pearl",
            "entity_type": "equip",
            "name": "聚灵珠",
            "base_info": "金丹期辅助法器，可自动汇聚天地灵气，生成精纯灵液。修炼速度+15%，是金丹期修士的修炼利器。",
            "attr": "品级:灵器 | 类型:辅助类/聚灵 | 效果:修炼速度+15%，生成灵液 | 认主要求:灵力注入 | 对应境界:金丹期",
            "birth_story": "聚灵珠以先天灵脉核心碎片炼制，可自动汇聚天地灵气。是金丹期修士的修炼利器，极为珍贵。",
            "belong_area": "青云古域",
            "equip_type": "accessory",
            "grade": "灵器",
        },
        {
            "id": "equip_danlu",
            "entity_type": "equip",
            "name": "玄火丹炉",
            "base_info": "金丹期炼丹法器，内置玄火，可自动控温炼丹。炼丹成功率+10%，是炼丹师的必备法器。",
            "attr": "品级:灵器 | 类型:辅助类/丹炉 | 效果:炼丹成功率+10% | 认主要求:灵力注入 | 对应境界:金丹期",
            "birth_story": "玄火丹炉以玄铁与火属性灵石炼制，内置玄火可自动控温。是丹霞门弟子标配法器，也是炼丹师的必备之物。",
            "belong_area": "青云古域",
            "equip_type": "accessory",
            "grade": "灵器",
        },
    ]
    return equipments


def build_technique_entities() -> List[dict]:
    """构建功法武技实体数据"""
    techniques = [
        # ── 心法 ──
        {
            "id": "tech_xinfa_tuna",
            "entity_type": "technique",
            "name": "吐纳归元诀",
            "base_info": "凡阶心法，最基础的灵力修炼之法。修炼速度+5%，是所有修士入门必修功法。",
            "attr": "品级:凡阶 | 类型:心法 | 效果:修炼速度+5% | 习得条件:无 | 对应境界:炼气期",
            "birth_story": "吐纳归元诀是上古大劫后流传最广的基础心法，几乎所有修士都从此法入门。简单易学，但上限有限。",
            "belong_area": "全境通用",
            "technique_type": "心法",
            "grade": "凡阶",
        },
        {
            "id": "tech_xinfa_qingyun",
            "entity_type": "technique",
            "name": "青云心经",
            "base_info": "灵阶心法，青云宗核心传承心法。灵力修炼+15%，道心稳固+5%，需先天灵根或变异灵根方可修炼。",
            "attr": "品级:灵阶 | 类型:心法 | 效果:灵力修炼+15%，道心稳固+5% | 习得条件:先天/变异灵根 | 对应境界:筑基期",
            "birth_story": "青云心经为青云宗开宗祖师青云子所创，以上古道经残卷为根基，结合自身悟道心得而成。是青云宗弟子的核心修炼功法。",
            "belong_area": "青云古域",
            "technique_type": "心法",
            "grade": "灵阶",
        },
        {
            "id": "tech_xinfa_taixu",
            "entity_type": "technique",
            "name": "太虚道心诀",
            "base_info": "仙阶心法，残缺1/4。灵力修炼+30%，道心稳固+15%，悟道效率+10%。需在秘境中感悟道韵补全残缺部分。",
            "attr": "品级:仙阶 | 类型:心法 | 效果:灵力修炼+30%，道心稳固+15%，悟道+10% | 习得条件:元婴期+先天灵根 | 残缺程度:1/4 | 对应境界:元婴期",
            "birth_story": "太虚道心诀为上古太虚道人所创，大劫后残缺1/4。残卷藏于太虚遗迹中，需感悟道韵方可补全。补全后效果极为强大。",
            "belong_area": "上古秘境",
            "technique_type": "心法",
            "grade": "仙阶",
        },
        # ── 身法 ──
        {
            "id": "tech_shenfa_qingfeng",
            "entity_type": "technique",
            "name": "轻风步",
            "base_info": "凡阶身法，速度+10%，闪避+5%。简单实用，是低阶修士最常用的身法。",
            "attr": "品级:凡阶 | 类型:身法 | 效果:速度+10%，闪避+5% | 习得条件:无 | 对应境界:炼气期",
            "birth_story": "轻风步是修行界流传最广的基础身法，以风属性灵力催动，简单易学但上限有限。",
            "belong_area": "全境通用",
            "technique_type": "身法",
            "grade": "凡阶",
        },
        {
            "id": "tech_shenfa_yunzong",
            "entity_type": "technique",
            "name": "云踪幻影",
            "base_info": "灵阶身法，速度+25%，闪避+15%，可短距离瞬移。需风属性灵根方可修炼至大成。",
            "attr": "品级:灵阶 | 类型:身法 | 效果:速度+25%，闪避+15%，短距瞬移 | 习得条件:筑基期+风属性灵根 | 对应境界:筑基期",
            "birth_story": "云踪幻影为青云宗先辈观云悟道所创，修炼至大成可化身云雾，瞬息千里。需风属性灵根方可修炼至大成。",
            "belong_area": "青云古域",
            "technique_type": "身法",
            "grade": "灵阶",
        },
        # ── 攻击功法 ──
        {
            "id": "tech_gongfa_liehuo",
            "entity_type": "technique",
            "name": "烈火掌",
            "base_info": "凡阶攻击功法，火属性攻击，伤害+10%。简单直接，是火属性修士的入门攻击功法。",
            "attr": "品级:凡阶 | 类型:攻击功法 | 效果:火属性攻击，伤害+10% | 习得条件:火属性灵根 | 对应境界:炼气期",
            "birth_story": "烈火掌是修行界最常见的火属性攻击功法，以火属性灵力凝聚掌心，一掌击出烈焰灼人。",
            "belong_area": "全境通用",
            "technique_type": "攻击功法",
            "grade": "凡阶",
        },
        {
            "id": "tech_gongfa_tianlei",
            "entity_type": "technique",
            "name": "天雷剑诀",
            "base_info": "灵阶攻击功法，雷属性剑技，伤害+25%，附带麻痹效果。需雷属性灵根，配合飞剑使用。",
            "attr": "品级:灵阶 | 类型:攻击功法 | 效果:雷属性剑技，伤害+25%，麻痹 | 习得条件:筑基期+雷属性灵根 | 对应境界:筑基期",
            "birth_story": "天雷剑诀为青云宗宗主云无极所创，以先天雷灵根催动，剑出如雷，威力惊人。是青云宗内门弟子的核心攻击功法。",
            "belong_area": "青云古域",
            "technique_type": "攻击功法",
            "grade": "灵阶",
        },
        # ── 防御功法 ──
        {
            "id": "tech_gongfa_shifu",
            "entity_type": "technique",
            "name": "石肤术",
            "base_info": "凡阶防御功法，防御+10%。以土属性灵力硬化皮肤，简单实用。",
            "attr": "品级:凡阶 | 类型:防御功法 | 效果:防御+10% | 习得条件:土属性灵根 | 对应境界:炼气期",
            "birth_story": "石肤术是最基础的防御功法，以土属性灵力硬化皮肤，抵御物理攻击。简单易学，是土属性修士的入门防御功法。",
            "belong_area": "全境通用",
            "technique_type": "防御功法",
            "grade": "凡阶",
        },
        {
            "id": "tech_gongfa_jinguang",
            "entity_type": "technique",
            "name": "金光护体",
            "base_info": "灵阶防御功法，防御+25%，反弹10%伤害。需金属性灵根，是金丹期修士的强力防御功法。",
            "attr": "品级:灵阶 | 类型:防御功法 | 效果:防御+25%，反弹10% | 习得条件:金丹期+金属性灵根 | 对应境界:金丹期",
            "birth_story": "金光护体为玄清观核心防御功法，以金属性灵力形成金色护罩，防御与反击兼备。",
            "belong_area": "青云古域",
            "technique_type": "防御功法",
            "grade": "灵阶",
        },
        # ── 辅助功法 ──
        {
            "id": "tech_gongfa_juling",
            "entity_type": "technique",
            "name": "聚灵术",
            "base_info": "凡阶辅助功法，灵气吸收+10%。可加速灵力恢复，是低阶修士的常用辅助功法。",
            "attr": "品级:凡阶 | 类型:辅助功法 | 效果:灵气吸收+10% | 习得条件:无 | 对应境界:炼气期",
            "birth_story": "聚灵术是最基础的辅助功法，可加速灵气吸收，提升修炼效率。简单易学，几乎所有修士都会修炼。",
            "belong_area": "全境通用",
            "technique_type": "辅助功法",
            "grade": "凡阶",
        },
    ]
    return techniques


def build_links() -> List[dict]:
    """构建实体间的关联关系"""
    links = [
        # ── 地域包含关系 ──
        {"from_id": "area_qingyun", "to_id": "faction_qingyun", "rel_type": "contains", "desc": "青云古域包含青云宗"},
        {"from_id": "area_qingyun", "to_id": "faction_danxia", "rel_type": "contains", "desc": "青云古域包含丹霞门"},
        {"from_id": "area_qingyun", "to_id": "faction_xuanqing", "rel_type": "contains", "desc": "青云古域包含玄清观"},
        {"from_id": "area_youhan", "to_id": "faction_xueying", "rel_type": "contains", "desc": "幽寒邪域包含血影教"},
        {"from_id": "area_youhan", "to_id": "faction_gukui", "rel_type": "contains", "desc": "幽寒邪域包含骨傀门"},
        {"from_id": "area_youhan", "to_id": "faction_youyue", "rel_type": "contains", "desc": "幽寒邪域包含幽月谷"},
        {"from_id": "area_yuncen", "to_id": "faction_yuncen_spirit", "rel_type": "contains", "desc": "云岑灵境包含云岑灵族"},
        {"from_id": "area_huanggu", "to_id": "faction_heifeng_beast", "rel_type": "contains", "desc": "荒古野域包含黑风兽域"},

        # ── NPC归属关系 ──
        {"from_id": "npc_qingyun_zongzhu", "to_id": "faction_qingyun", "rel_type": "belongs_to", "desc": "云无极为青云宗宗主"},
        {"from_id": "npc_qingyun_zhifa", "to_id": "faction_qingyun", "rel_type": "belongs_to", "desc": "铁面真人为青云宗执法堂首席"},
        {"from_id": "npc_qingyun_neimen", "to_id": "faction_qingyun", "rel_type": "belongs_to", "desc": "苏瑶为青云宗内门弟子"},
        {"from_id": "npc_qingyun_waimen", "to_id": "faction_qingyun", "rel_type": "belongs_to", "desc": "林风为青云宗外门弟子"},
        {"from_id": "npc_danxia_zhangmen", "to_id": "faction_danxia", "rel_type": "belongs_to", "desc": "药尘子为丹霞门掌门"},
        {"from_id": "npc_xuanqing_guanzhu", "to_id": "faction_xuanqing", "rel_type": "belongs_to", "desc": "清虚道人为玄清观观主"},
        {"from_id": "npc_xueying_jiaozhu", "to_id": "faction_xueying", "rel_type": "belongs_to", "desc": "血魔尊者为血影教教主"},
        {"from_id": "npc_xueying_hufa", "to_id": "faction_xueying", "rel_type": "belongs_to", "desc": "厉魂为血影教左护法"},
        {"from_id": "npc_yuncen_zuzhang", "to_id": "faction_yuncen_spirit", "rel_type": "belongs_to", "desc": "碧梧长老为云岑灵族大长老"},
        {"from_id": "npc_heifeng_shouwang", "to_id": "faction_heifeng_beast", "rel_type": "belongs_to", "desc": "黑风兽王为黑风兽域兽王"},

        # ── NPC所在地域 ──
        {"from_id": "npc_qingyun_zongzhu", "to_id": "area_qingyun", "rel_type": "located_in", "desc": "云无极常驻青云古域"},
        {"from_id": "npc_sanxiu_xunbao", "to_id": "area_huanggu", "rel_type": "located_in", "desc": "寻宝散人常在荒古野域活动"},
        {"from_id": "npc_sanxiu_yinshi", "to_id": "area_huanggu", "rel_type": "located_in", "desc": "无名老者隐居荒古野域深处"},
        {"from_id": "npc_yuncen_zuzhang", "to_id": "area_yuncen", "rel_type": "located_in", "desc": "碧梧长老常驻云岑灵境"},
        {"from_id": "npc_heifeng_shouwang", "to_id": "area_huanggu", "rel_type": "located_in", "desc": "黑风兽王盘踞荒古野域"},

        # ── 宗门关系 ──
        {"from_id": "faction_qingyun", "to_id": "faction_danxia", "rel_type": "allied", "desc": "青云宗与丹霞门互为盟友"},
        {"from_id": "faction_qingyun", "to_id": "faction_xuanqing", "rel_type": "allied", "desc": "青云宗与玄清观互为盟友"},
        {"from_id": "faction_qingyun", "to_id": "faction_xueying", "rel_type": "hostile", "desc": "青云宗与血影教势不两立"},
        {"from_id": "faction_danxia", "to_id": "faction_xueying", "rel_type": "hostile", "desc": "丹霞门与血影教敌对"},
        {"from_id": "faction_xuanqing", "to_id": "faction_xueying", "rel_type": "hostile", "desc": "玄清观与血影教敌对"},

        # ── 物品归属关系 ──
        {"from_id": "equip_qingfeng_sword", "to_id": "faction_qingyun", "rel_type": "produced_by", "desc": "青锋剑为青云宗炼制"},
        {"from_id": "equip_danlu", "to_id": "faction_danxia", "rel_type": "produced_by", "desc": "玄火丹炉为丹霞门炼制"},
        {"from_id": "item_pill_zhuji", "to_id": "faction_danxia", "rel_type": "produced_by", "desc": "筑基丹为丹霞门炼制"},
        {"from_id": "item_talisman_huodan", "to_id": "faction_xuanqing", "rel_type": "produced_by", "desc": "火弹符为玄清观炼制"},
        {"from_id": "item_talisman_jingang", "to_id": "faction_xuanqing", "rel_type": "produced_by", "desc": "金刚符为玄清观炼制"},

        # ── 功法归属关系 ──
        {"from_id": "tech_xinfa_qingyun", "to_id": "faction_qingyun", "rel_type": "owned_by", "desc": "青云心经为青云宗核心传承"},
        {"from_id": "tech_gongfa_tianlei", "to_id": "faction_qingyun", "rel_type": "owned_by", "desc": "天雷剑诀为青云宗宗主所创"},
        {"from_id": "tech_gongfa_jinguang", "to_id": "faction_xuanqing", "rel_type": "owned_by", "desc": "金光护体为玄清观核心功法"},
        {"from_id": "tech_xinfa_taixu", "to_id": "area_ancient_realm", "rel_type": "located_in", "desc": "太虚道心诀残卷藏于上古秘境"},

        # ── NPC师徒关系 ──
        {"from_id": "npc_qingyun_neimen", "to_id": "npc_qingyun_zongzhu", "rel_type": "disciple_of", "desc": "苏瑶师从云无极"},
        {"from_id": "npc_xueying_hufa", "to_id": "npc_xueying_jiaozhu", "rel_type": "subordinate", "desc": "厉魂为血魔尊者左护法"},

        # ── NPC恩怨关系 ──
        {"from_id": "npc_xueying_jiaozhu", "to_id": "npc_qingyun_zongzhu", "rel_type": "enemy", "desc": "血魔尊者与云无极势不两立"},
        {"from_id": "npc_xueying_jiaozhu", "to_id": "faction_qingyun", "rel_type": "enemy", "desc": "血魔尊者被青云宗逐出，发誓覆灭青云宗"},
    ]
    return links


# ───────────────────────────────────────────────
# LLM 润色扩充
# ───────────────────────────────────────────────

SYSTEM_PROMPT_WORLD_SEED = """你是《青墟灵修志》的世界构建大师，精通修仙世界观设定。
你的任务是对给定的世界种子数据进行润色和扩充，使世界更加丰满、生动、有深度。

核心原则：
1. 保持与原始设定的一致性，不改变核心事实
2. 丰富细节描述，增加场景感、氛围感
3. 补充隐含的逻辑关联和因果线索
4. 融入"修心重于修为、因果缠身为行事准则"的核心精神
5. 体现"上古劫后遗落世道、重修古道"的世界基调

输出要求：严格输出 JSON 格式，保持原始数据结构，仅扩充 base_info、birth_story 和 scenes 字段的内容。"""


def llm_polish_entities(llm: LLMClient, entities: List[dict],
                        category_name: str) -> List[dict]:
    """使用 LLM 润色扩充实体数据"""
    info_log(f"正在通过 LLM 润色 {category_name}（共 {len(entities)} 个实体）...")

    # 分批处理，每批最多3个实体
    batch_size = 3
    polished_entities = []

    for i in range(0, len(entities), batch_size):
        batch = entities[i:i + batch_size]
        batch_names = [e.get("name", "未知") for e in batch]
        info_log(f"  润色批次 {i // batch_size + 1}: {', '.join(batch_names)}")

        user_prompt = f"""请润色和扩充以下{category_name}的数据，丰富描述细节，增加场景感和氛围感。
保持原始数据结构不变，仅扩充 base_info、birth_story 和 scenes（如有）字段的内容。
每个实体的 base_info 扩充到100字以上，birth_story 扩充到150字以上。

原始数据：
{json.dumps(batch, ensure_ascii=False, indent=2)}

请输出润色后的完整 JSON 数组，保持原始字段结构。"""

        result = llm.chat_json(SYSTEM_PROMPT_WORLD_SEED, user_prompt)
        if result:
            # 如果返回的是数组
            if isinstance(result, list):
                polished_entities.extend(result)
            # 如果返回的是包含数组的对象
            elif isinstance(result, dict):
                for key in ["entities", "data", "items", "results"]:
                    if key in result and isinstance(result[key], list):
                        polished_entities.extend(result[key])
                        break
                else:
                    # 单个对象，可能是批次中只有一个
                    polished_entities.append(result)
        else:
            warn_log(f"  批次 {i // batch_size + 1} LLM 润色失败，保留原始数据")
            polished_entities.extend(batch)

    info_log(f"{category_name} 润色完成，共 {len(polished_entities)} 个实体")
    return polished_entities


def llm_generate_world_narrative(llm: LLMClient, all_docs: Dict[str, str]) -> str:
    """使用 LLM 生成完整的世界叙事描述"""
    info_log("正在通过 LLM 生成世界叙事描述...")

    # 精简文档内容，避免超出 token 限制
    doc_summaries = []
    for filename, content in all_docs.items():
        # 取每个文档的前500字
        summary = content + ("..." if len(content) > 500 else "")
        doc_summaries.append(f"## {DOC_FILES.get(filename, filename)}\n{summary}")

    docs_text = "\n\n".join(doc_summaries)

    user_prompt = f"""基于以下《青墟灵修志》的世界设定文档，请生成一段完整的世界叙事描述。
这段描述将作为世界种子存储到记忆库中，供 AI 在后续交互中参考。

要求：
1. 以第三人称叙述，描述整个青墟大世界的现状
2. 涵盖世界起源、地域格局、势力分布、修行体系、资源物产、因果法则
3. 体现"上古劫后遗落世道、重修古道"的世界基调
4. 体现"修心重于修为、因果缠身为行事准则"的核心精神
5. 字数800-1200字
6. 语言风格：古风修仙，庄重典雅

世界设定文档摘要：
{docs_text}

请直接输出叙事文本，不需要 JSON 格式。"""

    narrative = llm.chat(SYSTEM_PROMPT_WORLD_SEED, user_prompt)
    if narrative:
        info_log(f"世界叙事描述生成完成，共 {len(narrative)} 字")
    else:
        warn_log("世界叙事描述生成失败")
    return narrative


# ───────────────────────────────────────────────
# 世界种子主流程
# ───────────────────────────────────────────────

class WorldSeedGenerator:
    """世界种子生成器"""

    def __init__(self, config: dict, skip_llm: bool = False,
                 skip_save: bool = False, verbose: bool = False):
        self.config = config
        self.skip_llm = skip_llm
        self.skip_save = skip_save
        self.verbose = verbose

        # 统计数据
        self.stats = {
            "areas": 0,
            "factions": 0,
            "npcs": 0,
            "items": 0,
            "equipments": 0,
            "techniques": 0,
            "links": 0,
            "memories": 0,
        }

    def run(self):
        """执行世界种子生成流程"""
        info_log("=" * 60)
        info_log("《青墟灵修志》世界种子生成器")
        info_log("=" * 60)

        # 1. 读取世界设定文档
        docs = read_all_docs()

        # 2. 构建基础种子数据
        info_log("\n--- 构建基础种子数据 ---")
        areas = build_area_entities()
        factions = build_faction_entities()
        npcs = build_npc_entities()
        items = build_item_entities()
        equipments = build_equipment_entities()
        techniques = build_technique_entities()
        links = build_links()

        info_log(f"地域: {len(areas)} | 宗门: {len(factions)} | NPC: {len(npcs)}")
        info_log(f"物品: {len(items)} | 装备: {len(equipments)} | 功法: {len(techniques)}")
        info_log(f"关联: {len(links)}")

        # 3. LLM 润色扩充
        if not self.skip_llm:
            info_log("\n--- LLM 润色扩充 ---")
            gm_cfg = self.config.get("gm", {})
            world_model_cfg = gm_cfg.get("world_model", {})

            with LLMClient(
                api_base=world_model_cfg.get("api_base", "http://localhost:7779/v1"),
                api_key=world_model_cfg.get("api_key", "not-needed"),
                model_name=world_model_cfg.get("model_name", "Qwen3.6-27B-MTP"),
                temperature=world_model_cfg.get("temperature", 0.7),
                max_tokens=world_model_cfg.get("max_tokens", 8192),
            ) as llm:
                areas = llm_polish_entities(llm, areas, "地域/大陆")
                factions = llm_polish_entities(llm, factions, "宗门势力")
                npcs = llm_polish_entities(llm, npcs, "NPC角色")
                items = llm_polish_entities(llm, items, "物品资源")
                equipments = llm_polish_entities(llm, equipments, "法宝装备")
                techniques = llm_polish_entities(llm, techniques, "功法武技")

                # 生成世界叙事描述
                world_narrative = llm_generate_world_narrative(llm, docs)
        else:
            info_log("\n--- 跳过 LLM 润色（--skip-llm）---")
            world_narrative = self._build_fallback_narrative(docs)

        # 4. 保存到数据库
        if not self.skip_save:
            info_log("\n--- 保存到数据库 ---")
            self._save_all(areas, factions, npcs, items, equipments,
                           techniques, links, world_narrative)
        else:
            info_log("\n--- 跳过保存（--skip-save）---")

        # 5. 输出统计
        self._print_summary()

    def _build_fallback_narrative(self, docs: Dict[str, str]) -> str:
        """当跳过 LLM 时，基于文档构建基础叙事"""
        return (
            "青墟大世界，上古劫后遗落之地。太古纪元万族共生，灵脉充盈，"
            "道祖大能悟大道修古法；上古纪元万族争霸，战火绵延万年，"
            "终触天地规则反噬，灵脉断裂、道则残缺、高阶传承焚毁，"
            "道祖大能或陨落或破碎虚空逃离，仅少数低阶修士与残缺典籍留存。"
            "\n\n"
            "大劫落幕十万载，青墟天地灵气缓慢复苏，但道统残缺、传承断层。"
            "修行界四大域各据一方：青云古域正道宗门守护灵脉传承古法，"
            "荒古野域无主之地妖兽横行机缘众多，"
            "幽寒邪域邪修盘踞掠夺修为，云岑灵境灵族隐居不问世事。"
            "上古秘境随机现世，藏有上古典籍与天材地宝，但时空错乱危机四伏。"
            "\n\n"
            "现世修士各持残缺古法，在重修古道的执念中演绎世间百态。"
            "修心重于修为，道心重于灵力，因果缠身为行事准则。"
            "恩怨皆有回响，心境不达标即便灵力充盈亦无法突破大境界。"
            "这是青墟大世界——上古劫后的遗落世道，重修古道之路。"
        )

    def _save_all(self, areas, factions, npcs, items, equipments,
                  techniques, links, world_narrative):
        """保存所有数据到 CouchDB 和 Hindsight"""
        gm_cfg = self.config.get("gm", {})
        couch_cfg = gm_cfg.get("couchdb", {})
        hindsight_cfg = gm_cfg.get("hindsight", {})

        # ── 保存到 CouchDB ──
        with CouchDBStore(
            url=couch_cfg.get("url", "http://localhost:5984"),
            db_prefix=couch_cfg.get("db_prefix", "thatman_"),
            user=couch_cfg.get("user", "admin"),
            password=couch_cfg.get("password", "password"),
        ) as couch:
            # 添加时间戳
            now = datetime.now(timezone.utc).isoformat()

            # 保存地域
            for entity in areas:
                entity["created_at"] = now
                entity["updated_at"] = now
                entity["seed_version"] = "v1"
                if couch.save_entity(entity["id"], entity):
                    self.stats["areas"] += 1

            # 保存宗门
            for entity in factions:
                entity["created_at"] = now
                entity["updated_at"] = now
                entity["seed_version"] = "v1"
                if couch.save_entity(entity["id"], entity):
                    self.stats["factions"] += 1

            # 保存NPC
            for entity in npcs:
                entity["created_at"] = now
                entity["updated_at"] = now
                entity["seed_version"] = "v1"
                if couch.save_entity(entity["id"], entity):
                    self.stats["npcs"] += 1

            # 保存物品
            for entity in items:
                entity["created_at"] = now
                entity["updated_at"] = now
                entity["seed_version"] = "v1"
                if couch.save_entity(entity["id"], entity):
                    self.stats["items"] += 1

            # 保存装备
            for entity in equipments:
                entity["created_at"] = now
                entity["updated_at"] = now
                entity["seed_version"] = "v1"
                if couch.save_entity(entity["id"], entity):
                    self.stats["equipments"] += 1

            # 保存功法
            for entity in techniques:
                entity["created_at"] = now
                entity["updated_at"] = now
                entity["seed_version"] = "v1"
                if couch.save_entity(entity["id"], entity):
                    self.stats["techniques"] += 1

            # 保存关联关系
            for link in links:
                if couch.save_link(
                    link["from_id"], link["to_id"],
                    link["rel_type"], link["desc"]
                ):
                    self.stats["links"] += 1

            # 保存世界快照
            snap_data = {
                "snap_type": "world_seed",
                "created_at": now,
                "seed_version": "v1",
                "summary": {
                    "areas": len(areas),
                    "factions": len(factions),
                    "npcs": len(npcs),
                    "items": len(items),
                    "equipments": len(equipments),
                    "techniques": len(techniques),
                    "links": len(links),
                },
                "world_narrative": world_narrative,
            }
            couch.save_world_snap(snap_data)

        # ── 保存到 Hindsight ──
        hindsight_base_url = hindsight_cfg.get("base_url", "http://localhost:8888")
        hindsight_api_key = hindsight_cfg.get("api_key")

        with HindsightStore(
            base_url=hindsight_base_url,
            api_key=hindsight_api_key,
            bank_id="world",
        ) as hindsight:
            # 保存世界叙事描述
            if world_narrative:
                if hindsight.retain(
                    content=world_narrative,
                    context="world_lore",
                    metadata={"type": "world_narrative", "version": "v1"},
                ):
                    self.stats["memories"] += 1

            # 保存地域记忆
            for area in areas:
                content = f"【{area['name']}】{area.get('base_info', '')}"
                if area.get("scenes"):
                    scene_desc = "；".join(
                        f"{s['name']}：{s['desc']}" for s in area["scenes"]
                    )
                    content += f"。主要场景：{scene_desc}"
                if hindsight.retain(
                    content=content,
                    context="world_location",
                    metadata={"type": "area", "area_id": area["id"]},
                ):
                    self.stats["memories"] += 1

            # 保存宗门记忆
            for faction in factions:
                content = f"【{faction['name']}】{faction.get('base_info', '')}"
                if hindsight.retain(
                    content=content,
                    context="world_lore",
                    metadata={"type": "faction", "faction_id": faction["id"]},
                ):
                    self.stats["memories"] += 1

            # 保存NPC记忆
            for npc in npcs:
                content = (
                    f"【{npc['name']}】{npc.get('base_info', '')}"
                    f"。境界：{npc.get('realm', '未知')}，"
                    f"灵根：{npc.get('spirit_root', '未知')}，"
                    f"身份：{npc.get('identity', '未知')}，"
                    f"心境：{npc.get('personality', '未知')}"
                )
                if hindsight.retain(
                    content=content,
                    context="world_npc",
                    metadata={"type": "npc", "npc_id": npc["id"]},
                ):
                    self.stats["memories"] += 1

            # 保存物品记忆
            for item in items:
                content = f"【{item['name']}】{item.get('base_info', '')}"
                if hindsight.retain(
                    content=content,
                    context="world_lore",
                    metadata={"type": "item", "item_id": item["id"]},
                ):
                    self.stats["memories"] += 1

            # 保存装备记忆
            for equip in equipments:
                content = f"【{equip['name']}】{equip.get('base_info', '')}"
                if hindsight.retain(
                    content=content,
                    context="world_lore",
                    metadata={"type": "equipment", "equip_id": equip["id"]},
                ):
                    self.stats["memories"] += 1

            # 保存功法记忆
            for tech in techniques:
                content = f"【{tech['name']}】{tech.get('base_info', '')}"
                if hindsight.retain(
                    content=content,
                    context="world_lore",
                    metadata={"type": "technique", "tech_id": tech["id"]},
                ):
                    self.stats["memories"] += 1

            # 保存关键因果法则记忆
            law_memories = [
                {
                    "content": "青墟大世界核心法则：修心重于修为，道心重于灵力。心境不达标，即便灵力充盈亦无法突破大境界。道心破碎则修为尽废。",
                    "context": "world_lore",
                    "metadata": {"type": "law", "category": "修行法则"},
                },
                {
                    "content": "青墟大世界因果法则：相遇即有因果，恩怨皆有回响。恩怨未解则道心难安，难以突破高阶境界。因果循环，凡有交集必留痕迹。",
                    "context": "world_lore",
                    "metadata": {"type": "law", "category": "因果法则"},
                },
                {
                    "content": "青墟大世界天地平衡法则：灵气不会无限暴涨或枯竭，势力不会一家独大，内置自然回调机制。天地规则会对过度掠夺、破坏平衡者施加反噬。",
                    "context": "world_lore",
                    "metadata": {"type": "law", "category": "天地法则"},
                },
                {
                    "content": "青墟大世界上古大劫历史：太古纪元万族共生，上古纪元万族争霸触发天地规则反噬，灵脉断裂、道则残缺、高阶传承焚毁。现世道统残缺，修士需在残缺典籍中拼凑古法。",
                    "context": "world_event",
                    "metadata": {"type": "history", "category": "上古大劫"},
                },
                {
                    "content": "青墟大世界正邪对立：正统宗门与邪修势力天生敌对，不可和解。正道坚守古法护持灵脉，邪修摒弃古法走速成捷径掠夺他人修为。双方相遇即触发敌对行为。",
                    "context": "world_lore",
                    "metadata": {"type": "law", "category": "阵营法则"},
                },
            ]
            count = hindsight.retain_batch(law_memories)
            self.stats["memories"] += count

    def _print_summary(self):
        """输出统计摘要"""
        info_log("\n" + "=" * 60)
        info_log("世界种子生成完成 - 统计摘要")
        info_log("=" * 60)
        info_log(f"  地域/大陆:  {self.stats['areas']} 个")
        info_log(f"  宗门势力:  {self.stats['factions']} 个")
        info_log(f"  NPC角色:   {self.stats['npcs']} 个")
        info_log(f"  物品资源:  {self.stats['items']} 个")
        info_log(f"  法宝装备:  {self.stats['equipments']} 个")
        info_log(f"  功法武技:  {self.stats['techniques']} 个")
        info_log(f"  关联关系:  {self.stats['links']} 条")
        info_log(f"  世界记忆:  {self.stats['memories']} 条")
        total = sum(self.stats.values())
        info_log(f"  总计:      {total} 条")
        info_log("=" * 60)

        if not self.skip_save:
            success_log("世界种子已保存到 CouchDB 和 Hindsight 记忆库")
        else:
            warn_log("世界种子未保存（--skip-save 模式）")


# ───────────────────────────────────────────────
# 入口
# ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="《青墟灵修志》世界种子生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python init_world_seed.py                  # 完整流程
  python init_world_seed.py --skip-llm       # 跳过LLM润色，使用基础数据
  python init_world_seed.py --skip-save      # 跳过保存，仅生成数据
  python init_world_seed.py --verbose        # 详细日志输出
        """,
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="跳过 LLM 润色扩充，使用基础种子数据"
    )
    parser.add_argument(
        "--skip-save", action="store_true",
        help="跳过保存到数据库，仅生成数据"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="输出详细日志"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    config = load_config()
    generator = WorldSeedGenerator(
        config=config,
        skip_llm=args.skip_llm,
        skip_save=args.skip_save,
        verbose=args.verbose,
    )
    generator.run()


if __name__ == "__main__":
    main()
