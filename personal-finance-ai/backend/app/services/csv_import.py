import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.services.duplicate_detection import find_duplicate_transaction_id
from app.services.merchant_learning import apply_merchant_history
from app.services.rule_engine import apply_rules_to_transaction

REQUIRED_COLUMNS = {"date", "vendor", "amount", "type"}


def _parse_date(value: str, row_number: int) -> date:
    for date_format in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    raise HTTPException(422, f"Row {row_number}: unsupported date '{value}'")


def _parse_amount(value: str, row_number: int) -> Decimal:
    normalized = value.strip().replace(" ", "")
    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")
    else:
        normalized = normalized.replace(",", "")
    try:
        amount = abs(Decimal(normalized)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise HTTPException(422, f"Row {row_number}: invalid amount '{value}'") from exc
    if amount == 0:
        raise HTTPException(422, f"Row {row_number}: amount must not be zero")
    return amount


async def import_transactions(
    db: Session, file: UploadFile, account_id: int, user_id: int = 1
) -> dict[str, int]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(415, "Only CSV files are supported")
    if db.get(Account, account_id) is None:
        raise HTTPException(404, "Account not found")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV file exceeds the 5 MB limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "CSV must use UTF-8 encoding") from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = {header.strip().lower() for header in (reader.fieldnames or [])}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise HTTPException(422, f"Missing CSV columns: {', '.join(sorted(missing))}")

    categories = {
        category.name.lower(): category.id
        for category in db.scalars(select(Category)).all()
    }
    imported = duplicates = 0
    for row_number, source_row in enumerate(reader, start=2):
        row = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in source_row.items()
        }
        transaction_date = _parse_date(row["date"], row_number)
        amount = _parse_amount(row["amount"], row_number)
        transaction_type = row["type"].lower()
        if transaction_type not in {"debit", "credit"}:
            raise HTTPException(422, f"Row {row_number}: type must be debit or credit")
        vendor = row["vendor"]
        if not vendor:
            raise HTTPException(422, f"Row {row_number}: vendor is required")

        description = row.get("description", "")
        transaction = Transaction(
            user_id=user_id,
            account_id=account_id,
            transaction_date=transaction_date,
            booking_date=_parse_date(row["booking_date"], row_number)
            if row.get("booking_date")
            else None,
            vendor=vendor,
            description=description,
            original_description=description,
            amount=amount,
            currency=(row.get("currency") or "EUR").upper(),
            transaction_type=transaction_type,
            category_id=categories.get(row.get("category", "").lower()),
            reference_number=row.get("reference_number") or None,
            is_validated=False,
            is_duplicate=False,
            classification_source="import",
        )
        transaction.is_duplicate = (
            find_duplicate_transaction_id(db, transaction) is not None
        )
        duplicates += int(transaction.is_duplicate)
        db.add(transaction)
        db.flush()
        if transaction.category_id is None:
            if not apply_rules_to_transaction(db, transaction):
                apply_merchant_history(db, transaction)
        imported += 1
    db.commit()
    return {"imported": imported, "duplicates": duplicates}
