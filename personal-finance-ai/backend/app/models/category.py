from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    parent_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    type: Mapped[str] = mapped_column(String(20))
    icon: Mapped[str] = mapped_column(String(40), default="category")
    color: Mapped[str] = mapped_column(String(20), default="green")

    parent = relationship("Category", remote_side=[id])
    transactions = relationship("Transaction", back_populates="category")
