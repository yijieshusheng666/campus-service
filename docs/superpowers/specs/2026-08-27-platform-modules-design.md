# 校园综合服务平台新模块设计（AI 模拟面试 / 快递代拿 / IM 私信）

日期：2026-08-27
状态：已与用户确认设计方向

## 背景与目标

现有平台已具备：二手交易（商品/收藏/订单）、AI 简历优化（解析/编辑/改良）、用户系统。
本次新增三个模块，目标：

1. 提升简历价值：SSE 流式输出、多轮 LLM 对话、WebSocket 实时通信、行锁并发控制均为后端面试高频考点
2. 产品定位升级：从"二手 + 简历"扩展为"校园生活服务 + 求职全链路"四位一体平台

## 实施顺序

```
1. AI 模拟面试   复用 app/services/llm.py，最快见效
2. 快递代拿      复用订单模块的状态机 + 行锁模式
3. IM 私信       WebSocket 全新能力，工作量最大
```

各模块独立交付，每完成一个模块同步更新 README。

---

## 模块一：AI 模拟面试

### 功能范围

- 用户选择自己的一份简历 + 输入目标岗位，创建面试会话
- AI 扮演面试官：基于简历内容与岗位画像逐题提问、多轮追问
- AI 回答流式输出（SSE，前端打字机效果）
- 用户主动结束面试后，生成结构化评估报告（可回看）

不做：语音面试、多 AI 面试官风格切换、报告导出 PDF。

### 数据模型（2 张表）

```
mock_interviews
  id, user_id(FK users), resume_id(FK resumes, nullable), job_position(100)
  status: ongoing | completed
  report(Text, nullable)      # 结束时写入评估报告 JSON
  created_at, updated_at

interview_messages
  id, interview_id(FK mock_interviews), role: assistant | user
  content(Text), created_at
```

### LLM 设计（复用 services/llm.py 模式）

- 面试官 system prompt：基于简历+岗位画像提问；每次只问一个问题；追问方向：技术细节、量化数据、STAR 展开；口吻专业但友好
- 简历注入：将 Resume 结构化数据序列化为文本，注入 system prompt（检索注入思路）
- 上下文管理：仅携带最近 10 轮消息 + 简历摘要，控制 token
- 评估报告 prompt：输出紧凑 JSON（复用 `_robust_json_parse` 解析）：
  `{"overall_score": 0-100, "dimensions": [{"name", "score", "comment"}], "strengths": [], "weaknesses": [], "suggestions": []}`
- 流式：`chain.astream()` + `StreamingResponse`（media_type="text/event-stream"）

### API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /interviews | 创建会话（resume_id + job_position），以 SSE 流式返回第一题；服务端先落库会话，再流式生成第一题并落库为 assistant 消息 |
| GET | /interviews | 我的面试会话列表 |
| GET | /interviews/{id} | 会话详情 + 全部消息 + 报告 |
| POST | /interviews/{id}/chat | 提交回答，SSE 流式返回追问 |
| POST | /interviews/{id}/finish | 结束并生成评估报告 |

SSE 事件格式：`event: delta`（增量文本）、`event: done`（完成）、`event: error`（失败，前端提示重试）。

### 错误处理

- 只能操作自己的会话（403）
- completed 状态不可继续 chat/finish（400）
- LLM 调用失败：SSE error 事件，消息不落库，用户可重发
- 评估报告生成失败：finish 返回 500，会话保持 ongoing 可重试

### 前端页面

- `views/interview/InterviewList.vue`：会话列表 + 新建入口（选简历 + 输入岗位）
- `views/interview/InterviewChat.vue`：聊天界面，SSE 打字机效果，结束按钮
- `views/interview/InterviewReport.vue`：评估报告展示（评分/维度/建议）

### 测试要点

- 创建会话 → 多轮问答 → 结束 → 报告全流程
- completed 会话拒绝继续（400）
- 他人会话 403
- SSE 增量事件序列正确（delta...done）

---

## 模块二：快递代拿

### 功能范围

- 发布代拿需求：取件地址（驿站）、取件码/快递描述、送达地址（宿舍楼）、报酬、期望时间、备注
- 跑腿大厅浏览待接单任务，接单配送
- 状态流转：待接单 → 已接单 → 已送达 → 已结算；待接单可取消
- 不能接自己发布的需求

不做：线上支付报酬（线下结算，与二手交易现状一致）、骑手定位、评价体系。

### 数据模型（1 张表）

