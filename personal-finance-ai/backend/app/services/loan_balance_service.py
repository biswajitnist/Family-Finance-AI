from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import Loan
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
    matches = matched_loan_transactions(db, loan, loan_count)
    payments = sum(
        (match.applied_amount for match in matches),
        start=Decimal("0"),
    )
    recorded = Decimal(loan.current_balance)
    adjusted = max(Decimal("0"), recorded - payments)
    return LoanBalance(
        recorded_balance=recorded.quantize(Decimal("0.01")),
        adjusted_balance=adjusted.quantize(Decimal("0.01")),
        payments_applied=payments.quantize(Decimal("0.01")),
        matched_transaction_count=len(matches),
    )


def loan_read(db: Session, loan: Loan, loan_count: int | None = None) -> dict:
    adjustment = loan_balance(db, loan, loan_count)
    return {
        "id": loan.id,
        "user_id": loan.user_id,
        "account_id": loan.account_id,
        "lender": loan.lender,
        "loan_type": loan.loan_type,
        "original_amount": loan.original_amount,
        "current_balance": adjustment.adjusted_balance,
        "recorded_balance": adjustment.recorded_balance,
        "payments_applied": adjustment.payments_applied,
        "matched_transaction_count": adjustment.matched_transaction_count,
        "interest_rate": loan.interest_rate,
        "monthly_payment": loan.monthly_payment,
        "currency": loan.currency,
        "start_date": loan.start_date,
        "end_date": loan.end_date,
    }
