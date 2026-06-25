from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.finance import Rule
from app.models.transaction import Transaction
from app.services.merchant_learning import apply_merchant_history


def _matches(rule: Rule, transaction: Transaction) -> bool:
    value = rule.condition_value.casefold()
    if rule.condition_type == "vendor":
        return value in transaction.vendor.casefold()
    if rule.condition_type == "keyword":
        return value in f"{transaction.vendor} {transaction.description}".casefold()
    if rule.condition_type == "account":
        return value == str(transaction.account_id)
    if rule.condition_type == "iban":
        return bool(transaction.iban and value in transaction.iban.casefold())
    if rule.condition_type in {"amount_min", "amount_max"}:
        try:
            threshold = Decimal(rule.condition_value)
        except InvalidOperation:
            return False
        return (
            transaction.amount >= threshold
            if rule.condition_type == "amount_min"
            else transaction.amount <= threshold
        )
    if rule.condition_type == "recurring":
        return value in transaction.vendor.casefold()
    return False


def apply_rules_to_transaction(db: Session, transaction: Transaction) -> Rule | None:
    rules = db.scalars(
        select(Rule)
        .where(Rule.is_active.is_(True))
        .order_by(Rule.priority.asc(), Rule.id.asc())
    ).all()
    categories = {
        category.name.casefold(): category.id
        for category in db.scalars(select(Category)).all()
    }
    for rule in rules:
        if not _matches(rule, transaction):
            continue
        if rule.action_type == "category":
            category_id = categories.get(rule.action_value.casefold())
            if category_id:
                transaction.category_id = category_id
                transaction.classification_source = "rule"
                transaction.confidence = Decimal("1.0000")
        elif rule.action_type == "transaction_type":
            if rule.action_value in {"debit", "credit"}:
                transaction.transaction_type = rule.action_value
        rule.last_applied_at = datetime.now()
        return rule
    return None


def apply_all_rules(db: Session) -> int:
    transactions = db.scalars(
        select(Transaction).where(Transaction.is_validated.is_(False))
    ).all()
    changed = sum(
        bool(apply_rules_to_transaction(db, item) or apply_merchant_history(db, item))
        for item in transactions
    )
    db.commit()
    return changed
