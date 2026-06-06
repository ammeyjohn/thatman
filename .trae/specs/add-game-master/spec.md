# Game Master 游戏流程主控 Spec

## Why

当前 `chat_agent.py` 仅做简单的 LLM 转发 + 记忆检索，缺少游戏流程编排能力：无工具调用循环、无结构化存储分发、无世界演化机制。需要新建 `game_master` 模块，实现完整的 GM 全链路标准化流程，覆盖玩家交互（chat）和定时世界演化（world\_tick）两条核心链路。

## What Changes

* 新建 `game_master.py`：GM 主控类，负责消息拼装、LLM 调用循环、save\_flag 分发

* 新建 `gm_tools.py`：全量 Tools 定义（10 个函数的 JSON Schema），供 LLM function calling 使用

* 新建 `gm_storage.py`：存储执行层，封装 CouchDB / Qdrant / Hindsight 记忆的读写操作

* 新建 `prompts/gm_system.md`：GM 专用 System 提示词

* 修改 `config.yaml`：增加 GM 模型调度配置（35B-A3B 常驻 / 27B-MTP 按需）

* 修改 `app.py`：注册 GM 路由蓝图

* 新建 `routes/gm.py`：GM 专用 HTTP 接口（接收前端标准入参）

## Impact

* Affected specs: 玩家交互流程、世界演化流程、数据持久化策略

* Affected code:

  * `server/agents/game_master.py`（新建）

  * `server/agents/gm_tools.py`（新建）

  * `server/agents/gm_storage.py`（新建）

  * `server/agents/prompts/gm_system.md`（新建）

  * `server/routes/gm.py`（新建）

  * `server/config.yaml`（修改）

  * `server/app.py`（修改）

## ADDED Requirements

### Requirement: GM 主控流程编排

系统 SHALL 提供 `GameMaster` 类，实现完整的玩家聊天串行流程：

1. 接收前端标准入参（uid, user\_input, current\_area, session\_history, req\_type）
2. 预拉外围数据（记忆 + 向量剧情）
3. 拼装 LLM messages 数组（system + session\_history + 记忆上下文 + 剧情上下文 + user\_input）
4. 调用 LLM 并处理工具调用循环，直到 LLM 输出标准 JSON 结果
5. 根据 save\_flag 执行落地存储逻辑

#### Scenario: 玩家聊天请求（req\_type=chat）

* **WHEN** 前端发送 `{uid, user_input, current_area, session_history, req_type:"chat"}` 请求

* **THEN** 系统预拉记忆和剧情向量，拼装上下文，调用 LLM，处理工具调用循环，返回 `{dialog, player_update, ui_config}` 并按 save\_flag 落库

#### Scenario: LLM 返回 FunctionCall

* **WHEN** LLM 返回 tool\_calls

* **THEN** 后端解析函数名和入参，执行对应查询，将结果回填 messages，再次调用 LLM，循环直到 LLM 不再返回 tool\_calls

#### Scenario: LLM 输出标准 JSON 结果

* **WHEN** LLM 输出包含 dialog, player\_update, ui\_config, save\_flag 的 JSON

* **THEN** 系统返回前端报文 `{dialog, player_update, ui_config}`，并根据 save\_flag 值执行对应存储逻辑

### Requirement: save\_flag 分发存储

系统 SHALL 根据 LLM 返回的 save\_flag 值执行不同的存储逻辑：

#### Scenario: save\_flag 为空

* **WHEN** save\_flag == ""

* **THEN** 无任何落库，流程结束

#### Scenario: save\_flag == "player\_update"

* **WHEN** save\_flag == "player\_update"

* **THEN** 执行 couch\_save\_player、解析关系数据 couch\_save\_link、save\_memory(user\_{uid})、insert\_plot\_vector

#### Scenario: save\_flag == "new\_entity"

* **WHEN** save\_flag == "new\_entity"

* **THEN** 自动生成唯一 entity\_id，执行 couch\_save\_entity、couch\_save\_link、save\_memory(world\_global\_history)、insert\_plot\_vector

#### Scenario: save\_flag == "world\_change"

* **WHEN** save\_flag == "world\_change"

* **THEN** 执行 couch\_save\_entity、couch\_save\_link、save\_memory(world\_global\_history)、insert\_plot\_vector

### Requirement: 定时世界演化（req\_type=world\_tick）

系统 SHALL 提供 `world_tick_task()` 函数，实现定时世界演化流程：

1. 初始化 GM 系统提示词 + 世界演化固定 Prompt
2. LLM 主动调用工具拉取全服数据（world\_snap、entity、link、memory）
3. LLM 推演全地图变化
4. 落地保存：world\_snap、新增 entity、新增 link、世界记忆、剧情向量

#### Scenario: 定时世界演化触发

* **WHEN** 定时器触发 world\_tick

* **THEN** 系统使用可选的 27B-MTP 模型，拉取全服数据，LLM 推演世界变化，落地保存所有变更

### Requirement: 全量 Tools 定义

系统 SHALL 定义 10 个工具函数的 JSON Schema，挂载在每次 LLM 请求的 tools 参数中：

* 玩家数据（CouchDB）：couch\_get\_player, couch\_save\_player

* 全局实体（CouchDB）：couch\_get\_entity, couch\_save\_entity

* 关联关系（CouchDB）：couch\_get\_link, couch\_save\_link

* 世界快照（CouchDB）：couch\_get\_last\_world\_snap, couch\_save\_world\_snap

* 长效记忆：recall\_all\_memory, save\_memory

* Qdrant 剧情向量：search\_plot\_vector, insert\_plot\_vector

#### Scenario: LLM 发起工具调用

* **WHEN** LLM 返回 tool\_calls 中的函数名匹配已注册工具

* **THEN** 后端执行对应存储/查询操作，返回结果给 LLM

### Requirement: GM HTTP 接口

系统 SHALL 提供 `/v1/gm/chat` POST 接口，接收前端标准入参并返回标准结构体。

#### Scenario: 前端调用 GM 接口

* **WHEN** 前端 POST `/v1/gm/chat` 发送标准入参

* **THEN** 系统返回 `{dialog, player_update, ui_config}` JSON 响应

### Requirement: 模型调度

系统 SHALL 支持双模型调度：

* 玩家日常聊天使用 Qwen3.6-35B-A3B（常驻 8080 端口）

* 定时大规模世界生成使用 Qwen3.6-27B-MTP（按需 8081 端口）

#### Scenario: 玩家聊天使用常驻模型

* **WHEN** req\_type == "chat"

* **THEN** 使用 35B-A3B 模型（8080 端口）

#### Scenario: 世界演化使用按需模型

* **WHEN** req\_type == "world\_tick"

* **THEN** 使用 27B-MTP 模型（8081 端口，可选回退到 35B-A3B）

### Requirement: 新增实体数据规范

系统 SHALL 遵循统一的 entity\_data 结构规范，包含 entity\_type、name、base\_info、attr、birth\_story、belong\_area、init\_link 字段。

#### Scenario: LLM 生成新实体

* **WHEN** save\_flag == "new\_entity" 且 LLM 返回 entity\_data

* **THEN** 系统验证 entity\_data 包含必要字段，自动生成唯一 entity\_id，存入 CouchDB

