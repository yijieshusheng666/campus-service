# AI 简历解析异步化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 简历上传秒回，LLM 解析转入进程内后台任务，前端轮询展示「解析中/失败/完成」三态，失败可重试。

**Architecture:** `resumes` 表新增 `parse_status` 列作为任务状态机；`POST /upload` 同步完成存文件/提文本/提照片后立即返回，用 `asyncio.create_task` 启动后台解析（独立 Session）；应用启动时把遗留 `pending` 兜底标记为 `failed`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Vue 3 + Element Plus。**零新依赖。**

## Global Constraints

- 不引入任何新依赖（无 Celery/Redis/WebSocket）
- 设计文档：`docs/superpowers/specs/2026-08-23-resume-async-parse-design.md`，语义以它为准
- 存量数据兼容：迁移后已有记录 `parse_status='completed'`
- 失败语义收紧：LLM 异常或返回空 dict → `failed`（可重试），不再静默存空值
- 后端验证命令一律在 `backend/` 目录下用 `.venv\Scripts\python.exe` 执行；前端命令在 `frontend/` 下执行

---

### Task 1: 数据模型 + Alembic 迁移

**Files:**
- Modify: `backend/app/models/resume.py`
- Create: `backend/alembic/versions/0006_add_resume_parse_status.py`

**Interfaces:**
- Produces: `app.models.resume.ParseStatus`（str 枚举：`pending`/`completed`/`failed`）与 `Resume.parse_status` 列，供 Task 2 使用。

- [ ] **Step 1: 模型添加枚举与列**

`backend/app/models/resume.py` 顶部导入改为：

```python
"""简历模型：存储原始文本、LLM 结构化提取结果与向量化状态。"""
import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ParseStatus(str, enum.Enum):
    pending = "pending"          # 待后台解析
    completed = "completed"      # 解析完成
    failed = "failed"            # 解析失败（可重试）
```

`Resume` 类内、`is_vectorized` 行之前加：

```python
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus), default=ParseStatus.completed, server_default="completed"
    )
```

- [ ] **Step 2: 创建迁移文件**

新建 `backend/alembic/versions/0006_add_resume_parse_status.py`：

```python
"""简历表新增解析状态列

Revision ID: 0006_add_resume_parse_status
Revises: 0005_add_orders
Create Date: 2026-08-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_resume_parse_status"
down_revision: Union[str, None] = "0005_add_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column(
            "parse_status",
            sa.Enum("pending", "completed", "failed", name="parsestatus"),
            nullable=False,
            server_default="completed",
        ),
    )


def downgrade() -> None:
    op.drop_column("resumes", "parse_status")
```

- [ ] **Step 3: 验证**

```bash
cd backend
.venv\Scripts\python.exe -m compileall app -q
alembic upgrade head      # 需本地 MySQL 可达；若数据库未启动，标注跳过并在实施说明中注明
alembic downgrade -1
alembic upgrade head
```

预期：compileall 无输出；upgrade/downgrade 往返成功。

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/resume.py backend/alembic/versions/0006_add_resume_parse_status.py
git commit -m "feat: 简历表新增 parse_status 解析状态列"
```

---

### Task 2: 后端——上传异步化、后台任务、重试接口、重启兜底

**Files:**
- Modify: `backend/app/schemas/resume.py`
- Modify: `backend/app/api/resumes.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `ParseStatus`、`Resume.parse_status`（Task 1）；现有 `extract_resume(text) -> dict`、`_to_out()`、`_get_owned_resume()`。
- Produces: `ResumeOut.parse_status: str`；`POST /api/v1/resumes/{id}/reparse`（409=pending 中重复触发，400=已完成）；`_parse_resume_task(resume_id: int) -> None`。

- [ ] **Step 1: Schema 增加字段**

`backend/app/schemas/resume.py` 的 `ResumeOut` 中 `file_name` 之后加一行：

```python
    parse_status: str = "completed"
```

- [ ] **Step 2: resumes.py 导入调整**

`backend/app/api/resumes.py` 两行导入改为：

