"""快递代拿契约。"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.errand import ErrandStatus


class ErrandUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str | None = None


class ErrandCreate(BaseModel):
    pickup_location: str = Field(min_length=1, max_length=200)
    package_info: str = Field(min_length=1, max_length=200)
    dropoff_location: str = Field(min_length=1, max_length=200)
    reward: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    deadline: datetime | None = None
    remark: str | None = Field(default=None, max_length=500)
    contact: str | None = Field(default=None, max_length=100)


class ErrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    runner_id: int | None
    pickup_location: str
    package_info: str
    dropoff_location: str
    reward: Decimal
    deadline: datetime | None
    remark: str | None
    contact: str | None
    status: ErrandStatus
    created_at: datetime
    updated_at: datetime

    publisher: ErrandUserOut | None = None
    runner: ErrandUserOut | None = None


class ErrandStatusUpdate(BaseModel):
    status: ErrandStatus
