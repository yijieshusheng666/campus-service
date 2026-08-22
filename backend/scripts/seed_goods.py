"""一次性脚本：从公开 API (DummyJSON) 抓取商品数据并批量导入 `goods` / `goods_images` 表。

- 数据源：https://dummyjson.com/products （公开、免费、无鉴权）
- 图片：使用 DummyJSON CDN 的原始商品图 URL（外部图床）
- 同时新建一个专用卖家账号，所有导入商品归属该卖家

用法（在 backend 目录下）：
    .venv\\Scripts\\python.exe -m scripts.seed_goods --limit 194

说明：可在 import(args) 脚本内自定义字段映射；重复运行会按标题去重。
"""

import argparse
import asyncio
import logging

import httpx

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.goods import Goods, GoodsImage, GoodsStatus
from app.models.user import User
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://dummyjson.com/products"
# 专用卖家账号（默认；如已存在则复用，不动原密码）
SELLER_USERNAME = "xiaoyu_admin"
SELLER_EMAIL = "xiaoyu_admin@campus.local"
SELLER_PASSWORD = "Admin@123456"

# 把 DummyJSON 的品类映射成本平台的前端分类（无匹配则用"其他"）
CATEGORY_MAP = {
    "smartphones": "数码",
    "laptops": "数码",
    "tablets": "数码",
    "mobile-accessories": "数码",
    "wearables": "数码",
    "next-gens-consoles": "数码",
    "computer-accessories": "数码",
    "graphics-sales": "数码",
    "home-decoration": "家居",
    "furniture": "家居",
    "kitchen-accessories": "家居",
    "groceries": "食品",
    "womens-bags": "服饰",
    "womens-dresses": "服饰",
    "womens-shoes": "服饰",
    "womens-watches": "服饰",
    "mens-shirts": "服饰",
    "mens-shoes": "服饰",
    "mens-watches": "服饰",
    "sports-accessories": "运动",
    "sunglasses": "时尚",
    "fragrances": "美妆",
    "beauty": "美妆",
    "skincare": "美妆",
    "motorcycle": "出行",
    "vehicle": "出行",
    "books": "图书",
    "stationery": "文具",
    "toys": "玩具",
    "tools": "工具",
    "electrical-supplies": "工具",
    "medicines": "日用",
    "home-appliances": "家电",
    "tvs": "家电",
}

CONDITIONS = ["全新", "九成新", "八成新", "七成新", "五成新"]


def _map_category(raw: str) -> str:
    return CATEGORY_MAP.get(raw, "其他")


def _map_condition() -> str:
    import random
    return random.choice(CONDITIONS)


async def _get_or_create_seller() -> User:
    """获取或创建专用卖家账号。"""
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.username == SELLER_USERNAME))
        ).scalar_one_or_none()
        if user:
            logger.info("复用已有卖家账号: %s (id=%s)", SELLER_USERNAME, user.id)
            return user
        seller = User(
            username=SELLER_USERNAME,
            email=SELLER_EMAIL,
            nickname="校园小卖部",
            hashed_password=hash_password(SELLER_PASSWORD),
            is_active=True,
        )
        db.add(seller)
        await db.commit()
        await db.refresh(seller)
        logger.info("已创建卖家账号: %s (id=%s)", SELLER_USERNAME, seller.id)
        return seller


async def fetch_products(limit: int | None) -> list[dict]:
    """分页拉取 DummyJSON 全部商品。"""
    all_products: list[dict] = []
    skip = 0
    lmt = limit or 194
    async with httpx.AsyncClient(timeout=30) as client:
        while len(all_products) < lmt:
            remaining = lmt - len(all_products)
            resp = await client.get(
                API_URL,
                params={"limit": min(remaining, 100), "skip": skip, "select": "id,title,description,price,category,images"},
            )
            resp.raise_for_status()
            payload = resp.json()
            products = payload.get("products") or []
            if not products:
                break
            all_products.extend(products)
            skip += len(products)
            logger.info("已抓取 %d/%d", len(all_products), lmt)
    return all_products[:lmt]


async def import_products(products: list[dict]) -> tuple[int, int]:
    """批量写入 goods 与 goods_images，按标题去重。返回 (已新增, 跳过)。"""
    seller = await _get_or_create_seller()
    added = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        existing_titles = set(
            (await db.execute(select(Goods.title))).scalars().all()
        )
        for item in products:
            title = (item.get("title") or "").strip()
            if not title or title in existing_titles:
                skipped += 1
                continue

            images = item.get("images") or []
            # 优先用大图，其次缩略图；兜底给一条占位描述
            description = (item.get("description") or "闲置好物，成色如图，欢迎咨询。").strip()

            goods = Goods(
                seller_id=seller.id,
                title=title[:120],
                description=description[:5000],
                price=float(item.get("price") or 0),
                category=_map_category(item.get("category") or ""),
                condition=_map_condition(),
                contact=seller.username,
                status=GoodsStatus.on_sale,
            )
            db.add(goods)
            await db.flush()

            for i, url in enumerate(images[:6]):
                db.add(GoodsImage(goods_id=goods.id, url=url, sort=i))
                existing_titles.add(title)

            added += 1

        await db.commit()
    return added, skipped


async def main() -> None:
    parser = argparse.ArgumentParser(description="从公开 API 批量导入商品")
    parser.add_argument("--limit", type=int, default=None,
                        help="导入条数，默认导入全部（约194条）")
    args = parser.parse_args()

    logger.info("开始抓取商品数据...")
    products = await fetch_products(args.limit)
    logger.info("抓取完成，共 %d 条", len(products))

    added, skipped = await import_products(products)
    logger.info("导入完成：新增 %d，跳过 %d", added, skipped)


if __name__ == "__main__":
    asyncio.run(main())