# 校园综合服务平台

一个面向校园场景的「**二手交易** + **AI 简历**」一体化全栈项目。

- **二手交易**：发布/浏览二手商品、图片上传、关键词与分类筛选、收藏、下单购买、订单状态流转（仿闲鱼 UI 风格）
- **AI 简历**：上传 PDF 简历 → 自动结构化提取 → 在线所见即所得编辑 → AI 智能优化改良

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python · FastAPI · SQLAlchemy 2.0 (Async) · Alembic · Pydantic V2 · PyJWT |
| AI | LangChain · OpenAI 兼容 API（默认智谱 BigModel，可切换 Ollama） |
| 前端 | Vue 3 · Vite · Pinia · Vue Router · Element Plus · Axios |
| 数据库 | MySQL 8.0 |

## 功能一览

### 用户系统
- 注册 / 登录（支持**用户名或邮箱** + 密码）
- JWT 令牌认证
- 账号设置：修改个人资料（昵称、手机号）、修改密码、退出登录

### 二手交易
- 商品发布 / 编辑 / 删除（多图上传，本地 `uploads/` 存储）
- 商品集市：关键词搜索、分类筛选、价格区间、排序（最新/价格升序/降序）
- 商品收藏与取消收藏
- **订单**：下单购买 → 买家付款 → 卖家发货 → 买家确认收货 → 完成；取消订单

### AI 简历
- 上传 PDF 简历（`pdfplumber` 提取文本）
- 上传时自动提取简历头像照片，并展示在简历中
- LLM 结构化提取（姓名、联系方式、求职意向、教育/技能/经历/项目等动态模块）
- 在线可视化编辑，支持保存多份简历
- **AI 改良**：可附带岗位要求定向优化，输出与原文同风格的预览
- 备份不同版本，随时应用回编辑器

## 目录结构

```
.
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/                # 路由：auth / users / goods / favorites / resumes / orders
│   │   ├── core/               # 安全（JWT/密码哈希）、通用工具
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── schemas/            # Pydantic V2 请求/响应契约
│   │   ├── services/           # llm.py（LLM 客户端复用 + 提取/改良）
│   │   ├── config.py           # 应用配置（pydantic-settings）
│   │   └── main.py
│   ├── alembic/versions/       # 数据库迁移
│   ├── scripts/                # 数据导入等一次性脚本
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   # Vue 3 前端
│   └── src/
│       ├── api/                # Axios 接口封装
│       ├── stores/             # Pinia（用户状态）
│       ├── router/             # Vue Router
│       ├── views/              # 页面（goods / resume / 登录注册 / 设置）
│       ├── layout/             # 主布局 + 侧边栏
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

前端地址：`http://localhost:5173`，已将 `/api` 与 `/static` 代理到 `:8000`。

### 3. 准备数据库

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
| 用户 | `PUT /users/me` · `POST /users/me/change-password` |
| 商品 | `GET/POST /goods` · `GET/PUT/DELETE /goods/{id}` · `GET /goods/categories` · `GET /goods/mine` · `POST /goods/upload` |
| 收藏 | `GET /favorites` · `POST/DELETE /favorites/{goods_id}` |
| 简历 | `POST /resumes/upload` · `GET /resumes/mine` · `GET/PUT/DELETE /resumes/{id}` · `POST /resumes/{id}/improve` |
| 订单 | `POST /orders` · `GET /orders` · `GET /orders/{id}` · `PUT /orders/{id}/status` |
| 系统 | `GET /health` |

## 安全说明

- 密码使用 **bcrypt** 单向哈希存储，数据库不保存明文密码
- JWT 使用 `SECRET_KEY` 签名，请务必在部署时替换为随机密钥
- 上传图片有格式与体积校验，文件名经随机化处理，防止路径穿越

## 数据批量导入

项目附带从公开 API 导入二手商品数据的脚本（`backend/scripts/seed_goods.py`），会在 `goods` / `goods_images` 表写入真实风格的商品数据，并新建一个专属卖家账号。默认连接配置在脚本头部可调整。

```bash
cd backend
.venv\Scripts\python.exe -m scripts.seed_goods --limit 194
```

> 使用前请确认 `.env` 中数据库连接正确，且已执行 `alembic upgrade head`。