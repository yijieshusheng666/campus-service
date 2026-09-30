"""客服平台数据查询工具：意图识别、关键词提取、只读查询、agent 接线。"""
import pytest
from sqlalchemy import select

import app.agents.support_agent as support_agent
from app.agents.platform_query import (
    detect_query_intent,
    extract_goods_keyword,
    query_my_errands,
    query_my_orders,
    query_search_goods,
)
from app.models.errand import Errand, ErrandStatus
from app.models.goods import Goods, GoodsStatus
from app.models.order import Order, OrderStatus
from app.models.user import User
from tests.conftest import TestingSessionLocal


# ---------- 意图识别 ----------

@pytest.mark.parametrize(
    "question,expected",
    [
        ("我的订单到哪了", "my_orders"),
        ("查一下订单状态", "my_orders"),
        ("我的跑腿什么进度", "my_errands"),
        ("我的快递到哪了", "my_errands"),
        ("有没有卖耳机的", "search_goods"),
        ("帮我找一台二手显示器", "search_goods"),
        ("怎么发布商品", None),
        ("你好", None),
    ],
)
def test_detect_query_intent(question, expected):
    assert detect_query_intent(question) == expected


def test_extract_goods_keyword():
    assert extract_goods_keyword("有没有卖耳机的") == "耳机"
    assert "显示器" in extract_goods_keyword("帮我找一台二手显示器")


# ---------- 查询工具（真实落库到测试库） ----------

@pytest.fixture
async def seeded_user():
    async with TestingSessionLocal() as db:
        u = User(username="buyer1", email="b1@test.com", hashed_password="x")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        g = Goods(seller_id=u.id, title="降噪耳机", description="九成新索尼",
                  price=199, status=GoodsStatus.on_sale)
        db.add(g)
        await db.commit()
        await db.refresh(g)
        db.add(Order(order_no="NO-T1", buyer_id=u.id, seller_id=u.id,
                     goods_id=g.id, price=199, status=OrderStatus.shipped))
        db.add(Errand(user_id=u.id, pickup_location="菜鸟驿站", package_info="一个小纸箱",
                      dropoff_location="3 号楼", reward=5, status=ErrandStatus.accepted))
        await db.commit()
        yield u


async def test_query_my_orders(seeded_user):
    text = await query_my_orders(seeded_user.id, TestingSessionLocal)
    assert "降噪耳机" in text
    assert "已发货待收货" in text


async def test_query_my_orders_empty():
    text = await query_my_orders(99999, TestingSessionLocal)
    assert "没有任何订单" in text


async def test_query_my_errands(seeded_user):
    text = await query_my_errands(seeded_user.id, TestingSessionLocal)
    assert "小纸箱" in text
    assert "配送中" in text


async def test_query_search_goods(seeded_user):
    text = await query_search_goods("耳机", TestingSessionLocal)
    assert "降噪耳机" in text
    assert "199" in text


async def test_query_search_goods_miss(seeded_user):
    text = await query_search_goods("冰箱", TestingSessionLocal)
    assert "暂时没有" in text


# ---------- agent 接线（不触网：LLM 与查询入口都 monkeypatch） ----------

async def test_agent_chat_injects_data_context(monkeypatch):
    captured = {}

    async def fake_run_query(intent, user_id, question):
        captured["intent"] = intent
        return "该用户最近的订单：\n- 买入《降噪耳机》，状态：已发货待收货"

    async def fake_general_chat(user_id, question, image_urls=None, data_context=None):
        captured["data_context"] = data_context
        return "你的耳机已经在路上了"

    monkeypatch.setattr(support_agent, "run_query", fake_run_query)
    monkeypatch.setattr(support_agent, "_general_chat", fake_general_chat)

    result = await support_agent.agent_chat(user_id=12345, question="我的订单到哪了")
    assert captured["intent"] == "my_orders"
    assert "降噪耳机" in captured["data_context"]
    assert result["answer"] == "你的耳机已经在路上了"


async def test_agent_chat_falls_back_when_query_fails(monkeypatch):
    """查询异常返回 None 时，降级为普通问答（data_context 为 None）。"""
    captured = {}

    async def fake_run_query(intent, user_id, question):
        return None

    async def fake_general_chat(user_id, question, image_urls=None, data_context=None):
        captured["data_context"] = data_context
        return "普通回答"

    monkeypatch.setattr(support_agent, "run_query", fake_run_query)
    monkeypatch.setattr(support_agent, "_general_chat", fake_general_chat)

    result = await support_agent.agent_chat(user_id=12345, question="我的订单到哪了")
    assert captured["data_context"] is None
    assert result["answer"] == "普通回答"


async def test_agent_chat_normal_question_skips_query(monkeypatch):
    """普通问题不触发数据查询。"""
    called = {"n": 0}

    async def fake_run_query(intent, user_id, question):
        called["n"] += 1
        return "data"

    async def fake_general_chat(user_id, question, image_urls=None, data_context=None):
        return "普通回答"

    monkeypatch.setattr(support_agent, "run_query", fake_run_query)
    monkeypatch.setattr(support_agent, "_general_chat", fake_general_chat)

    result = await support_agent.agent_chat(user_id=12345, question="怎么修改密码")
    assert called["n"] == 0
    assert result["answer"] == "普通回答"
