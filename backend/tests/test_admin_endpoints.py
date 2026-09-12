"""管理端接口冒烟：有数据时每个端点都必须返回 200。

**为什么需要这个文件**：`MissingGreenlet` 这类序列化错误只在「表里有数据」时才暴露——
空表直接返回 `[]`，不触发任何属性访问，测试怎么写都是绿的。
本项目已经因此连挂两次线上：
1. `/admin/messages` —— `MessageOut.goods` 需要 `Goods.images`，没预加载
2. `/admin/orders`   —— `OrderOut.goods.cover` 同样深入到 `Goods.images`，没预加载

两次的共同点：**改动一个公共 schema / 模型属性后，漏改了某个消费点的预加载**。
所以这里为每个实体各造一条最小数据，然后把管理端所有端点跑一遍——
以后任何「加了新字段却忘了预加载」的改动，都会在这里当场失败，而不是等用户点出来。
"""
import pytest
from sqlalchemy import select

from app.models.errand import Errand, ErrandStatus
from app.models.goods import Goods, GoodsImage
from app.models.message import Message
from app.models.order import Order, OrderStatus
from app.models.user import User
from tests.conftest import TestingSessionLocal


@pytest.fixture
async def admin_client(auth_client):
    """把已注册用户提升为管理员（直接改库，等价于服务器上跑 create_admin.py）。"""
    async with TestingSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == "tester"))).scalar_one()
        user.is_admin = True
        await db.commit()
    yield auth_client


@pytest.fixture
async def seeded(admin_client):
    """造一条覆盖全部关系链的最小数据：用户 → 商品+图片 → 订单 → 跑腿 → 私信带商品。"""
    async with TestingSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        me = next(u for u in users if u.username == "tester")
        peer = User(username="peer01", email="peer01@test.com", hashed_password="x")
        db.add(peer)
        await db.commit()
        await db.refresh(peer)

        goods = Goods(seller_id=me.id, title="二手降噪耳机", description="九成新",
                      price=199)
        db.add(goods)
        await db.commit()
        await db.refresh(goods)
        db.add(GoodsImage(goods_id=goods.id, url="/static/goods/demo.png", sort=0))

        db.add(Order(order_no="NO-SMOKE-0001", buyer_id=peer.id, seller_id=me.id,
                     goods_id=goods.id, price=199, status=OrderStatus.pending))
        db.add(Errand(user_id=me.id, pickup_location="菜鸟驿站", package_info="一个纸箱",
                      dropoff_location="3 号宿舍楼", reward=5,
                      status=ErrandStatus.pending))
        # 商品卡片消息：MessageOut.goods 同样会深入到 Goods.images
        db.add(Message(sender_id=me.id, receiver_id=peer.id, content="想问下这个耳机",
                       goods_id=goods.id))
        await db.commit()
        yield goods.id


async def test_admin_stats_ok(seeded, admin_client):
    resp = await admin_client.get("/api/v1/admin/stats")
    assert resp.status_code == 200, resp.text
    assert resp.json()["goods"] >= 1


async def test_admin_users_ok(seeded, admin_client):
    resp = await admin_client.get("/api/v1/admin/users")
    assert resp.status_code == 200, resp.text
    assert any(u["username"] == "tester" for u in resp.json())


async def test_admin_goods_ok(seeded, admin_client):
    """GoodsOut 含首图，必须预加载 Goods.images。"""
    resp = await admin_client.get("/api/v1/admin/goods")
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["id"] == seeded


async def test_admin_orders_ok(seeded, admin_client):
    """回归点：OrderOut.goods.cover → Goods.images，漏预加载即 500 MissingGreenlet。"""
    resp = await admin_client.get("/api/v1/admin/orders")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["goods"]["title"] == "二手降噪耳机"
    assert body[0]["goods"]["cover"], "商品首图应随订单一起返回"


async def test_admin_errands_ok(seeded, admin_client):
    resp = await admin_client.get("/api/v1/admin/errands")
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["pickup_location"] == "菜鸟驿站"


async def test_admin_set_goods_status_ok(seeded, admin_client):
    resp = await admin_client.put(f"/api/v1/admin/goods/{seeded}/status",
                                  json={"status": "off_shelf"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "off_shelf"


async def test_admin_toggle_user_status_ok(seeded, admin_client):
    async with TestingSessionLocal() as db:
        peer = (await db.execute(select(User).where(User.username == "peer01"))).scalar_one()
        peer_id = peer.id
    resp = await admin_client.put(f"/api/v1/admin/users/{peer_id}/status",
                                  json={"is_active": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False


async def test_admin_endpoints_require_admin(client):
    """反向校验：普通用户访问管理端必须是 403（而不是 200 或 500）。"""
    resp = await client.post("/api/v1/auth/register",
                             json={"username": "plain01", "email": "plain01@test.com",
                                   "password": "pass1234"})
    token = resp.json()["access_token"]
    resp = await client.get("/api/v1/admin/orders",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, resp.text
