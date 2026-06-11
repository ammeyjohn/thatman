# 标准输出格式规范

GM 必须返回以下标准 JSON，禁止额外说明、注释、多余文字：

```json
{"dialog":"对外展示对话文本，尽量使用markdown格式提供更丰富的展示效果","npc_name":"当前对话NPC名称，如'李长老'","npc_avatar":"当前对话NPC头像emoji，如'👴'","entities":[{"name":"实体名称","type":"character|place|weapon|technique|item","desc":"实体简要描述，20-50字","detail":{}}],"actions":["生成3-5个建议动作","……"],"player_update":{"current_location":"当前所在地点","current_status":"当前状态描述"},"ui_config":{"left_open":[],"right_open":[],"layout_hint":""},"save_flag":"","time_cost":0,"action_id":"chat"}
```

## 完整输出示例

```json
{
  "dialog": "你沿着小径来到云溪村东头，只见一位白发老者正坐在石凳上品茶。他抬头望来，微微一笑：'小友，老夫李长老，在此等候多时了。'说罢，他从袖中取出一卷泛黄的古卷——正是失传已久的引气诀。",
  "npc_name": "李长老",
  "npc_avatar": "👴",
  "entities": [
    {"name": "云溪村", "type": "place", "desc": "青墟古域东隅小村，灵气稀薄，民风淳朴", "detail": {"region": "青云古域", "spirit_level": "稀薄", "danger_level": "低", "features": "灵泉古井、后山秘境入口"}},
    {"name": "李长老", "type": "character", "desc": "白发老者，云溪村隐居前辈", "detail": {"realm": "金丹期巅峰", "faction": "青云宗", "personality": "温和慈祥，深藏不露", "specialty": "丹道与阵法"}},
    {"name": "引气诀", "type": "technique", "desc": "上古引气入门功法", "detail": {"grade": "凡阶下品", "category": "心法", "effect": "引天地灵气入体，凝聚灵力", "requirement": "引气入体期可修炼"}}
  ],
  "actions": ["向李长老请教修炼之道", "询问引气诀的来历", "婉拒继续赶路"],
  "player_update": {"current_location": "云溪村东头", "current_status": "与李长老交谈中"},
  "ui_config": {"left_open": [], "right_open": [], "layout_hint": ""},
  "save_flag": "new_entity",
  "time_cost": 5,
  "action_id": "chat"
}
```

## 字段说明

| 字段 | 说明 |
|------|------|
| dialog | 对外展示文本，支持 markdown。**禁止**在 dialog 中写状态更新和建议动作列表 |
| npc_name | 当前与玩家对话的NPC名称（如'李长老'），用于前端聊天框展示发送者名称 |
| npc_avatar | 当前对话NPC的头像emoji（如'👴'、'🧙'、'👩‍🦳'），用于前端聊天框展示头像 |
| entities | 本次对话中出现的实体列表，每项含 `name`（名称）、`type`（类型）、`desc`（简要描述，20-50字）、`detail`（类型专属详细信息）。前端会自动在 dialog 中匹配实体名称并生成可点击链接，`detail` 数据会自动持久化到世界实体数据库 |
| actions | 建议动作列表，3-5条，每条为简短中文描述 |
| player_update | 玩家数据变更，仅填需更新的字段（属性、背包、修为、坐标、地点、状态等） |
| ui_config | UI 面板配置，`layout_hint` 嵌入其中 |
| save_flag | 数据落库标识 |
| time_cost | 本次行为消耗的游戏分钟数。即时行为填0，耗时行为必须查询 `action_time_config.md` 后填写 |
| action_id | 本次行为的动作类型标识，如 `chat`, `meditate_depth`, `combat`, `move_region` 等。即时行为也必须填写 |

## save_flag 触发规则

| save_flag | 触发条件 |
|-----------|----------|
| `""` | 无数据变更 |
| `"player_update"` | 玩家属性/背包/修为/坐标变更 |
| `"new_entity"` | 新增NPC/法宝/地点/宗门，需附带 `entity_data` |
| `"world_change"` | 地域变动/宗门变化，触发世界快照更新 |
