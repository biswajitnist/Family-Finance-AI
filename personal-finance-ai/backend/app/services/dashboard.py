from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.category import Category
from app.models.finance import Investment, Loan, MonthlyBudget, Property, Rule
from app.models.transaction import Transaction
from app.services.currency_service import base_currency, convert_amount, converted_total
from app.services.loan_balance_service import loan_balance


def dashboard_summary(db: Session, year: int, month: int) -> dict:
    reporting_currency = base_currency(db)
    period_filters = (
        Transaction.is_validated.is_(True),
        Transaction.is_duplicate.is_(False),
        extract("year", Transaction.transaction_date) == year,
        extract("month", Transaction.transaction_date) == month,
    )
    period_transactions = list(db.scalars(select(Transaction).where(*period_filters)))
    income = Decimal("0")
    expenses = Decimal("0")
    transaction_fx_missing: set[str] = set()
    category_totals: dict[str, Decimal] = {}
    category_names = {
        item.id: item.name for item in db.scalars(select(Category)).all()
    }
    for transaction in period_transactions:
        converted = convert_amount(
            db,
            transaction.amount,
            transaction.currency,
            reporting_currency,
        )
        if converted is None:
            transaction_fx_missing.add(
                f"{transaction.currency.upper()} → {reporting_currency}"
            )
            continue
        if transaction.transaction_type == "credit":
            income += converted
        else:
            expenses += converted
            category = category_names.get(transaction.category_id, "Uncategorized")
            category_totals[category] = (
                category_totals.get(category, Decimal("0")) + converted
            )
    savings_rate = (
        ((income - expenses) / income * 100).quantize(Decimal("0.01"))
        if income
        else Decimal("0")
    )

    trend_start = date(year - 1, month, 1) if month == 12 else date(year, month + 1, 1)
    trend_start = date(
        trend_start.year - 1 if trend_start.month <= 6 else trend_start.year,
        trend_start.month + 6 if trend_start.month <= 6 else trend_start.month - 6,
        1,
    )
    trend_transactions = db.scalars(
        select(Transaction)
        .where(
            Transaction.is_validated.is_(True),
            Transaction.is_duplicate.is_(False),
            Transaction.transaction_date >= trend_start,
        )
        .order_by(Transaction.transaction_date)
    ).all()
    trend_totals: dict[str, dict[str, Decimal]] = {}
    for transaction in trend_transactions:
        trend_month = transaction.transaction_date.strftime("%Y-%m")
        converted = convert_amount(
            db,
            transaction.amount,
            transaction.currency,
            reporting_currency,
        )
        if converted is None:
            transaction_fx_missing.add(
                f"{transaction.currency.upper()} → {reporting_currency}"
            )
            continue
        bucket = trend_totals.setdefault(
            trend_month,
            {"income": Decimal("0"), "expenses": Decimal("0")},
        )
        if transaction.transaction_type == "credit":
            bucket["income"] += converted
        else:
            bucket["expenses"] += converted
    pending = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.is_validated.is_(False),
            Transaction.is_duplicate.is_(False),
        )
    )
    budgets = list(
        db.scalars(
            select(MonthlyBudget).where(
                MonthlyBudget.year == year,
                MonthlyBudget.month == month,
            )
        )
    )
    budget_total, budget_fx_missing = converted_total(
        db,
        budgets,
        "amount",
        to_currency=reporting_currency,
    )
    budget_spent = expenses if budget_total else Decimal("0")
    account_balance, account_fx_missing = converted_total(
        db,
        db.scalars(
            select(Account).where(Account.is_active.is_(True))
        ).all(),
        "current_balance",
        to_currency=reporting_currency,
    )
    investments, investment_fx_missing = converted_total(
        db,
        db.scalars(select(Investment)).all(),
        "current_value",
        to_currency=reporting_currency,
    )
    loans = list(db.scalars(select(Loan)).all())
    converted_debts = [
        (
            item,
            convert_amount(
                db,
                loan_balance(db, item, len(loans)).adjusted_balance,
                item.currency,
                reporting_currency,
            ),
        )
        for item in loans
    ]
    debt_balance = sum(
        (
            value or Decimal("0")
            for item, value in converted_debts
            if item.direction != "lent"
        ),
        Decimal("0"),
    )
    loan_receivables = sum(
        (
            value or Decimal("0")
            for item, value in converted_debts
            if item.direction == "lent"
        ),
        Decimal("0"),
    )
    debt_fx_missing = {
        f"{item.currency} → {reporting_currency}"
        for item, value in converted_debts
        if value is None
    }
    property_value, property_fx_missing = converted_total(
        db,
        db.scalars(select(Property)).all(),
        "current_value",
        to_currency=reporting_currency,
    )
    recurring = db.scalars(
        select(Rule)
        .where(Rule.is_active.is_(True), Rule.condition_type == "recurring")
        .order_by(Rule.priority)
        .limit(5)
    ).all()
    return {
        "currency": reporting_currency,
        "income": income,
        "expenses": expenses,
        "net_cash_flow": income - expenses,
        "savings_rate": savings_rate,
        "pending_review": pending or 0,
        "budget_total": budget_total,
        "budget_spent": budget_spent,
        "budget_remaining": budget_total - budget_spent,
        "budget_percentage": (
            (budget_spent / budget_total * 100).quantize(Decimal("0.01"))
            if budget_total
            else Decimal("0")
        ),
        "account_balance": account_balance,
        "investments": investments,
        "debt_balance": debt_balance,
        "property_value": property_value,
        "net_worth": (
            account_balance
            + investments
            + property_value
            + loan_receivables
            - debt_balance
        ),
        "fx_warnings": sorted(
            {
                *account_fx_missing,
                *investment_fx_missing,
                *debt_fx_missing,
                *property_fx_missing,
                *budget_fx_missing,
                *transaction_fx_missing,
            }
        ),
        "upcoming_bills": [
            {"name": item.name, "match": item.condition_value} for item in recurring
        ],
        "spending_by_category": [
            {"category": category, "amount": amount.quantize(Decimal("0.01"))}
            for category, amount in sorted(
                category_totals.items(),
                key=lambda entry: entry[1],
                reverse=True,
            )
        ],
        "monthly_trend": [
            {
                "month": trend_month,
                "income": values["income"].quantize(Decimal("0.01")),
                "expenses": values["expenses"].quantize(Decimal("0.01")),
            }
            for trend_month, values in sorted(trend_totals.items())
        ],
    }
