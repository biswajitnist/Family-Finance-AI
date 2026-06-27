import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.category import Category
from app.models.finance import (
    AIDashboardInsight,
    AIRecommendation,
    FinancialAlert,
    FinancialForecast,
    Insurance,
    Investment,
    Loan,
    Property,
)
from app.models.transaction import Transaction
from app.services.ai_service import generate_local_json
from app.services.currency_service import base_currency, convert_amount, converted_total
from app.services.loan_balance_service import loan_balance

ZERO = Decimal("0")


class InsightWording(BaseModel):
    summary_sentence_1: str = Field(max_length=240)
    summary_sentence_2: str = Field(max_length=240)
    explanation: str = Field(max_length=1200)


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _source_hash(
    transactions: list[Transaction],
    year: int,
    month: int,
    financial_position: dict[str, Decimal],
) -> str:
    values = [
        (
            item.id,
            str(item.transaction_date),
            str(item.amount),
            item.transaction_type,
            item.category_id,
            item.is_validated,
            item.is_duplicate,
        )
        for item in transactions
    ]
    return hashlib.sha256(
        json.dumps(
            [
                "advisor-financial-position-v2",
                year,
                month,
                values,
                {key: str(value) for key, value in financial_position.items()},
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _monthly_history(
    transactions: list[Transaction], current_month: str
) -> tuple[dict[str, dict[str, Decimal]], dict[str, dict[str, Decimal]]]:
    totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"credit": ZERO, "debit": ZERO}
    )
    categories: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: ZERO)
    )
    for item in transactions:
        key = item.transaction_date.strftime("%Y-%m")
        if key > current_month:
            continue
        totals[key][item.transaction_type] += Decimal(item.amount)
        if item.transaction_type == "debit":
            categories[key][str(item.category_id or "uncategorized")] += Decimal(
                item.amount
            )
    return totals, categories


def _average(values: list[Decimal]) -> Decimal:
    return (sum(values, ZERO) / len(values)) if values else ZERO


