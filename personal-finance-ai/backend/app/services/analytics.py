from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.finance import Insurance, Investment, Loan, Property
from app.models.transaction import Transaction
from app.services.currency_service import (
    base_currency,
    convert_amount,
    converted_total,
    latest_rate,
)
from app.services.insurance_payment_service import insurance_payment_summary
from app.services.loan_balance_service import loan_balance


def investment_analytics(db: Session) -> dict:
    items = db.scalars(select(Investment)).all()
    reporting_currency = base_currency(db)
    priced_items = [
        item for item in items if item.quantity > 0 and item.average_price > 0
    ]
    cost_basis = sum(
        (
            convert_amount(
                db,
                item.quantity * item.average_price,
                item.purchase_currency,
                reporting_currency,
            )
            or Decimal("0")
            for item in priced_items
        ),
        Decimal("0"),
    )
    converted_values = {
        item.id: convert_amount(
            db,
            item.current_value,
            item.currency or item.base_currency,
            reporting_currency,
        )
        for item in items
    }
    current_value = sum(
        (value or Decimal("0") for value in converted_values.values()),
        Decimal("0"),
    )
    priced_current_value = sum(
        (converted_values[item.id] or Decimal("0") for item in priced_items),
        Decimal("0"),
    )
    unpriced_value = current_value - priced_current_value
    allocation: dict[str, Decimal] = {}
    country_allocation: dict[str, Decimal] = {}
    currency_allocation: dict[str, Decimal] = {}
    for item in items:
        value = converted_values[item.id] or Decimal("0")
        allocation[item.asset_type] = (
            allocation.get(item.asset_type, Decimal("0")) + value
        )
        country = item.country or "Other"
        country_allocation[country] = (
            country_allocation.get(country, Decimal("0")) + value
        )
        currency = item.market_currency or item.purchase_currency or item.currency
        currency_allocation[currency] = (
            currency_allocation.get(currency, Decimal("0")) + value
        )
    indian_items = [item for item in items if item.purchase_currency == "INR"]
    indian_value_inr = sum(
        (item.native_value or Decimal("0") for item in indian_items), Decimal("0")
    )
    indian_value_base = sum(
        (converted_values[item.id] or Decimal("0") for item in indian_items),
        Decimal("0"),
    )
    indian_rate = latest_rate(db, "INR", reporting_currency)
    missing_fx = sorted(
        {
            f"{(item.currency or item.base_currency).upper()} → {reporting_currency}"
            for item in items
            if converted_values[item.id] is None
        }
    )
    def allocation_rows(values: dict[str, Decimal], key: str) -> list[dict]:
        return [
            {
                key: name,
                "value": value,
                "percentage": (
                    value / current_value * 100
                    if current_value
                    else Decimal("0")
                ).quantize(Decimal("0.01")),
            }
            for name, value in sorted(
                values.items(), key=lambda entry: entry[1], reverse=True
            )
        ]

    return {
        "base_currency": reporting_currency,
        "cost_basis": cost_basis,
        "current_value": current_value,
        "profit_loss": priced_current_value - cost_basis if priced_items else None,
        "cost_basis_complete": len(priced_items) == len(items),
        "value_missing_cost_basis": unpriced_value,
        "indian_investments": {
            "count": len(indian_items),
            "value_inr": indian_value_inr,
            "value_base": indian_value_base,
            "fx_rate_to_base": indian_rate,
        },
        "allocation": allocation_rows(allocation, "asset_type"),
        "country_allocation": allocation_rows(country_allocation, "country"),
        "currency_allocation": allocation_rows(currency_allocation, "currency"),
        "missing_fx_rates": missing_fx,
    }


def _loan_payoff(loan: Loan, balance: Decimal | None = None) -> dict:
    balance = balance if balance is not None else loan.current_balance
    monthly_rate = loan.interest_rate / Decimal("1200")
    payment = loan.monthly_payment
    months = 0
    interest_paid = Decimal("0")
    while balance > 0 and payment > 0 and months < 1200:
        interest = balance * monthly_rate
        principal = payment - interest
        if principal <= 0:
            return {"months": None, "interest": None, "warning": "Payment is too low"}
        balance -= principal
        interest_paid += interest
        months += 1
    return {
        "months": months if payment > 0 else None,
        "interest": interest_paid.quantize(Decimal("0.01")),
        "warning": None if payment > 0 else "Monthly payment is missing",
    }


def debt_analytics(db: Session) -> dict:
    loans = list(db.scalars(select(Loan)).all())
    reporting_currency = base_currency(db)
    adjustments = {
        item.id: loan_balance(db, item, len(loans)) for item in loans
    }
    converted_balances = {
        item.id: convert_amount(
            db,
            adjustments[item.id].adjusted_balance,
            item.currency,
            reporting_currency,
        )
        for item in loans
    }
    total_balance = sum(
        (value or Decimal("0") for value in converted_balances.values()),
        Decimal("0"),
    )
    missing_balance_fx = {
        f"{item.currency} → {reporting_currency}"
        for item in loans
        if converted_balances[item.id] is None
    }
    monthly_payments, missing_payment_fx = converted_total(
        db, loans, "monthly_payment", to_currency=reporting_currency
    )
    return {
        "base_currency": reporting_currency,
        "total_balance": total_balance,
        "monthly_payments": monthly_payments,
        "missing_fx_rates": sorted({*missing_balance_fx, *missing_payment_fx}),
        "loans": [
            {
                "id": item.id,
                "lender": item.lender,
                "recorded_balance": adjustments[item.id].recorded_balance,
                "adjusted_balance": adjustments[item.id].adjusted_balance,
                "payments_applied": adjustments[item.id].payments_applied,
                "matched_transaction_count": (
                    adjustments[item.id].matched_transaction_count
                ),
                **_loan_payoff(item, adjustments[item.id].adjusted_balance),
            }
            for item in loans
        ],
    }


