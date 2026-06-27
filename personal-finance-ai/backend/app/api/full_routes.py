import shutil
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path

import fitz
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.models.category import Category
from app.models.document import Document
from app.models.finance import (
    CustomReport,
    Insurance,
    InsuranceDocumentLink,
    Investment,
    Loan,
    LoanDocumentLink,
    LoanInterestRate,
    LoanLedgerEntry,
    MarketDataProvider,
    Property,
    Report,
    RetirementAccount,
    Rule,
    WatchlistItem,
)
from app.models.transaction import Transaction
from app.schemas.custom_report import (
    AIAssistedReportRequest,
    CustomReportCreate,
    CustomReportRead,
    DashboardWidgetRequest,
    ReportMetadata,
    ReportPreviewRequest,
    ReportResult,
    ReportScheduleRequest,
)
from app.schemas.document import (
    BatchProcessRequest,
    BatchProcessResult,
    CandidateUpdate,
    DocumentDetail,
    DocumentRead,
    ProcessResult,
    StatementAuditRead,
    StatementCheckpointUpdate,
)
from app.schemas.finance import (
    CashFlowComparison,
    ChatRequest,
    ChatResponse,
    HelpAgentRequest,
    HelpAgentResponse,
    InsuranceCreate,
    InsurancePaymentRead,
    InsuranceRead,
    InvestmentCreate,
    InvestmentRead,
    LoanCreate,
    LoanInterestCalculationRead,
    LoanInterestCalculationRequest,
    LoanInterestRateCreate,
    LoanInterestRateRead,
    LoanLedgerEntryCreate,
    LoanLedgerEntryRead,
    LoanPaymentRead,
    LoanRead,
    LoanSettingsUpdate,
    LoanYearSummary,
    MarketDataCredential,
    MarketDataProviderCreate,
    MarketDataProviderRead,
    MarketDataSettings,
    PropertyCreate,
    PropertyRead,
    ReportPeriodRequest,
    ReportRead,
    ReportRequest,
    RetirementCreate,
    RetirementRead,
    RuleCreate,
    RuleRead,
    WatchlistCreate,
    WatchlistRead,
)
from app.schemas.transaction import TransactionRead
from app.services.ai_service import classify_transaction, ollama_status
from app.services.analytics import (
    debt_analytics,
    investment_analytics,
    net_worth_projection,
    property_analytics,
    protection_analytics,
)
from app.services.chat_service import answer_finance_question
from app.services.custom_report_service import report_metadata, run_report
from app.services.document_processor import (
    delete_document_files,
    process_document,
    store_document,
)
from app.services.help_agent import run_help_agent
from app.services.insurance_payment_service import insurance_transaction_assignments
from app.services.loan_balance_service import (
    calculate_accrued_interest,
    interest_summary_as_of,
    loan_ledger_entries,
    loan_rate_changes,
    loan_read,
    post_interest_calculation,
    recalculate_loan_ledger,
)
from app.services.market_data_service import (
    investment_values_in_base,
    market_data_status,
    refresh_market_data,
    save_market_api_key,
    update_market_settings,
)
from app.services.merchant_learning import apply_merchant_history
from app.services.ocr_service import ocr_status
from app.services.provider_config_service import (
    encrypt_api_key,
    provider_read,
    test_provider,
)
from app.services.report_service import cash_flow_comparison, generate_report
from app.services.rule_engine import apply_all_rules, apply_rules_to_transaction
from app.services.statement_audit import (
    confirm_statement_set,
    create_statement_set,
    latest_audit_for_document,
    serialize_audit,
    update_candidate,
    update_checkpoint,
)

router = APIRouter()


def _validated_rule_payload(db: Session, payload: RuleCreate) -> RuleCreate:
    if payload.action_type == "category":
        category = db.scalar(
            select(Category).where(
                func.lower(Category.name) == payload.action_value.casefold()
            )
        )
        if category is None:
            raise HTTPException(
                422,
                "Select an existing category before saving the rule.",
            )
        return payload.model_copy(update={"action_value": category.name})
    if payload.action_value not in {"credit", "debit"}:
        raise HTTPException(
            422,
            "Transaction type rules must use credit or debit.",
        )
    return payload


def _list(db: Session, model: type) -> list:
    return list(db.scalars(select(model).order_by(model.id.desc())).all())


def _create(db: Session, model: type, payload: object) -> object:
    item = model(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _update(db: Session, model: type, item_id: int, payload: object) -> object:
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Record not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


def insurance_read(db: Session, policy: Insurance) -> dict:
    linked_documents = list(
        db.scalars(
            select(Document)
            .join(
                InsuranceDocumentLink,
                InsuranceDocumentLink.document_id == Document.id,
            )
            .where(InsuranceDocumentLink.insurance_id == policy.id)
            .order_by(Document.uploaded_at.desc(), Document.id.desc())
        ).all()
    )
    data = {
        column.name: getattr(policy, column.name)
        for column in Insurance.__table__.columns
    }
    data["documents"] = linked_documents
    return data


def _delete(db: Session, model: type, item_id: int) -> None:
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Record not found")
    db.delete(item)
    db.commit()


@router.get("/analytics/investments")
def get_investment_analytics(db: Session = Depends(get_db)) -> dict:
    return investment_analytics(db)


@router.get("/analytics/debt")
def get_debt_analytics(db: Session = Depends(get_db)) -> dict:
    return debt_analytics(db)


@router.get("/analytics/properties")
def get_property_analytics(db: Session = Depends(get_db)) -> dict:
    return property_analytics(db)


@router.get("/analytics/protection")
def get_protection_analytics(db: Session = Depends(get_db)) -> dict:
    return protection_analytics(db)


@router.get("/analytics/net-worth-projection")
def get_net_worth_projection(db: Session = Depends(get_db)) -> dict:
    return net_worth_projection(db)


@router.get("/rules", response_model=list[RuleRead])
def list_rules(db: Session = Depends(get_db)) -> list[Rule]:
    return _list(db, Rule)


@router.post("/rules", response_model=RuleRead, status_code=201)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)) -> Rule:
    return _create(db, Rule, _validated_rule_payload(db, payload))


@router.put("/rules/{item_id}", response_model=RuleRead)
def update_rule(
    item_id: int, payload: RuleCreate, db: Session = Depends(get_db)
) -> Rule:
    return _update(db, Rule, item_id, _validated_rule_payload(db, payload))


@router.delete("/rules/{item_id}", status_code=204)
def delete_rule(item_id: int, db: Session = Depends(get_db)) -> None:
    _delete(db, Rule, item_id)


@router.post("/rules/apply")
def apply_rules(db: Session = Depends(get_db)) -> dict[str, int]:
    return {"updated": apply_all_rules(db)}