def _forecast_data(db: Session, year: int, month: int) -> dict:
    key = _month_key(year, month)
    all_transactions = list(
        db.scalars(
            select(Transaction).order_by(Transaction.transaction_date, Transaction.id)
        ).all()
    )
    transactions = [
        item for item in all_transactions if item.is_validated and not item.is_duplicate
    ]
    duplicate_count = sum(item.is_duplicate for item in all_transactions)
    duplicate_ids = [item.id for item in all_transactions if item.is_duplicate]
    totals, category_history = _monthly_history(transactions, key)
    historical_months = sorted(item for item in totals if item < key)[-6:]
    sample_months = historical_months[-3:] or historical_months
    current = totals.get(key, {"credit": ZERO, "debit": ZERO})
    expected_income = max(
        current["credit"],
        _average([totals[item]["credit"] for item in sample_months]),
    )
    variable_expenses = _average([totals[item]["debit"] for item in sample_months])
    loans = list(db.scalars(select(Loan)).all())
    reporting_currency = base_currency(db)
    loan_payments, _ = converted_total(
        db, loans, "monthly_payment", to_currency=reporting_currency
    )
    debt_balance = sum(
        (
            convert_amount(
                db,
                loan_balance(db, item, len(loans)).adjusted_balance,
                item.currency,
                reporting_currency,
            )
            or ZERO
            for item in loans
        ),
        ZERO,
    )
    investment_value, _ = converted_total(
        db,
        db.scalars(select(Investment)).all(),
        "current_value",
        to_currency=reporting_currency,
    )
    property_value, _ = converted_total(
        db,
        db.scalars(select(Property)).all(),
        "current_value",
        to_currency=reporting_currency,
    )
    insurance_payments = ZERO
    for item in db.scalars(
        select(Insurance).where(Insurance.is_active.is_(True))
    ).all():
        premium = Decimal(item.premium_amount)
        factor = {
            "monthly": Decimal("1"),
            "quarterly": Decimal("0.3333"),
            "yearly": Decimal("0.0833"),
            "annual": Decimal("0.0833"),
        }.get(item.premium_frequency.casefold(), Decimal("1"))
        insurance_payments += premium * factor
    recurring_impact = (loan_payments + insurance_payments).quantize(Decimal("0.01"))
    expected_expenses = max(current["debit"], variable_expenses, recurring_impact)
    expected_income = expected_income.quantize(Decimal("0.01"))
    expected_expenses = expected_expenses.quantize(Decimal("0.01"))
    expected_surplus = expected_income - expected_expenses
    account_balance, _ = converted_total(
        db,
        db.scalars(
            select(Account).where(Account.is_active.is_(True))
        ).all(),
        "current_balance",
        to_currency=reporting_currency,
    )
    financial_position = {
        "cash_balance": account_balance.quantize(Decimal("0.01")),
        "investment_value": investment_value.quantize(Decimal("0.01")),
        "property_value": property_value.quantize(Decimal("0.01")),
        "debt_balance": debt_balance.quantize(Decimal("0.01")),
        "monthly_loan_payments": loan_payments.quantize(Decimal("0.01")),
        "net_worth": (
            account_balance + investment_value + property_value - debt_balance
        ).quantize(Decimal("0.01")),
    }

    category_names = {
        str(item.id): item.name for item in db.scalars(select(Category)).all()
    }
    category_risks = []
    current_categories = category_history.get(key, {})
    all_category_ids = set().union(
        *(category_history[item].keys() for item in sample_months),
        current_categories.keys(),
    )
    for category_id in all_category_ids:
        average = _average(
            [category_history[item].get(category_id, ZERO) for item in sample_months]
        )
        spent = current_categories.get(category_id, ZERO)
        if average > 0 and spent > average * Decimal("1.15"):
            category_risks.append(
                {
                    "category": category_names.get(category_id, "Uncategorized"),
                    "category_id": category_id,
                    "current": str(spent.quantize(Decimal("0.01"))),
                    "average": str(average.quantize(Decimal("0.01"))),
                    "over_by": str((spent - average).quantize(Decimal("0.01"))),
                    "percentage": str(
                        ((spent / average - 1) * 100).quantize(Decimal("0.1"))
                    ),
                }
            )
    category_risks.sort(key=lambda item: Decimal(item["over_by"]), reverse=True)
    historical_debits = [
        Decimal(item.amount)
        for item in transactions
        if item.transaction_type == "debit"
        and item.transaction_date.strftime("%Y-%m") < key
    ]
    average_debit = _average(historical_debits)
    unusual_transactions = [
        {
            "id": item.id,
            "vendor": item.vendor,
            "amount": str(Decimal(item.amount).quantize(Decimal("0.01"))),
        }
        for item in transactions
        if item.transaction_type == "debit"
        and item.transaction_date.strftime("%Y-%m") == key
        and Decimal(item.amount) > max(Decimal("500"), average_debit * 3)
    ]
    salary_category_ids = {
        item.id
        for item in db.scalars(select(Category).where(Category.name.ilike("Salary")))
    }
    historical_salary = any(
        item.category_id in salary_category_ids
        and item.transaction_type == "credit"
        and item.transaction_date.strftime("%Y-%m") < key
        for item in transactions
    )
    current_salary = any(
        item.category_id in salary_category_ids
        and item.transaction_type == "credit"
        and item.transaction_date.strftime("%Y-%m") == key
        for item in transactions
    )
    subscription_ids = {
        item.id
        for item in db.scalars(
            select(Category).where(Category.name.ilike("Subscriptions"))
        )
    }
    previous_subscriptions: dict[str, Decimal] = {}
    current_subscriptions: dict[str, Decimal] = {}
    for item in transactions:
        if item.category_id not in subscription_ids or item.transaction_type != "debit":
            continue
        merchant = item.vendor.casefold()
        item_month = item.transaction_date.strftime("%Y-%m")
        if item_month < key:
            previous_subscriptions[merchant] = max(
                previous_subscriptions.get(merchant, ZERO), Decimal(item.amount)
            )
        elif item_month == key:
            current_subscriptions[merchant] = max(
                current_subscriptions.get(merchant, ZERO), Decimal(item.amount)
            )
    subscription_increases = [
        {
            "merchant": merchant,
            "previous": str(previous_subscriptions[merchant]),
            "current": str(amount),
            "transaction_ids": [
                item.id
                for item in transactions
                if item.transaction_date.strftime("%Y-%m") == key
                and item.vendor.casefold() == merchant
                and item.category_id in subscription_ids
            ],
        }
        for merchant, amount in current_subscriptions.items()
        if merchant in previous_subscriptions
        and amount > previous_subscriptions[merchant] * Decimal("1.10")
    ]
    confidence = min(
        Decimal("0.95"),
        Decimal("0.55") + Decimal("0.07") * len(sample_months),
    )
    return {
        "month": key,
        "transactions": transactions,
        "source_hash": _source_hash(all_transactions, year, month, financial_position),
        "expected_income": expected_income,
        "expected_expenses": expected_expenses,
        "expected_surplus": expected_surplus,
        "expected_month_end_balance": (
            account_balance + expected_income - expected_expenses
        ).quantize(Decimal("0.01")),
        "recurring_payment_impact": recurring_impact,
        "confidence_score": confidence,
        "category_risks": category_risks[:5],
        "account_balance": account_balance.quantize(Decimal("0.01")),
        "financial_position": financial_position,
        "average_expenses": variable_expenses.quantize(Decimal("0.01")),
        "sample_months": sample_months,
        "duplicate_count": duplicate_count,
        "duplicate_ids": duplicate_ids,
        "missing_salary": historical_salary and not current_salary,
        "salary_category_ids": salary_category_ids,
        "subscription_increases": subscription_increases,
        "unusual_transactions": unusual_transactions,
    }