```
errands
  id, user_id(FK 发布者), runner_id(FK 接单者, nullable)
  pickup_location(200)    # 取件地址，如"菜鸟驿站3号店"
  package_info(200)       # 取件码/快递描述
  dropoff_location(200)   # 送达地址，如"梧桐苑5栋302"
  reward Numeric(10,2)
  deadline(DateTime, nullable)
  remark(Text, nullable), contact(100)
  status: pending | accepted | delivered | completed | cancelled
  created_at, updated_at
```

### API 设计（照搬订单模块模式）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /errands | 发布需求（contact 可选，缺省为当前用户名，同订单模式） |
| GET | /errands?role=all\|published\|accepted | 大厅 / 我发布的 / 我接的 |
| GET | /errands/{id} | 详情 |
| PUT | /errands/{id}/accept | 接单 |
| PUT | /errands/{id}/status | delivered(runner) / completed(发布者) / cancelled(发布者，仅 pending) |

### 并发安全（核心亮点）

接单与订单防超卖同款方案：`SELECT ... WITH FOR UPDATE` 行锁，两个跑腿员同时抢一单只有一个成功；状态流转校验防止非法跳转（如 delivered 状态不能再被接单）。

### 前端页面

- `views/errand/ErrandList.vue`：大厅 + 我的（发布/接单）切换
- `views/errand/ErrandPublish.vue`：发布表单
- `views/errand/ErrandDetail.vue`：详情 + 接单/送达/结算/取消操作

### 测试要点

- 状态机全路径：pending→accepted→delivered→completed；pending→cancelled
- 行锁并发接单：并发请求只有一个成功
- 接自己的单被拒（400）
- 他人需求无权操作（403）

---

## 模块三：IM 私信

### 功能范围

- 用户间一对一实时聊天（WebSocket，消息落库，离线可补拉）
- 会话列表（最近联系人 + 最后一条消息 + 未读数）
- 历史消息游标分页、标记已读
- 入口：商品详情"联系卖家"、订单页"联系对方"、会话列表

不做：群聊、图片/文件消息、消息撤回、已读回执推送。

### 数据模型（1 张表）

```
messages
  id, sender_id(FK), receiver_id(FK), content(Text)
  is_read(Boolean, default False)
  created_at
  复合索引 (sender_id, receiver_id, id) 加速会话查询
```

### WebSocket 设计（FastAPI 原生，不引入新依赖）

- 端点：`/ws?token=<JWT>`（浏览器 WebSocket 无法自定义 header，故 query 传 token）
- ConnectionManager：`dict[user_id, list[WebSocket]]`，支持同一账号多设备在线
- 消息协议（JSON）：

```
客户端→服务端：{"type": "chat", "receiver_id": 1, "content": "..."}
              {"type": "ping"}
服务端→客户端：{"type": "chat_ack", "message_id": 10, "created_at": "..."}   # 发送者确认
              {"type": "new_message", "id": 10, "sender_id": 2, "content": "...", "created_at": "..."}  # 接收者推送
              {"type": "pong"}
              {"type": "error", "detail": "..."}
```

- 发送链路：鉴权 → 校验接收者存在且非自己 → 落库 → ack 给发送者所有连接 → 推送给接收者所有在线连接
- 心跳：前端每 30s 发 ping，超时未 pong 断线重连（指数退避）
- 消息可靠性：落库优先，推送失败不影响消息持久化；接收者上线后通过 REST 拉历史补齐

### REST 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /messages/conversations | 会话列表（最近消息 + 未读数聚合） |
| GET | /messages/{user_id}?before_id=&limit= | 与某人的历史消息（游标分页） |
| PUT | /messages/{user_id}/read | 标记已读 |

### 前端

- `views/chat/Chat.vue`：聊天页（路由 /chat/:userId），WebSocket 收发 + 历史加载
- `MainLayout.vue`：顶栏消息图标 + 未读总数徽标（轮询会话列表，登录态生效）
- 商品详情/订单页：增加"联系卖家/联系对方"按钮跳转聊天

### 测试要点

- 两个浏览器窗口实时互发消息
- 接收者离线 → 上线拉历史消息完整
- 未读数正确标记/清零
- 无效 token 的 WebSocket 连接被关闭（code 4401）

---

## 横切事项

- 新表均通过 alembic 迁移（0007 起）
- 路由注册进 `app/api/__init__.py`，标签分别为"模拟面试""快递代拿""消息"
- 前端路由与导航（MainLayout）随各模块交付同步添加
- README 在每个模块完成后更新对应功能描述（遵循"README 严格反映实际功能"原则）
