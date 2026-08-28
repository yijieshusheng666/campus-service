"""API 路由包。"""
from fastapi import APIRouter

from app.api import auth, errands, favorites, goods, interviews, messages, orders, resumes, support, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(goods.router)
api_router.include_router(favorites.router)
api_router.include_router(resumes.router)
api_router.include_router(orders.router)
api_router.include_router(interviews.router)
api_router.include_router(errands.router)
api_router.include_router(messages.router)
api_router.include_router(support.router)
