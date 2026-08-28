# 智能校园 Agent 平台

> 面向校园场景的「**AI Agent 驱动** + **全品类交易** + **AI 简历诊断** + **AI 模拟面试** + **校园跑腿** + **站内私信**」一体化全栈项目。

## 项目亮点

- **行动型 AI 客服 Agent**：从问答型升级为**状态机驱动的行动型 Agent**，用户上传商品图片 → 多模态视觉模型自动识别 → 一键确认 → **自动写库入库**（真实入库，非模拟）。LLM 仅负责意图识别，状态流转由确定性代码控制，杜绝幻觉导致业务异常。
- **ReAct Agent 模拟面试**：LLM 面试官基于 ReAct 循环自适应追问，调用工具按需读取简历特定章节，生成五维量规教练式评估报告。
- **全链路 SSE 流式输出**：前后端统一事件契约（`delta`/`state`/`done`/`error`），前端打字机效果逐字渲染，支持任务状态实时推送。
- **多模态视觉识别**：智谱 `glm-4v-flash` 视觉模型解析商品图片，base64 data URL 嵌入（解决云端无法访问 localhost URL 的问题）。
- **Ponytail 工程审计**：主动清理全仓冗余，删除死代码、过度抽象、未使用依赖，提取公共工具函数消除 4 处重复定义，全后端 AST 语法校验通过。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python · FastAPI · SQLAlchemy 2.0 (Async) · Alembic · Pydantic V2 · PyJWT |
| AI & Agent | LangChain · ReAct Agent · 确定性状态机 · OpenAI 兼容 API（智谱 GLM-4 / GLM-4V，可切换 Ollama） · SSE 流式输出 |
| 前端 | Vue 3 · Vite · Pinia · Vue Router · Element Plus · Axios · 原生 fetch 流式读取 · WebSocket |
| 数据库 | MySQL 8.0 |
| 测试 | pytest · pytest-asyncio · aiosqlite（sqlite 内存库集成测试） |

## 功能一览

### 用户系统
- 注册 / 登录（支持**用户名或邮箱** + 密码）
- JWT 令牌认证
- 账号设置：修改个人资料（昵称、手机号）、修改密码、退出登录

### 全品类商品交易
- 商品发布 / 编辑 / 删除（多图上传，本地 `uploads/` 存储）
- 商品集市：关键词搜索、分类筛选、价格区间、排序（最新/价格升序/降序）
- 商品收藏与取消收藏
- **订单**：下单购买 → 买家付款 → 卖家发货 → 买家确认收货 → 完成；取消订单

### 行动型 AI 客服 Agent
- **确定性状态机驱动**：`collecting_images → analyzing → awaiting_confirm → awaiting_publish → published/cancelled`，含防非法跳转校验与可逆取消
- **多模态商品自动发布**：上传图片 → `glm-4v` 视觉识别商品信息 → 生成结构化发布数据 → 一键确认 → **自动写库入库**（真实入库，非模拟）
- **全链路 SSE 流式**：`delta` 文本增量 / `state` 状态变化 / `done` 完成 / `error` 错误，前端打字机效果 + 阶段提示条 + 确认/取消行动按钮
- 普通对话降级：非发布任务时自动降级为问答型客服

### AI 简历诊断（只诊断，不改写）
- 上传 PDF 简历（`pdfplumber` 提取文本），后台异步 LLM 结构化提取（姓名、求职意向、教育/技能/经历/项目等动态模块）
- 解析状态可视化：解析中自动轮询、失败一键重试
- **AI 优化建议**：
  - 基于专业简历审计方法论：ATS 兼容、招聘者 7 秒扫描、XYZ 公式、So What 三连问、动词等级资历信号、AI 生成味检测、应届生校准
  - 输出总评分 + 一句话总评 + **五项维度评级**（强/中/弱 + 证据）+ 4-8 条结构化建议（模块 / 优先级 / 引用原文的问题 / 可直接照抄的修改示例）
  - 可附带目标岗位要求做定向诊断（关键词覆盖优先）
  - 建议持久化存储（每份简历保留最新一轮），刷新不丢失
- 支持多份简历管理、原 PDF 新窗口查看、删除

