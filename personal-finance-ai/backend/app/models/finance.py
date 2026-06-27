from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MonthlyBudget(Base):
    __tablename__ = "monthly_budgets"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "year", "month", "category_id", name="uq_monthly_budget"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    year: Mapped[int]
    month: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BudgetProposal(Base):
    __tablename__ = "budget_proposals"
    __table_args__ = (
        UniqueConstraint(
            "source_transaction_id",
            "year",
            "month",
            name="uq_recurring_budget_proposal",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1, index=True)
    source_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), index=True
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    year: Mapped[int] = mapped_column(index=True)
    month: Mapped[int] = mapped_column(index=True)
    merchant: Mapped[str] = mapped_column(String(180))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    recurrence_frequency: Mapped[str] = mapped_column(String(20))
    expected_date: Mapped[date] = mapped_column(Date)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    detection_source: Mapped[str] = mapped_column(String(20), default="detected")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    name: Mapped[str] = mapped_column(String(120))
    condition_type: Mapped[str] = mapped_column(String(30))
    condition_value: Mapped[str] = mapped_column(String(255))
    action_type: Mapped[str] = mapped_column(String(30), default="category")
    action_value: Mapped[str] = mapped_column(String(255))
    priority: Mapped[int] = mapped_column(default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Investment(Base):
    __tablename__ = "investments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    asset_name: Mapped[str] = mapped_column(String(160))
    asset_type: Mapped[str] = mapped_column(String(40))
    isin: Mapped[str | None] = mapped_column(String(20))
    ticker: Mapped[str | None] = mapped_column(String(30))
    provider_symbol: Mapped[str | None] = mapped_column(String(50))
    exchange: Mapped[str | None] = mapped_column(String(40))
    broker: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(2), default="DE")
    market_provider: Mapped[str | None] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0)
    average_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    purchase_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    native_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    current_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    market_currency: Mapped[str | None] = mapped_column(String(3))
    fx_rate_to_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    price_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    quote_status: Mapped[str | None] = mapped_column(String(30))
    market_price_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    market_data_source: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketPriceCache(Base):
    __tablename__ = "market_price_cache"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "provider",
            "interval",
            "quote_timestamp",
            name="uq_market_price_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="Finnhub")
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str | None] = mapped_column(String(3))
    interval: Mapped[str] = mapped_column(String(20), default="intraday", index=True)
    quote_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint(
            "from_currency",
            "to_currency",
            "rate_date",
            name="uq_fx_rate_pair_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_currency: Mapped[str] = mapped_column(String(3), index=True)
    to_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    provider: Mapped[str] = mapped_column(String(40))
    rate_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MarketDataPreference(Base):
    __tablename__ = "market_data_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1, unique=True)
    provider: Mapped[str] = mapped_column(String(40), default="Finnhub")
    refresh_interval: Mapped[str] = mapped_column(String(20), default="hourly")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(30), default="not_refreshed")
    last_error: Mapped[str | None] = mapped_column(Text)


