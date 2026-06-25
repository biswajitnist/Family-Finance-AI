import calendar
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models.finance import BudgetProposal, MonthlyBudget
from app.models.transaction import Transaction
from app.services.ai_service import generate_local_json
from app.services.merchant_learning import normalize_merchant

FREQUENCY_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "semiannual": 6,
    "yearly": 12,
}
FREQUENCY_DAYS = {"weekly": 7, "biweekly": 14}


class AIRecurrenceResult(BaseModel):
    frequency: str | None = Field(
        default=None,
        pattern="^(weekly|biweekly|monthly|quarterly|semiannual|yearly)$",
    )
    confidence: float = Field(default=0, ge=0, le=1)


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def next_occurrence(value: date, frequency: str) -> date:
    if frequency in FREQUENCY_MONTHS:
        return add_months(value, FREQUENCY_MONTHS[frequency])
    return value + timedelta(days=FREQUENCY_DAYS[frequency])


def recurrence_group_key(transaction: Transaction) -> str:
    merchant = normalize_merchant(transaction.vendor)
    return "|".join(
        [
            str(transaction.user_id),
            str(transaction.account_id),
            merchant,
            transaction.currency.upper(),
            transaction.transaction_type,
        ]
    )[:220]


def _stable_amount(rows: list[Transaction]) -> bool:
    amounts = [abs(Decimal(row.amount)) for row in rows]
    typical = Decimal(str(median(amounts)))
    if typical == 0:
        return False
    tolerance = max(Decimal("1.00"), typical * Decimal("0.08"))
    return max(abs(amount - typical) for amount in amounts) <= tolerance


def _frequency_from_dates(dates: list[date]) -> str | None:
    if len(dates) < 2:
        return None
    gaps = [
        (right - left).days
        for left, right in zip(dates, dates[1:], strict=False)
    ]
    typical = median(gaps)
    ranges = (
        ("weekly", 5, 9),
        ("biweekly", 11, 17),
        ("monthly", 25, 36),
        ("quarterly", 80, 101),
        ("semiannual", 170, 196),
        ("yearly", 350, 381),
    )
    return next(
        (frequency for frequency, low, high in ranges if low <= typical <= high),
        None,
    )


def _ai_frequency(rows: list[Transaction]) -> AIRecurrenceResult | None:
    prompt = (
        "You are a local recurring-payment detector. No cloud service is allowed. "
        "Return only JSON matching "
        '{"frequency": "weekly|biweekly|monthly|quarterly|semiannual|yearly|null", '
        '"confidence": 0.0}. Use null when the evidence is insufficient.\n'
        f"Merchant: {rows[-1].vendor}\n"
        f"Dates: {json.dumps([row.transaction_date.isoformat() for row in rows])}\n"
        f"Amounts: {json.dumps([str(row.amount) for row in rows])}\n"
        f"Currency: {rows[-1].currency}"
    )
    try:
        result = AIRecurrenceResult.model_validate_json(generate_local_json(prompt))
    except (RuntimeError, ValidationError, json.JSONDecodeError, KeyError):
        return None
    return result if result.frequency and result.confidence >= 0.7 else None


def detect_recurring_transactions(
    db: Session, user_id: int = 1, use_local_ai: bool = False
) -> dict[str, int]:
    rows = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.is_validated.is_(True),
                Transaction.is_duplicate.is_(False),
                Transaction.transaction_type == "debit",
            )
            .order_by(Transaction.transaction_date, Transaction.id)
        ).all()
    )
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for row in rows:
        groups[recurrence_group_key(row)].append(row)

    detected_groups = 0
    updated = 0
    ai_groups = 0
    for key, group in groups.items():
        if len(group) < 2 or not _stable_amount(group):
            continue
        dates = sorted({item.transaction_date for item in group})
        frequency = _frequency_from_dates(dates)
        source = "detected"
        confidence = Decimal("0.9000") if len(dates) >= 3 else Decimal("0.7800")
        if frequency is None and use_local_ai:
            ai_result = _ai_frequency(group)
            if ai_result:
                frequency = ai_result.frequency
                source = "ollama"
                confidence = Decimal(str(ai_result.confidence)).quantize(
                    Decimal("0.0001")
                )
                ai_groups += 1
        if frequency is None:
            continue
        detected_groups += 1
        latest_date = max(dates)
        expected = next_occurrence(latest_date, frequency)
        for row in group:
            if row.recurrence_source == "user":
                continue
            if (
                row.recurrence_frequency != frequency
                or row.recurrence_group_key != key
                or row.next_expected_date != expected
            ):
                updated += 1
            row.recurrence_frequency = frequency
            row.recurrence_confidence = confidence
            row.recurrence_source = source
            row.recurrence_group_key = key
            row.next_expected_date = expected
    db.commit()
    return {
        "groups_detected": detected_groups,
        "transactions_updated": updated,
        "ollama_groups": ai_groups,
    }


