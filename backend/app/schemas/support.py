"""智能客服契约（v2 行动型 + v3 SSE 流式）。

- v1：question -> answer 纯文本问答；
- v2：入参支持 image_urls（用户上传商品图片），出参携带 task_state/phase/action
  结构化字段，供前端渲染确认卡片、引导发布等操作（answer 保持向后兼容）。
- v3：新增 stream 字段控制 SSE 流式输出，默认 true。
"""
from typing import Any, Optional

from pydantic import BaseModel


class SupportChatIn(BaseModel):
    """客服对话请求（v3）。"""
    question: str = ""
    image_urls: list[str] = []
    stream: bool = True

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "question": "你好",
                "image_urls": [],
                "stream": True
            }
        }
    }


class SupportChatOut(BaseModel):
    """客服对话响应（v2/v3 兼容）。

    answer：AI 回复文本（前端直接展示，v1 兼容）；
    task_state：当前任务类型（idle / publish_goods）；
    phase：状态机阶段（collecting_images / analyzing / awaiting_confirm /
        awaiting_publish / published / cancelled）；
    action：需要前端执行的动作指令，无动作时为 null。
    """
    answer: str
    task_state: str = "idle"
    phase: Optional[str] = None
    action: Optional[dict[str, Any]] = None
