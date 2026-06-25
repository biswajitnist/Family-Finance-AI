from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StatementSet(Base):
    __tablename__ = "statement_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    completeness_status: Mapped[str] = mapped_column(
        String(30), default="unverified", index=True
    )
    expected_transaction_count: Mapped[int | None] = mapped_column(Integer)
    expected_debit_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    expected_credit_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    detected_opening_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    detected_closing_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    candidate_count: Mapped[int] = mapped_column(default=0)
    extracted_count: Mapped[int] = mapped_column(default=0)
    skipped_count: Mapped[int] = mapped_column(default=0)
    overlap_count: Mapped[int] = mapped_column(default=0)
    low_confidence_count: Mapped[int] = mapped_column(default=0)
    debit_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    credit_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    reconciliation_difference: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2)
    )
    confirmation_blockers: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StatementSetDocument(Base):
    __tablename__ = "statement_set_documents"
    __table_args__ = (
        UniqueConstraint(
            "statement_set_id", "document_id", name="uq_statement_set_document"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_set_id: Mapped[int] = mapped_column(
        ForeignKey("statement_sets.id"), index=True
    )
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    sequence: Mapped[int] = mapped_column(default=0)


class DocumentOCRLine(Base):
    __tablename__ = "document_ocr_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_set_id: Mapped[int] = mapped_column(
        ForeignKey("statement_sets.id"), index=True
    )
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(default=1)
    line_number: Mapped[int] = mapped_column(default=1)
    raw_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    bbox_json: Mapped[str | None] = mapped_column(Text)


class ExtractionCandidate(Base):
    __tablename__ = "extraction_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement_set_id: Mapped[int] = mapped_column(
        ForeignKey("statement_sets.id"), index=True
    )
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    source_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_ocr_lines.id"), index=True
    )
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), index=True)
    resolution: Mapped[str | None] = mapped_column(String(40))
    skip_reason: Mapped[str | None] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    transaction_date: Mapped[str | None] = mapped_column(String(20))
    vendor: Mapped[str | None] = mapped_column(String(180))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    transaction_type: Mapped[str | None] = mapped_column(String(10))
    field_confidence_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
