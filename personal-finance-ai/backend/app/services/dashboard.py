from datetime import date
from decimal import Decimal

from sqlalchemy import case, extract, func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.category import Category
from app.models.finance import Investment, Loan, MonthlyBudget, Property, Rule
from app.models.transaction import Transaction
from app.services.currency_service import base_currency, convert_amount, converted_total
from app.services.loan_balance_service import loan_balance


def dashboard_summary(db: Session, year: int, month: int) -> dict:
    period_filters = (
        Transaction.is_validated.is_(True),
        Transaction.is_duplicate.is_(False),
        extract("year", Transaction.transaction_date) == year,
        extract("month", Transaction.transaction_date) == month,
    )
    income, expenses = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.transaction_type == "credit", Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.transaction_type == "debit", Transaction.amount),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(*period_filters)
    ).one()
    income = Decimal(income)
    expenses = Decimal(expenses)
    savings_rate = (
        ((income - expenses) / income * 100).quantize(Decimal("0.01"))
        if income
        else Decimal("0")
    )

    category_rows = db.execute(
        select(
            func.coalesce(Category.name, "Uncategorized"),
            func.sum(Transaction.amount),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(*period_filters, Transaction.transaction_type == "debit")
        .group_by(Category.name)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()

    trend_start = date(year - 1, month, 1) if month == 12 else date(year, month + 1, 1)
    trend_start = date(
        trend_start.year - 1 if trend_start.month <= 6 else trend_start.year,
        trend_start.month + 6 if trend_start.month <= 6 else trend_start.month - 6,
        1,
    )
    trend_rows = db.execute(
        select(
            func.strftime("%Y-%m", Transaction.transaction_date),
            func.sum(
                case(
                    (Transaction.transaction_type == "credit", Transaction.amount),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (Transaction.transaction_type == "debit", Transaction.amount),
                    else_=0,
                )
            ),
        )
        .where(
            Transaction.is_validated.is_(True),
            Transaction.is_duplicate.is_(False),
            Transaction.transaction_date >= trend_start,
        )
        .group_by(func.strftime("%Y-%m", Transaction.transaction_date))
        .order_by(func.strftime("%Y-%m", Transaction.transaction_date))
    ).all()
    pending = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.is_validated.is_(False),
            Transaction.is_duplicate.is_(False),
        )
    )
    budget_total = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(MonthlyBudget.amount), 0)).where(
                MonthlyBudget.year == year,
                MonthlyBudget.month == month,
            )
        )
        or 0
    )
    budget_spent = expenses if budget_total else Decimal("0")
    reporting_currency = base_currency(db)
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
        (value or Decimal("0") for _, value in converted_debts), Decimal("0")
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
        "net_worth": account_balance + investments + property_value - debt_balance,
        "fx_warnings": sorted(
            {
                *account_fx_missing,
                *investment_fx_missing,
                *debt_fx_missing,
                *property_fx_missing,
            }
        ),
        "upcoming_bills": [
            {"name": item.name, "match": item.condition_value} for item in recurring
        ],
        "spending_by_category": [
            {"category": category, "amount": Decimal(amount)}
            for category, amount in category_rows
        ],
        "monthly_trend": [
            {
                "month": trend_month,
                "income": Decimal(trend_income or 0),
                "expenses": Decimal(trend_expenses or 0),
            }
            for trend_month, trend_income, trend_expenses in trend_rows
        ],
    }
