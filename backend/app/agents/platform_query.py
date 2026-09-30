"""平台数据查询工具（只读）：让智能客服能查到用户的真实业务数据。

设计原则与 support_agent 的 v2 哲学一致：
- 意图识别是确定性代码（正则关键词），不让 LLM 决定「要不要查、查什么」；
- 查询工具只读不写，LLM 只负责把查到的数据组织成自然语言；
- 不开放 LLM 自由 function calling：避免幻觉编造订单号、查错用户的数据。

安全边界：所有查询都以「当前登录用户 id」为过滤条件，客服永远只能看到
提问者自己的订单/跑腿，搜商品只返回公开在售数据。
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal
from app.models.errand import Errand
from app.models.goods import Goods, GoodsStatus
from app.models.order import Order

logger = logging.getLogger(__name__)

SessionFactory = async_sessionmaker[AsyncSession]

_ORDER_STATUS_CN = {
    "pending": "待确认",
    "paid": "已付款待发货",
    "shipped": "已发货待收货",
    "completed": "已完成",
    "cancelled": "已取消",
}
_ERRAND_STATUS_CN = {
    "pending": "待接单",
    "accepted": "配送中",
    "delivered": "已送达待确认",
    "completed": "已结算",
    "cancelled": "已取消",
}

# ---- 意图识别（确定性，与 _detect_publish_intent 同一套思路） ----
_ORDERS_RE = re.compile(
    r"(我的|查|看).{0,4}订单|订单.{0,4}(状态|到哪|怎么样|进度|查|看|发货)|我(买|卖)的.{0,6}(到哪|状态|怎么样)"
)
_ERRANDS_RE = re.compile(
    r"(我的|查|看).{0,4}跑腿|跑腿.{0,4}(状态|到哪|怎么样|进度|查|看)|快递.{0,4}(到哪|进度|状态)"
)
_GOODS_RE = re.compile(r"有没有|有卖|求购|搜(一?下|索)?|找(一?(下|个|台|部|本)|二手)")

# 关键词剥离：疑问词/动词/语气词一律替换为空格，剩下的名词部分就是搜索词
_KEYWORD_STRIP_RE = re.compile(
    r"请问|帮我|我想|我要|有没有|有卖|求购|搜索|搜一下|搜|"
    r"找一下|找一?(个|台|部|本)?|找二手|找|买个|买|卖|一下|呢|吗|的|[？?。！!，,]"
)


def detect_query_intent(question: str) -> str | None:
    """识别数据查询意图，返回 my_orders / my_errands / search_goods / None。

    优先级：订单 > 跑腿 > 搜商品（前两者带明确对象词，误判率最低）。
    """
    q = question.strip()
    if not q:
        return None
    if _ORDERS_RE.search(q):
        return "my_orders"
    if _ERRANDS_RE.search(q):
        return "my_errands"
    if _GOODS_RE.search(q):
        return "search_goods"
    return None


def extract_goods_keyword(question: str) -> str:
    """从问句中提取商品搜索关键词（剥掉疑问词/动词，留名词部分）。"""
    return " ".join(_KEYWORD_STRIP_RE.sub(" ", question.strip()).split())[:30]


# ---- 查询工具（只读） ----

async def query_my_orders(
    user_id: int, session_factory: SessionFactory = AsyncSessionLocal
) -> str:
    """查当前用户最近 5 条订单（买家/卖家视角都列）。"""
    async with session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(Order)
                    .where(or_(Order.buyer_id == user_id, Order.seller_id == user_id))
                    .order_by(Order.id.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return "该用户目前没有任何订单记录。"
    lines = []
    for o in rows:
        role = "买入" if o.buyer_id == user_id else "卖出"
        title = o.goods.title if o.goods else f"商品#{o.goods_id}"
        status_cn = _ORDER_STATUS_CN.get(o.status.value, o.status.value)
        lines.append(f"- {role}《{title}》，金额 ¥{o.price}，状态：{status_cn}")
    return "该用户最近的订单（最多 5 条）：\n" + "\n".join(lines)


async def query_my_errands(
    user_id: int, session_factory: SessionFactory = AsyncSessionLocal
) -> str:
    """查当前用户最近 5 条跑腿（发布的 + 接的单）。"""
    async with session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(Errand)
                    .where(or_(Errand.user_id == user_id, Errand.runner_id == user_id))
                    .order_by(Errand.id.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return "该用户目前没有发布或接过跑腿单。"
    lines = []
    for e in rows:
        role = "发布" if e.user_id == user_id else "接单"
        status_cn = _ERRAND_STATUS_CN.get(e.status.value, e.status.value)
        lines.append(
            f"- {role}：{e.package_info}（{e.pickup_location} → {e.dropoff_location}），"
            f"报酬 ¥{e.reward}，状态：{status_cn}"
        )
    return "该用户最近的跑腿单（最多 5 条）：\n" + "\n".join(lines)


async def query_search_goods(
    keyword: str,
    session_factory: SessionFactory = AsyncSessionLocal,
) -> str:
    """按关键词搜在售商品（标题/描述模糊匹配，最多 5 条）。"""
    if not keyword:
        return "（用户没有说明想找什么商品，请在回复中追问具体想找什么）"
    pattern = f"%{keyword}%"
    async with session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(Goods)
                    .where(
                        Goods.status == GoodsStatus.on_sale,
                        or_(Goods.title.like(pattern), Goods.description.like(pattern)),
                    )
                    .order_by(Goods.id.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
    if not rows:
        return f"平台上暂时没有在售的「{keyword}」相关商品。"
    lines = [f"- 《{g.title}》，¥{g.price}，{g.condition}，分类：{g.category}" for g in rows]
    return f"在售的「{keyword}」相关商品（最多 5 条）：\n" + "\n".join(lines)


async def run_query(
    intent: str,
    user_id: int,
    question: str,
    session_factory: SessionFactory = AsyncSessionLocal,
) -> str | None:
    """按意图分发查询；任何异常都回落 None（调用方降级为普通问答）。"""
    try:
        if intent == "my_orders":
            return await query_my_orders(user_id, session_factory)
        if intent == "my_errands":
            return await query_my_errands(user_id, session_factory)
        if intent == "search_goods":
            return await query_search_goods(extract_goods_keyword(question), session_factory)
    except Exception:
        logger.exception("平台数据查询失败 intent=%s user=%s", intent, user_id)
    return None
