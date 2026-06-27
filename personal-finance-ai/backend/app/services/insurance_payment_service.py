from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import Insurance
from app.models.transaction import Transaction
from app.services.currency_service import base_currency, convert_amount
from app.services.merchant_learning import normalize_merchant


@dataclass(frozen=True)
class MatchedInsuranceTransaction:
    transaction: Transaction
    applied_amount: Decimal


POLICY_KEYWORDS = {
    "liability": ("liability", "haftpflicht"),
    "household": ("household", "hausrat"),
    "legal": ("legal", "rechtsschutz"),
    "disability": ("disability", "berufsunfahigkeit", "lebensversicherung"),
    "eye glasses": ("eye glasses", "brille", "fielmann", "nulltarif"),
    "term insurance": ("term insurance", "lebensversicherung"),
}


def _eligible_transactions(db: Session) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .join(Transaction.category)
            .where(
                Transaction.is_validated.is_(True),
                Transaction.is_duplicate.is_(False),
                Transaction.transaction_type == "debit",
                Transaction.category.has(name="Insurance"),
            )
            .order_by(Transaction.transaction_date, Transaction.id)
        ).all()
    )


def _within_policy_dates(transaction: Transaction, policy: Insurance) -> bool:
    if policy.start_date and transaction.transaction_date < policy.start_date:
        return False
    return not (policy.end_date and transaction.transaction_date > policy.end_date)


def _provider_matches(transaction: Transaction, policy: Insurance) -> bool:
    transaction_text = normalize_merchant(
        f"{transaction.vendor} {transaction.description}"
    )
    provider = normalize_merchant(policy.provider)
    if provider and (provider in transaction_text or transaction_text in provider):
        return True
    provider_tokens = {
        token
        for token in provider.split()
        if len(token) >= 5 and token not in {"aktiengesellschaft"}
    }
    return bool(provider_tokens.intersection(transaction_text.split()))


def _policy_keyword_matches(transaction: Transaction, policy: Insurance) -> bool:
    text = normalize_merchant(f"{transaction.vendor} {transaction.description}")
    keywords = POLICY_KEYWORDS.get(normalize_merchant(policy.policy_type), ())
    return any(normalize_merchant(keyword) in text for keyword in keywords)


def _converted_amount(
    db: Session,
    transaction: Transaction,
    policy: Insurance,
) -> Decimal | None:
    converted = convert_amount(
        db,
        transaction.amount,
        transaction.currency,
        policy.currency,
    )
    return converted.quantize(Decimal("0.01")) if converted is not None else None


def insurance_transaction_assignments(
    db: Session,
    policies: list[Insurance] | None = None,
) -> tuple[dict[int, list[MatchedInsuranceTransaction]], list[Transaction]]:
    active_policies = policies or list(
        db.scalars(select(Insurance).where(Insurance.is_active.is_(True))).all()
    )
    assignments = {policy.id: [] for policy in active_policies}
    unmatched: list[Transaction] = []

    for transaction in _eligible_transactions(db):
        candidates: list[tuple[int, Insurance, Decimal]] = []
        for policy in active_policies:
            if not _within_policy_dates(transaction, policy):
                continue
            converted = _converted_amount(db, transaction, policy)
            if converted is None:
                continue
            text = normalize_merchant(
                f"{transaction.vendor} {transaction.description}"
            )
            policy_number = normalize_merchant(policy.policy_number or "")
            number_match = bool(policy_number and policy_number in text)
            provider_match = _provider_matches(transaction, policy)
            amount_match = abs(converted - policy.premium_amount) <= Decimal("0.02")
            keyword_match = _policy_keyword_matches(transaction, policy)
            if not number_match and not provider_match:
                continue
            if not number_match and not amount_match and not keyword_match:
                continue
            score = (
                (100 if number_match else 0)
                + (30 if amount_match else 0)
                + (20 if keyword_match else 0)
                + (10 if provider_match else 0)
            )
            candidates.append((score, policy, converted))

        candidates.sort(key=lambda entry: entry[0], reverse=True)
        if not candidates or (
            len(candidates) > 1 and candidates[0][0] == candidates[1][0]
        ):
            unmatched.append(transaction)
            continue
        _, policy, converted = candidates[0]
        assignments[policy.id].append(
            MatchedInsuranceTransaction(
                transaction=transaction,
                applied_amount=converted,
            )
        )

    return assignments, unmatched


def insurance_payment_summary(db: Session) -> dict:
    policies = list(
        db.scalars(select(Insurance).where(Insurance.is_active.is_(True))).all()
    )
    assignments, unmatched = insurance_transaction_assignments(db, policies)
    reporting_currency = base_currency(db)
    reporting_year = date.today().year
    reporting_month = date.today().month
    factors = {
        "monthly": Decimal("12"),
        "quarterly": Decimal("4"),
        "yearly": Decimal("1"),
    }
    scheduled_annual = Decimal("0")
    actual_year = Decimal("0")
    actual_month = Decimal("0")
    policy_rows = []

    for policy in policies:
        annual_native = policy.premium_amount * factors.get(
            policy.premium_frequency,
            Decimal("1"),
        )
        annual_base = convert_amount(
            db,
            annual_native,
            policy.currency,
            reporting_currency,
        ) or Decimal("0")
        monthly_base = annual_base / 12
        scheduled_annual += annual_base
        policy_year = sum(
            (
                match.applied_amount
                for match in assignments[policy.id]
                if match.transaction.transaction_date.year == reporting_year
            ),
            Decimal("0"),
        )
        policy_month = sum(
            (
                match.applied_amount
                for match in assignments[policy.id]
                if match.transaction.transaction_date.year == reporting_year
                and match.transaction.transaction_date.month == reporting_month
            ),
            Decimal("0"),
        )
        actual_year += convert_amount(
            db, policy_year, policy.currency, reporting_currency
        ) or Decimal("0")
        actual_month += convert_amount(
            db, policy_month, policy.currency, reporting_currency
        ) or Decimal("0")
        policy_rows.append(
            {
                "id": policy.id,
                "provider": policy.provider,
                "policy_type": policy.policy_type,
                "scheduled_annual": annual_native.quantize(Decimal("0.01")),
                "scheduled_monthly": (annual_native / 12).quantize(Decimal("0.01")),
                "scheduled_annual_base": annual_base.quantize(Decimal("0.01")),
                "scheduled_monthly_base": monthly_base.quantize(Decimal("0.01")),
                "actual_year": policy_year.quantize(Decimal("0.01")),
                "actual_month": policy_month.quantize(Decimal("0.01")),
                "currency": policy.currency,
                "matched_transaction_count": len(assignments[policy.id]),
            }
        )

    return {
        "base_currency": reporting_currency,
        "reporting_year": reporting_year,
        "reporting_month": reporting_month,
        "active_policies": len(policies),
        "scheduled_annual": scheduled_annual.quantize(Decimal("0.01")),
        "scheduled_monthly": (scheduled_annual / 12).quantize(Decimal("0.01")),
        "actual_year": actual_year.quantize(Decimal("0.01")),
        "actual_month": actual_month.quantize(Decimal("0.01")),
        "unmatched_transaction_count": len(unmatched),
        "unmatched_transactions": [
            {
                "id": transaction.id,
                "transaction_date": transaction.transaction_date,
                "vendor": transaction.vendor,
                "description": transaction.description or "",
                "amount": transaction.amount,
                "currency": transaction.currency,
            }
            for transaction in unmatched
        ],
        "policies": policy_rows,
    }