@router.get("/investments", response_model=list[InvestmentRead])
def list_investments(db: Session = Depends(get_db)) -> list[Investment]:
    return _list(db, Investment)


@router.post("/investments", response_model=InvestmentRead, status_code=201)
def create_investment(
    payload: InvestmentCreate, db: Session = Depends(get_db)
) -> Investment:
    values = investment_values_in_base(db, payload.model_dump())
    return _create(db, Investment, InvestmentCreate(**values))


@router.put("/investments/{item_id}", response_model=InvestmentRead)
def update_investment(
    item_id: int, payload: InvestmentCreate, db: Session = Depends(get_db)
) -> Investment:
    values = investment_values_in_base(db, payload.model_dump())
    return _update(db, Investment, item_id, InvestmentCreate(**values))


@router.delete("/investments/{item_id}", status_code=204)
def delete_investment(item_id: int, db: Session = Depends(get_db)) -> None:
    _delete(db, Investment, item_id)


@router.get("/watchlist", response_model=list[WatchlistRead])
def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItem]:
    return _list(db, WatchlistItem)


@router.post("/watchlist", response_model=WatchlistRead, status_code=201)
def create_watchlist_item(
    payload: WatchlistCreate, db: Session = Depends(get_db)
) -> WatchlistItem:
    return _create(db, WatchlistItem, payload)


@router.put("/watchlist/{item_id}", response_model=WatchlistRead)
def update_watchlist_item(
    item_id: int, payload: WatchlistCreate, db: Session = Depends(get_db)
) -> WatchlistItem:
    return _update(db, WatchlistItem, item_id, payload)


@router.delete("/watchlist/{item_id}", status_code=204)
def delete_watchlist_item(item_id: int, db: Session = Depends(get_db)) -> None:
    _delete(db, WatchlistItem, item_id)


@router.get("/market-data/status")
def get_market_data_status(db: Session = Depends(get_db)) -> dict:
    return market_data_status(db)


@router.post("/market-data/refresh")
def refresh_market_prices(db: Session = Depends(get_db)) -> dict:
    return refresh_market_data(db)


@router.put("/market-data/settings")
def set_market_data_settings(
    payload: MarketDataSettings, db: Session = Depends(get_db)
) -> dict:
    return update_market_settings(db, payload.refresh_interval)


@router.put("/market-data/credentials")
def set_market_data_credentials(
    payload: MarketDataCredential, db: Session = Depends(get_db)
) -> dict:
    try:
        save_market_api_key(db, payload.api_key, payload.provider)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    status = market_data_status(db)
    status["credential_saved"] = True
    return status


@router.get(
    "/market-data/providers",
    response_model=list[MarketDataProviderRead],
)
def list_market_data_providers(
    db: Session = Depends(get_db),
) -> list[dict]:
    providers = db.scalars(
        select(MarketDataProvider).order_by(
            MarketDataProvider.priority,
            MarketDataProvider.provider_name,
        )
    ).all()
    return [provider_read(item) for item in providers]


@router.post(
    "/market-data/providers",
    response_model=MarketDataProviderRead,
    status_code=201,
)
def create_market_data_provider(
    payload: MarketDataProviderCreate,
    db: Session = Depends(get_db),
) -> dict:
    values = payload.model_dump(exclude={"api_key"})
    if payload.api_key:
        values["api_key_encrypted"] = encrypt_api_key(payload.api_key)
    provider = MarketDataProvider(**values)
    db.add(provider)
    try:
        db.commit()
    except Exception as error:
        db.rollback()
        raise HTTPException(409, "Provider name already exists") from error
    db.refresh(provider)
    return provider_read(provider)


@router.put(
    "/market-data/providers/{provider_id}",
    response_model=MarketDataProviderRead,
)
def update_market_data_provider(
    provider_id: int,
    payload: MarketDataProviderCreate,
    db: Session = Depends(get_db),
) -> dict:
    provider = db.get(MarketDataProvider, provider_id)
    if provider is None:
        raise HTTPException(404, "Provider not found")
    for field, value in payload.model_dump(exclude={"api_key"}).items():
        setattr(provider, field, value)
    if payload.api_key:
        provider.api_key_encrypted = encrypt_api_key(payload.api_key)
    db.commit()
    db.refresh(provider)
    return provider_read(provider)


@router.delete("/market-data/providers/{provider_id}", status_code=204)
def delete_market_data_provider(
    provider_id: int,
    db: Session = Depends(get_db),
) -> None:
    _delete(db, MarketDataProvider, provider_id)


@router.post(
    "/market-data/providers/{provider_id}/test",
    response_model=MarketDataProviderRead,
)
def test_market_data_provider(
    provider_id: int,
    db: Session = Depends(get_db),
) -> dict:
    provider = db.get(MarketDataProvider, provider_id)
    if provider is None:
        raise HTTPException(404, "Provider not found")
    return test_provider(db, provider)


@router.get("/loans", response_model=list[LoanRead])
def list_loans(db: Session = Depends(get_db)) -> list[dict]:
    loans = _list(db, Loan)
    return [loan_read(db, loan, len(loans)) for loan in loans]


@router.post("/loans", response_model=LoanRead, status_code=201)
def create_loan(payload: LoanCreate, db: Session = Depends(get_db)) -> dict:
    loan = _create(db, Loan, payload)
    if payload.current_balance:
        opening = LoanLedgerEntry(
            loan_id=loan.id,
            entry_date=payload.start_date or date.today(),
            description="Opening balance",
            entry_type="opening_balance",
            direction="debit",
            amount=payload.current_balance,
            signed_amount=payload.current_balance,
            running_balance=payload.current_balance,
            principal_component=payload.current_balance,
            interest_component=0,
            currency=payload.currency,
            user_confirmed=True,
            notes="Created from the loan opening balance.",
        )
        db.add(opening)
        recalculate_loan_ledger(db, loan)
    db.commit()
    db.refresh(loan)
    return loan_read(db, loan)


@router.put("/loans/{item_id}", response_model=LoanRead)
def update_loan(
    item_id: int, payload: LoanCreate, db: Session = Depends(get_db)
) -> dict:
    existing = db.get(Loan, item_id)
    if existing is None:
        raise HTTPException(404, "Record not found")
    existing_entries = loan_ledger_entries(db, existing)
    data = payload.model_dump()
    if existing_entries:
        data["current_balance"] = existing.current_balance
    for key, value in data.items():
        setattr(existing, key, value)
    existing.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(existing)
    loan = existing
    return loan_read(db, loan)


@router.put("/loans/{item_id}/settings", response_model=LoanRead)
def update_loan_settings(
    item_id: int, payload: LoanSettingsUpdate, db: Session = Depends(get_db)
) -> dict:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Record not found")
    for key, value in payload.model_dump().items():
        setattr(loan, key, value)
    loan.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(loan)
    return loan_read(db, loan)


