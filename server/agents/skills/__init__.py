"""
Skills Package - Agents 技能模块

提供常用的技能功能，供 ChatAgent 调用。

Available Skills:
    - read_doc: 读取文档文件内容
    - find_skill: 查找和列出可用的 skills
    - search_episode: 查询相似剧情片段
    - couchdb_skill: CouchDB 读写技能（玩家/实体/关系/世界快照）
    - memory_skill: 长效记忆技能（召回/保存记忆）
    - vector_skill: Qdrant 剧情向量技能（检索/入库剧情）
    - character_status_skill: 角色状态更新技能（带验证限制）

Usage:
    from skills import read_doc, find_skill

    # 读取文档
    result = read_doc.read_doc("world_config.md")

    # 查找 skills
    skills = find_skill.list_all_skills()
"""

from . import read_doc
from . import find_skill
from . import couchdb_skill
from . import memory_skill
from . import character_status_skill
from . import action_definition
from . import karma_skill

# search_episode 和 vector_skill 依赖 torch/qdrant，懒加载避免缺依赖时崩溃
try:
    from . import search_episode
    from . import vector_skill
    _HAS_VECTOR_DEPS = True
except (ImportError, NameError):
    _HAS_VECTOR_DEPS = False

__all__ = [
    "read_doc",
    "find_skill",
    "search_episode",
    "couchdb_skill",
    "memory_skill",
    "vector_skill",
    "character_status_skill",
    "action_definition",
    "karma_skill",
]
