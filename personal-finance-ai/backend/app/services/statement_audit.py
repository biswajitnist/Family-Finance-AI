import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.audit import (
    DocumentOCRLine,
    ExtractionCandidate,
    StatementSet,
    StatementSetDocument,
)
from app.models.document import Document
from app.models.transaction import Transaction
from app.services.merchant_learning import normalize_merchant
from app.services.ocr_service import OCRLine

AMOUNT_LIKE = re.compile(r"(?<!\d)\d{1,3}(?:[.\s]\d{3})*[.,]\d{2}(?!\d)")
BALANCE_PATTERN = re.compile(
    r"(?P<label>Alter Kontostand|Neuer Kontostand|opening balance|closing balance)"
    r".*?(?P<amount>-?\d{1,3}(?:[.\s]\d{3})*[.,]\d{2})",
    re.IGNORECASE,
)
CONFIDENCE_THRESHOLD = Decimal("0.9000")


def _decimal(value: str | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    normalized = str(value).strip().replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return abs(Decimal(normalized)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _merchant_similarity(left: str | None, right: str | None) -> float:
    left_normalized = normalize_merchant(left or "")
    right_normalized = normalize_merchant(right or "")
    if not left_normalized or not right_normalized:
        return 0.0
    return round(SequenceMatcher(None, left_normalized, right_normalized).ratio(), 4)


def create_statement_set(
    db: Session, documents: list[Document], name: str | None = None
) -> StatementSet:
    if not documents:
        raise HTTPException(422, "Select at least one document")
    item = StatementSet(
        user_id=1,
        name=name or f"Statement audit · {documents[0].file_name}",
        status="processing",
    )
    db.add(item)
    db.flush()
    for sequence, document in enumerate(documents, start=1):
        db.add(
            StatementSetDocument(
                statement_set_id=item.id,
                document_id=document.id,
                sequence=sequence,
            )
        )
    db.commit()
    db.refresh(item)
    return item


def _find_source_line(
    row: dict[str, str], lines: list[DocumentOCRLine], used: set[int]
) -> DocumentOCRLine | None:
    source_number = row.get("_source_line_number")
    if source_number:
        match = next(
            (line for line in lines if line.line_number == int(source_number)),
            None,
        )
        if match:
            return match
    vendor = normalize_merchant(row.get("vendor", ""))
    amount = str(row.get("amount", "")).replace(".", "").replace(",", "")
    for line in lines:
        normalized_line = normalize_merchant(line.raw_text)
        numeric_line = re.sub(r"\D", "", line.raw_text)
        if line.id not in used and vendor and vendor in normalized_line:
            if not amount or amount in numeric_line:
                return line
    return None


def record_document_audit(
    db: Session,
    statement_set: StatementSet,
    document: Document,
    rows: list[dict[str, str]],
    transaction_pairs: list[tuple[dict[str, str], Transaction]],
    text: str,
    ocr_lines: list[OCRLine] | None,
) -> None:
    structured = ocr_lines or [
        OCRLine(1, index, line, None, None)
        for index, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
    stored_lines = []
    for line in structured:
        stored = DocumentOCRLine(
            statement_set_id=statement_set.id,
            document_id=document.id,
            page_number=line.page_number,
            line_number=line.line_number,
            raw_text=line.text,
            confidence=(
                Decimal(str(line.confidence)).quantize(Decimal("0.0001"))
                if line.confidence is not None
                else None
            ),
            bbox_json=json.dumps(line.bbox) if line.bbox else None,
        )
        db.add(stored)
        stored_lines.append(stored)
    db.flush()

    used_lines: set[int] = set()
    transaction_by_row = {
        id(row): transaction for row, transaction in transaction_pairs
    }
    for row in rows:
        transaction = transaction_by_row.get(id(row))
        source = _find_source_line(row, stored_lines, used_lines)
        if source:
            used_lines.add(source.id)
        base_confidence = (
            Decimal(str(row.get("confidence")))
            if row.get("confidence")
            else source.confidence
            if source and source.confidence is not None
            else Decimal("0.6500")
        )
        base_confidence = base_confidence.quantize(Decimal("0.0001"))
        warnings = []
        amount = _decimal(row.get("amount"))
        date_value = row.get("date") or row.get("transaction_date")
        if base_confidence < CONFIDENCE_THRESHOLD:
            warnings.append("Low OCR or extraction confidence")
        if source is None:
            warnings.append("Source line could not be located")
        if row.get("amount") and "," in row["amount"] and "." in row["amount"]:
            warnings.append("Verify decimal and thousands separators")
        if not date_value:
            warnings.append("Transaction date is missing")
        if amount is None:
            warnings.append("Amount is missing or invalid")
        transaction_type = row.get("type") or row.get("transaction_type")
        if transaction_type not in {"debit", "credit"}:
            warnings.append("Debit or credit sign is unclear")
        status = "needs_review" if warnings else "extracted"
        db.add(
            ExtractionCandidate(
                statement_set_id=statement_set.id,
                document_id=document.id,
                source_line_id=source.id if source else None,
                transaction_id=transaction.id if transaction else None,
                status=status,
                raw_text=source.raw_text if source else row.get("_source_text", ""),
                transaction_date=date_value,
                vendor=row.get("vendor") or row.get("merchant") or row.get("payee"),
                amount=amount,
                currency=(row.get("currency") or "EUR").upper(),
                transaction_type=transaction_type,
                field_confidence_json=json.dumps(
                    {
                        "date": float(base_confidence),
                        "vendor": float(base_confidence),
                        "amount": float(base_confidence),
                        "transaction_type": float(base_confidence),
                        "currency": float(base_confidence),
                    }
                ),
                warnings_json=json.dumps(warnings),
            )
        )

    for line in stored_lines:
        if line.id in used_lines or not AMOUNT_LIKE.search(line.raw_text):
            continue
        if BALANCE_PATTERN.search(line.raw_text):
            continue
        db.add(
            ExtractionCandidate(
                statement_set_id=statement_set.id,
                document_id=document.id,
                source_line_id=line.id,
                status="skipped",
                skip_reason="Amount-like line was not parsed as a transaction",
                raw_text=line.raw_text,
                field_confidence_json="{}",
                warnings_json=json.dumps(["Possible transaction was skipped"]),
            )
        )
    _capture_balances(statement_set, text)
    db.commit()
    recalculate_audit(db, statement_set.id)


def _capture_balances(statement_set: StatementSet, text: str) -> None:
    for match in BALANCE_PATTERN.finditer(text):
        amount = _decimal(match.group("amount"))
        label = match.group("label").casefold()
        if "alter" in label or "opening" in label:
            statement_set.detected_opening_balance = amount
        else:
            statement_set.detected_closing_balance = amount


def _signature(candidate: ExtractionCandidate) -> tuple:
    return (
        candidate.transaction_date,
        normalize_merchant(candidate.vendor or ""),
        str(candidate.amount or ""),
        candidate.currency,
        candidate.transaction_type,
    )


def recalculate_audit(db: Session, statement_set_id: int) -> StatementSet:
    statement_set = db.get(StatementSet, statement_set_id)
    if statement_set is None:
        raise HTTPException(404, "Statement audit not found")
    candidates = list(
        db.scalars(
            select(ExtractionCandidate)
            .where(ExtractionCandidate.statement_set_id == statement_set_id)
            .order_by(ExtractionCandidate.id)
        ).all()
    )
    seen: dict[tuple, ExtractionCandidate] = {}
    for candidate in candidates:
        if candidate.status not in {"extracted", "needs_review", "overlap"}:
            continue
        signature = _signature(candidate)
        previous = seen.get(signature)
        if previous and previous.document_id != candidate.document_id:
            candidate.status = "overlap"
            candidate.resolution = candidate.resolution or "overlap_confirmed"
            candidate.skip_reason = "Exact transaction repeated in another screenshot"
            if candidate.transaction_id:
                transaction = db.get(Transaction, candidate.transaction_id)
                if transaction:
                    transaction.is_duplicate = True
        else:
            seen[signature] = candidate

    active = [
        item
        for item in candidates
        if item.status in {"extracted", "needs_review"}
        and item.resolution not in {"not_transaction", "duplicate_rejected"}
    ]
    debit_total = sum(
        (item.amount or Decimal("0"))
        for item in active
        if item.transaction_type == "debit"
    )
    credit_total = sum(
        (item.amount or Decimal("0"))
        for item in active
        if item.transaction_type == "credit"
    )
    unresolved_review = [
        item
        for item in active
        if item.status == "needs_review" and item.resolution != "accepted"
    ]
    unresolved_skipped = [
        item
        for item in candidates
        if item.status == "skipped"
        and item.resolution not in {"not_transaction", "accepted", "duplicate_rejected"}
    ]
    blockers = []
    if unresolved_review:
        blockers.append(
            f"{len(unresolved_review)} low-confidence row(s) need review"
        )
    if unresolved_skipped:
        blockers.append(
            f"{len(unresolved_skipped)} possible skipped transaction "
            "line(s) need review"
        )

    difference = None
    has_balance_reconciliation = (
        statement_set.detected_opening_balance is not None
        and statement_set.detected_closing_balance is not None
    )
    if has_balance_reconciliation:
        expected_closing = (
            statement_set.detected_opening_balance + credit_total - debit_total
        )
        difference = (
            statement_set.detected_closing_balance - expected_closing
        ).quantize(Decimal("0.01"))
        if abs(difference) > Decimal("0.01"):
            blockers.append(f"Statement balance differs by {difference}")
    else:
        checkpoints = (
            statement_set.expected_transaction_count,
            statement_set.expected_debit_total,
            statement_set.expected_credit_total,
        )
        if all(value is None for value in checkpoints):
            blockers.append(
                "Provide an expected transaction count or debit/credit total"
            )
        if (
            statement_set.expected_transaction_count is not None
            and statement_set.expected_transaction_count != len(active)
        ):
            blockers.append(
                "Extracted transaction count does not match the expected count"
            )
        if (
            statement_set.expected_debit_total is not None
            and abs(statement_set.expected_debit_total - debit_total)
            > Decimal("0.01")
        ):
            blockers.append("Extracted debit total does not match the checkpoint")
        if (
            statement_set.expected_credit_total is not None
            and abs(statement_set.expected_credit_total - credit_total)
            > Decimal("0.01")
        ):
            blockers.append("Extracted credit total does not match the checkpoint")

    statement_set.candidate_count = len(candidates)
    statement_set.extracted_count = len(active)
    statement_set.skipped_count = sum(item.status == "skipped" for item in candidates)
    statement_set.overlap_count = sum(item.status == "overlap" for item in candidates)
    statement_set.low_confidence_count = len(unresolved_review)
    statement_set.debit_total = debit_total
    statement_set.credit_total = credit_total
    statement_set.reconciliation_difference = difference
    statement_set.confirmation_blockers = json.dumps(blockers)
    statement_set.completeness_status = (
        "verified" if not blockers else "needs_review"
    )
    statement_set.status = "ready" if not blockers else "review"
    db.commit()
    db.refresh(statement_set)
    return statement_set


def serialize_audit(db: Session, statement_set_id: int) -> dict:
    statement_set = recalculate_audit(db, statement_set_id)
    links = list(
        db.scalars(
            select(StatementSetDocument)
            .where(StatementSetDocument.statement_set_id == statement_set_id)
            .order_by(StatementSetDocument.sequence)
        ).all()
    )
    documents = [db.get(Document, link.document_id) for link in links]
    candidates = list(
        db.scalars(
            select(ExtractionCandidate)
            .where(ExtractionCandidate.statement_set_id == statement_set_id)
            .order_by(ExtractionCandidate.document_id, ExtractionCandidate.id)
        ).all()
    )
    source_ids = {item.source_line_id for item in candidates if item.source_line_id}
    sources = {
        item.id: item
        for item in db.scalars(
            select(DocumentOCRLine).where(DocumentOCRLine.id.in_(source_ids))
        ).all()
    } if source_ids else {}

    def source_read(source: DocumentOCRLine | None) -> dict | None:
        if source is None:
            return None
        return {
            "id": source.id,
            "document_id": source.document_id,
            "page_number": source.page_number,
            "line_number": source.line_number,
            "raw_text": source.raw_text,
            "confidence": source.confidence,
            "bbox": json.loads(source.bbox_json) if source.bbox_json else None,
        }

    document_by_id = {
        document.id: document for document in documents if document is not None
    }

    def duplicate_matches(item: ExtractionCandidate) -> list[dict]:
        if not item.transaction_date or not item.amount or not item.vendor:
            return []
        document = document_by_id.get(item.document_id)
        clauses = [
            Transaction.transaction_date == date.fromisoformat(item.transaction_date),
            Transaction.amount == item.amount,
            Transaction.is_validated.is_(True),
            Transaction.is_duplicate.is_(False),
        ]
        if item.transaction_type:
            clauses.append(Transaction.transaction_type == item.transaction_type)
        if document and document.source_account_id:
            clauses.append(Transaction.account_id == document.source_account_id)
        if item.transaction_id:
            clauses.append(Transaction.id != item.transaction_id)
        if item.document_id:
            clauses.append(
                or_(
                    Transaction.document_id.is_(None),
                    Transaction.document_id != item.document_id,
                )
            )
        matches = []
        for transaction in db.scalars(select(Transaction).where(*clauses)).all():
            similarity = _merchant_similarity(item.vendor, transaction.vendor)
            if similarity < 0.6:
                continue
            matches.append(
                {
                    "id": transaction.id,
                    "transaction_date": transaction.transaction_date,
                    "vendor": transaction.vendor,
                    "description": transaction.description,
                    "amount": transaction.amount,
                    "currency": transaction.currency,
                    "transaction_type": transaction.transaction_type,
                    "category": (
                        transaction.category.name if transaction.category else None
                    ),
                    "account": (
                        transaction.account.name if transaction.account else None
                    ),
                    "merchant_similarity": similarity,
                }
            )
        return sorted(
            matches,
            key=lambda match: match["merchant_similarity"],
            reverse=True,
        )[:3]

    blockers = json.loads(statement_set.confirmation_blockers or "[]")
    return {
        "id": statement_set.id,
        "name": statement_set.name,
        "status": statement_set.status,
        "completeness_status": statement_set.completeness_status,
        "expected_transaction_count": statement_set.expected_transaction_count,
        "expected_debit_total": statement_set.expected_debit_total,
        "expected_credit_total": statement_set.expected_credit_total,
        "detected_opening_balance": statement_set.detected_opening_balance,
        "detected_closing_balance": statement_set.detected_closing_balance,
        "candidate_count": statement_set.candidate_count,
        "extracted_count": statement_set.extracted_count,
        "skipped_count": statement_set.skipped_count,
        "overlap_count": statement_set.overlap_count,
        "low_confidence_count": statement_set.low_confidence_count,
        "debit_total": statement_set.debit_total,
        "credit_total": statement_set.credit_total,
        "reconciliation_difference": statement_set.reconciliation_difference,
        "confirmation_blockers": blockers,
        "can_confirm": not blockers,
        "documents": [
            {
                "id": document.id,
                "file_name": document.file_name,
                "file_type": document.file_type,
                "sequence": link.sequence,
                "preview_url": f"/api/documents/{document.id}/preview",
                "page_count": document.page_count,
            }
            for link, document in zip(links, documents, strict=True)
            if document
        ],
        "candidates": [
            {
                "id": item.id,
                "document_id": item.document_id,
                "source_line_id": item.source_line_id,
                "transaction_id": item.transaction_id,
                "status": item.status,
                "resolution": item.resolution,
                "skip_reason": item.skip_reason,
                "raw_text": item.raw_text,
                "transaction_date": item.transaction_date,
                "vendor": item.vendor,
                "amount": item.amount,
                "currency": item.currency,
                "transaction_type": item.transaction_type,
                "field_confidence": json.loads(item.field_confidence_json or "{}"),
                "warnings": json.loads(item.warnings_json or "[]"),
                "duplicate_matches": duplicate_matches(item),
                "source_line": source_read(sources.get(item.source_line_id)),
            }
            for item in candidates
        ],
    }


def latest_audit_for_document(db: Session, document_id: int) -> dict:
    link = db.scalar(
        select(StatementSetDocument)
        .where(StatementSetDocument.document_id == document_id)
        .order_by(StatementSetDocument.id.desc())
    )
    if link is None:
        raise HTTPException(404, "No extraction audit exists for this document")
    return serialize_audit(db, link.statement_set_id)


def update_checkpoint(
    db: Session,
    statement_set_id: int,
    expected_transaction_count: int | None,
    expected_debit_total: Decimal | None,
    expected_credit_total: Decimal | None,
) -> dict:
    item = db.get(StatementSet, statement_set_id)
    if item is None:
        raise HTTPException(404, "Statement audit not found")
    item.expected_transaction_count = expected_transaction_count
    item.expected_debit_total = expected_debit_total
    item.expected_credit_total = expected_credit_total
    db.commit()
    return serialize_audit(db, statement_set_id)


def update_candidate(
    db: Session, candidate_id: int, updates: dict
) -> dict:
    candidate = db.get(ExtractionCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(404, "Extraction candidate not found")
    for field, value in updates.items():
        if value is not None and field != "resolution":
            setattr(
                candidate,
                field,
                str(value) if field == "transaction_date" else value,
            )
        elif field == "resolution":
            candidate.resolution = value
    if candidate.transaction_id:
        transaction = db.get(Transaction, candidate.transaction_id)
        if transaction:
            for field in (
                "transaction_date",
                "vendor",
                "amount",
                "currency",
                "transaction_type",
            ):
                value = updates.get(field)
                if value is not None:
                    setattr(transaction, field, value)
    elif updates.get("resolution") == "accepted":
        document = db.get(Document, candidate.document_id)
        required = (
            candidate.transaction_date,
            candidate.vendor,
            candidate.amount,
            candidate.currency,
            candidate.transaction_type,
            document.source_account_id if document else None,
        )
        if not all(required):
            raise HTTPException(
                422,
                "Date, vendor, amount, currency, type, and source account are "
                "required to convert this line into a transaction.",
            )
        transaction = Transaction(
            user_id=1,
            account_id=document.source_account_id,
            document_id=document.id,
            transaction_date=date.fromisoformat(candidate.transaction_date),
            vendor=candidate.vendor,
            description=candidate.raw_text,
            original_description=candidate.raw_text,
            amount=candidate.amount,
            currency=candidate.currency,
            transaction_type=candidate.transaction_type,
            is_validated=False,
            is_duplicate=False,
            classification_source="audit_review",
            confidence=Decimal("1.0000"),
        )
        db.add(transaction)
        db.flush()
        candidate.transaction_id = transaction.id
    if updates.get("resolution") == "accepted":
        candidate.status = "extracted"
        candidate.warnings_json = "[]"
    elif updates.get("resolution") == "duplicate_rejected":
        candidate.status = "skipped"
        candidate.skip_reason = "Rejected because a matching transaction already exists"
        candidate.warnings_json = "[]"
    db.commit()
    return serialize_audit(db, candidate.statement_set_id)


def confirm_statement_set(db: Session, statement_set_id: int) -> dict:
    audit = serialize_audit(db, statement_set_id)
    if not audit["can_confirm"]:
        raise HTTPException(
            409,
            {
                "message": "Statement audit has unresolved blockers",
                "blockers": audit["confirmation_blockers"],
            },
        )
    candidates = list(
        db.scalars(
            select(ExtractionCandidate).where(
                ExtractionCandidate.statement_set_id == statement_set_id
            )
        ).all()
    )
    confirmed = 0
    document_ids = set()
    for candidate in candidates:
        document_ids.add(candidate.document_id)
        if (
            candidate.transaction_id
            and candidate.status == "extracted"
            and candidate.resolution != "not_transaction"
        ):
            transaction = db.get(Transaction, candidate.transaction_id)
            if transaction and not transaction.is_duplicate:
                transaction.is_validated = True
                confirmed += 1
    for document_id in document_ids:
        document = db.get(Document, document_id)
        if document:
            document.status = "validated"
            document.validation_status = "validated"
            document.processing_stage = "confirmed"
            document.processing_message = (
                "Statement audit verified. Transactions are available."
            )
    statement_set = db.get(StatementSet, statement_set_id)
    statement_set.status = "confirmed"
    statement_set.confirmed_at = datetime.now(UTC)
    db.commit()
    return {"confirmed": confirmed, "status": "confirmed"}