def _wording(data: dict, use_local_ai: bool) -> tuple[str, str, str, bool]:
    surplus = data["expected_surplus"]
    sentence_1 = (
        f"You are expected to end this month with €{abs(surplus):,.2f} "
        f"{'surplus cash' if surplus >= 0 else 'cash deficit'}."
    )
    risks = data["category_risks"]
    sentence_2 = (
        f"{risks[0]['category']} spending is {risks[0]['percentage']}% above "
        f"its recent monthly average."
        if risks
        else "No category is currently more than 15% above its recent average."
    )
    explanation = (
        f"The forecast uses {len(data['sample_months'])} prior month(s), validated "
        "non-duplicate transactions, active account balances, loan payments, and "
        "insurance premiums. Investment values, debt balances, and property values "
        "provide net-worth context. Ollama only rewrites these calculated facts."
    )
    if not use_local_ai:
        return sentence_1, sentence_2, explanation, False
    prompt = (
        "Rewrite the following deterministic local finance results in simple language. "
        "Do not calculate, change, or invent any number. Return only JSON with "
        "summary_sentence_1, summary_sentence_2, explanation. Use exactly two short "
        "summary sentences and avoid guaranteed investment advice.\n"
        + json.dumps(
            {
                "sentence_1": sentence_1,
                "sentence_2": sentence_2,
                "explanation": explanation,
            }
        )
    )
    try:
        result = InsightWording.model_validate_json(generate_local_json(prompt))
        return (
            result.summary_sentence_1,
            result.summary_sentence_2,
            result.explanation,
            True,
        )
    except (
        httpx.HTTPError,
        RuntimeError,
        ValidationError,
        ValueError,
        KeyError,
    ):
        return sentence_1, sentence_2, explanation, False


def _recommendations(data: dict) -> list[dict]:
    items = []
    emergency_target = data["average_expenses"] * 3
    if emergency_target > 0 and data["account_balance"] < emergency_target:
        gap = emergency_target - data["account_balance"]
        items.append(
            {
                "title": "Strengthen your emergency fund",
                "description": "Build a reserve covering about three typical months.",
                "priority": "High",
                "estimated_impact_amount": gap,
                "recommendation_type": "emergency_fund",
                "explanation": (
                    "Available cash is below three months of recent expenses."
                ),
                "related_data": {
                    "cash_balance": str(data["account_balance"]),
                    "target": str(emergency_target.quantize(Decimal("0.01"))),
                },
            }
        )
    if data["category_risks"]:
        risk = data["category_risks"][0]
        items.append(
            {
                "title": f"Review {risk['category']} spending",
                "description": (
                    f"Spending is €{risk['over_by']} above its recent average."
                ),
                "priority": "High" if Decimal(risk["percentage"]) >= 30 else "Medium",
                "estimated_impact_amount": Decimal(risk["over_by"]),
                "recommendation_type": "reduce_expenses",
                "explanation": "This category crossed the 15% overspending threshold.",
                "related_data": risk,
            }
        )
    if data["expected_surplus"] > 0:
        impact = (data["expected_surplus"] * Decimal("0.25")).quantize(Decimal("0.01"))
        items.append(
            {
                "title": "Automate part of the expected surplus",
                "description": (
                    "Move a portion to savings after essential payments clear."
                ),
                "priority": "Medium",
                "estimated_impact_amount": impact,
                "recommendation_type": "improve_savings",
                "explanation": (
                    "The deterministic forecast currently shows positive cash flow."
                ),
                "related_data": {"expected_surplus": str(data["expected_surplus"])},
            }
        )
    return items[:3]


