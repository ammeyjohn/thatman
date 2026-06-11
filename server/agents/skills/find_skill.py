"""
Find Skill - 查找可用技能

列出和搜索 agents 模块中所有可用的 skills 功能。
"""

import os
import logging
import importlib
import inspect
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

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


# Skills 目录路径
SKILLS_DIR = Path(__file__).parent

# 预定义的 skill 描述信息
SKILL_DESCRIPTIONS = {
    "read_doc": {
        "name": "read_doc",
        "description": "读取文档文件内容",
        "functions": {
            "read_doc": {
                "description": "读取指定文档文件的完整内容",
                "params": ["filename: str - 文档文件名，如 'world_config.md' 或 '世界观.md'"],
                "returns": "Dict[str, Any] - 包含 success, filename, title, content, error 的字典",
            },
            "list_available_docs": {
                "description": "列出所有可用的文档文件",
                "params": [],
                "returns": "Dict[str, str] - 文档文件名到标题的映射",
            },
            "search_doc_content": {
                "description": "在所有文档中搜索包含关键词的内容",
                "params": ["keyword: str - 搜索关键词"],
                "returns": "Dict[str, Any] - 包含搜索结果的字典",
            },
        },
    },
    "find_skill": {
        "name": "find_skill",
        "description": "查找和列出所有可用的 skills 功能",
        "functions": {
            "list_all_skills": {
                "description": "列出所有可用的 skills",
                "params": ["include_details: bool - 是否包含详细信息，默认为 True"],
                "returns": "Dict[str, Any] - 包含所有 skill 信息的字典",
            },
            "search_skill": {
                "description": "根据关键词搜索 skill",
                "params": [
                    "keyword: str - 搜索关键词",
                    "search_in_description: bool - 是否在描述中搜索，默认为 True",
                ],
                "returns": "Dict[str, Any] - 包含搜索结果的字典",
            },
            "get_skill_info": {
                "description": "获取指定 skill 的详细信息",
                "params": ["skill_name: str - skill 名称"],
                "returns": "Dict[str, Any] - 包含 skill 详细信息的字典",
            },
        },
    },
    "search_episode": {
        "name": "search_episode",
        "description": "根据用户输入和历史聊天内容，从 Qdrant 向量数据库查询相似的小说剧情片段",
        "functions": {
            "search_similar_episodes": {
                "description": "查询相似的剧情片段",
                "params": [
                    "query: str - 用户输入的查询文本",
                    "conversation_history: Optional[List[Dict[str, str]]] - 对话历史消息列表",
                    "top_k: int - 返回的相似剧情数量，默认 5",
                    "collection_name: Optional[str] - Qdrant 集合名称，默认 episode",
                ],
                "returns": "Dict[str, Any] - 包含 success, query, total, episodes, error 的字典",
            },
            "format_episodes_as_context": {
                "description": "将搜索结果格式化为 LLM 可用的上下文字符串",
                "params": [
                    "search_result: Dict[str, Any] - search_similar_episodes 的返回结果",
                    "max_chars: int - 最大字符数限制，默认 2048",
                ],
                "returns": "str - 格式化的上下文字符串",
            },
        },
    },
    "couchdb_skill": {
        "name": "couchdb_skill",
        "description": "CouchDB 读写技能，封装玩家、实体、关系、世界快照的读写操作",
        "functions": {
            "couch_get_player": {
                "description": "查询玩家全档案，返回玩家的完整数据",
                "params": ["uid: str - 玩家唯一标识"],
                "returns": "Dict[str, Any] - 包含 success, uid, data, error 的字典",
            },
            "couch_save_player": {
                "description": "保存玩家变更数据，新增或更新玩家档案",
                "params": [
                    "uid: str - 玩家唯一标识",
                    "data: dict - 玩家变更后的完整数据",
                ],
                "returns": "Dict[str, Any] - 包含 success, uid, rev, error 的字典",
            },
            "couch_get_entity": {
                "description": "按实体ID查询实体详情，如NPC、装备、区域等",
                "params": ["entity_id: str - 实体唯一标识"],
                "returns": "Dict[str, Any] - 包含 success, entity_id, data, error 的字典",
            },
            "couch_save_entity": {
                "description": "新增或修改实体数据",
                "params": [
                    "entity_id: str - 实体唯一标识",
                    "entity_data: dict - 实体变更后的完整数据",
                ],
                "returns": "Dict[str, Any] - 包含 success, entity_id, rev, error 的字典",
            },
            "couch_get_link": {
                "description": "查询指定目标ID和关系类型的关联关系",
                "params": [
                    "target_id: str - 目标实体ID",
                    "rel_type: str - 关系类型，如 owns、belongs_to、located_in 等",
                ],
                "returns": "Dict[str, Any] - 包含 success, target_id, rel_type, total, docs, error 的字典",
            },
            "couch_save_link": {
                "description": "新增两个实体之间的关系",
                "params": [
                    "from_id: str - 关系起点实体ID",
                    "to_id: str - 关系终点实体ID",
                    "rel_type: str - 关系类型",
                    "desc: str - 关系描述",
                ],
                "returns": "Dict[str, Any] - 包含 success, from_id, to_id, rel_type, rev, error 的字典",
            },
            "couch_get_last_world_snap": {
                "description": "获取上一轮世界存档快照",
                "params": [],
                "returns": "Dict[str, Any] - 包含 success, data, error 的字典",
            },
            "couch_save_world_snap": {
                "description": "保存新的世界快照存档",
                "params": ["snap_data: dict - 世界快照数据"],
                "returns": "Dict[str, Any] - 包含 success, doc_id, rev, error 的字典",
            },
        },
    },
    "memory_skill": {
        "name": "memory_skill",
        "description": "长效记忆技能，合并召回个人记忆和世界记忆，支持记忆保存",
        "functions": {
            "recall_all_memory": {
                "description": "合并召回个人记忆和世界记忆，返回与查询相关的记忆内容",
                "params": [
                    "uid: str - 玩家唯一标识",
                    "query: str - 记忆检索查询文本",
                ],
                "returns": "Dict[str, Any] - 包含 success, uid, query, memory_text, error 的字典",
            },
            "save_memory": {
                "description": "保存记忆，namespace 为 user_{uid} 或 world_global_history",
                "params": [
                    "namespace: str - 记忆命名空间，如 user_{uid} 或 world_global_history",
                    "summary: str - 记忆摘要内容",
                ],
                "returns": "Dict[str, Any] - 包含 success, namespace, error 的字典",
            },
        },
    },
    "vector_skill": {
        "name": "vector_skill",
        "description": "Qdrant 剧情向量技能，语义检索过往剧情和剧情入库",
        "functions": {
            "search_plot_vector": {
                "description": "语义检索过往剧情，返回与查询最相似的剧情片段",
                "params": [
                    "query: str - 语义检索查询文本",
                    "top_k: int - 返回最相似的 top_k 条结果，默认3",
                ],
                "returns": "Dict[str, Any] - 包含 success, query, total, episodes, error 的字典",
            },
            "insert_plot_vector": {
                "description": "将剧情内容入库，支持 NPC、装备、区域、阵营等类型",
                "params": [
                    "content: str - 剧情文本内容",
                    "meta: dict - 剧情元数据，包含 type(npc/equip/area/faction) 和 area(地域名)",
                ],
                "returns": "Dict[str, Any] - 包含 success, point_id, error 的字典",
            },
        },
    },
    "action_definition": {
        "name": "action_definition",
        "description": "动作类型定义管理工具，用于查询、创建和列出游戏中的动作类型定义。每个动作类型包含基础耗时、难度、约束规则（允许/禁止的操作）、耗时影响因子等",
        "functions": {
            "create_action_definition": {
                "description": "创建或更新动作类型定义",
                "params": [
                    "definition: dict - 动作定义字典，必须包含 action_id, name, category, base_time_cost, difficulty, restrictions, time_modifiers 等字段",
                ],
                "returns": "Dict[str, Any] - 包含 success, action_id, definition, error 的字典",
            },
            "get_action_definition": {
                "description": "查询指定动作类型定义",
                "params": [
                    "action_id: str - 动作唯一标识",
                ],
                "returns": "Dict[str, Any] - 包含 success, action_id, definition, error 的字典",
            },
            "list_action_definitions": {
                "description": "列出所有动作类型定义，可按类别过滤",
                "params": [
                    "category: str - 类别过滤，如 修炼/战斗/移动/采集/炼制/休息/社交/即时，为空返回所有",
                ],
                "returns": "Dict[str, Any] - 包含 success, total, definitions, error 的字典",
            },
        },
    },
    "character_status_skill": {
        "name": "character_status_skill",
        "description": "角色核心属性状态更新技能，带验证限制。所有核心属性（境界、等级、生命值、法力值、神识值、装备、背包）的修改必须通过此技能完成",
        "functions": {
            "update_character_status": {
                "description": "更新角色核心属性状态（带验证限制）。核心属性包括：realm(境界)、realm_stage(境界阶段)、level(等级)、health/max_health(生命值)、mana/max_mana(法力值)、spirit/max_spirit(神识值)、equipment(装备)、inventory(背包)",
                "params": [
                    "uid: str - 玩家唯一标识",
                    "updates: dict - 待更新的状态字段字典，仅包含需要更新的核心属性字段",
                ],
                "returns": "Dict[str, Any] - 包含 success, uid, updated_fields/rejected_fields, reasons 的字典",
            },
        },
    },
    "karma_skill": {
        "name": "karma_skill",
        "description": "因果业力技能，记录因果事件、查询业力状态、善恶判定、因果羁绊管理、了结因果",
        "functions": {
            "record_karma": {
                "description": "记录一条因果事件，更新玩家业力值",
                "params": [
                    "uid: str - 玩家唯一标识",
                    "karma_type: str - 因果类型：grace(恩情)/enmity(仇怨)/fellowship(同门)/friendship(知己)/contract(契约)/neutral(陌路)",
                    "target_id: str - 目标实体ID（NPC/宗门等）",
                    "target_name: str - 目标名称",
                    "description: str - 因果事件描述",
                    "karma_value: int - 业力变化值，正=善/功德，负=恶/业障",
                ],
                "returns": "Dict[str, Any] - 包含 success, uid, karma_after, karma_level, karma_title 的字典",
            },
            "get_karma_status": {
                "description": "获取玩家业力总览",
                "params": [
                    "uid: str - 玩家唯一标识",
                ],
                "returns": "Dict[str, Any] - 包含 karma, karma_level, karma_title, recent_records, bonds 的字典",
            },
            "judge_karma": {
                "description": "善恶判定，根据行为描述返回善恶判定结果和建议业力值",
                "params": [
                    "uid: str - 玩家唯一标识",
                    "action_description: str - 行为描述",
                    "context: str - 行为上下文",
                ],
                "returns": "Dict[str, Any] - 包含 judgment, suggested_karma_value, reason 的字典",
            },
            "get_karma_bonds": {
                "description": "获取玩家与NPC/实体的因果羁绊列表",
                "params": [
                    "uid: str - 玩家唯一标识",
                ],
                "returns": "Dict[str, Any] - 包含 bonds 列表的字典",
            },
            "resolve_karma": {
                "description": "了结因果，了结后业力变化",
                "params": [
                    "uid: str - 玩家唯一标识",
                    "target_id: str - 因果羁绊的目标实体ID",
                    "resolution_type: str - 了结方式：repay(报恩)/betray(忘恩)/revenge(复仇)/forgive(宽恕)/part(分别)/reunite(重聚)/deepen(加深)/fulfill(履约)/break(违约)",
                ],
                "returns": "Dict[str, Any] - 包含 karma_change, karma_after, karma_level 的字典",
            },
        },
    },
}


