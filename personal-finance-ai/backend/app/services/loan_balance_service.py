from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.finance import (
    Loan,
    LoanDocumentLink,
    LoanInterestCalculation,
    LoanInterestRate,
    LoanLedgerEntry,
)
from app.models.transaction import Transaction
from app.services.currency_service import convert_amount
from app.services.merchant_learning import normalize_merchant


@dataclass(frozen=True)
class LoanBalance:
    recorded_balance: Decimal
    adjusted_balance: Decimal
    payments_applied: Decimal
    matched_transaction_count: int


@dataclass(frozen=True)
class MatchedLoanTransaction:
    transaction: Transaction
    applied_amount: Decimal


DEBIT_TYPES = {
    "opening_balance",
    "loan_taken",
    "interest_posted",
    "interest_accrued",
    "charge",
    "adjustment",
    "correction",
    "drawdown",
}

CREDIT_TYPES = {"repayment", "waiver"}

LEDGER_TYPE_SORT_ORDER = {
    "opening_balance": 0,
    "loan_taken": 1,
    "drawdown": 1,
    "interest": 2,
    "interest_posted": 2,
    "interest_accrued": 2,
    "charge": 3,
    "adjustment": 4,
    "repayment": 5,
    "waiver": 6,
    "correction": 7,
}


def entry_signed_amount(entry_type: str, direction: str, amount: Decimal) -> Decimal:
    normalized_type = (entry_type or "").strip().lower()
    normalized_direction = (direction or "").strip().lower()
    value = abs(Decimal(amount or 0))
    if normalized_type in CREDIT_TYPES:
        return -value
    if normalized_type in {
        "opening_balance",
        "loan_taken",
        "drawdown",
        "interest_posted",
        "interest_accrued",
        "charge",
    }:
        return value
    if normalized_direction == "credit":
        return -value
    return value


def recalculate_loan_ledger(db: Session, loan: Loan) -> Decimal:
    entries = loan_ledger_entries(db, loan)
    balance = Decimal("0")
    for entry in entries:
        entry.signed_amount = entry_signed_amount(
            entry.entry_type,
            entry.direction,
            Decimal(entry.amount),
        ).quantize(Decimal("0.01"))
        entry.direction = "credit" if entry.signed_amount < 0 else "debit"
        balance = (balance + Decimal(entry.signed_amount)).quantize(Decimal("0.01"))
        entry.running_balance = balance
    loan.current_balance = balance
    return balance


def loan_rate_changes(db: Session, loan: Loan) -> list[LoanInterestRate]:
    return list(
        db.scalars(
            select(LoanInterestRate)
            .where(LoanInterestRate.loan_id == loan.id)
            .order_by(LoanInterestRate.effective_date, LoanInterestRate.id)
        ).all()
    )


def loan_ledger_entries(db: Session, loan: Loan) -> list[LoanLedgerEntry]:
    entries = list(
        db.scalars(
            select(LoanLedgerEntry)
            .where(LoanLedgerEntry.loan_id == loan.id)
            .order_by(LoanLedgerEntry.entry_date, LoanLedgerEntry.id)
        ).all()
    )
    return sorted(
        entries,
        key=lambda entry: (
            entry.entry_date,
            LEDGER_TYPE_SORT_ORDER.get(entry.entry_type, 99),
            entry.id,
        ),
    )


def ledger_balance(db: Session, loan: Loan) -> Decimal | None:
    entries = loan_ledger_entries(db, loan)
    if not entries:
        return None
    balance = sum(
        (
            entry.signed_amount
            if Decimal(entry.signed_amount or 0) != 0
            else entry_signed_amount(entry.entry_type, entry.direction, entry.amount)
            for entry in entries
        ),
        start=Decimal("0"),
    )
    return balance.quantize(Decimal("0.01"))


def effective_interest_rate(
    db: Session,
    loan: Loan,
    as_of: date | None = None,
) -> Decimal:
    effective_date = as_of or date.today()
    change = db.scalars(
        select(LoanInterestRate)
        .where(
            LoanInterestRate.loan_id == loan.id,
            LoanInterestRate.effective_date <= effective_date,
        )
        .order_by(
            LoanInterestRate.effective_date.desc(),
            LoanInterestRate.id.desc(),
        )
    ).first()
    if change is not None:
        return Decimal(change.interest_rate)
    return Decimal(loan.interest_rate or 0)