```python
from app.database import AsyncSessionLocal, get_db
from app.models.resume import ParseStatus, Resume
```

- [ ] **Step 3: 新增后台任务函数**

放在 `_ensure_resume_dir` 之后、`_extract_pdf_text` 之前：

```python
async def _parse_resume_task(resume_id: int) -> None:
    """后台解析任务：独立会话执行 LLM 提取，成功写回字段，失败置 failed。"""
    async with AsyncSessionLocal() as db:
        resume = await db.get(Resume, resume_id)
        if not resume:
            return
        try:
            parsed = await asyncio.to_thread(extract_resume, resume.raw_text)
            if not parsed:
                raise RuntimeError("LLM 返回空结果")
        except Exception:
            logger.exception("简历后台解析失败 id=%s", resume_id)
            resume.parse_status = ParseStatus.failed
            await db.commit()
            return
        resume.parsed_name = parsed.get("name")
        resume.parsed_phone = parsed.get("phone")
        resume.parsed_email = parsed.get("email")
        resume.parsed_location = parsed.get("location")
        resume.parsed_job_title = parsed.get("job_title")
        resume.parsed_education = parsed.get("education") or None
        resume.parsed_skills = parsed.get("skills") or None
        resume.parsed_experience = parsed.get("experience") or None
        resume.parsed_summary = parsed.get("summary")
        resume.parsed_sections = parsed.get("sections") or None
        resume.parse_status = ParseStatus.completed
        await db.commit()
        logger.info("简历后台解析完成 id=%s", resume_id)
```

- [ ] **Step 4: 改造 upload 端点为秒回**

将 `upload_resume` 中从「LLM 结构化提取」注释起、到函数结尾的整段替换为：

```python
    # 提取PDF中的照片（同步阶段完成，秒级）
    photo_path = None
    try:
        resume_dir = _ensure_resume_dir()
        base_name = Path(filename).stem
        photo_path = await asyncio.to_thread(
            _extract_photo_from_pdf, file_path, resume_dir, base_name
        )
        if photo_path:
            logger.info("已提取简历照片: %s", photo_path)
    except Exception as e:
        logger.debug("照片提取异常: %s", e)

    # 入库为待解析状态并立即返回；LLM 结构化解析转后台任务
    resume = Resume(
        user_id=user.id,
        file_name=file.filename or filename,
        file_path=str(file_path),
        photo_path=photo_path,
        raw_text=raw_text,
        parse_status=ParseStatus.pending,
        vector_id=new_id(),
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    asyncio.create_task(_parse_resume_task(resume.id))
    logger.info("简历已入库待解析 id=%s 文本长度=%d", resume.id, len(raw_text))
    return _to_out(resume)
```

注意：原代码中 `logger.info("开始 LLM 解析简历...")`、`extract_resume` 调用及旧 `Resume(...)` 构造全部删除。

- [ ] **Step 5: 新增 reparse 端点**

放在 `improve_resume_endpoint` 之前：

```python
@router.post("/{resume_id}/reparse", response_model=ResumeOut)
async def reparse_resume(
    resume_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """解析失败的简历重新触发后台 AI 解析。"""
    resume = await _get_owned_resume(db, resume_id, user)
    if resume.parse_status == ParseStatus.pending:
        raise HTTPException(status_code=409, detail="该简历正在解析中，请稍候")
    if resume.parse_status == ParseStatus.completed:
        raise HTTPException(status_code=400, detail="该简历已完成解析，无需重试")
    resume.parse_status = ParseStatus.pending
    await db.commit()
    asyncio.create_task(_parse_resume_task(resume.id))
    return _to_out(resume)
```

- [ ] **Step 6: main.py 重启兜底**

`backend/app/main.py` 导入区增加：

```python
from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.models.resume import ParseStatus, Resume
```

`lifespan` 整体替换为：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 进程重启会丢失进行中的后台解析任务：遗留 pending 一律标记为 failed，用户可手动重试
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Resume)
            .where(Resume.parse_status == ParseStatus.pending)
            .values(parse_status=ParseStatus.failed)
        )
        await db.commit()
    yield
