# 设计：AI 简历解析异步化（后台任务 + 轮询）

日期：2026-08-23
状态：已确认

## 背景与目标

现状：`POST /resumes/upload` 同步等待 LLM 结构化解析（超时上限 120s），
浏览器可能超时，期间前端只能干等，服务端虽已用线程池但请求仍长时间挂起。

目标：上传秒回，解析在后台进行；前端通过轮询展示「解析中 / 失败 / 完成」三态；
失败可重试。

## 非目标（YAGNI）

- 不引入任务队列（Celery/ARQ/Redis）
- 不做进度百分比、阶段细分推送
- 不用 WebSocket/SSE 推送
- 不做每用户并发任务限流

## 数据模型

`resumes` 表新增一列（Alembic 迁移）：

| 列 | 类型 | 默认 | 说明 |
|----|------|------|------|
| `parse_status` | Enum(`pending`,`completed`,`failed`) | `completed` | 存量数据默认视为已完成 |

新上传记录初始为 `pending`。

## 后端设计

### API 变更

| 接口 | 行为 |
|------|------|
| `POST /resumes/upload` | 同步完成：存文件 → 线程池提文本 → 提照片 → 入库(`parse_status=pending`) → **立即返回** `ResumeOut`；返回前以 `asyncio.create_task(_parse_resume_task(resume_id))` 触发后台解析 |
| `GET /resumes/mine`、`GET /resumes/{id}` | `ResumeOut` 增加 `parse_status` 字段 |
| `POST /resumes/{id}/reparse` | 新增。仅属主可调：`failed` → 重新置 `pending` 并触发后台任务；`pending` 返回 409 拒绝重复触发；`completed` 返回 400 无需重试 |

### 后台任务 `_parse_resume_task(resume_id)`

1. 通过 `AsyncSessionLocal` 自建独立会话（不复用请求级会话），加载 Resume
2. `asyncio.to_thread(extract_resume, raw_text)` 执行解析
3. 成功且结果非空 → 写回 `parsed_*` 字段，置 `completed`
4. LLM 异常**或返回空结果** → 置 `failed`（语义收紧：替代现在静默存空值的行为），记录日志
5. 会话用完即关，异常路径同样保证置为 `failed`

### 重启兜底

应用 lifespan 启动时执行一次性清理：
`UPDATE resumes SET parse_status='failed' WHERE parse_status='pending'`
——覆盖进程重启导致后台任务丢失的边缘情况，用户可手动重试。

## 前端设计

### api/resume.js
- 上传接口行为不变（现在本来就秒回了）；新增 `reparseResume(id)`

### views/resume/ResumeManage.vue
- 卡片右上角状态标签三态：
  - `pending` → 「AI 解析中」+ loading 图标
  - `failed` → 「解析失败」+ 点击重试按钮（调 reparse）
  - `completed` → 无标签（现状外观）
- 页面存在任一 `pending` 卡片时，每 2s 轮询 `/resumes/mine`；全部非 pending 后停止轮询
- 上传成功提示文案：「已上传，AI 解析完成后即可编辑」

## 错误处理汇总

| 场景 | 行为 |
|------|------|
| PDF 无文本 | 保持同步 400（上传阶段即判定） |
| LLM 超时/异常 | 任务置 `failed`，卡片显示重试 |
| 进程重启丢任务 | 启动时 pending→failed 兜底 |
| 重复触发解析 | 409 |

## 验证方式

- 后端：`python -m compileall` + 导入 app 冒烟；手工 curl 验证 upload 秒回与 reparse 状态机
- 前端：`npm run build` 通过
- 数据库：alembic 迁移 up/down 各跑一遍验证可逆