def _matches_lender(transaction: Transaction, loan: Loan, loan_count: int) -> bool:
    if loan.account_id and transaction.account_id == loan.account_id:
        return True
    if loan_count == 1:
        return True
    lender = normalize_merchant(loan.lender)
    transaction_text = normalize_merchant(
        f"{transaction.vendor} {transaction.description}"
    )
    return bool(lender and lender in transaction_text)


def matched_loan_transactions(
    db: Session,
    loan: Loan,
    loan_count: int | None = None,
) -> list[MatchedLoanTransaction]:
    count = loan_count
    if count is None:
        count = len(db.scalars(select(Loan.id)).all())
    transactions = db.scalars(
        select(Transaction)
        .join(Transaction.category)
        .where(
            Transaction.is_validated.is_(True),
            Transaction.is_duplicate.is_(False),
            Transaction.transaction_type == "debit",
            Transaction.category.has(name="Loan Repayment"),
            *(
                [Transaction.transaction_date >= loan.start_date]
                if loan.start_date
                else []
            ),
        )
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    matches: list[MatchedLoanTransaction] = []
    for transaction in transactions:
        if not _matches_lender(transaction, loan, count):
            continue
        converted = convert_amount(
            db,
            transaction.amount,
            transaction.currency,
            loan.currency,
        )
        if converted is None:
            continue
        matches.append(
            MatchedLoanTransaction(
                transaction=transaction,
                applied_amount=converted.quantize(Decimal("0.01")),
            )
        )
    return matches


def loan_balance(db: Session, loan: Loan, loan_count: int | None = None) -> LoanBalance:
    ledger_recorded = ledger_balance(db, loan)
    matches = (
        []
        if ledger_recorded is not None
        else matched_loan_transactions(db, loan, loan_count)
    )
    payments = sum(
        (match.applied_amount for match in matches),
        start=Decimal("0"),
    )
    recorded = (
        ledger_recorded
        if ledger_recorded is not None
        else Decimal(loan.current_balance)
    )
    adjusted = max(Decimal("0"), recorded - payments)
    return LoanBalance(
        recorded_balance=recorded.quantize(Decimal("0.01")),
        adjusted_balance=adjusted.quantize(Decimal("0.01")),
        payments_applied=payments.quantize(Decimal("0.01")),
        matched_transaction_count=len(matches),
    )


def loan_read(db: Session, loan: Loan, loan_count: int | None = None) -> dict:
    if loan_ledger_entries(db, loan):
        recalculate_loan_ledger(db, loan)
    adjustment = loan_balance(db, loan, loan_count)
    active_rate = effective_interest_rate(db, loan)
    rate_changes = loan_rate_changes(db, loan)
    ledger_entries = loan_ledger_entries(db, loan)
    ledger_total = sum(
        (
            Decimal(entry.amount)
            for entry in ledger_entries
            if entry.direction == "debit"
        ),
        start=Decimal("0"),
    ).quantize(Decimal("0.01"))
    total_borrowed = sum(
        (
            Decimal(entry.amount)
            for entry in ledger_entries
            if entry.entry_type in {"opening_balance", "loan_taken", "drawdown"}
        ),
        start=Decimal("0"),
    ).quantize(Decimal("0.01"))
    total_repaid = sum(
        (
            Decimal(entry.amount)
            for entry in ledger_entries
            if entry.entry_type == "repayment"
        ),
        start=Decimal("0"),
    ).quantize(Decimal("0.01"))
    total_interest_posted = sum(
        (
            Decimal(entry.amount)
            for entry in ledger_entries
            if entry.entry_type == "interest_posted"
        ),
        start=Decimal("0"),
    ).quantize(Decimal("0.01"))
    interest_summary = interest_summary_as_of(db, loan, date.today())
    accumulated_interest = interest_summary["unposted_accumulated_interest"]
    principal_balance = interest_summary["outstanding_principal"]
    posted_interest_balance = interest_summary["posted_interest"]
    monthly_interest = (
        adjustment.adjusted_balance * active_rate / Decimal("1200")
    ).quantize(Decimal("0.01"))
    linked_documents = list(
        db.scalars(
            select(Document)
            .join(LoanDocumentLink, LoanDocumentLink.document_id == Document.id)
            .where(LoanDocumentLink.loan_id == loan.id)
            .order_by(Document.uploaded_at.desc(), Document.id.desc())
        ).all()
    )
    return {
        "id": loan.id,
        "user_id": loan.user_id,
        "account_id": loan.account_id,
        "lender": loan.lender,
        "direction": loan.direction,
        "loan_type": loan.loan_type,
        "original_amount": loan.original_amount,
        "current_balance": adjustment.recorded_balance,
        "recorded_balance": adjustment.recorded_balance,
        "principal_balance": principal_balance,
        "posted_interest_balance": posted_interest_balance,
        "payments_applied": adjustment.payments_applied,
        "matched_transaction_count": adjustment.matched_transaction_count,
        "interest_rate": loan.interest_rate,
        "effective_interest_rate": active_rate.quantize(Decimal("0.0001")),
        "monthly_interest_estimate": monthly_interest,
        "interest_mode": loan.interest_mode,
        "interest_calculation_basis": loan.interest_calculation_basis,
        "interest_posting_frequency": loan.interest_posting_frequency,
        "payment_allocation_rule": loan.payment_allocation_rule,
        "status": loan.status,
        "locked_before": loan.locked_before,
        "lock_reason": loan.lock_reason,
        "interest_rate_changes": [
            {
                "id": change.id,
                "loan_id": change.loan_id,
                "effective_date": change.effective_date,
                "interest_rate": change.interest_rate,
                "notes": change.notes,
                "created_at": change.created_at,
            }
            for change in rate_changes
        ],
        "ledger_entries": [
            {
                "id": entry.id,
                "loan_id": entry.loan_id,
                "entry_date": entry.entry_date,
                "description": entry.description,
                "entry_type": entry.entry_type,
                "direction": entry.direction,
                "amount": entry.amount,
                "signed_amount": entry.signed_amount,
                "running_balance": entry.running_balance,
                "principal_component": entry.principal_component,
                "interest_component": entry.interest_component,
                "currency": entry.currency,
                "transaction_id": entry.transaction_id,
                "mapping_confidence": entry.mapping_confidence,
                "user_confirmed": entry.user_confirmed,
                "is_locked": entry.is_locked,
                "unlock_reason": entry.unlock_reason,
                "notes": entry.notes,
                "created_at": entry.created_at,
            }
            for entry in ledger_entries
        ],
        "ledger_total": ledger_total,
        "accumulated_interest_as_of_today": accumulated_interest,
        "total_borrowed": total_borrowed,
        "total_repaid": total_repaid,
        "total_interest_posted": total_interest_posted,
        "total_payable_today": interest_summary["total_payable"],
        "documents": linked_documents,
        "monthly_payment": loan.monthly_payment,
        "currency": loan.currency,
        "start_date": loan.start_date,
        "end_date": loan.end_date,
    }


def balance_as_of(db: Session, loan: Loan, as_of: date) -> Decimal:
    entries = [
        entry
        for entry in loan_ledger_entries(db, loan)
        if entry.entry_date <= as_of and entry.entry_type != "interest_accrued"
    ]
    if not entries:
        return Decimal(loan.current_balance or 0).quantize(Decimal("0.01"))
    balance = sum(
        (
            entry.signed_amount
            if Decimal(entry.signed_amount or 0) != 0
            else entry_signed_amount(entry.entry_type, entry.direction, entry.amount)
            for entry in entries
        ),
        start=Decimal("0"),
    )
    return balance.quantize(Decimal("0.01"))


def calculate_accrued_interest(
    db: Session,
    loan: Loan,
    period_start: date,
    period_end: date,
) -> dict:
    if period_end < period_start:
        return {"amount": Decimal("0.00"), "segments": []}
    current = period_start
    segments = []
    total = Decimal("0")
    while current <= period_end:
        rate = effective_interest_rate(db, loan, current)
        next_day = current + timedelta(days=1)
        balance = balance_as_of(db, loan, current)
        interest = (balance * rate * Decimal("1") / Decimal("36500")).quantize(
            Decimal("0.0001")
        )
        total += interest
        segments.append(
            {
                "date": current.isoformat(),
                "balance": str(balance),
                "annual_rate": str(rate),
                "interest": str(interest),
            }
        )
        current = next_day
    return {"amount": total.quantize(Decimal("0.01")), "segments": segments}


def interest_summary_as_of(db: Session, loan: Loan, as_of: date) -> dict:
    ledger_entries = loan_ledger_entries(db, loan)
    automatic_interest = (loan.interest_mode or "manual") == "automatic"
    last_posted_interest = max(
        (
            entry.entry_date
            for entry in ledger_entries
            if entry.entry_type == "interest_posted" and entry.entry_date <= as_of
        ),
        default=loan.start_date or as_of,
    )
    period_start = last_posted_interest + timedelta(days=1)
    if period_start > as_of:
        period_start = as_of
    result = (
        calculate_accrued_interest(db, loan, period_start, as_of)
        if automatic_interest
        else {"amount": Decimal("0.00"), "segments": []}
    )
    posted_interest = sum(
        (
            Decimal(entry.amount)
            for entry in ledger_entries
            if entry.entry_type == "interest_posted" and entry.entry_date <= as_of
        ),
        start=Decimal("0"),
    ).quantize(Decimal("0.01"))
    principal_balance = sum(
        (
            entry.signed_amount
            if Decimal(entry.signed_amount or 0) != 0
            else entry_signed_amount(entry.entry_type, entry.direction, entry.amount)
            for entry in ledger_entries
            if entry.entry_date <= as_of
            and entry.entry_type not in {"interest_posted", "interest_accrued"}
        ),
        start=Decimal("0"),
    ).quantize(Decimal("0.01"))
    unposted = result["amount"]
    return {
        "loan_id": loan.id,
        "as_of": as_of,
        "currency": loan.currency,
        "outstanding_principal": principal_balance,
        "posted_interest": posted_interest,
        "unposted_accumulated_interest": unposted,
        "current_balance_excluding_unposted_interest": (
            principal_balance + posted_interest
        ).quantize(Decimal("0.01")),
        "total_payable": (
            principal_balance + posted_interest + unposted
        ).quantize(Decimal("0.01")),
        "period_start": period_start,
        "period_end": as_of,
        "segments": compress_interest_segments(result["segments"]),
    }


def compress_interest_segments(segments: list[dict]) -> list[dict]:
    compressed: list[dict] = []
    for segment in segments:
        key = (segment["balance"], segment["annual_rate"])
        if compressed and compressed[-1]["_key"] == key:
            compressed[-1]["period_end"] = segment["date"]
            compressed[-1]["days"] += 1
            compressed[-1]["interest"] = str(
                (
                    Decimal(compressed[-1]["interest"])
                    + Decimal(segment["interest"])
                ).quantize(Decimal("0.01"))
            )
            continue
        compressed.append(
            {
                "_key": key,
                "period_start": segment["date"],
                "period_end": segment["date"],
                "balance": segment["balance"],
                "days": 1,
                "annual_rate": segment["annual_rate"],
                "interest": str(Decimal(segment["interest"]).quantize(Decimal("0.01"))),
            }
        )
    for segment in compressed:
        segment.pop("_key", None)
    return compressed


def post_interest_calculation(
    db: Session,
    loan: Loan,
    period_start: date,
    period_end: date,
) -> LoanInterestCalculation:
    result = calculate_accrued_interest(db, loan, period_start, period_end)
    amount = result["amount"]
    entry = LoanLedgerEntry(
        loan_id=loan.id,
        entry_date=period_end,
        description=f"Interest posted {period_start} to {period_end}",
        entry_type="interest_posted",
        direction="debit",
        amount=amount,
        signed_amount=amount,
        principal_component=Decimal("0"),
        interest_component=amount,
        currency=loan.currency,
        user_confirmed=True,
    )
    db.add(entry)
    db.flush()
    calculation = LoanInterestCalculation(
        loan_id=loan.id,
        period_start=period_start,
        period_end=period_end,
        basis=loan.interest_calculation_basis,
        amount=amount,
        currency=loan.currency,
        preview_json=str(result["segments"][:500]),
        status="posted",
        posted_ledger_entry_id=entry.id,
    )
    db.add(calculation)
    recalculate_loan_ledger(db, loan)
    return calculation
