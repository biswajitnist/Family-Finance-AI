from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    user_id: int = 1
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=40)
    institution: str | None = None
    country: str = Field(default="DE", min_length=2, max_length=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    opening_balance: Decimal = Decimal("0")
    current_balance: Decimal = Decimal("0")
    notes: str | None = None
    is_active: bool = True


class AccountRead(AccountCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    institution: str | None = None
    country: str | None = None
    currency: str | None = None
    opening_balance: Decimal | None = None
    current_balance: Decimal | None = None
    notes: str | None = None
    is_active: bool | None = None
