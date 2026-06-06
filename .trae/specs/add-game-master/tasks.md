# Tasks

- [ ] Task 1: 创建 `gm_tools.py` - 全量 Tools JSON Schema 定义
  - [ ] SubTask 1.1: 定义 10 个工具函数的 JSON Schema（couch_get_player, couch_save_player, couch_get_entity, couch_save_entity, couch_get_link, couch_save_link, couch_get_last_world_snap, couch_save_world_snap, recall_all_memory, save_memory, search_plot_vector, insert_plot_vector）
  - [ ] SubTask 1.2: 实现 `get_all_tools()` 函数返回全量 tools 数组
  - [ ] SubTask 1.3: 实现 `match_and_execute_tool()` 工具名匹配与参数解析

- [ ] Task 2: 创建 `gm_storage.py` - 存储执行层
  - [ ] SubTask 2.1: 封装 CouchDB 客户端连接与 CRUD 操作（player, entity, link, world_snap 四类文档）
  - [ ] SubTask 2.2: 封装 Qdrant 剧情向量操作（search_plot_vector, insert_plot_vector），复用现有 search_episode 的 EmbeddingClient
  - [ ] SubTask 2.3: 封装长效记忆操作（recall_all_memory, save_memory），复用现有 hindsight_memory 模块
  - [ ] SubTask 2.4: 实现 `save_dispatcher()` - 根据 save_flag 分发存储逻辑（player_update / new_entity / world_change / world_snap 四个分支）

- [ ] Task 3: 创建 `prompts/gm_system.md` - GM 专用 System 提示词
  - [ ] SubTask 3.1: 基于现有 system.md 重写，增加工具使用指引、标准输出格式规范、save_flag 触发规则

- [ ] Task 4: 创建 `game_master.py` - GM 主控类
  - [ ] SubTask 4.1: 实现 `GameMaster.__init__` - 加载配置、初始化 LLM 连接（双模型）、加载 system prompt、初始化存储层
  - [ ] SubTask 4.2: 实现 `pre_context()` - 预拉记忆 + 向量剧情，拼装上下文字符串
  - [ ] SubTask 4.3: 实现 `build_messages()` - 拼装 LLM messages 数组（system + session_history + 记忆 + 剧情 + user_input）
  - [ ] SubTask 4.4: 实现 `llm_chat_loop()` - 工具调用循环逻辑（解析 tool_calls → 执行 → 回填 → 再调用，直到无 tool_calls）
  - [ ] SubTask 4.5: 实现 `handle_chat()` - 玩家聊天完整串行流程入口（req_type=chat）
  - [ ] SubTask 4.6: 实现 `world_tick_task()` - 定时世界演化流程入口（req_type=world_tick）

- [ ] Task 5: 创建 `routes/gm.py` - GM HTTP 接口
  - [ ] SubTask 5.1: 实现 `POST /v1/gm/chat` 接口，接收前端标准入参，调用 GameMaster 处理，返回标准结构体

- [ ] Task 6: 修改 `config.yaml` 和 `app.py` - 配置与路由注册
  - [ ] SubTask 6.1: 在 config.yaml 增加 gm 配置段（双模型端口、CouchDB/Qdrant 连接参数、world_tick 定时间隔）
  - [ ] SubTask 6.2: 在 app.py 注册 gm_bp 蓝图

# Task Dependencies
- Task 2 依赖 Task 1（save_dispatcher 需要调用工具执行结果）
- Task 4 依赖 Task 1 + Task 2 + Task 3（主控类需要 tools、storage、prompt）
- Task 5 依赖 Task 4（路由需要调用 GameMaster）
- Task 6 依赖 Task 5（注册路由需要路由模块存在）
- Task 1 和 Task 3 可并行
