"""
Read Document Skill - 读取文档文件技能

根据大模型要求读取 /Users/patrick/Workspaces/ThatMan/docs/ 目录中的文件内容。
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

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


# 文档目录路径
DOCS_DIR = Path("/Users/patrick/Workspaces/ThatMan/docs")

# 支持的文档文件映射
DOC_FILES = {
    # 英文文件名
    "world_config.md": "世界基础设定",
    "game_manual.md": "游戏手册",
    "level_config.md": "境界属性配置",
    "item_config.md": "物品资源配置",
    "skill_config.md": "功法配置",
    "npc_config.md": "NPC角色配置",
    "guild_config.md": "宗门势力配置",
    "task_config.md": "任务等级配置",
    "gm_tools_reference.md": "GM工具函数参考",
    "karma_rules.md": "因果业力规则",
    "scene_consistency_rules.md": "场景一致性约束",
    "output_format_spec.md": "输出格式规范",
    "entity_rules.md": "实体字段规则",
    "layout_hint_rules.md": "布局刷新规则",
    "player_update_rules.md": "玩家更新规则",
    "world_evolution_rules.md": "世界演进规则",
    "tutorial_rules.md": "引导教程规则",
    # 中文文件名
    "世界观.md": "世界观设定",
}


def read_doc(filename: str) -> Dict[str, Any]:
    """
    读取指定文档文件的内容

    Args:
        filename: 文档文件名，如 "world_config.md" 或 "世界观.md"

    Returns:
        包含文档内容的字典，格式如下:
        {
            "success": True/False,
            "filename": "文件名",
            "title": "文档标题",
            "content": "文档内容",
            "error": "错误信息（如果有）"
        }

    Examples:
        >>> result = read_doc("world_config.md")
        >>> print(result["content"])

        >>> result = read_doc("世界观.md")
        >>> print(result["content"])
    """
    # 清理文件名
    filename = filename.strip()
    
    # 如果文件名不包含 .md 后缀，自动添加
    if not filename.endswith(".md"):
        filename += ".md"
    
    # 构建完整路径
    file_path = DOCS_DIR / filename
    
    # 安全检查：确保文件在 docs 目录内
    try:
        file_path.resolve().relative_to(DOCS_DIR.resolve())
    except ValueError:
        error_msg = f"非法文件路径: {filename}"
        error_log(error_msg)
        return {
            "success": False,
            "filename": filename,
            "title": "",
            "content": "",
            "error": error_msg,
        }
    
    # 检查文件是否存在
    if not file_path.exists():
        # 尝试查找相似文件名
        available_files = list_available_docs()
        error_msg = f"文件不存在: {filename}。可用文档: {', '.join(available_files.keys())}"
        warn_log(error_msg)
        return {
            "success": False,
            "filename": filename,
            "title": "",
            "content": "",
            "error": error_msg,
        }
    
    # 读取文件内容
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 获取文档标题
        title = DOC_FILES.get(filename, filename)
        
        info_log(f"成功读取文档: {filename} ({len(content)} 字符)")
        
        return {
            "success": True,
            "filename": filename,
            "title": title,
            "content": content,
            "error": "",
        }
        
    except Exception as e:
        error_msg = f"读取文件失败: {e}"
        error_log(error_msg)
        return {
            "success": False,
            "filename": filename,
            "title": "",
            "content": "",
            "error": error_msg,
        }


def list_available_docs() -> Dict[str, str]:
    """
    列出所有可用的文档文件

    Returns:
        文档文件名到标题的映射字典
    """
    available = {}
    
    for filename, title in DOC_FILES.items():
        file_path = DOCS_DIR / filename
        if file_path.exists():
            available[filename] = title
    
    return available


def search_doc_content(keyword: str) -> Dict[str, Any]:
    """
    在所有文档中搜索包含关键词的内容

    Args:
        keyword: 搜索关键词

    Returns:
        搜索结果字典
    """
    results = []
    available_docs = list_available_docs()
    
    for filename in available_docs.keys():
        result = read_doc(filename)
        if result["success"]:
            content = result["content"]
            # 查找包含关键词的行
            matching_lines = []
            for i, line in enumerate(content.split("\n"), 1):
                if keyword.lower() in line.lower():
                    matching_lines.append({
                        "line": i,
                        "content": line.strip(),
                    })
            
            if matching_lines:
                results.append({
                    "filename": filename,
                    "title": result["title"],
                    "matches": matching_lines,
                })
    
    info_log(f"文档搜索完成: 关键词 '{keyword}' 在 {len(results)} 个文件中找到匹配")
    
    return {
        "success": True,
        "keyword": keyword,
        "results": results,
        "total_files": len(results),
    }


if __name__ == "__main__":
    # 测试代码
    info_log("测试 read_doc skill...")
    
    # 测试列出可用文档
    info_log("可用文档列表:")
    docs = list_available_docs()
    for filename, title in docs.items():
        print(f"  - {filename}: {title}")
    
    # 测试读取文档
    test_files = ["world_config.md", "世界观.md", "game_manual.md"]
    for filename in test_files:
        result = read_doc(filename)
        if result["success"]:
            info_log(f"成功读取 {filename}: {len(result['content'])} 字符")
        else:
            warn_log(f"读取失败: {result['error']}")
    
    # 测试搜索
    info_log("\n测试搜索功能:")
    search_result = search_doc_content("修仙")
    print(f"搜索结果: {search_result}")
