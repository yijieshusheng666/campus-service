"""二手商品契约。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.goods import GoodsStatus


class GoodsImageOut(BaseModel):
    id: int
    url: str

    model_config = {"from_attributes": True}


class GoodsCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    price: Decimal = Field(gt=0, le=Decimal("99999999.99"))
    category: str = "其他"
    condition: str = "九成新"
    contact: str | None = None
    image_urls: list[str] = Field(default_factory=list)


class GoodsUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, le=Decimal("99999999.99"))
    category: str | None = None
    condition: str | None = None
    contact: str | None = None
    status: GoodsStatus | None = None
    image_urls: list[str] | None = None


class GoodsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    price: Decimal
    category: str
    condition: str
    contact: str | None
    status: GoodsStatus
    created_at: datetime
    seller_id: int | None = None
    seller_name: str = ""
    images: list[GoodsImageOut] = Field(default_factory=list)
    is_favorited: bool = False