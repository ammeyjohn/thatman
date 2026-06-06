* [x] gm\_tools.py 中定义了 12 个工具函数的 JSON Schema（couch\_get\_player, couch\_save\_player, couch\_get\_entity, couch\_save\_entity, couch\_get\_link, couch\_save\_link, couch\_get\_last\_world\_snap, couch\_save\_world\_snap, recall\_all\_memory, save\_memory, search\_plot\_vector, insert\_plot\_vector）

* [x] gm\_tools.py 中 get\_all\_tools() 返回完整的 tools 数组

* [x] gm\_tools.py 中 match\_and\_execute\_tool() 能正确匹配工具名并解析参数

* [x] gm\_storage.py 封装了 CouchDB CRUD 操作（player, entity, link, world\_snap）

* [x] gm\_storage.py 封装了 Qdrant 剧情向量操作（search/insert），复用 EmbeddingClient

* [x] gm\_storage.py 封装了长效记忆操作（recall/save），复用 hindsight\_memory

* [x] gm\_storage.py 中 save\_dispatcher() 正确处理四种 save\_flag 分支（空/player\_update/new\_entity/world\_change/world\_snap）

* [x] prompts/gm\_system.md 包含工具使用指引、标准输出格式规范、save\_flag 触发规则

* [x] GameMaster.__init__ 正确初始化双模型连接（35B-A3B 常驻 + 27B-MTP 按需）

* [x] GameMaster.pre\_context() 预拉记忆和向量剧情并拼装上下文

* [x] GameMaster.build\_messages() 按规范拼装 messages 数组（system + session\_history + 记忆 + 剧情 + user\_input）

* [x] GameMaster.llm\_chat\_loop() 正确处理工具调用循环（解析→执行→回填→再调用，直到无 tool\_calls）

* [x] GameMaster.handle\_chat() 实现玩家聊天完整串行流程（req\_type=chat）

* [x] GameMaster.world\_tick\_task() 实现定时世界演化流程（req\_type=world\_tick）

* [x] routes/gm.py 提供 POST /v1/gm/chat 接口，接收标准入参返回标准结构体

* [x] config.yaml 包含 gm 配置段（双模型端口、CouchDB/Qdrant 连接、world\_tick 间隔）

* [x] app.py 注册了 gm\_bp 蓝图