### AI 模拟面试（ReAct Agent + 教练式 Debrief）
- 选择简历（可选）与目标岗位，创建面试会话
- **ReAct Agent 循环**：观察简历 → LLM 思考 → 调用工具按需读取简历特定章节 → 生成自适应追问
- **SSE 流式打字机输出**，提问策略模拟真实面试：难度递进（自我介绍 → 项目深挖 → 技术基础 → 场景/压力题）+ 自适应追问（回答含糊追问个人贡献、「我们」式表述要求拆分、矛盾之处当场抓住）；题目之间不给反馈
- 结束面试生成**教练式评估报告**：
  - **Hire Signal** 定级（强推荐 / 推荐 / 存疑 / 不推荐）+ 综合得分 + 一句话总评
  - **五维量规评分**（实质证据 / 叙事结构 / 切题聚焦 / 可信度 / 差异化，1-5 分，按应届生标准校准，评价必须引用候选人原话）
  - **逐题复盘**：每题五维分 + 最强时刻 + 错失机会
  - **整体模式**：口头禅套路、回避话题、全场最佳/最弱时刻（只有看完整场才能发现的问题）
  - **下一场最该改的 3 件事**（按影响力排序，可执行）
- 会话与报告保存，可随时回看历史面试；支持删除会话（级联删除消息）

### 校园跑腿（快递代拿）
- 发布代拿需求：取件点、快递信息、送达地址、报酬、期望时限、备注
- 跑腿大厅浏览待接单需求；**接单采用单语句原子条件更新**（`UPDATE ... WHERE status=pending`），并发抢单只有一个成功，防重复接单
- 状态流转：待接单 → 已接单 → 已送达 → 已结算；待接单时发布者可取消
- 角色视图：大厅 / 我发布的 / 我接的单；取件码仅发布者与接单者可见

### 站内私信
- 用户间一对一实时聊天（**原生 WebSocket**，连接管理器支持同一账号多设备在线）
- 消息落库优先，推送失败不影响持久化；接收方离线后上线可拉历史补齐
- 会话列表：最近联系人 + 最后一条消息 + 未读数（SQL 聚合一次查询）
- 历史消息游标分页（`before_id` 翻页）、进入会话自动标记已读
- 顶栏消息图标 + 未读总数徽标；商品详情页「聊一聊」直达卖家
- 心跳保活（30s ping/pong）+ 断线指数退避重连；无效 token 连接以 4401 关闭码拒绝

## 目录结构

```
.
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── agents/             # Agent 层：support_agent（行动型客服）、interview_agent（ReAct 面试）、goods_agent（视觉识别）
│   │   ├── api/                # 路由：auth / users / goods / favorites / resumes / orders / interviews / errands / messages / support / ws
│   │   ├── core/               # 安全（JWT/密码哈希）、通用工具
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── schemas/            # Pydantic V2 请求/响应契约
│   │   ├── services/           # llm.py（LLM 客户端复用 + _bind_tools 工具注册表 + _msg_text 公共工具） / interview.py（面试官+评估报告）
│   │   ├── config.py           # 应用配置（pydantic-settings）
│   │   └── main.py
│   ├── alembic/versions/       # 数据库迁移
│   ├── scripts/                # 数据导入等一次性脚本
│   ├── tests/                  # pytest 集成测试（sqlite 内存库）
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   # Vue 3 前端
│   └── src/
│       ├── api/                # Axios 接口封装 + SSE 流式工具
│       ├── stores/             # Pinia（用户状态）
│       ├── router/             # Vue Router
│       ├── views/              # 页面（goods / resume / interview / errand / chat / 登录注册 / 设置）
│       ├── components/         # 组件：SmartSupport.vue（智能客服浮窗 + 流式渲染 + 阶段提示条）
│       ├── layout/             # 主布局 + 侧边栏 + 顶部消息入口
│       └── styles/             # 全局样式
└── README.md / .env
```

## 本地开发

### 前置条件
- Python 3.10+
- Node.js 18+
- MySQL 8.0（本地实例）

### 1. 启动后端

```bash
cd backend

# 创建并激活虚拟环境
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

> ⚠️ 注意：`requirements.txt` 固定了 `bcrypt==4.0.1`（2026-08 排查到 `bcrypt>=5.0` 与 `passlib 1.7.4` 不兼容，会导致登录接口 500 报错）。请勿在环境中手动升级 bcrypt；若已升级可执行 `pip install "bcrypt==4.0.1"` 降级。

# 配置环境变量
cp .env.example .env       # 然后编辑 .env 填入 DB 账号密码与 LLM API Key

# 建表（迁移）
alembic upgrade head

# 启动开发服务器（自动重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端地址：`http://localhost:8000`，交互式 API 文档：`http://localhost:8000/docs`

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:5173`，已将 `/api`、`/static` 与 `/ws`（WebSocket）代理到 `:8000`。

### 3. 运行测试

```bash
cd backend
python -m pytest -v
```

测试使用 sqlite 内存库，不依赖 MySQL 与 LLM（AI 服务在测试中被 mock）。

### 4. 准备数据库

默认库名 `campus_platform`，连接信息由 `.env` 控制：

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的密码
DB_NAME=campus_platform
```

