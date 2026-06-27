from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    booking_date: Mapped[date | None] = mapped_column(Date)
    vendor: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    original_description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    transaction_type: Mapped[str] = mapped_column(String(10))
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
    reference_number: Mapped[str | None] = mapped_column(String(120))
    payment_method: Mapped[str | None] = mapped_column(String(40))
    iban: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    classification_source: Mapped[str] = mapped_column(String(20), default="manual")
    recurrence_frequency: Mapped[str | None] = mapped_column(String(20), index=True)
    recurrence_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    recurrence_source: Mapped[str | None] = mapped_column(String(20))
    recurrence_group_key: Mapped[str | None] = mapped_column(String(220), index=True)
    next_expected_date: Mapped[date | None] = mapped_column(Date)
    edited_fields: Mapped[str | None] = mapped_column(Text)
    linked_loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id"))
    loan_ledger_type: Mapped[str | None] = mapped_column(String(30))
    loan_balance_effect: Mapped[str | None] = mapped_column(String(10))
    loan_principal_component: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2)
    )
    loan_interest_component: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    loan_mapping_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    loan_user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    document = relationship("Document", back_populates="transactions")
