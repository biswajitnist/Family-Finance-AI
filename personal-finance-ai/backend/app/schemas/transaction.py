from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RECURRENCE_PATTERN = "^(weekly|biweekly|monthly|quarterly|semiannual|yearly)$"


class TransactionCreate(BaseModel):
    user_id: int = 1
    account_id: int
    transaction_date: date
    booking_date: date | None = None
    vendor: str = Field(min_length=1, max_length=180)
    description: str = ""
    amount: Decimal
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    transaction_type: str = Field(pattern="^(debit|credit)$")
    category_id: int | None = None
    reference_number: str | None = None
    payment_method: str | None = None
    iban: str | None = None
    is_validated: bool = True
    recurrence_frequency: str | None = Field(
        default=None, pattern=RECURRENCE_PATTERN
    )
    linked_loan_id: int | None = None
    loan_ledger_type: str | None = None
    loan_balance_effect: str | None = None
    loan_principal_component: Decimal | None = None
    loan_interest_component: Decimal | None = None
    loan_mapping_confidence: Decimal | None = None
    loan_user_confirmed: bool = False

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value.quantize(Decimal("0.01"))


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    transaction_date: date | None = None
    booking_date: date | None = None
    vendor: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    transaction_type: str | None = Field(default=None, pattern="^(debit|credit)$")
    category_id: int | None = None
    reference_number: str | None = None
    is_validated: bool | None = None
    is_duplicate: bool | None = None
    payment_method: str | None = None
    iban: str | None = None
    recurrence_frequency: str | None = Field(
        default=None, pattern=RECURRENCE_PATTERN
    )
    linked_loan_id: int | None = None
    loan_ledger_type: str | None = None
    loan_balance_effect: str | None = None
    loan_principal_component: Decimal | None = None
    loan_interest_component: Decimal | None = None
    loan_mapping_confidence: Decimal | None = None
    loan_user_confirmed: bool | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("amount must be greater than zero")
        return value.quantize(Decimal("0.01")) if value is not None else None


class TransactionRead(BaseModel):
    id: int
    user_id: int
    account_id: int
    document_id: int | None
    transaction_date: date
    booking_date: date | None
    vendor: str
    description: str
    original_description: str
    amount: Decimal
    currency: str
    transaction_type: str
    category_id: int | None
    reference_number: str | None
    payment_method: str | None
    iban: str | None
    confidence: Decimal | None
    classification_source: str
    recurrence_frequency: str | None
    recurrence_confidence: Decimal | None
    recurrence_source: str | None
    recurrence_group_key: str | None
    next_expected_date: date | None
    edited_fields: str | None
    linked_loan_id: int | None
    loan_ledger_type: str | None
    loan_balance_effect: str | None
    loan_principal_component: Decimal | None
    loan_interest_component: Decimal | None
    loan_mapping_confidence: Decimal | None
    loan_user_confirmed: bool
    is_validated: bool
    is_duplicate: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionWithBaseRead(TransactionRead):
    base_amount: Decimal | None = None
    base_currency: str = "EUR"
    fx_rate_missing: bool = False


class ValidationRequest(BaseModel):
    transaction_ids: list[int] = Field(min_length=1)
    is_validated: bool = True
