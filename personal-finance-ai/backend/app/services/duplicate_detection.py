import re
import unicodedata
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction


def _normalize(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def _identity(transaction: Transaction) -> tuple:
    reference = _normalize(transaction.reference_number)
    description = _normalize(transaction.description)
    return (
        transaction.account_id,
        transaction.transaction_date,
        transaction.amount,
        transaction.transaction_type,
        _normalize(transaction.vendor),
        "reference" if reference else "description",
        reference or description,
    )


def _merchant_similarity(left: str | None, right: str | None) -> float:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    if not left_normalized or not right_normalized:
        return 0.0
    return SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _has_conflicting_reference(left: Transaction, right: Transaction) -> bool:
    left_reference = _normalize(left.reference_number)
    right_reference = _normalize(right.reference_number)
    return bool(
        left_reference and right_reference and left_reference != right_reference
    )


def _is_duplicate_match(transaction: Transaction, candidate: Transaction) -> bool:
    return (
        transaction.account_id == candidate.account_id
        and transaction.transaction_date == candidate.transaction_date
        and transaction.amount == candidate.amount
        and transaction.transaction_type == candidate.transaction_type
        and not _has_conflicting_reference(transaction, candidate)
        and _merchant_similarity(transaction.vendor, candidate.vendor) >= 0.6
    )


def find_duplicate_transaction_id(db: Session, transaction: Transaction) -> int | None:
    candidates = db.scalars(
        select(Transaction).where(
            Transaction.account_id == transaction.account_id,
            Transaction.transaction_date == transaction.transaction_date,
            Transaction.amount == transaction.amount,
            Transaction.transaction_type == transaction.transaction_type,
            Transaction.is_duplicate.is_(False),
        )
    ).all()
    for candidate in candidates:
        if candidate.id == transaction.id:
            continue
        if _is_duplicate_match(transaction, candidate):
            return candidate.id
    return None


def reconcile_duplicate_flags(db: Session) -> dict[str, int]:
    transactions = list(
        db.scalars(
            select(Transaction).order_by(
                Transaction.transaction_date,
                Transaction.id,
            )
        ).all()
    )
    seen_exact: set[tuple] = set()
    seen_active: list[Transaction] = []
    changed = 0
    duplicates = 0
    for transaction in transactions:
        identity = _identity(transaction)
        if transaction.is_validated:
            is_duplicate = identity in seen_exact
        else:
            is_duplicate = any(
                _is_duplicate_match(transaction, candidate)
                for candidate in seen_active
                if not candidate.is_duplicate
            )
        if transaction.is_duplicate != is_duplicate:
            transaction.is_duplicate = is_duplicate
            changed += 1
        duplicates += int(is_duplicate)
        if not is_duplicate:
            seen_exact.add(identity)
            seen_active.append(transaction)
    db.commit()
    return {"changed": changed, "duplicates": duplicates}
