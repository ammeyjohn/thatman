# ThatMan-文字修仙游戏

本作是一款沉浸式单人文字修仙游戏，以真实时辰流逝、自由剧情抉择、慢节奏修仙养成为核心。玩家将从普通修士起步，拜入宗门，经历拜师、修行、实战、突破境界等修仙日常。
本作整体操作简单易上手，依托文字交互与选择驱动剧情，主打自由养成与沉浸式修仙体验。同时具备两大核心特点：
- 高自由养成：无强制绑定玩法，玩家可自由安排修行节奏，自主进行闭关修炼、地图探索、处理宗门事务、搜集稀缺资源，按照自身喜好塑造专属修士成长路线。
- AI动态内容：摒弃固定脚本，由AI全权生成全部游戏内容，包含大世界场景、NPC人设与对话、支线剧情、随机奇遇、突发事件；内容动态适配玩家境界、过往决策与行为习惯，规避流水线剧情，每次游玩都拥有独一无二的修仙历程。

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Conda（Miniconda 或 Anaconda）
- Docker & Docker Compose
- llama.cpp（需编译 `llama-server`）
- 显存：建议 24GB+（3 个 LLM 模型同时加载约需 20GB 显存）

### 创建 Conda 环境

```bash
conda create -n thatman python=3.10 -y
conda activate thatman
```

> 后续所有 Python 相关命令（pip install、python app.py 等）均需在 `thatman` 环境下执行。

### 端口总览

| 端口 | 服务 |
|------|------|
| 5984 | CouchDB API |
| 6333 | Qdrant gRPC |
| 6334 | Qdrant REST |
| 7777 | Qwen3-Coder-Next（布局生成 LLM） |
| 7778 | Qwen3.6-35B-A3B（聊天主 LLM） |
| 7779 | Qwen3.6-27B-MTP（世界演化 LLM） |
| 8080 | Flask 后端 API |
| 8888 | Hindsight 记忆服务 |
| 9999 | Hindsight 管理端口 |

### 第一步：下载模型

本项目使用 3 个本地 GGUF 量化模型 + 2 个 Embedding/Rerank 模型，均从 ModelScope 下载。

#### 1. 安装 ModelScope 下载工具

```bash
pip install modelscope
```

#### 2. 设置模型缓存目录

```bash
export MODELSCOPE_CACHE=~/.cache/modelscope/hub
```

> LLM 启动脚本通过 `$MODELSCOPE` 环境变量定位模型文件，需保持一致：
```bash
export MODELSCOPE=$MODELSCOPE_CACHE
```

#### 3. 下载 LLM 模型（GGUF 量化）

```bash
# 聊天主模型 Qwen3.6-35B-A3B-MTP（约 18GB）
modelscope download --model unsloth/Qwen3___6-35B-A3B-MTP-GGUF --include "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"

# 世界演化模型 Qwen3.6-27B-MTP（约 16GB）
modelscope download --model unsloth/Qwen3___6-27B-MTP-GGUF --include "Qwen3.6-27B-UD-Q4_K_XL.gguf"

# 布局生成模型 Qwen3-Coder-Next（约 10GB）
modelscope download --model unsloth/Qwen3-Coder-Next-GGUF --include "Qwen3-Coder-Next-UD-Q4_K_XL.gguf"
```

#### 4. 下载 Embedding / Rerank 模型

```bash
# Embedding 模型（后端向量检索使用）
modelscope download --model Qwen/Qwen3-Embedding-0.6B

# Rerank 模型（Hindsight 容器内使用，需挂载到 docker/hindsight/hf_cache）
modelscope download --model Qwen/Qwen3-Rerank-0.6B
```

> Hindsight 容器通过 `HF_ENDPOINT=https://hf-mirror.com` 可自动下载 Embedding/Rerank 模型，也可提前下载到 `docker/hindsight/hf_cache/` 目录避免容器启动时联网下载。

### 第二步：启动 Docker 基础服务

```bash
# 启动 CouchDB（文档数据库）
docker compose -f docker/couchdb/docker-compose.yaml up -d

# 启动 Qdrant（向量数据库）
docker compose -f docker/qdrant/docker-compose.yml up -d

# 启动 Hindsight（长短期记忆服务）
docker compose -f docker/hindsight/docker-compose.yaml up -d
```

验证服务状态：
```bash
curl http://localhost:5984/_up          # CouchDB
curl http://localhost:6333/healthz      # Qdrant
curl http://localhost:8888/health       # Hindsight
```

### 第三步：启动 LLM 模型服务

