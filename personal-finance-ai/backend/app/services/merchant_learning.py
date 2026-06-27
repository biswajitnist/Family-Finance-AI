import re
import unicodedata
from collections import Counter
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction


def normalize_merchant(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def apply_merchant_history(db: Session, transaction: Transaction) -> int | None:
    if transaction.category_id is not None:
        return None

    merchant_key = normalize_merchant(transaction.vendor)
    if not merchant_key:
        return None

    candidates = db.execute(
        select(Transaction.vendor, Transaction.category_id).where(
            Transaction.user_id == transaction.user_id,
            Transaction.transaction_type == transaction.transaction_type,
            Transaction.is_validated.is_(True),
            Transaction.is_duplicate.is_(False),
            Transaction.category_id.is_not(None),
        )
    ).all()
    category_counts = Counter(
        category_id
        for vendor, category_id in candidates
        if category_id is not None and normalize_merchant(vendor) == merchant_key
    )
    if len(category_counts) != 1:
        return None

    category_id, match_count = category_counts.most_common(1)[0]
    transaction.category_id = category_id
    transaction.classification_source = "merchant_history"
    transaction.confidence = Decimal("0.9800") if match_count > 1 else Decimal("0.9000")
    return category_id
