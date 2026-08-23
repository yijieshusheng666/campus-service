"""收藏 API：收藏/取消收藏、我的收藏列表。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.favorite import Favorite
from app.models.goods import Goods
from app.models.user import User
from app.schemas.goods import GoodsOut

router = APIRouter(prefix="/favorites", tags=["收藏"])


@router.post("/{goods_id}", status_code=status.HTTP_200_OK)
async def add_favorite(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goods = (await db.execute(select(Goods).where(Goods.id == goods_id))).scalar_one_or_none()
    if not goods:
        raise HTTPException(status_code=404, detail="商品不存在")
    exists = (
        await db.execute(
            select(Favorite.id).where(Favorite.user_id == user.id, Favorite.goods_id == goods_id)
        )
    ).scalar_one_or_none()
    if not exists:
        db.add(Favorite(user_id=user.id, goods_id=goods_id))
        await db.commit()
    return {"message": "收藏成功"}


@router.delete("/{goods_id}", status_code=status.HTTP_200_OK)
async def remove_favorite(
    goods_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fav = (
        await db.execute(
            select(Favorite).where(Favorite.user_id == user.id, Favorite.goods_id == goods_id)
        )
    ).scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()
    return {"message": "已取消收藏"}


@router.get("", response_model=list[GoodsOut])
async def my_favorites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Favorite)
        .options(selectinload(Favorite.goods).selectinload(Goods.images),
                 selectinload(Favorite.goods).selectinload(Goods.seller))
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.id.desc())
    )
    favorites = list((await db.execute(stmt)).scalars().all())

    from app.api.goods import _serialize
    # 收藏列表里的商品天然处于已收藏状态，直接置位，避免逐条回查数据库
    return [_serialize(fav.goods, is_favorited=True) for fav in favorites]