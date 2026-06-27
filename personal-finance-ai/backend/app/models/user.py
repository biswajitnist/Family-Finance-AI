from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    country: Mapped[str] = mapped_column(String(2), default="DE")
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Berlin")
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")
    tax_country: Mapped[str] = mapped_column(String(2), default="DE")
    date_format: Mapped[str] = mapped_column(String(30), default="DD-MM-YYYY")
    number_format: Mapped[str] = mapped_column(String(30), default="1.234,56")
    financial_year_start: Mapped[str] = mapped_column(String(5), default="01-01")
    default_portfolio_view: Mapped[str] = mapped_column(
        String(30), default="overview"
    )
    default_refresh_frequency: Mapped[str] = mapped_column(
        String(20), default="hourly"
    )
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    accounts = relationship("Account", back_populates="user")
    documents = relationship("Document", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
