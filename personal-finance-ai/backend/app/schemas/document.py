from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DocumentRead(BaseModel):
    id: int
    file_name: str
    file_type: str
    document_type: str
    source_account_id: int | None
    status: str
    validation_status: str
    processing_stage: str
    processing_progress: int
    processing_message: str | None
    processing_error: str | None
    processed_at: datetime | None
    page_count: int | None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentDetail(DocumentRead):
    extracted_text: str | None


class ProcessResult(BaseModel):
    document_id: int
    status: str
    extracted_characters: int
    transactions_created: int
    investments_created: int = 0
    record_type: str = "transaction"
    message: str
    used_ocr: bool = False
    ocr_confidence: float | None = None
    statement_set_id: int | None = None


class BatchProcessRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1)
    force_ocr: bool = False
    use_local_ai: bool = True


class BatchProcessItem(BaseModel):
    document_id: int
    file_name: str
    status: str
    transactions_created: int = 0
    investments_created: int = 0
    record_type: str = "transaction"
    message: str


class BatchProcessResult(BaseModel):
    requested: int
    completed: int
    failed: int
    transactions_created: int
    investments_created: int
    statement_set_id: int
    results: list[BatchProcessItem]


class StatementSetCreate(BaseModel):
    document_ids: list[int] = Field(min_length=1)
    name: str | None = None


class StatementCheckpointUpdate(BaseModel):
    expected_transaction_count: int | None = Field(default=None, ge=0)
    expected_debit_total: Decimal | None = Field(default=None, ge=0)
    expected_credit_total: Decimal | None = Field(default=None, ge=0)


class CandidateUpdate(BaseModel):
    transaction_date: date | None = None
    vendor: str | None = Field(default=None, max_length=180)
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    transaction_type: str | None = Field(
        default=None, pattern="^(debit|credit)$"
    )
    resolution: str | None = Field(
        default=None,
        pattern="^(accepted|not_transaction|overlap_confirmed|duplicate_rejected)$",
    )


class OCRLineRead(BaseModel):
    id: int
    document_id: int
    page_number: int
    line_number: int
    raw_text: str
    confidence: Decimal | None
    bbox: list[float] | None = None


class CandidateDuplicateMatchRead(BaseModel):
    id: int
    transaction_date: date
    vendor: str
    description: str
    amount: Decimal
    currency: str
    transaction_type: str
    category: str | None = None
    account: str | None = None
    merchant_similarity: float


class CandidateRead(BaseModel):
    id: int
    document_id: int
    source_line_id: int | None
    transaction_id: int | None
    status: str
    resolution: str | None
    skip_reason: str | None
    raw_text: str
    transaction_date: str | None
    vendor: str | None
    amount: Decimal | None
    currency: str | None
    transaction_type: str | None
    field_confidence: dict[str, float]
    warnings: list[str]
    duplicate_matches: list[CandidateDuplicateMatchRead] = Field(default_factory=list)
    source_line: OCRLineRead | None = None


class StatementDocumentRead(BaseModel):
    id: int
    file_name: str
    file_type: str
    sequence: int
    preview_url: str
    page_count: int | None = None


class StatementAuditRead(BaseModel):
    id: int
    name: str
    status: str
    completeness_status: str
    expected_transaction_count: int | None
    expected_debit_total: Decimal | None
    expected_credit_total: Decimal | None
    detected_opening_balance: Decimal | None
    detected_closing_balance: Decimal | None
    candidate_count: int
    extracted_count: int
    skipped_count: int
    overlap_count: int
    low_confidence_count: int
    debit_total: Decimal
    credit_total: Decimal
    reconciliation_difference: Decimal | None
    confirmation_blockers: list[str]
    can_confirm: bool
    documents: list[StatementDocumentRead]
    candidates: list[CandidateRead]