```

- [ ] **Step 7: 验证**

```bash
cd backend
.venv\Scripts\python.exe -m compileall app -q
.venv\Scripts\python.exe -c "from app.main import app; from app.schemas.resume import ResumeOut; assert 'parse_status' in ResumeOut.model_fields; assert any(getattr(r,'path','').endswith('/reparse') for r in app.routes); print('SMOKE OK')"
```

预期：输出 `SMOKE OK`。（完整链路验证依赖 LLM key，属手工验收：上传后立即返回 `parse_status:"pending"`，数秒后 `/mine` 变 `completed`。）

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/resume.py backend/app/api/resumes.py backend/app/main.py
git commit -m "feat: 简历解析异步化——上传秒回、后台任务、失败重试、重启兜底"
```

---

### Task 3: 前端——状态标签、轮询、失败重试

**Files:**
- Modify: `frontend/src/api/resume.js`
- Modify: `frontend/src/views/resume/ResumeManage.vue`

**Interfaces:**
- Consumes: `GET /resumes/mine` 响应的 `parse_status` 字段、`POST /resumes/{id}/reparse`（Task 2）。
- Produces: `reparseResume(id)` API 封装；卡片三态 UI 与自动停轮询逻辑。

- [ ] **Step 1: api/resume.js 增加 reparse**

文件末尾追加：

```js
export const reparseResume = (id) => request.post(`/api/v1/resumes/${id}/reparse`)
```

- [ ] **Step 2: 卡片模板加状态标签**

`ResumeManage.vue` 模板中 `<div class="resume-title">` 内、「已改良」tag 之后追加：

```html
              <el-tag v-if="r.parse_status === 'pending'" size="small" type="warning" class="ml-8">
                <el-icon class="is-loading" style="vertical-align:-2px;margin-right:2px"><Loading /></el-icon>
                AI 解析中
              </el-tag>
              <el-tag
                v-else-if="r.parse_status === 'failed'"
                size="small"
                type="danger"
                class="ml-8"
                style="cursor:pointer"
                @click="onReparse(r)"
              >解析失败，点击重试</el-tag>
```

同时把「AI 改良」按钮加上解析未完成的禁用（`openEditor` 的按钮同理隐藏编辑入口意义不大，仅禁用即可）：

```html
            <el-button type="primary" plain :disabled="r.parse_status !== 'completed'" @click="openImprove(r)">AI 改良</el-button>
```

- [ ] **Step 3: 脚本——轮询与重试处理**

`<script setup>` 中导入行补充 `onUnmounted` 与 `reparseResume`：

```js
import { onMounted, onUnmounted, ref } from 'vue'
import { uploadResume, myResumes, deleteResume, improveResume, updateResume, reparseResume } from '@/api/resume'
```

`load()` 函数整体替换为：

```js
let pollTimer = null
function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
async function load() {
  loading.value = true
  try {
    const res = await myResumes()
    resumes.value = res.data
    // 存在解析中的卡片时每 2s 轮询，全部落定后停止
    stopPoll()
    if (res.data.some((r) => r.parse_status === 'pending')) {
      pollTimer = setInterval(async () => {
        const r2 = await myResumes()
        resumes.value = r2.data
        if (!r2.data.some((x) => x.parse_status === 'pending')) stopPoll()
      }, 2000)
    }
  } finally {
    loading.value = false
  }
}
onUnmounted(stopPoll)
```

`onUpload` 内成功提示文案替换：

```js
    ElMessage.success('已上传，AI 解析完成后即可编辑')
```

新增重试处理（放 `onDelete` 之前）：

```js
async function onReparse(row) {
  try {
    await reparseResume(row.id)
    ElMessage.success('已重新提交 AI 解析')
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '重试失败')
  }
}
```

- [ ] **Step 4: 验证**

```bash
cd frontend
npm run build
```

预期：构建成功无报错。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/resume.js frontend/src/views/resume/ResumeManage.vue
git commit -m "feat: 简历列表解析状态三态展示与自动轮询刷新"
```
