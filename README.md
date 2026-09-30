# 智能校园 Agent 平台

校园场景一站式平台：二手交易 + AI 简历诊断 + AI 模拟面试 + 校园跑腿 + 站内私信 + 平台公告。

技术栈：FastAPI · SQLAlchemy 2.0 · MySQL 8.0 · Redis · Celery · Vue 3 + Vite · LangChain（OpenAI 兼容协议，默认智谱 GLM）

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

## 四、部署模式：单机 / 分布式

平台支持两种模式，**由 `backend/.env` 里的 `REDIS_URL` 决定**，代码零改动：

| | 单机模式（默认） | 分布式模式 |
|---|---|---|
| `REDIS_URL` | 留空 | `redis://127.0.0.1:6379/0` |
| 简历 AI 解析 | asyncio 后台任务（进程内，重启即丢） | Celery 队列（独立 worker 消费，崩溃重投） |
| WebSocket 推送 | 进程内存连接表 | Redis pub/sub 跨进程桥 |
| uvicorn workers | 必须 1 | 可调大※ |
| 额外服务 | 无 | redis-server + campus-worker.service |

※ 分布式模式下「WS 连接表」与「解析任务」已迁出进程内存，但**智能客服的多轮任务状态
（`app/agents/support_agent.py` 的三个内存 dict）仍在进程内**，多 worker 时可能丢状态；
把它也换成 Redis 存储后才能把 workers 调大。当前生产保持 `--workers 1`。

启用分布式模式（服务器上）：

```bash
sudo apt install -y redis-server                 # 1. 装 Redis
echo 'REDIS_URL=redis://127.0.0.1:6379/0' | sudo tee -a /opt/campus/backend/.env   # 2. 打开开关
sudo cp deploy/campus-worker.service /etc/systemd/system/ && sudo systemctl enable --now campus-worker  # 3. 起 worker
sudo systemctl restart campus-api                # 4. 重启后端
```

---

## 五、容器化部署（可选，与 systemd 方案二选一）

```bash
docker compose up -d --build     # mysql + redis + api + celery + web 一键起
```

---

## 六、AI 能力清单

| 能力 | 入口 | 实现 |
|---|---|---|
| AI 简历解析与优化建议 | 我的简历 | LangChain 结构化提取 + 诊断 prompt |
| AI 模拟面试 | AI 模拟面试 | ReAct Agent + SSE 流式 + 结构化评估报告 |
| 商品图片识别 | 发布宝贝 | 多模态视觉模型（GLM-4V） |
| 智能客服（能办事） | 全局悬浮球 | 状态机 + 只读数据查询工具（查订单/查跑腿/搜商品） |
| 公告 AI 摘要 | 平台公告 | 发布时后台生成一句话摘要，失败回落正文截断 |

---

部署到公网（阿里云）：见 [`docs/部署手册.md`](docs/部署手册.md)；HTTPS 配置模板见
[`deploy/nginx-https.conf`](deploy/nginx-https.conf)。