确保 `llama-server` 已安装（来自 [llama.cpp](https://github.com/ggml-org/llama.cpp)），然后依次启动 3 个模型：

```bash
# 聊天主模型（端口 7778）
bash llm/Qwen3.6-35B-A3B-MTP-Q4.sh &

# 世界演化模型（端口 7779）
bash llm/Qwen3.6-27B-MTP-Q4.sh &

# 布局生成模型（端口 7777）
bash llm/Qwen3-Coder-Next-Q4.sh &
```

验证模型服务：
```bash
curl http://localhost:7777/v1/models    # 布局生成模型
curl http://localhost:7778/v1/models    # 聊天主模型
curl http://localhost:7779/v1/models    # 世界演化模型
```

### 第四步：初始化世界种子数据（首次运行）

将 `docs/` 目录下的世界观设定写入 Hindsight 记忆库：

```bash
cd tools
pip install hindsight-client
python init_world_seed.py
```

可选参数：
- `--clear`：清空已有记忆后重新写入
- `--dry-run`：仅预览解析结果，不实际写入
- `--bank world`：指定记忆库 ID（默认 `world`）

### 第五步：启动后端服务

```bash
cd server
pip install -r requirements.txt
pip install -r agents/requirements.txt
python app.py
```

后端启动在 `http://localhost:8080`，验证：
```bash
curl http://localhost:8080/health
```

### 第六步：启动前端服务

```bash
cd web
npm install
npm run dev
```

前端默认启动在 `http://localhost:5173`，浏览器打开即可开始游戏。

### 环境变量配置

**后端** — 复制并修改配置文件：
```bash
cp server/.env.example server/.env
```
实际运行以 `server/config.yaml` 为准，`.env` 文件为可选覆盖。

**前端** — 复制并修改配置文件：
```bash
cp web/.env.example web/.env
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_API_BASE_URL` | `http://localhost:8080/v1` | 后端 API 地址 |
| `VITE_API_TIMEOUT` | `30000` | 请求超时（ms） |
| `VITE_ENABLE_MOCK` | `false` | 是否启用 Mock |

---

## 功能列表

### 一、底层AI驱动系统 ✅ 已完成
1. ✅ AI GM中枢驱动系统
AI自主判断剧情、查库、生成内容、生成新实体、自主落库。
2. ✅ 完整FunctionCall技能调度系统
模型可自主调用所有数据库、记忆、向量剧情技能。
3. ✅ CouchDB全域数据持久化系统
玩家、NPC、宗门、地点、法宝、关系、世界快照永久存档。
4. ✅ Qdrant剧情向量记忆系统
所有过往剧情语义检索，永久保留故事脉络。
5. ✅ 长短期人物+世界记忆系统
记住玩家一生经历、世界重大事件。
6. ✅ 前端聊天会话上下文系统
本地短时对话连贯，不割裂聊天。
7. ✅ 全自动世界定时演化系统
世界会自己成长、变迁、刷新事件、刷新实体。

### 二、基础自由交互玩法 ✅ 已完成
1. ✅ 自由文字探索交互
玩家随便聊天、探索、发问、互动，AI自由生成剧情。
2. ✅ 动态奇遇随机事件系统
聊天即可触发机缘、秘宝、偶遇高人、秘境开启。
3. ✅ 动态生成全新游戏内容
可动态生成：新NPC、新地点、新法宝、新宗门、新秘境。
4. ✅ 角色状态动态变更系统
修为、位置、背包、状态可实时变化并永久保存。
5. ✅ 大世界真实变迁系统
世界随时间自行演化，玩家离线世界依旧变化。
6. ✅ 人物关系动态生成系统
可拜师、结仇、隶属宗门、产生羁绊关系。

### 三、角色修仙养成体系 ❌ 未完成
1. 境界修炼突破系统
2. 打坐耗时修炼系统
3. 灵力运转、境界压制机制
4. 寿元增减系统
5. 心魔、悟道、感悟机制
6. 功法习得、升级、遗忘系统
7. 武技、秘术修炼系统
8. 法宝获得、佩戴、替换系统
9. 法宝淬炼、炼化、进阶系统
10. 丹药服用、增益、药效消退系统

### 四、地图探索大世界玩法 ❌ 未完成
1. 大地图区域穿梭、赶路系统
2. 秘境刷新、限时秘境系统
3. 禁地、危险区域、特殊地貌机制
4. 野外妖兽刷新、探索遭遇系统
5. 资源采集（灵草、矿石、灵药）

### 五、宗门势力玩法 ❌ 未完成
1. 加入宗门、脱离宗门机制
2. 宗门职位、权限体系
3. 宗门任务、宗门贡献系统
4. 宗门俸禄、宝库、福利系统
5. 宗门大比、宗门考核
6. 宗门兴衰、扩张、覆灭机制
7. 自建宗门、开山立派玩法

### 六、NPC深度AI互动 ❌ 未完成
1. NPC自主生活、作息、走动AI
2. NPC好感度、亲密度系统
3. NPC送礼、交友、结怨系统
4. 完整主线、支线任务链系统
5. NPC传道、授业、指点机缘

### 七、战斗斗法系统 ❌ 未完成
1. 文字即时战斗系统
2. 功法对决、法宝对战机制
3. 闪避、防御、反击、遁逃机制
4. 阵法对战、多人合击系统
5. BOSS秘境讨伐战斗

### 八、经济交易体系 ❌ 未完成
1. 灵石货币体系
2. 坊市商店购买机制
3. 玩家/ NPC摆摊交易
4. 拍卖行竞价系统
5. 材料合成、炼器、炼丹玩法

### 九、宠物坐骑养成 ❌ 未完成
1. 妖兽抓捕、收服系统
2. 灵宠升级、进化、进阶
3. 坐骑飞行、代步功能
4. 灵宠参战、辅助斗法

### 十、高阶修仙特色玩法 ❌ 未完成
1. 渡劫飞升系统
2. 转世重生、保留记忆机制
3. 因果业力、善恶判定
4. 天机推演、命理机缘
5. 禁术、诅咒、特殊体质系统

### 十一、多人社交玩法 ❌ 未完成
1. 多玩家在线共存
2. 玩家组队、结伴修行
3. 玩家切磋、斗法PK
4. 玩家结为道侣、师徒
5. 玩家自建势力、结盟对抗

### 十二、长线沙盒大世界玩法 ❌ 未完成
1. 位面飞升、灵界、仙界解锁
2. 大世界历史迭代、纪元更替
3. 上古秘闻、遗迹复苏玩法
4. 玩家行为影响世界走向
5. 完全自由沙盒创世玩法