def set_user_recurrence(transaction: Transaction, frequency: str | None) -> None:
    transaction.recurrence_frequency = frequency
    if frequency is None:
        transaction.recurrence_confidence = None
        transaction.recurrence_source = None
        transaction.recurrence_group_key = None
        transaction.next_expected_date = None
        return
    transaction.recurrence_confidence = Decimal("1.0000")
    transaction.recurrence_source = "user"
    transaction.recurrence_group_key = recurrence_group_key(transaction)
    transaction.next_expected_date = next_occurrence(
        transaction.transaction_date, frequency
    )


def _falls_in_month(value: date, year: int, month: int) -> bool:
    return value.year == year and value.month == month


def _matching_actual_exists(
    db: Session, source: Transaction, year: int, month: int
) -> bool:
    candidates = list(
        db.scalars(
            select(Transaction).where(
                Transaction.user_id == source.user_id,
                Transaction.is_validated.is_(True),
                Transaction.is_duplicate.is_(False),
                Transaction.transaction_type == source.transaction_type,
                Transaction.currency == source.currency,
                Transaction.transaction_date >= date(year, month, 1),
                Transaction.transaction_date
                <= date(year, month, calendar.monthrange(year, month)[1]),
            )
        ).all()
    )
    tolerance = max(Decimal("1.00"), Decimal(source.amount) * Decimal("0.08"))
    merchant = normalize_merchant(source.vendor)
    return any(
        normalize_merchant(item.vendor) == merchant
        and abs(Decimal(item.amount) - Decimal(source.amount)) <= tolerance
        for item in candidates
    )


def generate_budget_proposals(
    db: Session,
    year: int,
    month: int,
    user_id: int = 1,
    use_local_ai: bool = False,
) -> list[BudgetProposal]:
    detect_recurring_transactions(db, user_id, use_local_ai)
    recurring = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.is_validated.is_(True),
                Transaction.is_duplicate.is_(False),
                Transaction.transaction_type == "debit",
                Transaction.recurrence_frequency.is_not(None),
            )
            .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        ).all()
    )
    latest_by_group: dict[str, Transaction] = {}
    for row in recurring:
        key = row.recurrence_group_key or recurrence_group_key(row)
        latest_by_group.setdefault(key, row)

    for source in latest_by_group.values():
        expected = next_occurrence(
            source.transaction_date, source.recurrence_frequency or "monthly"
        )
        while expected < date(year, month, 1):
            expected = next_occurrence(expected, source.recurrence_frequency)
        if not _falls_in_month(expected, year, month):
            continue
        if _matching_actual_exists(db, source, year, month):
            continue
        existing = db.scalar(
            select(BudgetProposal).where(
                BudgetProposal.source_transaction_id == source.id,
                BudgetProposal.year == year,
                BudgetProposal.month == month,
            )
        )
        if existing is None:
            db.execute(
                insert(BudgetProposal)
                .values(
                    user_id=user_id,
                    source_transaction_id=source.id,
                    category_id=source.category_id,
                    year=year,
                    month=month,
                    merchant=source.vendor,
                    amount=source.amount,
                    currency=source.currency,
                    recurrence_frequency=source.recurrence_frequency,
                    expected_date=expected,
                    confidence=source.recurrence_confidence,
                    detection_source=source.recurrence_source or "detected",
                )
                .on_conflict_do_nothing(
                    index_elements=["source_transaction_id", "year", "month"]
                )
            )
    db.commit()
    return list(
        db.scalars(
            select(BudgetProposal)
            .where(
                BudgetProposal.user_id == user_id,
                BudgetProposal.year == year,
                BudgetProposal.month == month,
            )
            .order_by(BudgetProposal.status, BudgetProposal.expected_date)
        ).all()
    )


def confirm_budget_proposal(
    db: Session, proposal: BudgetProposal
) -> MonthlyBudget:
    if proposal.status == "confirmed":
        budget = db.scalar(
            select(MonthlyBudget).where(
                MonthlyBudget.user_id == proposal.user_id,
                MonthlyBudget.year == proposal.year,
                MonthlyBudget.month == proposal.month,
                MonthlyBudget.category_id == proposal.category_id,
            )
        )
        if budget is None:
            raise ValueError("Confirmed proposal has no matching budget")
        return budget

    budget = db.scalar(
        select(MonthlyBudget).where(
            MonthlyBudget.user_id == proposal.user_id,
            MonthlyBudget.year == proposal.year,
            MonthlyBudget.month == proposal.month,
            MonthlyBudget.category_id == proposal.category_id,
        )
    )
    note = f"Recurring proposal: {proposal.merchant}"
    if budget:
        budget.amount = Decimal(budget.amount) + Decimal(proposal.amount)
        if note not in (budget.notes or ""):
            budget.notes = "; ".join(filter(None, [budget.notes, note]))
    else:
        budget = MonthlyBudget(
            user_id=proposal.user_id,
            category_id=proposal.category_id,
            year=proposal.year,
            month=proposal.month,
            amount=proposal.amount,
            currency=proposal.currency,
            notes=note,
        )
        db.add(budget)
    proposal.status = "confirmed"
    proposal.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(budget)
    return budget
