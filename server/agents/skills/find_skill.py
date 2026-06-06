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
