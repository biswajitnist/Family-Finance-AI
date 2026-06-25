from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MoneyModel(ORMModel):
    @field_validator("*", mode="before")
    @classmethod
    def empty_strings_to_none(cls, value: object) -> object:
        return None if value == "" else value


class RuleCreate(ORMModel):
    user_id: int = 1
    name: str = Field(min_length=1, max_length=120)
    condition_type: str = Field(
        pattern="^(vendor|keyword|amount_min|amount_max|account|iban|recurring)$"
    )
    condition_value: str = Field(min_length=1, max_length=255)
    action_type: str = Field(
        default="category", pattern="^(category|transaction_type)$"
    )
    action_value: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True


class RuleRead(RuleCreate):
    id: int
    created_at: datetime
    last_applied_at: datetime | None


class InvestmentCreate(MoneyModel):
    user_id: int = 1
    account_id: int | None = None
    source_document_id: int | None = None
    asset_name: str
    asset_type: str
    isin: str | None = None
    ticker: str | None = None
    provider_symbol: str | None = None
    exchange: str | None = None
    broker: str | None = None
    country: str = "DE"
    market_provider: str | None = None
    quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    currency: str = "EUR"
    purchase_currency: str = "EUR"
    base_currency: str = "EUR"
    native_value: Decimal | None = None
    current_value: Decimal = Decimal("0")


class InvestmentRead(InvestmentCreate):
    id: int
    market_price: Decimal | None = None
    market_currency: str | None = None
    fx_rate_to_eur: Decimal | None = None
    price_eur: Decimal | None = None
    quote_status: str | None = None
    market_price_updated_at: datetime | None = None
    market_data_source: str | None = None
    updated_at: datetime


class WatchlistCreate(ORMModel):
    user_id: int = 1
    symbol: str = Field(min_length=1, max_length=30)
    name: str | None = Field(default=None, max_length=160)
    asset_type: str = Field(default="Stock", max_length=40)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    notes: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class WatchlistRead(WatchlistCreate):
    id: int
    created_at: datetime


class MarketDataSettings(BaseModel):
    refresh_interval: str = Field(
        pattern="^(manual|15_minutes|30_minutes|hourly|daily)$"
    )


class MarketDataCredential(BaseModel):
    provider: str = Field(default="finnhub", pattern="^(finnhub|twelve_data)$")
    api_key: str = Field(min_length=16, max_length=200)

    @field_validator("api_key")
    @classmethod
    def clean_api_key(cls, value: str) -> str:
        return value.strip()


class MarketDataProviderCreate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=80)
    provider_type: str = "Generic"
    base_url: str | None = None
    api_key: str | None = Field(default=None, max_length=500)
    auth_method: str = "None"
    api_key_parameter_name: str | None = None
    api_key_header_name: str | None = None
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=10000)
    supported_asset_classes: str | None = None
    default_currency: str | None = None
    default_exchange_code: str | None = None
    symbol_format: str | None = None
    test_symbol: str | None = None
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    retry_count: int = Field(default=2, ge=0, le=5)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    notes: str | None = None


class MarketDataProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_name: str
    provider_type: str
    base_url: str | None
    auth_method: str
    api_key_parameter_name: str | None
    api_key_header_name: str | None
    api_key_masked: str | None = None
    has_api_key: bool = False
    enabled: bool
    priority: int
    supported_asset_classes: str | None
    default_currency: str | None
    default_exchange_code: str | None
    symbol_format: str | None
    test_symbol: str | None
    timeout_seconds: int
    retry_count: int
    rate_limit_per_minute: int | None
    last_test_status: str | None
    last_tested_at: datetime | None
    last_successful_refresh: datetime | None
    last_error: str | None
    notes: str | None


class LoanCreate(MoneyModel):
    user_id: int = 1
    account_id: int | None = None
    lender: str
    loan_type: str = "personal"
    original_amount: Decimal
    current_balance: Decimal
    interest_rate: Decimal = Decimal("0")
    monthly_payment: Decimal = Decimal("0")
    currency: str = "EUR"
    start_date: date | None = None
    end_date: date | None = None


class LoanRead(LoanCreate):
    id: int
    recorded_balance: Decimal | None = None
    payments_applied: Decimal = Decimal("0")
    matched_transaction_count: int = 0


class LoanPaymentRead(ORMModel):
    id: int
    transaction_date: date
    vendor: str
    description: str
    reference_number: str | None = None
    amount: Decimal
    currency: str
    applied_amount: Decimal
    applied_currency: str
    is_validated: bool


