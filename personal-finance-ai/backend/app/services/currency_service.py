from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import FxRate
from app.models.user import User

ZERO = Decimal("0")
ONE = Decimal("1")


def base_currency(db: Session) -> str:
    profile = db.scalar(select(User).order_by(User.id))
    return (profile.base_currency if profile else "EUR").upper()


def latest_rate(
    db: Session,
    from_currency: str | None,
    to_currency: str | None,
) -> Decimal | None:
    source = (from_currency or "").upper()
    target = (to_currency or "").upper()
    if not source or not target:
        return None
    if source == target:
        return ONE

    direct = db.scalar(
        select(FxRate)
        .where(
            FxRate.from_currency == source,
            FxRate.to_currency == target,
        )
        .order_by(FxRate.rate_date.desc(), FxRate.created_at.desc())
    )
    if direct and direct.rate > 0:
        return Decimal(direct.rate)

    inverse = db.scalar(
        select(FxRate)
        .where(
            FxRate.from_currency == target,
            FxRate.to_currency == source,
        )
        .order_by(FxRate.rate_date.desc(), FxRate.created_at.desc())
    )
    if inverse and inverse.rate > 0:
        return ONE / Decimal(inverse.rate)
    return None


def convert_amount(
    db: Session,
    amount: Decimal | int | float | str | None,
    from_currency: str | None,
    to_currency: str | None = None,
) -> Decimal | None:
    target = (to_currency or base_currency(db)).upper()
    rate = latest_rate(db, from_currency, target)
    if rate is None:
        return None
    return (Decimal(amount or 0) * rate).quantize(Decimal("0.01"))


def converted_total(
    db: Session,
    records: Iterable[object],
    amount_field: str,
    currency_field: str = "currency",
    to_currency: str | None = None,
) -> tuple[Decimal, list[str]]:
    target = (to_currency or base_currency(db)).upper()
    total = ZERO
    missing: set[str] = set()
    for record in records:
        source = str(getattr(record, currency_field, target) or target).upper()
        converted = convert_amount(
            db,
            getattr(record, amount_field, ZERO),
            source,
            target,
        )
        if converted is None:
            missing.add(f"{source} → {target}")
            continue
        total += converted
    return total.quantize(Decimal("0.01")), sorted(missing)
