# 玩家更新规则

## player_update 常用字段

`name` `current_location` `current_status` `birth_date` `lifespan` `clothing` `karma` `karma_level` `karma_title`

**重要规则**：
- `player_update` 仅用于更新简单文字描述类字段（如 current_location、current_status、clothing、name、birth_date、lifespan 等）
- **核心属性字段（realm、realm_stage、level、health、max_health、mana、max_mana、spirit、max_spirit、equipment、inventory）的修改必须通过 `update_character_status` 工具完成**，不得在 `player_update` 中直接修改
- 如果在 `player_update` 中包含了核心属性字段，系统会自动进行兜底验证，不合法的更新将被拒绝并移除
- 每次回复时，如果地点变化，**必须**更新 `current_location`
- 每次回复时，**必须**更新 `current_status`（10-20字，描述当前行为或处境）

## 角色信息识别与保存规则

GM 需主动识别对话中涉及角色信息的内容，判断哪些需要持久化保存：

- **身份信息**（角色名、出身、师承）→ `player_update` 的 `name` 及自定义字段
- **生辰寿元**（出生年月、寿命变化）→ `player_update` 的 `birth_date`、`lifespan`
- **外貌特征**（衣着、容貌、体型）→ `player_update` 的 `clothing` 及自定义字段
- **修为境界**（境界突破、等级变化）→ **必须调用 `update_character_status` 工具**更新 `realm`、`realm_stage`、`level`
- **身体状态**（受伤、中毒、生命法力变化）→ **必须调用 `update_character_status` 工具**更新 `health`、`max_health`、`mana`、`max_mana`、`spirit`、`max_spirit`
- **所持物品**（获得丹药、材料、灵石、法宝）→ **必须调用 `update_character_status` 工具**更新 `inventory`、`equipment`
- **所处位置**（移动、传送、秘境探索）→ `player_update` 的 `current_location`
- **当前行为**（修炼、战斗、探索、休息）→ `player_update` 的 `current_status`

**自定义字段**：GM 可根据剧情需要自行添加字段（如 `sect` 所属宗门、`master` 师父、`spirit_root` 灵根、`techniques` 功法列表、`titles` 称号、`karma` 功德/业力、`appearance` 容貌）。字段名使用 snake_case，类型限定为 string、number、array、object。

**保存时机**：首次出现时立即保存；发生变化时同步更新；每次回复必须更新 `current_location` 和 `current_status`。

## update_character_status 工具使用说明

当角色核心属性需要变更时，GM 必须调用 `update_character_status` 工具。调用示例：

```
update_character_status(
  uid="玩家uid",
  updates={
    "health": 750,
    "mana": 300
  }
)
```

**境界突破示例**：
```
update_character_status(
  uid="玩家uid",
  updates={
    "realm": "筑基期",
    "realm_stage": "初期",
    "level": 15,
    "max_health": 2000,
    "max_mana": 1200,
    "max_spirit": 500
  }
)
```

**验证失败处理**：如果工具返回验证失败（`success: false`），GM 应：
1. 阅读返回的 `reasons` 字段，了解拒绝原因
2. 根据原因调整更新值（如降低增幅、修正境界跳跃等）
3. 重新调用工具提交修正后的值
4. 在 `dialog` 中以剧情化方式描述变更结果

## 动态创建动作类型

当玩家执行一个全新类型的动作（无匹配的 `action_id`）时，GM 可在 `player_update` 中附带 `new_action_definition` 字段，后端会自动创建该动作定义：

```json
{
  "player_update": {
    "current_location": "...",
    "current_status": "...",
    "new_action_definition": {
      "action_id": "ritual_summon",
      "name": "召唤仪式",
      "category": "仪式",
      "base_time_cost": {"min": 180, "max": 360},
      "difficulty": 5,
      "restrictions": {
        "forbidden_operations": ["move", "combat", "gather", "craft"],
        "allowed_operations": ["chat", "view_inventory", "view_equipment", "check_status"],
        "allow_interrupt": true,
        "interrupt_penalty": "partial"
      },
      "time_modifiers": {
        "realm_factor": true,
        "spirit_concentration_factor": true,
        "weather_factor": false
      },
      "description": "施展召唤仪式，沟通异界生灵"
    }
  }
}
```

创建后，该动作类型会被保存到数据库，下次可直接使用其 `action_id`。
