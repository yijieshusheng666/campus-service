"""快递代拿 API：发布、大厅/我的列表、接单（原子更新防并发抢单）、状态流转。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.errand import Errand, ErrandStatus
from app.models.user import User
from app.schemas.errand import ErrandCreate, ErrandOut, ErrandStatusUpdate

router = APIRouter(prefix="/errands", tags=["快递代拿"])

# 角色视图：状态流转规则
# pending -> accepted(runner接单) -> delivered(runner送达) -> completed(发布者结算)
# pending -> cancelled(发布者取消)


async def _load_errand(db: AsyncSession, errand_id: int) -> Errand:
    # populate_existing：强制刷新 identity map 中已缓存对象的属性与关系（接单后重载 runner）
    errand = (
        await db.execute(
            select(Errand)
            .options(selectinload(Errand.publisher), selectinload(Errand.runner))
            .where(Errand.id == errand_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not errand:
        raise HTTPException(status_code=404, detail="代拿需求不存在")
    return errand


# ---- 发布 ----
@router.post("", response_model=ErrandOut, status_code=status.HTTP_201_CREATED)
async def create_errand(
    payload: ErrandCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    errand = Errand(
        user_id=user.id,
        pickup_location=payload.pickup_location.strip(),
        package_info=payload.package_info.strip(),
        dropoff_location=payload.dropoff_location.strip(),
        reward=payload.reward,
        deadline=payload.deadline,
        remark=payload.remark,
        contact=payload.contact or user.username,
        status=ErrandStatus.pending,
    )
    db.add(errand)
    await db.commit()
    return await _load_errand(db, errand.id)


# ---- 列表：大厅(all) / 我发布的(published) / 我接的(accepted) ----
@router.get("", response_model=list[ErrandOut])
async def list_errands(
    role: str = "all",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Errand).options(
        selectinload(Errand.publisher), selectinload(Errand.runner)
    )
    if role == "published":
        stmt = stmt.where(Errand.user_id == user.id)
    elif role == "accepted":
        stmt = stmt.where(Errand.runner_id == user.id)
    else:
        # 大厅只展示待接单且非自己发布的需求
        stmt = stmt.where(
            Errand.status == ErrandStatus.pending, Errand.user_id != user.id
        )
    stmt = stmt.order_by(Errand.id.desc())
    errands = list((await db.execute(stmt)).scalars().all())
    return errands


# ---- 详情 ----
@router.get("/{errand_id}", response_model=ErrandOut)
async def get_errand(
    errand_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    errand = await _load_errand(db, errand_id)
    # 取件码属于隐私信息：仅发布者与接单者可见
    is_involved = errand.user_id == user.id or errand.runner_id == user.id
    if not is_involved and errand.status != ErrandStatus.pending:
        raise HTTPException(status_code=403, detail="无权查看该代拿需求")
    return errand


# ---- 接单（原子条件更新：并发抢单只有一个成功，MySQL 上等效行锁）----
@router.put("/{errand_id}/accept", response_model=ErrandOut)
async def accept_errand(
    errand_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    errand = await db.get(Errand, errand_id)
    if not errand:
        raise HTTPException(status_code=404, detail="代拿需求不存在")
    if errand.user_id == user.id:
        raise HTTPException(status_code=400, detail="不能接自己发布的需求")

    # 单语句原子更新：WHERE status=pending 保证并发下只有一个事务能改到行，
    # 其余事务 rowcount=0（MySQL 下 UPDATE 本身持有行锁，与订单防超卖同款思路）
    result = await db.execute(
        update(Errand)
        .where(Errand.id == errand_id, Errand.status == ErrandStatus.pending)
        .values(runner_id=user.id, status=ErrandStatus.accepted)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=400, detail="手慢了，该需求已被接单")
    await db.commit()
    return await _load_errand(db, errand_id)


# ---- 状态流转：delivered(runner) / completed(发布者) / cancelled(发布者，仅 pending) ----
@router.put("/{errand_id}/status", response_model=ErrandOut)
async def update_errand_status(
    errand_id: int,
    payload: ErrandStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    errand = (
        await db.execute(
            select(Errand).where(Errand.id == errand_id).with_for_update()
        )
    ).scalar_one_or_none()
    if not errand:
        raise HTTPException(status_code=404, detail="代拿需求不存在")
    new_status = payload.status

    if new_status == ErrandStatus.delivered:
        # 跑腿员送达（accepted -> delivered）
        if errand.runner_id != user.id:
            raise HTTPException(status_code=403, detail="只有接单人可以确认送达")
        if errand.status != ErrandStatus.accepted:
            raise HTTPException(status_code=400, detail="当前状态不可确认送达")
    elif new_status == ErrandStatus.completed:
        # 发布者确认结算（delivered -> completed）
        if errand.user_id != user.id:
            raise HTTPException(status_code=403, detail="只有发布人可以确认结算")
        if errand.status != ErrandStatus.delivered:
            raise HTTPException(status_code=400, detail="当前状态不可结算")
    elif new_status == ErrandStatus.cancelled:
        # 发布者取消（仅 pending）
        if errand.user_id != user.id:
            raise HTTPException(status_code=403, detail="只有发布人可以取消")
        if errand.status != ErrandStatus.pending:
            raise HTTPException(status_code=400, detail="需求已被接单，无法取消")
    else:
        raise HTTPException(status_code=400, detail="不支持的状态")

    errand.status = new_status
    await db.commit()
    return await _load_errand(db, errand_id)