def list_all_skills(include_details: bool = True) -> Dict[str, Any]:
    """
    列出所有可用的 skills

    Args:
        include_details: 是否包含详细信息，默认为 True

    Returns:
        包含所有 skill 信息的字典，格式如下:
        {
            "success": True,
            "total": 10,
            "skills": [
                {
                    "name": "skill_name",
                    "description": "skill 描述",
                    "functions": [...]  # 如果 include_details=True
                }
            ]
        }
    """
    skills = []
    
    # 扫描 skills 目录
    if SKILLS_DIR.exists():
        for file_path in SKILLS_DIR.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            skill_name = file_path.stem
            skill_info = SKILL_DESCRIPTIONS.get(skill_name, {})
            
            skill_data = {
                "name": skill_name,
                "description": skill_info.get("description", f"Skill 模块: {skill_name}"),
            }
            
            if include_details:
                skill_data["functions"] = skill_info.get("functions", {})
                skill_data["file"] = str(file_path.relative_to(Path(__file__).parent.parent))
            
            skills.append(skill_data)
    
    # 按名称排序
    skills.sort(key=lambda x: x["name"])
    
    info_log(f"发现 {len(skills)} 个可用 skills")
    
    return {
        "success": True,
        "total": len(skills),
        "skills": skills,
    }


