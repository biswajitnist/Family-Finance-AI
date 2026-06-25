from decimal import Decimal

from pydantic import BaseModel


class CategoryTotal(BaseModel):
    category: str
    amount: Decimal


class MonthlyTotal(BaseModel):
    month: str
    income: Decimal
    expenses: Decimal


class DashboardSummary(BaseModel):
    currency: str
    income: Decimal
    expenses: Decimal
    net_cash_flow: Decimal
    savings_rate: Decimal
    pending_review: int
    budget_total: Decimal
    budget_spent: Decimal
    budget_remaining: Decimal
    budget_percentage: Decimal
    account_balance: Decimal
    investments: Decimal
    debt_balance: Decimal
    property_value: Decimal
    net_worth: Decimal
    fx_warnings: list[str] = []
    upcoming_bills: list[dict]
    spending_by_category: list[CategoryTotal]
    monthly_trend: list[MonthlyTotal]
