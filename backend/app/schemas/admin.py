"""管理后台契约。

列表类接口刻意复用各模块已有的 XxxOut（GoodsOut / OrderOut / ErrandOut /
MessageOut），而不是另起一套 AdminXxxOut —— 复用可以保证字段永远和各业务模块
一致，不会出现「后台加了下架字段但商品页没同步」这类漂移。
这里只定义「统计」和「管理动作入参」两类新契约。
"""
from datetime import datetime

from pydantic import BaseModel

from app.models.goods import GoodsStatus


class AdminStatsOut(BaseModel):
    """数据总览。一次返回全部计数，前端一个请求就能渲染看板。"""

    users: int
    admins: int
    users_active: int

    goods: int
    goods_on_sale: int
    goods_off_shelf: int

    orders: int
    orders_completed: int

    errands: int
    errands_pending: int

    messages: int

    # 简历与模拟面试只统计条数，不提供内容浏览。
    # 这两类数据含电话、邮箱、工作经历等个人信息，属于用户隐私；
    # 「管理员能管数据」不等于「管理员能逐条翻看用户简历」——权限该有边界。
    resumes: int
    interviews: int


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str
    nickname: str | None = None
    phone: str | None = None
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserStatusIn(BaseModel):
    """封禁 / 解封。"""

    is_active: bool


class AdminGoodsStatusIn(BaseModel):
    """下架 / 恢复 / 标记已售。

    用 GoodsStatus 枚举而不是裸 str：pydantic 会在入口就把非法值挡掉，
    不会出现「传了 on_sale_flag 这种拼错的值、写进库才发现」的情况。
    """

    status: GoodsStatus
