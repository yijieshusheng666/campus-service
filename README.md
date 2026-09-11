# 智能校园 Agent 平台

校园场景一站式平台：二手交易 + AI 简历诊断 + AI 模拟面试 + 校园跑腿 + 站内私信。

技术栈：FastAPI · SQLAlchemy 2.0 · MySQL 8.0 · Vue 3 + Vite · LangChain（OpenAI 兼容协议，默认智谱 GLM）

---

## 一、启动前修改（只改 2 处）

```bash
copy backend\.env.example backend\.env          # Windows，只在第一次执行
cp backend/.env.example backend/.env            # macOS / Linux
```

打开 `backend\.env`，改这两行：

```ini
DB_PASSWORD=你本机MySQL的密码      # 只能 ASCII，不能含中文
LLM_API_KEY=你的大模型APIKey       # 留空则 AI 功能不可用，但后端能正常启动
```

---

## 二、启动命令

```bash
# 建库（只做一次；已存在会跳过。若报 "mysql 不是内部或外部命令"，
# 说明 MySQL 的 bin 目录没加进 PATH，把 mysql 换成完整路径即可，
# 例如 "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS campus_platform DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 后端
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# 前端（另开一个终端）
cd frontend
npm install
npm run dev
```

访问：前端 http://localhost:5173 ｜ 接口文档 http://localhost:8001/docs

> macOS / Linux：`.venv\Scripts\python.exe` 换成 `.venv/bin/python`，`.venv\Scripts\alembic.exe` 换成 `.venv/bin/alembic`。

---

## 三、换大模型（可选）

改 `backend\.env` 三行即可，**不需要改代码**：

```ini
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=你的Key
LLM_MODEL=qwen-plus
```

> 文本模型与视觉模型（`LLM_VISION_MODEL`）共用同一个 `LLM_BASE_URL`，
> 所以要选**同一家同时提供文本和视觉模型**的服务商（如智谱、通义千问）。

---

部署到公网（阿里云）：见 [`docs/部署手册.md`](docs/部署手册.md)。
