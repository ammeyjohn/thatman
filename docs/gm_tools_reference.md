# GM 工具函数参考

GM 可调用以下 21 个工具函数完成数据读写，所有世界变更必须通过工具落库，禁止凭空修改数据。

## 玩家数据

- **couch_get_player** — 获取玩家角色完整数据（属性、背包、修为、坐标等）
- **couch_save_player** — 保存玩家角色数据变更（仅用于非核心属性的保存）

## 角色核心属性更新（必须使用）

- **update_character_status** — 更新角色核心属性状态（带验证限制）。**所有核心属性（realm、realm_stage、level、health、max_health、mana、max_mana、spirit、max_spirit、equipment、inventory）的修改必须通过此工具完成**，工具会验证状态变更的合理性，拒绝不合理的更新。验证规则：境界只能升一级、境界阶段只能升一级（突破时重置为初期）、等级单次增幅不超过10、当前属性值不能超过上限、属性上限普通变化不超过50%（突破时不超过200%）、装备增减不超过3件、背包物品种类增减不超过5种

## 全局实体

- **couch_get_entity** — 获取指定实体数据（NPC、法宝、地点、宗门等）
- **couch_save_entity** — 保存/新增实体数据

## 关联关系

- **couch_get_link** — 获取实体间的关联关系（师徒、仇敌、从属、领地等）
- **couch_save_link** — 保存/新增关联关系

## 世界快照

- **couch_get_last_world_snap** — 获取上一轮世界快照
- **couch_save_world_snap** — 保存新一轮世界快照

## 长效记忆

- **recall_all_memory** — 召回全部长效记忆
- **save_memory** — 存入长效记忆

## 剧情向量

- **search_plot_vector** — 向量搜索相关剧情片段
- **insert_plot_vector** — 插入新剧情向量记录

## 动作类型定义

- **create_action_definition** — 创建或更新动作类型定义（当玩家执行全新类型动作时使用）
- **get_action_definition** — 查询指定动作类型定义
- **list_action_definitions** — 列出所有已定义的动作类型

## 因果业力

- **record_karma** — 记录因果事件，更新玩家业力值（当玩家行为涉及善恶因果时必须调用）
- **get_karma_status** — 获取玩家业力总览（业力值、善恶等级、因果记录、因果羁绊）
- **judge_karma** — 善恶判定，根据行为描述返回判定结果和建议业力值（仅作参考）
- **get_karma_bonds** — 获取玩家与NPC/实体的因果羁绊列表
- **resolve_karma** — 了结因果（恩报恩、仇复仇等，了结后业力变化）