def search_skill(
    keyword: str,
    search_in_description: bool = True,
) -> Dict[str, Any]:
    """
    根据关键词搜索 skill

    Args:
        keyword: 搜索关键词
        search_in_description: 是否在描述中搜索，默认为 True

    Returns:
        包含搜索结果的字典
    """
    keyword = keyword.lower().strip()
    if not keyword:
        return {
            "success": False,
            "error": "搜索关键词不能为空",
            "matches": [],
        }
    
    matches = []
    all_skills = list_all_skills(include_details=True)
    
    for skill in all_skills.get("skills", []):
        # 在名称中搜索
        if keyword in skill["name"].lower():
            matches.append(skill)
            continue
        
        # 在描述中搜索
        if search_in_description and keyword in skill.get("description", "").lower():
            matches.append(skill)
            continue
        
        # 在函数中搜索
        for func_name, func_info in skill.get("functions", {}).items():
            if keyword in func_name.lower():
                matches.append(skill)
                break
            if search_in_description and keyword in func_info.get("description", "").lower():
                matches.append(skill)
                break
    
    info_log(f"搜索完成: 关键词 '{keyword}' 找到 {len(matches)} 个匹配")
    
    return {
        "success": True,
        "keyword": keyword,
        "total_matches": len(matches),
        "matches": matches,
    }


