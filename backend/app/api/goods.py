"""二手商品 API：CRUD、图片上传、分页搜索、收藏联动。"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_optional_user
from app.config import settings
from app.core.utils import ALLOWED_IMAGE_EXT, escape_like, looks_like_image, safe_filename
from app.database import get_db
from app.models.favorite import Favorite
from app.models.goods import Goods, GoodsImage, GoodsStatus
from app.models.user import User
from app.agents.goods_agent import analyze_goods, suggest_price
from app.schemas.goods import GoodsAnalyzeIn, GoodsCreate, GoodsOut, GoodsUpdate

router = APIRouter(prefix="/goods", tags=["二手交易"])

logger = logging.getLogger(__name__)


def _ensure_upload_dir() -> Path:
    d = Path(settings.UPLOAD_DIR) / "goods"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _serialize(goods: Goods, *, is_favorited: bool = False) -> GoodsOut:
    out = GoodsOut.model_validate(goods)
    out.seller_name = goods.seller.username if goods.seller else ""
    out.is_favorited = is_favorited
    return out


async def _favorited_ids(
    db: AsyncSession, viewer_id: int | None, goods_ids: list[int]
) -> set[int]:
    if not viewer_id or not goods_ids:
        return set()
    rows = await db.execute(
        select(Favorite.goods_id).where(
            Favorite.user_id == viewer_id,
            Favorite.goods_id.in_(goods_ids),
        )
    )
    return {gid for (gid,) in rows.all()}


async def _load_goods(db: AsyncSession, goods_id: int) -> Goods:
    goods = (
        await db.execute(
            select(Goods)
            .options(selectinload(Goods.images), selectinload(Goods.seller))
            .where(Goods.id == goods_id)
        )
    ).scalar_one_or_none()
    if not goods:
        raise HTTPException(status_code=404, detail="商品不存在")
    return goods


# ---- 上传图片 ----
@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式：{suffix or '未知'}")
    content = await file.read(settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片超过大小限制")
    if not looks_like_image(content[:16]):
        raise HTTPException(status_code=400, detail="文件内容与图片格式不符")
    filename = safe_filename(file.filename or "img.png", prefix="img_")
    upload_dir = _ensure_upload_dir()
    (upload_dir / filename).write_bytes(content)
    url = f"{settings.STATIC_URL}/goods/{filename}"
    return {"url": url}


# ---- 商品 CRUD ----
@router.post("", response_model=GoodsOut, status_code=status.HTTP_201_CREATED)
async def create_goods(
    payload: GoodsCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goods = Goods(
        seller_id=user.id,
        title=payload.title,
        description=payload.description,
        price=payload.price,
        category=payload.category,
        condition=payload.condition,
        contact=payload.contact or user.username,
    )
    db.add(goods)
    await db.flush()
    for i, url in enumerate(payload.image_urls):
        db.add(GoodsImage(goods_id=goods.id, url=url, sort=i))
    await db.commit()
    return _serialize(await _load_goods(db, goods.id))


@router.get("", response_model=dict)
async def list_goods(
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
    keyword: str | None = Query(None),
    category: str | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    sort: str = Query("latest"),  # latest / price_asc / price_desc
):
    viewer_id = user.id if user is not None else None

    conditions = [Goods.status == GoodsStatus.on_sale]
    if keyword:
        kw = escape_like(keyword.strip())
        if kw:
            conditions.append(or_(Goods.title.like(f"%{kw}%"), Goods.description.like(f"%{kw}%")))
    if category:
        conditions.append(Goods.category == category)
    if min_price is not None:
        conditions.append(Goods.price >= min_price)
    if max_price is not None:
        conditions.append(Goods.price <= max_price)

    total = (await db.execute(select(func.count(Goods.id)).where(*conditions))).scalar_one()
    stmt = (
        select(Goods)
        .options(selectinload(Goods.images), selectinload(Goods.seller))
        .where(*conditions)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if sort == "price_asc":
        stmt = stmt.order_by(Goods.price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Goods.price.desc())
    else:
        stmt = stmt.order_by(Goods.id.desc())

    items = list((await db.execute(stmt)).scalars().all())
    faved = await _favorited_ids(db, viewer_id, [g.id for g in items])
    return {"items": [_serialize(g, is_favorited=g.id in faved) for g in items],
            "total": total, "page": page, "page_size": page_size}


@router.get("/categories", response_model=list)
async def list_categories(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Goods.category).distinct())).scalars().all()
    return [r for r in rows if r]


@router.post("/analyze", response_model=dict)
async def analyze_goods_info(
    payload: GoodsAnalyzeIn,
    db: AsyncSession = Depends(get_db),
):
    """Agent 分析商品信息：图片 + 描述 → 标题/描述/分类/成色 + 定价建议。

    定价参考同类商品历史成交价（RAG），失败回退空建议不阻塞前端。
    """
    urls = [u for u in payload.image_urls if isinstance(u, str) and u.strip()]
    hint = payload.user_hint.strip()

    # 1. 基础信息分析（agent 内部会自动将相对路径转为 base64 data URL）
    base = await analyze_goods(urls, hint)

    # 2. 同类商品历史成交价（RAG 定价参考）
    category = base.get("category", "其他")
    condition = base.get("condition", "九成新")
    price_text = "无历史数据"
    if category:
        try:
            rows = await db.execute(
                select(Goods.price)
                .where(
                    Goods.category == category,
                    Goods.status == GoodsStatus.on_sale,
                )
                .order_by(Goods.price.desc())
                .limit(20)
            )
            prices = [float(r) for (r,) in rows.all() if r is not None]
            if prices:
                avg = sum(prices) / len(prices)
                min_p, max_p = min(prices), max(prices)
                price_text = f"历史成交价区间 ¥{min_p:.0f}-{max_p:.0f}，平均 ¥{avg:.0f}（共{len(prices)}件）"
        except Exception as e:
            logger.warning("price query failed: %s", e)

    # 3. 定价建议
    price = await suggest_price(
        category=category,
        condition=condition,
        description=base.get("description", ""),
        price_range_text=price_text,
    )

    return {
        "title": base.get("title", ""),
        "description": base.get("description", ""),
        "category": category,
        "condition": condition,
        "suggested_price": base.get("suggested_price", 0),
        "price_advice": price,
        "debug": {"price_range_text": price_text},
    }


@router.get("/mine", response_model=list[GoodsOut])
async def my_goods(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Goods)
        .options(selectinload(Goods.images), selectinload(Goods.seller))
        .where(Goods.seller_id == user.id)
        .order_by(Goods.id.desc())
    )
    items = list((await db.execute(stmt)).scalars().all())
    faved = await _favorited_ids(db, user.id, [g.id for g in items])
    return [_serialize(g, is_favorited=g.id in faved) for g in items]


@router.get("/{goods_id}", response_model=GoodsOut)
async def get_goods(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    goods = await _load_goods(db, goods_id)
    viewer_id = user.id if user is not None else None
    return _serialize(
        goods, is_favorited=goods.id in await _favorited_ids(db, viewer_id, [goods.id])
    )


@router.put("/{goods_id}", response_model=GoodsOut)
async def update_goods(
    goods_id: int,
    payload: GoodsUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goods = await _load_goods(db, goods_id)
    if goods.seller_id != user.id:
        raise HTTPException(status_code=403, detail="只能操作自己的商品")

    data = payload.model_dump(exclude_unset=True)
    images = data.pop("image_urls", None)

    for field, value in data.items():
        setattr(goods, field, value)

    if images is not None:
        for old in list(goods.images):
            await db.delete(old)
        for i, url in enumerate(images):
            db.add(GoodsImage(goods_id=goods.id, url=url, sort=i))

    await db.commit()
    return _serialize(await _load_goods(db, goods_id))


@router.delete("/{goods_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goods(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goods = await _load_goods(db, goods_id)
    if goods.seller_id != user.id:
        raise HTTPException(status_code=403, detail="只能删除自己的商品")
    # 级联删除收藏与图片
    await db.execute(delete(Favorite).where(Favorite.goods_id == goods.id))
    await db.delete(goods)
    await db.commit()