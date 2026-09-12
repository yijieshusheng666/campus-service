"""二手商品模型 + 商品图片。"""
import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GoodsStatus(str, enum.Enum):
    on_sale = "on_sale"      # 在售
    sold = "sold"            # 已售
    off_shelf = "off_shelf"  # 下架


class Goods(Base):
    __tablename__ = "goods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, default="其他")
    condition: Mapped[str] = mapped_column(String(30), default="九成新")
    contact: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 联系方式
    status: Mapped[GoodsStatus] = mapped_column(Enum(GoodsStatus), default=GoodsStatus.on_sale, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    seller: Mapped["User"] = relationship(back_populates="goods", lazy="joined")
    images: Mapped[list["GoodsImage"]] = relationship(
        back_populates="goods", cascade="all, delete-orphan", order_by="GoodsImage.sort"
    )

    @property
    def cover(self) -> str | None:
        """首图 URL，供私信商品卡片等「只需要一张缩略图」的场景使用。

        注意：images 是懒加载关系，async 上下文里若未 eager load 就访问会抛
        MissingGreenlet —— 调用方需 joinedload/selectinload 预加载（见 api/messages.py）。
        """
        return self.images[0].url if self.images else None


class GoodsImage(Base):
    __tablename__ = "goods_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goods_id: Mapped[int] = mapped_column(ForeignKey("goods.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    sort: Mapped[int] = mapped_column(default=0)

    goods: Mapped["Goods"] = relationship(back_populates="images")