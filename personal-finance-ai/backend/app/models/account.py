from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(40))
    institution: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), default="DE")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
    documents = relationship("Document", back_populates="source_account")