def get_skill_info(skill_name: str) -> Dict[str, Any]:
    """
    获取指定 skill 的详细信息

    Args:
        skill_name: skill 名称

    Returns:
        包含 skill 详细信息的字典
    """
    skill_name = skill_name.strip()
    
    # 从预定义描述中获取
    skill_info = SKILL_DESCRIPTIONS.get(skill_name)
    
    if skill_info:
        return {
            "success": True,
            "skill": skill_info,
        }
    
    # 尝试动态加载模块
    try:
        skill_file = SKILLS_DIR / f"{skill_name}.py"
        if skill_file.exists():
            # 获取文件中的函数信息
            functions = _extract_functions_from_file(skill_file)
            
            return {
                "success": True,
                "skill": {
                    "name": skill_name,
                    "description": f"Skill 模块: {skill_name}",
                    "functions": functions,
                    "file": str(skill_file.relative_to(Path(__file__).parent.parent)),
                },
            }
    except Exception as e:
        error_log(f"获取 skill 信息失败: {e}")
    
    return {
        "success": False,
        "error": f"未找到 skill: {skill_name}",
        "available_skills": list(SKILL_DESCRIPTIONS.keys()),
    }


def _extract_functions_from_file(file_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    从 Python 文件中提取函数信息

    Args:
        file_path: Python 文件路径

    Returns:
        函数名到函数信息的映射
    """
    functions = {}
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 简单解析：查找 def 语句和 docstring
        import ast
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 跳过私有函数
                if node.name.startswith("_"):
                    continue
                
                # 提取 docstring
                docstring = ast.get_docstring(node) or ""
                
                # 提取参数
                params = []
                for arg in node.args.args:
                    if arg.arg != "self":
                        params.append(arg.arg)
                
                functions[node.name] = {
                    "description": docstring.split("\n")[0] if docstring else "",
                    "params": params,
                }
                
    except Exception as e:
        debug_log(f"解析文件失败: {e}")
    
    return functions


def get_skill_usage_example(skill_name: str, function_name: Optional[str] = None) -> str:
    """
    获取 skill 使用示例

    Args:
        skill_name: skill 名称
        function_name: 特定函数名（可选）

    Returns:
        使用示例字符串
    """
    examples = {
        "read_doc": """
# 读取 world_config.md 文件
from skills.read_doc import read_doc
result = read_doc("world_config.md")
if result["success"]:
    print(result["content"])

# 列出所有可用文档
from skills.read_doc import list_available_docs
docs = list_available_docs()
for filename, title in docs.items():
    print(f"{filename}: {title}")

# 搜索文档内容
from skills.read_doc import search_doc_content
results = search_doc_content("修仙")
for result in results["results"]:
    print(f"在 {result['filename']} 中找到 {len(result['matches'])} 处匹配")
""",
        "find_skill": """
# 列出所有 skills
from skills.find_skill import list_all_skills
skills = list_all_skills()
for skill in skills["skills"]:
    print(f"- {skill['name']}: {skill['description']}")

# 搜索 skill
from skills.find_skill import search_skill
results = search_skill("文档")
for match in results["matches"]:
    print(f"找到: {match['name']}")

# 获取 skill 详细信息
from skills.find_skill import get_skill_info
info = get_skill_info("read_doc")
print(info["skill"])
""",
        "search_episode": """
# 查询相似剧情
from skills.search_episode import search_similar_episodes, format_episodes_as_context

result = search_similar_episodes(
    query="我想修炼炼丹术",
    conversation_history=messages,
    top_k=3,
)

if result["success"]:
    for ep in result["episodes"]:
        print(f"[score={ep['score']:.4f}] {ep['content'][:100]}...")

    # 格式化为上下文
    context = format_episodes_as_context(result)
    print(context)
""",
    }
    
    return examples.get(skill_name, f"# 暂无 {skill_name} 的使用示例")


if __name__ == "__main__":
    # 测试代码
    info_log("测试 find_skill skill...")
    
    # 测试列出所有 skills
    info_log("\n所有可用 skills:")
    all_skills = list_all_skills()
    for skill in all_skills["skills"]:
        print(f"  - {skill['name']}: {skill['description']}")
    
    # 测试搜索
    info_log("\n搜索 '文档':")
    search_results = search_skill("文档")
    for match in search_results["matches"]:
        print(f"  找到: {match['name']}")
    
    # 测试获取详细信息
    info_log("\n获取 read_doc 详细信息:")
    skill_info = get_skill_info("read_doc")
    if skill_info["success"]:
        skill = skill_info["skill"]
        print(f"  名称: {skill['name']}")
        print(f"  描述: {skill['description']}")
        print(f"  函数:")
        for func_name, func_info in skill.get("functions", {}).items():
            print(f"    - {func_name}: {func_info['description']}")
    
    # 显示使用示例
    info_log("\nread_doc 使用示例:")
    print(get_skill_usage_example("read_doc"))
