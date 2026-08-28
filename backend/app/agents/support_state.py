"""SupportSessionState：智能客服（行动型 Agent）的会话级状态机。

- 状态机管理多步骤任务（如商品发布），防止用户中途切换话题后状态混乱；
- 状态持久化：per-user 内存存储（与旧版对话缓存兼容，扩展为状态机）；
- 任务隔离：用户可在同一客服会话中发起新任务，旧任务状态自动清理。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class TaskType(str, enum.Enum):
    """客服可执行的任务类型。"""
    idle = "idle"           # 无活跃任务，纯问答
    publish_goods = "publish_goods"  # 帮用户发布二手商品


class PublishGoodsPhase(str, enum.Enum):
    """商品发布任务的阶段状态机。"""
    collecting_images = "collecting_images"   # 等待用户上传图片
    analyzing = "analyzing"                     # AI 分析图片中（后端执行）
    awaiting_confirm = "awaiting_confirm"       # 等待用户确认分析结果
    awaiting_publish = "awaiting_publish"         # 等待用户确认正式发布
    published = "published"                       # 已发布完成
    cancelled = "cancelled"                     # 用户取消/放弃


@dataclass
class SupportSessionState:
    """客服会话状态。

    Attributes:
        task: 当前任务类型
        phase: 当前任务阶段（仅 task != idle 时有效）
        collected_images: 已收集的商品图片 URL 列表
        user_hint: 用户对商品的额外描述
        analysis_result: AI 分析结果（商品信息草稿）
        publish_payload: 待发布的商品完整数据（含定价建议）
        last_error: 最近一次错误信息（用于失败回退提示）
        task_history: 当前任务已执行的步骤记录
    """
    task: TaskType = TaskType.idle
    phase: PublishGoodsPhase | None = None

    # 商品发布任务数据
    collected_images: list[str] = field(default_factory=list)
    user_hint: str = ""                  # 用户补充描述
    analysis_result: dict[str, Any] = field(default_factory=dict)
    publish_payload: dict[str, Any] = field(default_factory=dict)

    last_error: str = ""
    task_history: list[str] = field(default_factory=list)

    def reset_task(self) -> None:
        """重置任务状态（用于用户中途切换话题或任务完成/取消后）。"""
        self.task = TaskType.idle
        self.phase = None
        self.collected_images = []
        self.user_hint = ""
        self.analysis_result = {}
        self.publish_payload = {}
        self.last_error = ""
        self.task_history = []

    def start_publish_goods(self) -> None:
        """启动商品发布任务。"""
        self.reset_task()
        self.task = TaskType.publish_goods
        self.phase = PublishGoodsPhase.collecting_images
        self.task_history.append("用户发起发布商品任务")

    def add_images(self, image_urls: list[str]) -> None:
        """添加商品图片 URL。上传新图时清理上次错误，允许重试。"""
        for url in image_urls:
            if url and url not in self.collected_images:
                self.collected_images.append(url)
        self.last_error = ""  # 新图上传，清理失败标记，允许重试
        self.task_history.append(f"上传了 {len(image_urls)} 张图片")

    def set_user_hint(self, hint: str) -> None:
        """设置用户补充描述。"""
        self.user_hint = (self.user_hint + " " + hint).strip() if self.user_hint else hint
        self.task_history.append("补充了商品描述")

    def set_analysis_result(self, result: dict) -> None:
        """设置 AI 分析结果，进入等待确认阶段。"""
        self.analysis_result = result
        self.phase = PublishGoodsPhase.awaiting_confirm
        self.task_history.append("AI 分析完成，等待用户确认")

    def confirm_analysis(self) -> None:
        """用户确认分析结果，进入等待发布阶段。"""
        self.phase = PublishGoodsPhase.awaiting_publish
        # 构建发布 payload
        self.publish_payload = {
            "title": self.analysis_result.get("title", ""),
            "description": self.analysis_result.get("description", ""),
            "category": self.analysis_result.get("category", "其他"),
            "condition": self.analysis_result.get("condition", "九成新"),
            "price": self.analysis_result.get("suggested_price", 0),
            "image_urls": list(self.collected_images),
        }
        self.task_history.append("用户确认了分析结果，等待正式发布确认")

    def mark_published(self) -> None:
        """标记任务已发布完成。"""
        self.phase = PublishGoodsPhase.published
        self.task_history.append("商品已正式发布")

    def mark_cancelled(self, reason: str = "用户取消") -> None:
        """标记任务已取消。"""
        self.phase = PublishGoodsPhase.cancelled
        self.last_error = reason
        self.task_history.append(f"任务取消: {reason}")

    def can_transition(self, target_phase: PublishGoodsPhase) -> bool:
        """检查是否允许从当前阶段转换到目标阶段（防止非法跳转）。"""
        if self.task != TaskType.publish_goods:
            return target_phase == PublishGoodsPhase.collecting_images

        valid_transitions: dict[str, set[str]] = {
            "collecting_images": {"analyzing", "cancelled"},
            "analyzing": {"awaiting_confirm", "collecting_images", "cancelled"},
            "awaiting_confirm": {"awaiting_publish", "collecting_images", "cancelled"},
            "awaiting_publish": {"published", "awaiting_confirm", "cancelled"},
            "published": {"collecting_images"},  # 完成后可开启新任务
            "cancelled": {"collecting_images"},   # 取消后可重新开始
        }
        current = self.phase.value if self.phase else ""
        return target_phase.value in valid_transitions.get(current, set())

    @property
    def is_active_task(self) -> bool:
        """是否有未完成的活跃任务。"""
        return self.task != TaskType.idle and self.phase not in (
            PublishGoodsPhase.published,
            PublishGoodsPhase.cancelled,
        )