def _alerts(data: dict) -> list[dict]:
    alerts = []
    current_month = data["month"]
    current_transactions = [
        item
        for item in data["transactions"]
        if item.transaction_date.strftime("%Y-%m") == current_month
    ]
    for risk in data["category_risks"][:2]:
        category_id = risk["category_id"]
        alerts.append(
            {
                "alert_type": "category_overspending",
                "severity": "high" if Decimal(risk["percentage"]) >= 30 else "medium",
                "message": f"{risk['category']} is {risk['percentage']}% above normal.",
                "reason": (
                    f"Current €{risk['current']} versus average €{risk['average']}."
                ),
                "recommended_action": (
                    "Review recent transactions and adjust the monthly plan."
                ),
                "transaction_ids": [
                    item.id
                    for item in current_transactions
                    if str(item.category_id or "uncategorized") == category_id
                    and item.transaction_type == "debit"
                ],
            }
        )
    duplicate_count = data["duplicate_count"]
    if duplicate_count:
        alerts.append(
            {
                "alert_type": "duplicate_transactions",
                "severity": "medium",
                "message": (
                    f"{duplicate_count} duplicate transaction(s) need attention."
                ),
                "reason": (
                    "Matching date, merchant, amount, type, and account were detected."
                ),
                "recommended_action": (
                    "Review duplicates before confirming imported rows."
                ),
                "transaction_ids": data["duplicate_ids"],
            }
        )
    if data["missing_salary"]:
        alerts.append(
            {
                "alert_type": "missing_expected_income",
                "severity": "high",
                "message": "Expected salary income is not recorded this month.",
                "reason": (
                    "Salary appeared in prior months but not in the selected month."
                ),
                "recommended_action": (
                    "Check the statement period or confirm the payment date."
                ),
                "transaction_ids": [
                    item.id
                    for item in data["transactions"]
                    if item.category_id in data["salary_category_ids"]
                    and item.transaction_type == "credit"
                ][-6:],
            }
        )
    for item in data["subscription_increases"][:1]:
        alerts.append(
            {
                "alert_type": "subscription_increase",
                "severity": "medium",
                "message": f"A subscription increased to €{item['current']}.",
                "reason": f"The prior recorded amount was €{item['previous']}.",
                "recommended_action": (
                    "Check the provider notice and cancel if no longer useful."
                ),
                "transaction_ids": item["transaction_ids"],
            }
        )
    for item in data["unusual_transactions"][:1]:
        alerts.append(
            {
                "alert_type": "large_unusual_transaction",
                "severity": "medium",
                "message": f"Large transaction of €{item['amount']} detected.",
                "reason": f"{item['vendor']} is well above the typical debit amount.",
                "recommended_action": (
                    "Confirm the transaction is expected and categorized."
                ),
                "transaction_ids": [item["id"]],
            }
        )
    emergency_target = data["average_expenses"] * 3
    if emergency_target > 0 and data["account_balance"] < emergency_target:
        alerts.append(
            {
                "alert_type": "emergency_fund",
                "severity": "medium",
                "message": "Cash reserves are below three typical months of expenses.",
                "reason": (
                    f"Balance €{data['account_balance']} versus target "
                    f"€{emergency_target.quantize(Decimal('0.01'))}."
                ),
                "recommended_action": "Build the reserve before adding optional risk.",
                "transaction_ids": [
                    item.id
                    for item in current_transactions
                    if item.transaction_type == "debit"
                ][:20],
            }
        )
    if data["expected_month_end_balance"] < 0:
        alerts.append(
            {
                "alert_type": "cash_flow_risk",
                "severity": "high",
                "message": "The month-end balance forecast is below zero.",
                "reason": (
                    "Expected expenses exceed available balance and expected income."
                ),
                "recommended_action": (
                    "Delay optional spending or arrange additional cash cover."
                ),
                "transaction_ids": [
                    item.id
                    for item in current_transactions
                    if item.transaction_type == "debit"
                ][:20],
            }
        )
    return alerts


def refresh_advisor(
    db: Session, year: int, month: int, use_local_ai: bool = False
) -> dict:
    key = _month_key(year, month)
    data = _forecast_data(db, year, month)
    sentence_1, sentence_2, explanation, local_ai_used = _wording(data, use_local_ai)
    db.execute(delete(AIDashboardInsight).where(AIDashboardInsight.month == key))
    db.execute(delete(FinancialForecast).where(FinancialForecast.month == key))
    db.execute(delete(AIRecommendation).where(AIRecommendation.month == key))
    db.execute(delete(FinancialAlert).where(FinancialAlert.month == key))
    insight = AIDashboardInsight(
        month=key,
        generated_at=datetime.now(),
        summary_sentence_1=sentence_1,
        summary_sentence_2=sentence_2,
        explanation=explanation,
        confidence_score=data["confidence_score"],
        source_data_hash=data["source_hash"],
        local_ai_used=local_ai_used,
    )
    forecast = FinancialForecast(
        month=key,
        expected_income=data["expected_income"],
        expected_expenses=data["expected_expenses"],
        expected_surplus=data["expected_surplus"],
        expected_month_end_balance=data["expected_month_end_balance"],
        recurring_payment_impact=data["recurring_payment_impact"],
        confidence_score=data["confidence_score"],
        category_risks=json.dumps(data["category_risks"]),
    )
    db.add_all([insight, forecast])
    db.flush()
    for item in _recommendations(data):
        db.add(
            AIRecommendation(
                month=key,
                related_data=json.dumps(item.pop("related_data")),
                **item,
            )
        )
    for item in _alerts(data):
        db.add(
            FinancialAlert(
                month=key,
                transaction_ids=json.dumps(item.pop("transaction_ids")),
                **item,
            )
        )
    db.commit()
    return advisor_dashboard(db, year, month, ensure_fresh=False)


