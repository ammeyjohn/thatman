"""
Skills Package - Agents 技能模块

提供常用的技能功能，供 ChatAgent 调用。

Available Skills:
    - read_doc: 读取文档文件内容
    - find_skill: 查找和列出可用的 skills

Usage:
    from skills import read_doc, find_skill
    
    # 读取文档
    result = read_doc.read_doc("world_config.md")
    
    # 查找 skills
    skills = find_skill.list_all_skills()
"""

from . import read_doc
from . import find_skill
from . import search_episode

__all__ = ["read_doc", "find_skill", "search_episode"]