def property_analytics(db: Session) -> dict:
    properties = db.scalars(select(Property)).all()
    reporting_currency = base_currency(db)
    results = []
    for item in properties:
        annual_rent = item.monthly_rental_income * 12
        annual_net = (item.monthly_rental_income - item.monthly_costs) * 12
        current_value_base = convert_amount(
            db, item.current_value, item.currency, reporting_currency
        )
        purchase_price_base = convert_amount(
            db, item.purchase_price, item.currency, reporting_currency
        )
        annual_rent_base = convert_amount(
            db, annual_rent, item.currency, reporting_currency
        )
        annual_net_base = convert_amount(
            db, annual_net, item.currency, reporting_currency
        )
        results.append(
            {
                "id": item.id,
                "name": item.name,
                "annual_rent": annual_rent,
                "annual_net_cash_flow": annual_net,
                "currency": item.currency,
                "base_currency": reporting_currency,
                "purchase_price_base": purchase_price_base,
                "current_value_base": current_value_base,
                "annual_rent_base": annual_rent_base,
                "annual_net_cash_flow_base": annual_net_base,
                "fx_rate_to_base": latest_rate(
                    db, item.currency, reporting_currency
                ),
                "gross_yield": (
                    annual_rent / item.current_value * 100
                    if item.current_value
                    else Decimal("0")
                ).quantize(Decimal("0.01")),
                "net_yield": (
                    annual_net / item.current_value * 100
                    if item.current_value
                    else Decimal("0")
                ).quantize(Decimal("0.01")),
            }
        )
    total_value, missing_fx = converted_total(
        db, properties, "current_value", to_currency=reporting_currency
    )
    annual_rental_income, rent_missing_fx = converted_total(
        db,
        properties,
        "monthly_rental_income",
        to_currency=reporting_currency,
    )
    return {
        "base_currency": reporting_currency,
        "total_value": total_value,
        "annual_rental_income": annual_rental_income * 12,
        "missing_fx_rates": sorted({*missing_fx, *rent_missing_fx}),
        "properties": results,
    }


def protection_analytics(db: Session) -> dict:
    policies = db.scalars(select(Insurance).where(Insurance.is_active.is_(True))).all()
    coverage = sum((item.coverage_amount for item in policies), Decimal("0"))
    annual_premiums = Decimal("0")
    factors = {"monthly": 12, "quarterly": 4, "yearly": 1}
    for item in policies:
        annual_premiums += item.premium_amount * factors.get(item.premium_frequency, 1)
    liquid_balance = db.scalar(
        select(func.coalesce(func.sum(Account.current_balance), 0)).where(
            Account.type.in_(["bank", "cash"]), Account.is_active.is_(True)
        )
    )
    return {
        "active_policies": len(policies),
        "total_coverage": coverage,
        "annual_premiums": annual_premiums,
        "emergency_fund": Decimal(liquid_balance or 0),
        **insurance_payment_summary(db),
    }


def net_worth_projection(db: Session, years: int = 10) -> dict:
    reporting_currency = base_currency(db)
    account_assets, _ = converted_total(
        db,
        db.scalars(select(Account)).all(),
        "current_balance",
        to_currency=reporting_currency,
    )
    investment_assets, _ = converted_total(
        db,
        db.scalars(select(Investment)).all(),
        "current_value",
        to_currency=reporting_currency,
    )
    property_assets, _ = converted_total(
        db,
        db.scalars(select(Property)).all(),
        "current_value",
        to_currency=reporting_currency,
    )
    loans = list(db.scalars(select(Loan)).all())
    debts = sum(
        (
            convert_amount(
                db,
                loan_balance(db, item, len(loans)).adjusted_balance,
                item.currency,
                reporting_currency,
            )
            or Decimal("0")
            for item in loans
        ),
        Decimal("0"),
    )
    assets = account_assets + investment_assets + property_assets
    current = assets - debts
    start = date(date.today().year - 1, date.today().month, 1)
    income = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.is_validated.is_(True),
                Transaction.is_duplicate.is_(False),
                Transaction.transaction_date >= start,
                Transaction.transaction_type == "credit",
            )
        )
        or 0
    )
    expenses = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.is_validated.is_(True),
                Transaction.is_duplicate.is_(False),
                Transaction.transaction_date >= start,
                Transaction.transaction_type == "debit",
            )
        )
        or 0
    )
    annual_savings = income - expenses
    projection = []
    projected = current
    for offset in range(years + 1):
        projection.append(
            {
                "year": date.today().year + offset,
                "net_worth": projected.quantize(Decimal("0.01")),
            }
        )
        projected = projected * Decimal("1.05") + annual_savings
    return {
        "current_net_worth": current,
        "annual_savings_basis": annual_savings,
        "assumed_growth_rate": Decimal("5.00"),
        "projection": projection,
    }