class PropertyCreate(MoneyModel):
    user_id: int = 1
    name: str
    address: str | None = None
    country: str = "DE"
    currency: str = "EUR"
    purchase_price: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")
    monthly_rental_income: Decimal = Decimal("0")
    monthly_costs: Decimal = Decimal("0")
    loan_id: int | None = None
    afa_rate: Decimal = Decimal("0")
    land_share_percentage: Decimal = Decimal("0")


class PropertyRead(PropertyCreate):
    id: int


class RetirementCreate(MoneyModel):
    user_id: int = 1
    name: str
    provider: str | None = None
    account_type: str = "pension"
    country: str = "DE"
    currency: str = "EUR"
    current_value: Decimal = Decimal("0")
    monthly_contribution: Decimal = Decimal("0")
    employer_contribution: Decimal = Decimal("0")
    projected_value: Decimal = Decimal("0")
    retirement_age: int = Field(default=67, ge=40, le=100)
    notes: str | None = None


class RetirementRead(RetirementCreate):
    id: int


class InsuranceCreate(MoneyModel):
    user_id: int = 1
    provider: str
    policy_type: str
    policy_number: str | None = None
    coverage_amount: Decimal = Decimal("0")
    premium_amount: Decimal = Decimal("0")
    premium_frequency: str = "monthly"
    currency: str = "EUR"
    start_date: date | None = None
    end_date: date | None = None
    beneficiaries: str | None = None
    notes: str | None = None
    is_active: bool = True


class InsuranceRead(InsuranceCreate):
    id: int


class InsurancePaymentRead(ORMModel):
    id: int
    transaction_date: date
    vendor: str
    description: str
    reference_number: str | None = None
    amount: Decimal
    currency: str
    applied_amount: Decimal
    applied_currency: str
    is_validated: bool


class MonthlyBudgetCreate(MoneyModel):
    user_id: int = 1
    category_id: int | None = None
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    notes: str | None = None


class MonthlyBudgetRead(MonthlyBudgetCreate):
    id: int
    created_at: datetime


class BudgetProposalRead(ORMModel):
    id: int
    source_transaction_id: int
    category_id: int | None
    year: int
    month: int
    merchant: str
    amount: Decimal
    currency: str
    recurrence_frequency: str
    expected_date: date
    confidence: Decimal | None
    detection_source: str
    status: str
    created_at: datetime
    confirmed_at: datetime | None


class BudgetCategorySummary(BaseModel):
    budget_id: int
    category_id: int | None
    category: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    percentage: Decimal


class MonthlyBudgetSummary(BaseModel):
    year: int
    month: int
    currency: str
    total_budget: Decimal
    spent: Decimal
    remaining: Decimal
    percentage: Decimal
    categories: list[BudgetCategorySummary]


class ReportRequest(BaseModel):
    report_type: str = Field(
        pattern="^(monthly|yearly|tax|investment|debt|property|protection)$"
    )
    period_start: date
    period_end: date
    format: str = Field(default="pdf", pattern="^(pdf|xlsx|csv)$")


class ReportPeriodRequest(BaseModel):
    period_start: date
    period_end: date
    format: str = Field(default="pdf", pattern="^(pdf|xlsx|csv)$")


class ReportRead(ORMModel):
    id: int
    user_id: int
    report_type: str
    period_start: date
    period_end: date
    format: str
    created_at: datetime


class CashFlowCategory(BaseModel):
    category: str
    amount: Decimal


class CashFlowDay(BaseModel):
    day: int
    current_income: Decimal
    current_expense: Decimal
    current_cash_flow: Decimal
    previous_income: Decimal
    previous_expense: Decimal
    previous_cash_flow: Decimal


class CashFlowMonthTotals(BaseModel):
    income: Decimal
    expense: Decimal
    cash_flow: Decimal


class CashFlowComparison(BaseModel):
    currency: str
    current_month: str
    previous_month: str
    current: CashFlowMonthTotals
    previous: CashFlowMonthTotals
    expense_categories: list[CashFlowCategory]
    income_categories: list[CashFlowCategory]
    daily: list[CashFlowDay]


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class ChatResponse(BaseModel):
    answer: str
    calculation_basis: str
    sources: list[dict]
    confidence: float
    missing_data_warning: str | None = None
    local_ai_used: bool = False


class HelpAgentRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


class HelpAgentResponse(BaseModel):
    intent: str = Field(
        pattern=(
            "^(app_help|finance_query|document_query|report_request|troubleshooting)$"
        )
    )
    answer: str
    source_basis: list[str]
    sources: list[dict]
    missing_data: list[str]
    local_ai_used: bool
    report: dict | None = None
