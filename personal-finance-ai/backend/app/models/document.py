from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(40))
    document_type: Mapped[str] = mapped_column(String(60), default="other")
    source_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="uploaded")
    validation_status: Mapped[str] = mapped_column(String(30), default="not_reviewed")
    processing_stage: Mapped[str] = mapped_column(String(40), default="uploaded")
    processing_progress: Mapped[int] = mapped_column(Integer, default=0)
    processing_message: Mapped[str | None] = mapped_column(Text)
    processing_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_count: Mapped[int | None]
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="documents")
    source_account = relationship("Account", back_populates="documents")
    transactions = relationship("Transaction", back_populates="document")