@router.get(
    "/loans/{item_id}/interest-rates",
    response_model=list[LoanInterestRateRead],
)
def list_loan_interest_rates(
    item_id: int,
    db: Session = Depends(get_db),
) -> list[LoanInterestRate]:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    return loan_rate_changes(db, loan)


@router.post(
    "/loans/{item_id}/interest-rates",
    response_model=LoanInterestRateRead,
    status_code=201,
)
def create_loan_interest_rate(
    item_id: int,
    payload: LoanInterestRateCreate,
    db: Session = Depends(get_db),
) -> LoanInterestRate:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    change = LoanInterestRate(
        loan_id=loan.id,
        **payload.model_dump(),
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change


@router.put(
    "/loans/{item_id}/interest-rates/{rate_id}",
    response_model=LoanInterestRateRead,
)
def update_loan_interest_rate(
    item_id: int,
    rate_id: int,
    payload: LoanInterestRateCreate,
    db: Session = Depends(get_db),
) -> LoanInterestRate:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    change = db.get(LoanInterestRate, rate_id)
    if change is None or change.loan_id != loan.id:
        raise HTTPException(404, "Interest rate change not found")
    for key, value in payload.model_dump().items():
        setattr(change, key, value)
    db.commit()
    db.refresh(change)
    return change


@router.delete("/loans/{item_id}/interest-rates/{rate_id}", status_code=204)
def delete_loan_interest_rate(
    item_id: int,
    rate_id: int,
    db: Session = Depends(get_db),
) -> None:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    change = db.get(LoanInterestRate, rate_id)
    if change is None or change.loan_id != loan.id:
        raise HTTPException(404, "Interest rate change not found")
    db.delete(change)
    db.commit()


@router.get(
    "/loans/{item_id}/ledger-entries",
    response_model=list[LoanLedgerEntryRead],
)
def list_loan_ledger_entries(
    item_id: int,
    db: Session = Depends(get_db),
) -> list[LoanLedgerEntry]:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    return loan_ledger_entries(db, loan)


@router.post(
    "/loans/{item_id}/ledger-entries",
    response_model=LoanLedgerEntryRead,
    status_code=201,
)
def create_loan_ledger_entry(
    item_id: int,
    payload: LoanLedgerEntryCreate,
    db: Session = Depends(get_db),
) -> LoanLedgerEntry:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    if loan.status == "closed":
        raise HTTPException(409, "Closed loans must be reopened before editing")
    if loan.locked_before and payload.entry_date <= loan.locked_before:
        raise HTTPException(409, "This loan period is locked")
    entry = LoanLedgerEntry(loan_id=loan.id, **payload.model_dump())
    db.add(entry)
    db.flush()
    recalculate_loan_ledger(db, loan)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/loans/{item_id}/ledger-entries/{entry_id}", status_code=204)
def delete_loan_ledger_entry(
    item_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
) -> None:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    entry = db.get(LoanLedgerEntry, entry_id)
    if entry is None or entry.loan_id != loan.id:
        raise HTTPException(404, "Loan ledger entry not found")
    if entry.is_locked or loan.status == "closed":
        raise HTTPException(409, "Locked loan entries cannot be deleted")
    db.delete(entry)
    recalculate_loan_ledger(db, loan)
    db.commit()


@router.post(
    "/loans/{item_id}/interest-preview",
    response_model=LoanInterestCalculationRead,
)
def preview_loan_interest(
    item_id: int,
    payload: LoanInterestCalculationRequest,
    db: Session = Depends(get_db),
) -> dict:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    result = calculate_accrued_interest(
        db,
        loan,
        payload.period_start,
        payload.period_end,
    )
    if payload.post:
        calculation = post_interest_calculation(
            db,
            loan,
            payload.period_start,
            payload.period_end,
        )
        db.commit()
        return {
            "id": calculation.id,
            "loan_id": loan.id,
            "period_start": calculation.period_start,
            "period_end": calculation.period_end,
            "basis": calculation.basis,
            "amount": calculation.amount,
            "currency": calculation.currency,
            "status": calculation.status,
            "posted_ledger_entry_id": calculation.posted_ledger_entry_id,
            "segments": result["segments"],
        }
    return {
        "id": None,
        "loan_id": loan.id,
        "period_start": payload.period_start,
        "period_end": payload.period_end,
        "basis": loan.interest_calculation_basis,
        "amount": result["amount"],
        "currency": loan.currency,
        "status": "preview",
        "posted_ledger_entry_id": None,
        "segments": result["segments"],
    }


@router.get("/loans/{item_id}/interest-as-of")
def loan_interest_as_of(
    item_id: int,
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    return interest_summary_as_of(db, loan, as_of or date.today())


@router.get("/loans/{item_id}/reconciliation")
def loan_reconciliation(
    item_id: int,
    expected_balance: Decimal | None = None,
    db: Session = Depends(get_db),
) -> dict:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    calculated = recalculate_loan_ledger(db, loan)
    db.commit()
    expected = (
        expected_balance if expected_balance is not None else loan.current_balance
    )
    return {
        "loan_id": loan.id,
        "expected_balance": expected,
        "calculated_balance": calculated,
        "difference": (Decimal(expected) - calculated).quantize(Decimal("0.01")),
        "ledger_entries": len(loan_ledger_entries(db, loan)),
    }


@router.get("/loans/{item_id}/yearly-summary", response_model=list[LoanYearSummary])
def loan_yearly_summary(
    item_id: int,
    db: Session = Depends(get_db),
) -> list[dict]:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    entries = loan_ledger_entries(db, loan)
    if not entries:
        return []
    years = range(entries[0].entry_date.year, entries[-1].entry_date.year + 1)
    summaries = []
    for year in years:
        year_entries = [entry for entry in entries if entry.entry_date.year == year]
        opening = next(
            (
                entry.running_balance
                for entry in reversed(entries)
                if entry.entry_date.year < year
            ),
            Decimal("0"),
        )
        loan_taken = sum(
            (
                Decimal(entry.amount)
                for entry in year_entries
                if entry.entry_type in {"opening_balance", "loan_taken", "drawdown"}
            ),
            Decimal("0"),
        )
        interest_posted = sum(
            (
                Decimal(entry.amount)
                for entry in year_entries
                if entry.entry_type == "interest_posted"
            ),
            Decimal("0"),
        )
        repayments = sum(
            (
                Decimal(entry.amount)
                for entry in year_entries
                if entry.entry_type == "repayment"
            ),
            Decimal("0"),
        )
        closing = next(
            (
                entry.running_balance
                for entry in reversed(entries)
                if entry.entry_date.year <= year
            ),
            Decimal("0"),
        )
        summaries.append(
            {
                "year": year,
                "opening_balance": opening,
                "loan_taken": loan_taken,
                "interest_posted": interest_posted,
                "repayments": repayments,
                "closing_balance": closing,
            }
        )
    return summaries


@router.get("/loans/{item_id}/transactions", response_model=list[LoanPaymentRead])
def list_loan_transactions(
    item_id: int,
    db: Session = Depends(get_db),
) -> list[dict]:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.linked_loan_id == loan.id)
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    return [
        {
            "id": transaction.id,
            "transaction_date": transaction.transaction_date,
            "vendor": transaction.vendor,
            "description": transaction.description or "",
            "reference_number": transaction.reference_number,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "applied_amount": transaction.amount,
            "applied_currency": loan.currency,
            "is_validated": transaction.is_validated,
        }
        for transaction in transactions
    ]


@router.delete("/loans/{item_id}", status_code=204)
def delete_loan(item_id: int, db: Session = Depends(get_db)) -> None:
    db.query(LoanInterestRate).filter(LoanInterestRate.loan_id == item_id).delete()
    db.query(LoanLedgerEntry).filter(LoanLedgerEntry.loan_id == item_id).delete()
    db.query(LoanDocumentLink).filter(LoanDocumentLink.loan_id == item_id).delete()
    _delete(db, Loan, item_id)


@router.post(
    "/loans/{item_id}/documents/upload",
    response_model=LoanRead,
    status_code=201,
)
async def upload_loan_document(
    item_id: int,
    file: UploadFile = File(...),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    document = await store_document(db, file, "loan_statement", None)
    existing = db.scalar(
        select(LoanDocumentLink).where(
            LoanDocumentLink.loan_id == loan.id,
            LoanDocumentLink.document_id == document.id,
        )
    )
    if existing is None:
        db.add(
            LoanDocumentLink(
                loan_id=loan.id,
                document_id=document.id,
                notes=notes,
            )
        )
    db.commit()
    db.refresh(loan)
    return loan_read(db, loan)


@router.delete("/loans/{item_id}/documents/{document_id}", response_model=LoanRead)
def unlink_loan_document(
    item_id: int,
    document_id: int,
    db: Session = Depends(get_db),
) -> dict:
    loan = db.get(Loan, item_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    link = db.scalar(
        select(LoanDocumentLink).where(
            LoanDocumentLink.loan_id == item_id,
            LoanDocumentLink.document_id == document_id,
        )
    )
    if link is None:
        raise HTTPException(404, "Loan document link not found")
    db.delete(link)
    db.commit()
    db.refresh(loan)
    return loan_read(db, loan)


@router.get("/properties", response_model=list[PropertyRead])
def list_properties(db: Session = Depends(get_db)) -> list[Property]:
    return _list(db, Property)


@router.post("/properties", response_model=PropertyRead, status_code=201)
def create_property(payload: PropertyCreate, db: Session = Depends(get_db)) -> Property:
    return _create(db, Property, payload)


@router.put("/properties/{item_id}", response_model=PropertyRead)
def update_property(
    item_id: int, payload: PropertyCreate, db: Session = Depends(get_db)
) -> Property:
    return _update(db, Property, item_id, payload)


@router.delete("/properties/{item_id}", status_code=204)
def delete_property(item_id: int, db: Session = Depends(get_db)) -> None:
    _delete(db, Property, item_id)


@router.get("/retirement", response_model=list[RetirementRead])
def list_retirement(db: Session = Depends(get_db)) -> list[RetirementAccount]:
    return _list(db, RetirementAccount)


@router.post("/retirement", response_model=RetirementRead, status_code=201)
def create_retirement(
    payload: RetirementCreate, db: Session = Depends(get_db)
) -> RetirementAccount:
    return _create(db, RetirementAccount, payload)


@router.put("/retirement/{item_id}", response_model=RetirementRead)
def update_retirement(
    item_id: int, payload: RetirementCreate, db: Session = Depends(get_db)
) -> RetirementAccount:
    return _update(db, RetirementAccount, item_id, payload)


@router.delete("/retirement/{item_id}", status_code=204)
def delete_retirement(item_id: int, db: Session = Depends(get_db)) -> None:
    _delete(db, RetirementAccount, item_id)


@router.get("/insurance", response_model=list[InsuranceRead])
def list_insurance(db: Session = Depends(get_db)) -> list[dict]:
    return [insurance_read(db, policy) for policy in _list(db, Insurance)]


@router.post("/insurance", response_model=InsuranceRead, status_code=201)
def create_insurance(
    payload: InsuranceCreate, db: Session = Depends(get_db)
) -> dict:
    policy = _create(db, Insurance, payload)
    return insurance_read(db, policy)


@router.put("/insurance/{item_id}", response_model=InsuranceRead)
def update_insurance(
    item_id: int, payload: InsuranceCreate, db: Session = Depends(get_db)
) -> dict:
    policy = _update(db, Insurance, item_id, payload)
    return insurance_read(db, policy)


@router.get(
    "/insurance/{item_id}/transactions",
    response_model=list[InsurancePaymentRead],
)
def list_insurance_transactions(
    item_id: int,
    db: Session = Depends(get_db),
) -> list[dict]:
    policy = db.get(Insurance, item_id)
    if policy is None:
        raise HTTPException(404, "Insurance policy not found")
    policies = list(
        db.scalars(select(Insurance).where(Insurance.is_active.is_(True))).all()
    )
    assignments, _ = insurance_transaction_assignments(db, policies)
    return [
        {
            "id": match.transaction.id,
            "transaction_date": match.transaction.transaction_date,
            "vendor": match.transaction.vendor,
            "description": match.transaction.description or "",
            "reference_number": match.transaction.reference_number,
            "amount": match.transaction.amount,
            "currency": match.transaction.currency,
            "applied_amount": match.applied_amount,
            "applied_currency": policy.currency,
            "is_validated": match.transaction.is_validated,
        }
        for match in assignments.get(policy.id, [])
    ]


@router.delete("/insurance/{item_id}", status_code=204)
def delete_insurance(item_id: int, db: Session = Depends(get_db)) -> None:
    db.query(InsuranceDocumentLink).filter(
        InsuranceDocumentLink.insurance_id == item_id
    ).delete()
    _delete(db, Insurance, item_id)


@router.post(
    "/insurance/{item_id}/documents/upload",
    response_model=InsuranceRead,
    status_code=201,
)
async def upload_insurance_document(
    item_id: int,
    file: UploadFile = File(...),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    policy = db.get(Insurance, item_id)
    if policy is None:
        raise HTTPException(404, "Insurance policy not found")
    document = await store_document(db, file, "insurance_policy", None)
    existing = db.scalar(
        select(InsuranceDocumentLink).where(
            InsuranceDocumentLink.insurance_id == policy.id,
            InsuranceDocumentLink.document_id == document.id,
        )
    )
    if existing is None:
        db.add(
            InsuranceDocumentLink(
                insurance_id=policy.id,
                document_id=document.id,
                notes=notes,
            )
        )
    db.commit()
    db.refresh(policy)
    return insurance_read(db, policy)


@router.delete(
    "/insurance/{item_id}/documents/{document_id}",
    response_model=InsuranceRead,
)
def unlink_insurance_document(
    item_id: int,
    document_id: int,
    db: Session = Depends(get_db),
) -> dict:
    policy = db.get(Insurance, item_id)
    if policy is None:
        raise HTTPException(404, "Insurance policy not found")
    db.query(InsuranceDocumentLink).filter(
        InsuranceDocumentLink.insurance_id == item_id,
        InsuranceDocumentLink.document_id == document_id,
    ).delete()
    db.commit()
    db.refresh(policy)
    return insurance_read(db, policy)


@router.post("/documents/upload", response_model=DocumentRead, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    source_account_id: int | None = Form(None),
    db: Session = Depends(get_db),
) -> Document:
    return await store_document(db, file, document_type, source_account_id)


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return _list(db, Document)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    path = Path(document.file_path)
    if path.suffix.lower() == ".pdf" and path.exists() and not document.page_count:
        try:
            with fitz.open(path) as pdf:
                if pdf.needs_pass:
                    document.status = "password_required"
                    document.processing_stage = "locked"
                    document.processing_message = (
                        "This PDF is password protected. Enter the password to "
                        "preview or process it."
                    )
                    db.commit()
                    db.refresh(document)
                    return document
                document.page_count = len(pdf)
            db.commit()
            db.refresh(document)
        except Exception as exc:
            if "password" in str(exc).casefold() or "encrypted" in str(exc).casefold():
                document.status = "password_required"
                document.processing_stage = "locked"
                document.processing_message = (
                    "This PDF is password protected. Enter the password to "
                    "preview or process it."
                )
                document.processing_error = str(exc)
                db.commit()
                db.refresh(document)
                return document
            raise
    return document


@router.get(
    "/documents/{document_id}/transactions", response_model=list[TransactionRead]
)
def document_transactions(
    document_id: int, db: Session = Depends(get_db)
) -> list[Transaction]:
    if db.get(Document, document_id) is None:
        raise HTTPException(404, "Document not found")
    return list(
        db.scalars(
            select(Transaction)
            .where(Transaction.document_id == document_id)
            .order_by(Transaction.transaction_date, Transaction.id)
        ).all()
    )


@router.post("/documents/{document_id}/confirm")
def confirm_document(
    document_id: int,
    transaction_ids: list[int] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    try:
        audit = latest_audit_for_document(db, document_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    else:
        if not audit["can_confirm"]:
            raise HTTPException(
                409,
                {
                    "message": "Resolve the statement audit before confirmation",
                    "blockers": audit["confirmation_blockers"],
                },
            )
    statement = select(Transaction).where(
        Transaction.document_id == document_id,
        Transaction.is_validated.is_(False),
    )
    if transaction_ids:
        statement = statement.where(Transaction.id.in_(transaction_ids))
    transactions = list(db.scalars(statement).all())
    for transaction in transactions:
        if not transaction.is_duplicate:
            transaction.is_validated = True
    db.flush()
    remaining = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.document_id == document_id,
            Transaction.is_validated.is_(False),
            Transaction.is_duplicate.is_(False),
        )
    )
    document.validation_status = "validated" if not remaining else "partially_validated"
    document.status = "validated" if not remaining else "needs_review"
    document.processing_stage = "confirmed" if not remaining else "human_review"
    document.processing_message = (
        "All reviewed rows are now available in transactions."
        if not remaining
        else f"{remaining} row(s) still need review."
    )
    db.commit()
    return {
        "confirmed": sum(not item.is_duplicate for item in transactions),
        "remaining": remaining or 0,
        "status": document.status,
    }


@router.post("/documents/{document_id}/process", response_model=ProcessResult)
def process_uploaded_document(
    document_id: int,
    force_ocr: bool = False,
    use_local_ai: bool = True,
    password: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    return process_document(
        db,
        document,
        force_ocr=force_ocr,
        use_local_ai=use_local_ai,
        password=password,
    )


@router.post("/documents/process-batch", response_model=BatchProcessResult)
def process_uploaded_documents(
    payload: BatchProcessRequest,
    db: Session = Depends(get_db),
) -> dict:
    document_ids = list(dict.fromkeys(payload.document_ids))
    documents = [
        document
        for document_id in document_ids
        if (document := db.get(Document, document_id)) is not None
    ]
    statement_set = create_statement_set(
        db,
        documents,
        name=f"Statement batch · {len(documents)} document(s)",
    )
    results = []
    transactions_created = 0
    investments_created = 0
    failed = 0
    for document_id in document_ids:
        document = db.get(Document, document_id)
        if document is None:
            failed += 1
            results.append(
                {
                    "document_id": document_id,
                    "file_name": f"Document {document_id}",
                    "status": "failed",
                    "message": "Document not found",
                }
            )
            continue
        try:
            result = process_document(
                db,
                document,
                force_ocr=payload.force_ocr,
                use_local_ai=payload.use_local_ai,
                statement_set_id=statement_set.id,
            )
            transactions_created += result["transactions_created"]
            investments_created += result["investments_created"]
            results.append(
                {
                    "document_id": document.id,
                    "file_name": document.file_name,
                    "status": result["status"],
                    "transactions_created": result["transactions_created"],
                    "investments_created": result["investments_created"],
                    "record_type": result["record_type"],
                    "message": result["message"],
                }
            )
        except HTTPException as exc:
            failed += 1
            results.append(
                {
                    "document_id": document.id,
                    "file_name": document.file_name,
                    "status": "failed",
                    "message": str(exc.detail),
                }
            )
    return {
        "requested": len(document_ids),
        "completed": len(document_ids) - failed,
        "failed": failed,
        "transactions_created": transactions_created,
        "investments_created": investments_created,
        "statement_set_id": statement_set.id,
        "results": results,
    }


@router.get("/documents/{document_id}/audit", response_model=StatementAuditRead)
def get_document_audit(
    document_id: int, db: Session = Depends(get_db)
) -> dict:
    if db.get(Document, document_id) is None:
        raise HTTPException(404, "Document not found")
    return latest_audit_for_document(db, document_id)


@router.post("/documents/{document_id}/reaudit", response_model=ProcessResult)
def reaudit_document(
    document_id: int,
    force_ocr: bool = True,
    use_local_ai: bool = True,
    password: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    return process_document(
        db,
        document,
        force_ocr=force_ocr,
        use_local_ai=use_local_ai,
        audit_only=True,
        password=password,
    )


@router.get("/documents/{document_id}/preview")
def document_preview(
    document_id: int,
    page: int = 1,
    password: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    path = Path(document.file_path)
    if path.suffix.lower() == ".pdf":
        try:
            with fitz.open(path) as pdf:
                if pdf.needs_pass:
                    if not password:
                        raise HTTPException(423, "This PDF is password protected.")
                    if not pdf.authenticate(password):
                        raise HTTPException(403, "The PDF password is incorrect.")
                    if not document.page_count:
                        document.page_count = len(pdf)
                        db.commit()
                if page < 1 or page > len(pdf):
                    raise HTTPException(404, "Document page not found")
                pixmap = pdf[page - 1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                return Response(content=pixmap.tobytes("png"), media_type="image/png")
        except HTTPException:
            raise
        except Exception as exc:
            if "password" in str(exc).casefold() or "encrypted" in str(exc).casefold():
                if password:
                    raise HTTPException(403, "The PDF password is incorrect.") from exc
                raise HTTPException(423, "This PDF is password protected.") from exc
            raise
    if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(path, media_type=media_type)
    raise HTTPException(415, "Preview is available for PDF and image documents")


@router.get("/documents/{document_id}/file")
def document_file(document_id: int, db: Session = Depends(get_db)) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    path = Path(document.file_path)
    if not path.exists():
        raise HTTPException(404, "Document file not found")
    return FileResponse(path, filename=document.file_name)


@router.get("/statement-sets/{statement_set_id}", response_model=StatementAuditRead)
def get_statement_audit(
    statement_set_id: int, db: Session = Depends(get_db)
) -> dict:
    return serialize_audit(db, statement_set_id)


@router.put(
    "/statement-sets/{statement_set_id}/checkpoint",
    response_model=StatementAuditRead,
)
def set_statement_checkpoint(
    statement_set_id: int,
    payload: StatementCheckpointUpdate,
    db: Session = Depends(get_db),
) -> dict:
    return update_checkpoint(
        db,
        statement_set_id,
        payload.expected_transaction_count,
        payload.expected_debit_total,
        payload.expected_credit_total,
    )


@router.put(
    "/statement-candidates/{candidate_id}",
    response_model=StatementAuditRead,
)
def edit_statement_candidate(
    candidate_id: int,
    payload: CandidateUpdate,
    db: Session = Depends(get_db),
) -> dict:
    return update_candidate(db, candidate_id, payload.model_dump(exclude_unset=True))


@router.post("/statement-sets/{statement_set_id}/confirm")
def confirm_statement_audit(
    statement_set_id: int, db: Session = Depends(get_db)
) -> dict:
    return confirm_statement_set(db, statement_set_id)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    for transaction in document.transactions:
        transaction.document_id = None
    for investment in db.scalars(
        select(Investment).where(Investment.source_document_id == document_id)
    ).all():
        db.delete(investment)
    db.query(LoanDocumentLink).filter(
        LoanDocumentLink.document_id == document_id
    ).delete()
    db.query(InsuranceDocumentLink).filter(
        InsuranceDocumentLink.document_id == document_id
    ).delete()
    delete_document_files(document)
    db.delete(document)
    db.commit()


@router.post(
    "/ai/classify-transaction/{transaction_id}", response_model=TransactionRead
)
def classify_one(transaction_id: int, db: Session = Depends(get_db)) -> Transaction:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    apply_rules_to_transaction(db, transaction)
    if transaction.category_id is None:
        apply_merchant_history(db, transaction)
    if transaction.category_id is None:
        classify_transaction(db, transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.post("/ai/classify-transaction", response_model=TransactionRead)
def classify_one_compatibility(
    transaction_id: int, db: Session = Depends(get_db)
) -> Transaction:
    return classify_one(transaction_id, db)


@router.post("/ai/extract-document", response_model=ProcessResult)
def extract_document(
    document_id: int = Body(embed=True), db: Session = Depends(get_db)
) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "Document not found")
    return process_document(db, document)


@router.get("/ai/status")
def ai_status() -> dict:
    return ollama_status()


@router.get("/ocr/status")
def get_ocr_status() -> dict:
    return ocr_status()


@router.post("/ai/classify-pending")
def classify_pending(
    transaction_ids: list[int] | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    statement = select(Transaction).where(
        Transaction.is_validated.is_(False),
        Transaction.category_id.is_(None),
    )
    if transaction_ids:
        statement = statement.where(Transaction.id.in_(transaction_ids))
    transactions = list(db.scalars(statement).all())
    runtime = ollama_status()
    by_source = {"rule": 0, "merchant_history": 0, "ollama": 0}
    unresolved: list[str] = []
    for transaction in transactions:
        apply_rules_to_transaction(db, transaction)
        if transaction.category_id is not None:
            by_source["rule"] += 1
            continue
        apply_merchant_history(db, transaction)
        if transaction.category_id is not None:
            by_source["merchant_history"] += 1
            continue
        if runtime["available"] and runtime["model_installed"]:
            classify_transaction(db, transaction)
        if transaction.category_id is not None:
            by_source["ollama"] += 1
        else:
            unresolved.append(transaction.vendor)
    db.commit()
    classified = sum(by_source.values())
    return {
        "classified": classified,
        "total": len(transactions),
        "unresolved": unresolved,
        "by_source": by_source,
        "ollama_available": runtime["available"],
        "model_installed": runtime["model_installed"],
        "model": runtime["model"],
    }


@router.post("/ai/chat", response_model=ChatResponse)
def finance_chat(payload: ChatRequest, db: Session = Depends(get_db)) -> dict:
    return answer_finance_question(db, payload.question)


@router.post("/ai/help-agent", response_model=HelpAgentResponse)
def help_agent(payload: HelpAgentRequest, db: Session = Depends(get_db)) -> dict:
    return run_help_agent(db, payload.message)


@router.post("/ai/generate-summary", response_model=ChatResponse)
def generate_summary(payload: ChatRequest, db: Session = Depends(get_db)) -> dict:
    return answer_finance_question(db, payload.question)


@router.post("/generated-reports", response_model=ReportRead, status_code=201)
def create_generated_report(
    payload: ReportRequest, db: Session = Depends(get_db)
) -> Report:
    if payload.period_end < payload.period_start:
        raise HTTPException(422, "period_end must not precede period_start")
    return generate_report(
        db,
        payload.report_type,
        payload.period_start,
        payload.period_end,
        payload.format,
    )


def _create_typed_report(
    report_type: str, payload: ReportPeriodRequest, db: Session
) -> Report:
    if payload.period_end < payload.period_start:
        raise HTTPException(422, "period_end must not precede period_start")
    return generate_report(
        db,
        report_type,
        payload.period_start,
        payload.period_end,
        payload.format,
    )


@router.post("/generated-reports/monthly", response_model=ReportRead)
def monthly_report(
    payload: ReportPeriodRequest, db: Session = Depends(get_db)
) -> Report:
    return _create_typed_report("monthly", payload, db)


@router.post("/generated-reports/yearly", response_model=ReportRead)
def yearly_report(
    payload: ReportPeriodRequest, db: Session = Depends(get_db)
) -> Report:
    return _create_typed_report("yearly", payload, db)


@router.post("/generated-reports/tax", response_model=ReportRead)
def tax_report(payload: ReportPeriodRequest, db: Session = Depends(get_db)) -> Report:
    return _create_typed_report("tax", payload, db)


@router.post("/generated-reports/investment", response_model=ReportRead)
def investment_report(
    payload: ReportPeriodRequest, db: Session = Depends(get_db)
) -> Report:
    return _create_typed_report("investment", payload, db)


@router.post("/generated-reports/property", response_model=ReportRead)
def property_report(
    payload: ReportPeriodRequest, db: Session = Depends(get_db)
) -> Report:
    return _create_typed_report("property", payload, db)


@router.post("/generated-reports/debt", response_model=ReportRead)
def debt_report(payload: ReportPeriodRequest, db: Session = Depends(get_db)) -> Report:
    return _create_typed_report("debt", payload, db)


@router.post("/generated-reports/protection", response_model=ReportRead)
def protection_report(
    payload: ReportPeriodRequest, db: Session = Depends(get_db)
) -> Report:
    return _create_typed_report("protection", payload, db)


@router.get("/generated-reports", response_model=list[ReportRead])
def list_generated_reports(db: Session = Depends(get_db)) -> list[Report]:
    return _list(db, Report)


@router.get("/reports/cash-flow/comparison", response_model=CashFlowComparison)
def get_cash_flow_comparison(
    year: int,
    month: int,
    db: Session = Depends(get_db),
) -> dict:
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(422, "Invalid report month")
    return cash_flow_comparison(db, year, month)


@router.get("/generated-reports/{report_id}/download")
def download_generated_report(
    report_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    report = db.get(Report, report_id)
    if report is None or not Path(report.file_path).exists():
        raise HTTPException(404, "Report file not found")
    return FileResponse(
        report.file_path,
        filename=Path(report.file_path).name,
        media_type="application/octet-stream",
    )


@router.get("/reports/metadata", response_model=ReportMetadata)
def custom_report_metadata() -> dict:
    return report_metadata()


@router.post("/reports/preview", response_model=ReportResult)
def preview_custom_report(
    payload: ReportPreviewRequest, db: Session = Depends(get_db)
) -> ReportResult:
    return run_report(db, payload.data_source, payload.config_json)


@router.get("/reports", response_model=list[CustomReportRead])
def list_custom_reports(db: Session = Depends(get_db)) -> list[CustomReport]:
    return list(
        db.scalars(
            select(CustomReport)
            .where(CustomReport.user_id == 1)
            .order_by(CustomReport.updated_at.desc(), CustomReport.id.desc())
        ).all()
    )


@router.get("/reports/dashboard/widgets", response_model=list[CustomReportRead])
def list_dashboard_report_widgets(db: Session = Depends(get_db)) -> list[CustomReport]:
    return list(
        db.scalars(
            select(CustomReport)
            .where(
                CustomReport.user_id == 1,
                CustomReport.dashboard_section.is_not(None),
            )
            .order_by(CustomReport.widget_position, CustomReport.updated_at.desc())
        ).all()
    )


@router.get("/reports/scheduled", response_model=list[CustomReportRead])
def list_scheduled_reports(db: Session = Depends(get_db)) -> list[CustomReport]:
    return list(
        db.scalars(
            select(CustomReport)
            .where(
                CustomReport.user_id == 1,
                CustomReport.schedule_frequency.is_not(None),
                CustomReport.schedule_frequency != "manual",
            )
            .order_by(CustomReport.updated_at.desc())
        ).all()
    )


@router.post("/reports/ai-draft", response_model=CustomReportCreate)
def ai_assisted_report_draft(payload: AIAssistedReportRequest) -> CustomReportCreate:
    prompt = payload.prompt.casefold()
    if "loan" in prompt:
        return CustomReportCreate(
            name="Loan Balance Overview",
            description="AI-assisted draft: outstanding balance by lender.",
            data_source="loans",
            chart_type="bar",
            config_json={
                "fields": ["lender", "current_balance"],
                "filters": [],
                "groupBy": ["lender"],
                "aggregation": {"field": "current_balance", "function": "sum"},
                "sort": {"field": "current_balance", "direction": "desc"},
                "limit": 20,
                "chart": {
                    "type": "bar",
                    "xAxis": "lender",
                    "yAxis": "current_balance",
                },
            },
        )
    if "net worth" in prompt:
        return CustomReportCreate(
            name="Net Worth Snapshot",
            description="AI-assisted draft: calculated current net worth.",
            data_source="net_worth",
            chart_type="kpi",
            config_json={
                "fields": ["metric", "value", "currency"],
                "filters": [],
                "groupBy": [],
                "aggregation": None,
                "sort": None,
                "limit": 10,
                "chart": {"type": "kpi", "xAxis": "metric", "yAxis": "value"},
            },
        )
    return CustomReportCreate(
        name="Monthly Expense by Category",
        description="AI-assisted draft: spending grouped by category.",
        data_source="transactions",
        chart_type="bar",
        config_json={
            "fields": ["category", "amount"],
            "filters": [
                {"field": "transaction_type", "operator": "equals", "value": "debit"}
            ],
            "groupBy": ["category"],
            "aggregation": {"field": "amount", "function": "sum"},
            "sort": {"field": "amount", "direction": "desc"},
            "limit": 10,
            "chart": {"type": "bar", "xAxis": "category", "yAxis": "amount"},
        },
    )


@router.get("/reports/{report_id}", response_model=CustomReportRead)
def get_custom_report(
    report_id: int, db: Session = Depends(get_db)
) -> CustomReport:
    report = db.get(CustomReport, report_id)
    if report is None or report.user_id != 1:
        raise HTTPException(404, "Custom report not found")
    return report


@router.post(
    "/reports",
    response_model=CustomReportRead | ReportRead,
    status_code=201,
)
def create_custom_report(
    body: dict = Body(...), db: Session = Depends(get_db)
) -> CustomReport | Report:
    if "report_type" in body:
        payload = ReportRequest.model_validate(body)
        if payload.period_end < payload.period_start:
            raise HTTPException(422, "period_end must not precede period_start")
        return generate_report(
            db,
            payload.report_type,
            payload.period_start,
            payload.period_end,
            payload.format,
        )
    payload = CustomReportCreate.model_validate(body)
    run_report(db, payload.data_source, payload.config_json)
    report = CustomReport(
        user_id=1,
        name=payload.name.strip(),
        description=payload.description,
        data_source=payload.data_source,
        chart_type=payload.chart_type,
        config_json=payload.config_json.model_dump_json(),
        dashboard_section=payload.dashboard_section,
        widget_size=payload.widget_size,
        widget_position=payload.widget_position,
        schedule_frequency=payload.schedule_frequency,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/reports/{report_id}/download")
def download_report_compatibility(
    report_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    report = db.get(Report, report_id)
    if report is None or not Path(report.file_path).exists():
        raise HTTPException(404, "Report file not found")
    return FileResponse(
        report.file_path,
        filename=Path(report.file_path).name,
        media_type="application/octet-stream",
    )


@router.put("/reports/{report_id}", response_model=CustomReportRead)
def update_custom_report(
    report_id: int,
    payload: CustomReportCreate,
    db: Session = Depends(get_db),
) -> CustomReport:
    report = db.get(CustomReport, report_id)
    if report is None or report.user_id != 1:
        raise HTTPException(404, "Custom report not found")
    run_report(db, payload.data_source, payload.config_json)
    report.name = payload.name.strip()
    report.description = payload.description
    report.data_source = payload.data_source
    report.chart_type = payload.chart_type
    report.config_json = payload.config_json.model_dump_json()
    report.dashboard_section = payload.dashboard_section
    report.widget_size = payload.widget_size
    report.widget_position = payload.widget_position
    report.schedule_frequency = payload.schedule_frequency
    report.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(report)
    return report


@router.delete("/reports/{report_id}", status_code=204)
def delete_custom_report(report_id: int, db: Session = Depends(get_db)) -> Response:
    report = db.get(CustomReport, report_id)
    if report is None or report.user_id != 1:
        raise HTTPException(404, "Custom report not found")
    db.delete(report)
    db.commit()
    return Response(status_code=204)


@router.post("/reports/{report_id}/run", response_model=ReportResult)
def run_custom_report(
    report_id: int, db: Session = Depends(get_db)
) -> ReportResult:
    _, result = _run_saved_report(db, report_id)
    return result


@router.post(
    "/reports/{report_id}/duplicate",
    response_model=CustomReportRead,
    status_code=201,
)
def duplicate_custom_report(
    report_id: int, db: Session = Depends(get_db)
) -> CustomReport:
    report = db.get(CustomReport, report_id)
    if report is None or report.user_id != 1:
        raise HTTPException(404, "Custom report not found")
    duplicate = CustomReport(
        user_id=1,
        name=f"{report.name} (Copy)",
        description=report.description,
        data_source=report.data_source,
        chart_type=report.chart_type,
        config_json=report.config_json,
        dashboard_section=report.dashboard_section,
        widget_size=report.widget_size,
        widget_position=report.widget_position,
        schedule_frequency=report.schedule_frequency,
    )
    db.add(duplicate)
    db.commit()
    db.refresh(duplicate)
    return duplicate


def _custom_report_or_404(db: Session, report_id: int) -> CustomReport:
    report = db.get(CustomReport, report_id)
    if report is None or report.user_id != 1:
        raise HTTPException(404, "Custom report not found")
    return report


def _run_saved_report(db: Session, report_id: int) -> tuple[CustomReport, ReportResult]:
    report = _custom_report_or_404(db, report_id)
    payload = CustomReportRead.model_validate(report)
    report.last_run_at = datetime.now(UTC)
    db.commit()
    return report, run_report(db, payload.data_source, payload.config_json)


@router.post("/reports/{report_id}/dashboard", response_model=CustomReportRead)
def add_custom_report_to_dashboard(
    report_id: int,
    payload: DashboardWidgetRequest,
    db: Session = Depends(get_db),
) -> CustomReport:
    report = _custom_report_or_404(db, report_id)
    report.dashboard_section = payload.section
    report.widget_size = payload.widget_size
    report.widget_position = payload.position
    report.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(report)
    return report


@router.post("/reports/{report_id}/schedule", response_model=CustomReportRead)
def schedule_custom_report(
    report_id: int,
    payload: ReportScheduleRequest,
    db: Session = Depends(get_db),
) -> CustomReport:
    report = _custom_report_or_404(db, report_id)
    report.schedule_frequency = payload.frequency
    report.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(report)
    return report


@router.get("/reports/{report_id}/export/{export_format}")
def export_custom_report(
    report_id: int,
    export_format: str,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    report, result = _run_saved_report(db, report_id)
    safe_name = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in report.name
    ).strip("-")
    safe_name = safe_name or f"report-{report.id}"
    if export_format == "csv":
        buffer = StringIO()
        buffer.write(",".join(column["label"] for column in result.columns) + "\n")
        for row in result.rows:
            buffer.write(
                ",".join(
                    '"' + str(row.get(column["key"], "")).replace('"', '""') + '"'
                    for column in result.columns
                )
                + "\n"
            )
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}.csv"'
            },
        )
    if export_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Report"
        sheet.append([column["label"] for column in result.columns])
        for row in result.rows:
            sheet.append([row.get(column["key"]) for column in result.columns])
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}.xlsx"'
            },
        )
    if export_format == "pdf":
        output = BytesIO()
        pdf = canvas.Canvas(output, pagesize=A4)
        width, height = A4
        y = height - 48
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(42, y, report.name)
        y -= 26
        pdf.setFont("Helvetica", 8)
        pdf.drawString(42, y, " | ".join(column["label"] for column in result.columns))
        y -= 16
        for row in result.rows[:45]:
            line = " | ".join(
                str(row.get(column["key"], "")) for column in result.columns
            )
            pdf.drawString(
                42,
                y,
                line,
            )
            y -= 13
            if y < 42:
                pdf.showPage()
                y = height - 42
        pdf.save()
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}.pdf"'
            },
        )
    raise HTTPException(422, "Supported export formats are csv, xlsx, and pdf.")


@router.post("/backup")
def create_backup() -> FileResponse:
    if not settings.database_url.startswith("sqlite:///"):
        raise HTTPException(400, "Backup endpoint supports SQLite only")
    source = Path(settings.database_url.removeprefix("sqlite:///"))
    if not source.exists():
        raise HTTPException(404, "Database not found")
    target = settings.reports_dir / f"ledger-local-backup-{date.today()}.db"
    shutil.copy2(source, target)
    return FileResponse(
        target, filename=target.name, media_type="application/x-sqlite3"
    )
