# 实体字段规则

在每次回复中，识别 dialog 中出现的重要实体并列入 `entities` 数组。**每个实体必须包含 `detail` 对象**，根据实体类型填写对应的专属字段，这些信息将自动保存到世界实体数据库。

## 实体类型与 detail 字段

| 类型 | 标识 | 适用对象 | detail 字段 |
|------|------|----------|-------------|
| 人物 | `character` | NPC、角色、师父、对手 | `realm`（修为境界）、`faction`（所属宗门）、`personality`（性格特点）、`specialty`（擅长领域）、`karma_bond`（与玩家的因果类型：grace/enmity/fellowship/friendship/contract/neutral） |
| 地点 | `place` | 地域、秘境、洞府、宗门所在地 | `region`（所属地域）、`spirit_level`（灵气浓度）、`danger_level`（危险等级）、`features`（特色/地标） |
| 武器/法宝 | `weapon` | 法宝、灵器、防具 | `grade`（品级）、`effect`（效果/特性）、`requirement`（使用要求）、`origin`（来历） |
| 功法 | `technique` | 功法、秘术、阵法 | `grade`（品级）、`category`（分类：心法/身法/攻击/防御/辅助）、`effect`（效果描述）、`requirement`（修炼要求） |
| 物品 | `item` | 丹药、材料、灵石、天材地宝 | `grade`（品级）、`effect`（效果/作用）、`rarity`（稀有度）、`usage`（使用方式） |

## 标记原则

- 仅列出本次对话中新出现或重要的实体，不列常见通用词（如"灵气""修为"）
- `name` 须与 dialog 中出现的名称完全一致，以便前端自动匹配
- `desc` 须简洁准确，20-50字
- `detail` 为必填对象，根据实体类型填写对应字段，每个字段值须简明准确（10-30字）。若某字段暂无信息可填空字符串 `""`
- 若本次对话无重要实体，`entities` 为空数组 `[]`

## 新增实体数据规范

当 `save_flag` 为 `"new_entity"` 时，必须附带 `entity_data`：

```json
{
  "entity_type": "npc|faction|equip|treasure|area",
  "name": "名称",
  "base_info": "基础设定",
  "attr": "属性/修为/品级",
  "birth_story": "诞生背景",
  "belong_area": "所属地域",
  "init_link": [{"link_type":"belong/enemy/master","target_id":"关联对象ID"}]
}
```

- `entity_type`：`npc`（NPC）、`faction`（宗门）、`equip`（法宝）、`treasure`（天材地宝）、`area`（地域）
- `attr`：NPC填修为境界，法宝填品级，地域填灵气浓度等
- `init_link`：初始关联关系，`link_type` 取值 `belong`（从属）、`enemy`（敌对）、`master`（师徒）等