class MarketDataProvider(Base):
    __tablename__ = "market_data_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    provider_type: Mapped[str] = mapped_column(String(40), default="Generic")
    base_url: Mapped[str | None] = mapped_column(String(500))
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    auth_method: Mapped[str] = mapped_column(String(40), default="None")
    api_key_parameter_name: Mapped[str | None] = mapped_column(String(80))
    api_key_header_name: Mapped[str | None] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(default=100)
    supported_asset_classes: Mapped[str | None] = mapped_column(Text)
    default_currency: Mapped[str | None] = mapped_column(String(3))
    default_exchange_code: Mapped[str | None] = mapped_column(String(30))
    symbol_format: Mapped[str | None] = mapped_column(String(120))
    test_symbol: Mapped[str | None] = mapped_column(String(80))
    timeout_seconds: Mapped[int] = mapped_column(default=10)
    retry_count: Mapped[int] = mapped_column(default=2)
    rate_limit_per_minute: Mapped[int | None] = mapped_column()
    last_test_status: Mapped[str | None] = mapped_column(String(30))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_refresh: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketDataRefreshLog(Base):
    __tablename__ = "market_data_refresh_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    refresh_batch_id: Mapped[str | None] = mapped_column(String(64), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("investments.id"))
    provider_name: Mapped[str | None] = mapped_column(String(80))
    requested_symbol: Mapped[str | None] = mapped_column(String(80))
    requested_exchange_code: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30))
    raw_currency: Mapped[str | None] = mapped_column(String(3))
    raw_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    fx_rate_to_base: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    price_base_currency: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    response_time_ms: Mapped[int | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_response_preview: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    symbol: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(160))
    asset_type: Mapped[str] = mapped_column(String(40), default="Stock")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    lender: Mapped[str] = mapped_column(String(160))
    direction: Mapped[str] = mapped_column(String(20), default="borrowed")
    loan_type: Mapped[str] = mapped_column(String(40), default="personal")
    original_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    current_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    interest_mode: Mapped[str] = mapped_column(String(20), default="manual")
    interest_calculation_basis: Mapped[str] = mapped_column(
        String(30), default="daily_balance"
    )
    interest_posting_frequency: Mapped[str] = mapped_column(
        String(20), default="manual"
    )
    payment_allocation_rule: Mapped[str] = mapped_column(
        String(30), default="interest_first"
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    locked_before: Mapped[date | None] = mapped_column(Date)
    lock_reason: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoanInterestRate(Base):
    __tablename__ = "loan_interest_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), index=True)
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LoanLedgerEntry(Base):
    __tablename__ = "loan_ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(220))
    entry_type: Mapped[str] = mapped_column(String(30), default="drawdown")
    direction: Mapped[str] = mapped_column(String(10), default="debit")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    signed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    running_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    principal_component: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    interest_component: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id"), index=True
    )
    mapping_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    unlock_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoanInterestCalculation(Base):
    __tablename__ = "loan_interest_calculations"

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    basis: Mapped[str] = mapped_column(String(30), default="daily_balance")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    preview_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="preview")
    posted_ledger_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("loan_ledger_entries.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LoanTransactionLink(Base):
    __tablename__ = "loan_transaction_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), index=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), index=True
    )
    ledger_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("loan_ledger_entries.id")
    )
    mapping_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LoanDocumentLink(Base):
    __tablename__ = "loan_document_links"
    __table_args__ = (
        UniqueConstraint("loan_id", "document_id", name="uq_loan_document_link"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(2), default="DE")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    current_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    monthly_rental_income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    monthly_costs: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    loan_id: Mapped[int | None] = mapped_column(ForeignKey("loans.id"))
    afa_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    land_share_percentage: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)


class RetirementAccount(Base):
    __tablename__ = "retirement_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str | None] = mapped_column(String(160))
    account_type: Mapped[str] = mapped_column(String(50), default="pension")
    country: Mapped[str] = mapped_column(String(2), default="DE")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    current_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    monthly_contribution: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0
    )
    employer_contribution: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0
    )
    projected_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    retirement_age: Mapped[int] = mapped_column(default=67)
    notes: Mapped[str | None] = mapped_column(Text)


class Insurance(Base):
    __tablename__ = "insurance_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    provider: Mapped[str] = mapped_column(String(160))
    policy_type: Mapped[str] = mapped_column(String(60))
    policy_number: Mapped[str | None] = mapped_column(String(100))
    coverage_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    premium_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    premium_frequency: Mapped[str] = mapped_column(String(20), default="monthly")
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    beneficiaries: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class InsuranceDocumentLink(Base):
    __tablename__ = "insurance_document_links"
    __table_args__ = (
        UniqueConstraint(
            "insurance_id",
            "document_id",
            name="uq_insurance_document_link",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    insurance_id: Mapped[int] = mapped_column(
        ForeignKey("insurance_policies.id"), index=True
    )
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    report_type: Mapped[str] = mapped_column(String(40))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    format: Mapped[str] = mapped_column(String(10))
    file_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CustomReport(Base):
    __tablename__ = "custom_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    data_source: Mapped[str] = mapped_column(String(80))
    chart_type: Mapped[str] = mapped_column(String(40))
    config_json: Mapped[str] = mapped_column(Text)
    dashboard_section: Mapped[str | None] = mapped_column(String(80))
    widget_size: Mapped[str | None] = mapped_column(String(20))
    widget_position: Mapped[int | None] = mapped_column(default=None)
    schedule_frequency: Mapped[str | None] = mapped_column(String(40))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AIDashboardInsight(Base):
    __tablename__ = "ai_dashboard_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    month: Mapped[str] = mapped_column(String(7), index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    summary_sentence_1: Mapped[str] = mapped_column(Text)
    summary_sentence_2: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    source_data_hash: Mapped[str] = mapped_column(String(64), index=True)
    local_ai_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FinancialForecast(Base):
    __tablename__ = "financial_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    month: Mapped[str] = mapped_column(String(7), index=True)
    expected_income: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_expenses: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_surplus: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_month_end_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    recurring_payment_impact: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    category_risks: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    month: Mapped[str] = mapped_column(String(7), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10))
    estimated_impact_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    recommendation_type: Mapped[str] = mapped_column(String(40))
    explanation: Mapped[str] = mapped_column(Text)
    related_data: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FinancialAlert(Base):
    __tablename__ = "financial_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=1)
    month: Mapped[str] = mapped_column(String(7), index=True)
    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    transaction_ids: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