## 环境变量配置（backend/.env）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL 连接 | localhost / 3306 / root / / campus_platform |
| `SECRET_KEY` | JWT 签名密钥，**请务必修改为随机长字符串** | CHANGE_ME... |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token 有效期（分钟） | 10080（7 天） |
| `LLM_BASE_URL` | LLM 的 OpenAI 兼容端点 | `https://open.bigmodel.cn/api/paas/v4`（智谱） |
| `LLM_API_KEY` | LLM 平台 API Key | 空 |
| `LLM_MODEL` | 使用的模型名 | `glm-4-flash` |
| `OLLAMA_HOST` | 指向本地 Ollama 时的地址 | `http://localhost:11434` |
| `UPLOAD_DIR` | 上传文件存储目录 | `uploads` |
| `STATIC_URL` | 静态资源访问前缀 | `/static` |
| `CORS_ORIGINS` | 允许跨域的来源，`*` 表全部 | `*` |

> **AI 能力**：LLM 走 OpenAI 兼容协议。默认指向智谱 BigModel（需填 `LLM_API_KEY`）；如果你使用本地 Ollama，将 `LLM_BASE_URL` 改为 `http://localhost:11434/v1` 并填 `LLM_API_KEY=ollama` 即可，无需其他配置。

## API 一览

所有接口以 `/api/v1` 为前缀，需登录的接口在请求头携带 `Authorization: Bearer <token>`。

| 模块 | 接口 |
| --- | --- |
| 认证 | `POST /auth/register` · `POST /auth/login` · `GET /auth/me` |
| 用户 | `PUT /users/me` · `POST /users/me/change-password` · `GET /users/{id}`（私聊对象信息） |
| 商品 | `GET/POST /goods` · `GET/PUT/DELETE /goods/{id}` · `GET /goods/categories` · `GET /goods/mine` · `POST /goods/upload` |
| 收藏 | `GET /favorites` · `POST/DELETE /favorites/{goods_id}` |
| 简历 | `POST /resumes/upload` · `GET /resumes/mine` · `DELETE /resumes/{id}` · `POST /resumes/{id}/reparse` · `POST /resumes/{id}/advice` |
| 订单 | `POST /orders` · `GET /orders` · `GET /orders/{id}` · `PUT /orders/{id}/status` |
| 模拟面试 | `POST /interviews`（SSE） · `GET /interviews` · `GET /interviews/{id}` · `POST /interviews/{id}/chat`（SSE） · `POST /interviews/{id}/finish` · `DELETE /interviews/{id}` |
| 智能客服 | `POST /support/chat`（SSE，支持 `stream=true/false` 与 `image_urls` 多图上传） |
| 校园跑腿 | `POST /errands` · `GET /errands?role=all\|published\|accepted` · `GET /errands/{id}` · `PUT /errands/{id}/accept` · `PUT /errands/{id}/status` |
| 私信 | `GET /messages/conversations` · `GET /messages/{user_id}?before_id=&limit=` · `PUT /messages/{user_id}/read` |
| 私信(WS) | `WS /ws?token=<JWT>`：收发 `{"type":"chat"}` / 心跳 `ping`，服务端回 `chat_ack` / `new_message` / `pong` / `error` |
| 系统 | `GET /health` |

## 架构要点

### Agent 设计原则
- **确定性状态机**：LLM 只负责意图识别，状态跳转由代码控制（`SupportSessionState`），避免 LLM 幻觉导致业务异常
- **工具注册表**：`_bind_tools(state)` 返回工具注册表，支持 ReAct Agent 工具绑定与降级（不支持时自动回退纯文本模式）
- **SSE 事件契约**：`delta`（文本增量）/`state`（状态变化）/`done`（完成）/`error`（错误），前后端统一消费

### 多模态处理
- 视觉模型（`glm-4v-flash`）识别商品图片，输出结构化 JSON
- 图片通过 `_image_url_to_base64_dataurl()` 转为 base64 data URL 嵌入消息，解决云端无法访问 localhost URL 的问题

## 安全说明

- 密码使用 **bcrypt** 单向哈希存储，数据库不保存明文密码
- JWT 使用 `SECRET_KEY` 签名，请务必在部署时替换为随机密钥
- 上传图片有格式与体积校验，文件名经随机化处理，防止路径穿越

## 数据批量导入

项目附带从公开 API 导入商品数据的脚本（`backend/scripts/seed_goods.py`），会在 `goods` / `goods_images` 表写入真实风格的商品数据，并新建一个专属卖家账号。默认连接配置在脚本头部可调整。

```bash
cd backend
.venv\Scripts\python.exe -m scripts.seed_goods --limit 194
```

> 使用前请确认 `.env` 中数据库连接正确，且已执行 `alembic upgrade head`。
