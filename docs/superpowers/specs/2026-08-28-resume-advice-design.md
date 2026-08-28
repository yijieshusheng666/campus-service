# AI 简历「优化建议」改造设计

日期：2026-08-28
状态：已确认（用户批准）

## 背景与目标

原「AI 改良」流程：AI 自动改写简历 → PDF 样式预览 → 应用到在线编辑器保存 edited_data。
用户决策：**AI 只提建议、不改写**；删除在线编辑与所有预览功能；建议持久化（只留最新一轮）。

## 交互流程（新）

1. 上传 PDF → AI 解析（不变）
2. 卡片按钮「AI 优化建议」→ 弹窗可填岗位要求（可选）→ 生成（约 10-30s）
3. AI 输出结构化诊断建议（不改写简历）→ 覆盖存入 `resumes.suggestions` → 刷新不丢
4. 卡片下方展开区查看：总评分 + 总评 + 生成时间 + 建议列表（模块 / 优先级 / 问题 / 怎么改）
5. 用户自行修改原 PDF 后重新上传
6. 「查看原 PDF」（新窗口）保留；重新生成即覆盖旧建议

## 数据模型

`resumes` 表新增（需手动 ALTER，项目无自动迁移）：

- `suggestions JSON NULL`：`{"overall_score": int, "summary": str, "items": [{"module": str, "priority": "high|medium|low", "issue": str, "advice": str}]}`
- `suggestions_at DATETIME NULL`：生成时间

只留最新一轮：每次生成覆盖写入。`edited_data` 字段保留（面试模块兼容读取旧数据），但不再有写入入口。

## 后端

- 模型：Resume 加 `suggestions`、`suggestions_at`
- Schema：ResumeOut 加两字段；删 ResumeUpdateIn / ResumeImproveIn / ResumeImproveOut，新增 ResumeAdviceIn(job_requirement?)
- 服务：llm.py 删 improve_resume + RESUME_IMPROVE_SYSTEM；新增 RESUME_ADVICE_SYSTEM + advise_resume()
  - 提示词要求：资深 HR + 技术面试官视角；4-8 条；必须引用简历原文具体内容；advice 给可直接照抄的示例表述；可选按岗位要求定向；复用 _extract_text_chain（JSON 模式）+ _robust_json_parse
- API：新增 `POST /resumes/{id}/advice`（生成并覆盖保存，返回 ResumeOut）；删 `PUT /{id}` 与 `POST /{id}/improve`

## 前端

- 删除：ResumeEditor.vue、ResumePreviewCard.vue、EditableResumePreview.vue、EditableText.vue、EditableTextarea.vue、路由 `/resume/edit/:id`、api 的 updateResume/improveResume
- ResumeManage.vue 重构：
  - 卡片操作：AI 优化建议 / 查看原PDF（新窗口）/ 删除；「已改良」tag → 「N 条建议」tag
  - 卡片展开区：建议列表（模块 tag + 优先级红黄灰 tag + 问题 + 建议），顶部评分 + 总评 + 时间；空态引导
  - 弹窗：岗位要求输入 + 生成按钮，完成后提示已保存并刷新列表

## 测试

- 新增：advice 生成落库、重复生成覆盖、越权 403、未完成解析 400
- 全量回归 + 前端 build

## 明确不做

- 不保留历史多轮建议
- 不保留任何改写/预览/在线编辑能力
- 不做建议的「已采纳」标记等衍生功能