def advisor_dashboard(
    db: Session, year: int, month: int, ensure_fresh: bool = True
) -> dict:
    key = _month_key(year, month)
    insight = db.scalar(
        select(AIDashboardInsight)
        .where(AIDashboardInsight.month == key)
        .order_by(AIDashboardInsight.id.desc())
    )
    if ensure_fresh:
        current_hash = _forecast_data(db, year, month)["source_hash"]
        if insight is None or insight.source_data_hash != current_hash:
            return refresh_advisor(db, year, month)
    if insight is None:
        return refresh_advisor(db, year, month)
    forecast = db.scalar(
        select(FinancialForecast)
        .where(FinancialForecast.month == key)
        .order_by(FinancialForecast.id.desc())
    )
    recommendations = list(
        db.scalars(
            select(AIRecommendation).where(
                AIRecommendation.month == key,
                AIRecommendation.status == "active",
            )
        ).all()
    )
    alerts = list(
        db.scalars(
            select(FinancialAlert).where(
                FinancialAlert.month == key,
                FinancialAlert.status == "active",
            )
        ).all()
    )
    alert_transaction_ids = {
        transaction_id
        for alert in alerts
        for transaction_id in json.loads(alert.transaction_ids or "[]")
    }
    alert_transactions = {
        item.id: item
        for item in db.scalars(
            select(Transaction).where(Transaction.id.in_(alert_transaction_ids))
        ).all()
    }
    category_names = {item.id: item.name for item in db.scalars(select(Category)).all()}
    account_names = {item.id: item.name for item in db.scalars(select(Account)).all()}

    def transaction_details(transaction_id: int) -> dict | None:
        item = alert_transactions.get(transaction_id)
        if item is None:
            return None
        return {
            "id": item.id,
            "transaction_date": item.transaction_date,
            "vendor": item.vendor,
            "description": item.description,
            "amount": item.amount,
            "currency": item.currency,
            "transaction_type": item.transaction_type,
            "category": category_names.get(item.category_id, "Uncategorized"),
            "account": account_names.get(item.account_id, "Unknown account"),
            "is_validated": item.is_validated,
            "is_duplicate": item.is_duplicate,
        }

    return {
        "month": key,
        "summary_sentence_1": insight.summary_sentence_1,
        "summary_sentence_2": insight.summary_sentence_2,
        "explanation": insight.explanation,
        "confidence_score": insight.confidence_score,
        "generated_at": insight.generated_at,
        "local_ai_used": insight.local_ai_used,
        "source_basis": [
            "validated database",
            "investment records",
            "loan records",
            "deterministic forecast",
        ]
        + (["local Ollama wording"] if insight.local_ai_used else []),
        "financial_position": _forecast_data(db, year, month)["financial_position"],
        "forecast": {
            "expected_income": forecast.expected_income,
            "expected_expenses": forecast.expected_expenses,
            "expected_surplus": forecast.expected_surplus,
            "expected_month_end_balance": forecast.expected_month_end_balance,
            "recurring_payment_impact": forecast.recurring_payment_impact,
            "confidence_score": forecast.confidence_score,
            "category_risks": json.loads(forecast.category_risks),
        },
        "recommendations": [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "priority": item.priority,
                "estimated_impact_amount": item.estimated_impact_amount,
                "recommendation_type": item.recommendation_type,
                "explanation": item.explanation,
                "related_data": json.loads(item.related_data),
                "status": item.status,
            }
            for item in recommendations
        ],
        "alerts": [
            {
                "id": item.id,
                "alert_type": item.alert_type,
                "severity": item.severity,
                "message": item.message,
                "reason": item.reason,
                "recommended_action": item.recommended_action,
                "status": item.status,
                "transactions": [
                    details
                    for transaction_id in json.loads(item.transaction_ids or "[]")
                    if (details := transaction_details(transaction_id)) is not None
                ],
            }
            for item in alerts
        ],
    }
