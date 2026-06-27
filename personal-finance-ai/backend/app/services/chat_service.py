import re
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.document import Document
from app.models.finance import Investment, Loan, Property
from app.models.transaction import Transaction
from app.services.loan_balance_service import loan_balance

MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        [
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
    )
    if name
}


def _period(question: str) -> tuple[date, date]:
    today = date.today()
    lower = question.lower()
    if "this month" in lower or "current month" in lower:
        next_month = (
            date(today.year + 1, 1, 1)
            if today.month == 12
            else date(today.year, today.month + 1, 1)
        )
        return date(today.year, today.month, 1), date.fromordinal(
            next_month.toordinal() - 1
        )
    if "last month" in lower or "previous month" in lower:
        current_start = date(today.year, today.month, 1)
        previous_end = date.fromordinal(current_start.toordinal() - 1)
        return date(previous_end.year, previous_end.month, 1), previous_end
    year_match = re.search(r"\b(20\d{2})\b", question)
    year = int(year_match.group(1)) if year_match else today.year
    month = next((value for name, value in MONTHS.items() if name in lower), None)
    if month:
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        return date(year, month, 1), date.fromordinal(next_month.toordinal() - 1)
    return date(year, 1, 1), date(year, 12, 31)


def answer_finance_question(db: Session, question: str) -> dict:
    lower = question.lower()
    start, end = _period(question)
    base = (
        Transaction.is_validated.is_(True),
        Transaction.is_duplicate.is_(False),
        Transaction.transaction_date.between(start, end),
    )
    sources: list[dict] = []
    warning = None
    if any(word in lower for word in ("document", "statement", "invoice", "slip")):
        ignored = {"what", "show", "from", "about", "document", "statement"}
        terms = {
            term for term in re.findall(r"[a-zA-Z]{4,}", lower) if term not in ignored
        }
        documents = db.scalars(
            select(Document).where(Document.extracted_text.is_not(None))
        ).all()
        ranked = sorted(
            documents,
            key=lambda item: sum(
                term in (item.extracted_text or "").lower() for term in terms
            ),
            reverse=True,
        )
        matches = [
            item
            for item in ranked[:5]
            if not terms
            or any(term in (item.extracted_text or "").lower() for term in terms)
        ]
        sources = [
            {
                "type": "document",
                "id": item.id,
                "file_name": item.file_name,
                "document_type": item.document_type,
            }
            for item in matches
        ]
        if matches:
            snippets = [
                (item.extracted_text or "").replace("\n", " ")[:240]
                for item in matches[:3]
            ]
            answer = "Relevant local document text: " + " | ".join(snippets)
            basis = "Local keyword retrieval over extracted document text."
        else:
            answer = "No matching processed documents were found."
            basis = "Searched locally stored extracted document text."
            warning = "Process the relevant document before asking about its contents."
    elif "debt" in lower or "loan" in lower:
        loans = list(db.scalars(select(Loan)).all())
        total = sum(
            (
                loan_balance(db, item, len(loans)).adjusted_balance
                for item in loans
            ),
            Decimal("0"),
        )
        sources = [
            {"type": "loan", "id": item.id, "name": item.lender} for item in loans
        ]
        answer = f"Your total recorded debt balance is {total:.2f}."
        basis = (
            "Recorded loan balances minus matched validated Loan Repayment "
            "transactions."
        )
    elif "net worth" in lower:
        accounts = (
            db.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    *base, Transaction.transaction_type == "credit"
                )
            )
            or 0
        )
        expenses = (
            db.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    *base, Transaction.transaction_type == "debit"
                )
            )
            or 0
        )
        investments = (
            db.scalar(select(func.coalesce(func.sum(Investment.current_value), 0))) or 0
        )
        properties = (
            db.scalar(select(func.coalesce(func.sum(Property.current_value), 0))) or 0
        )
        loans = list(db.scalars(select(Loan)).all())
        debts = sum(
            (
                loan_balance(db, item, len(loans)).adjusted_balance
                for item in loans
            ),
            Decimal("0"),
        )
        total = (
            Decimal(accounts)
            - Decimal(expenses)
            + Decimal(investments)
            + Decimal(properties)
            - Decimal(debts)
        )
        answer = f"Estimated net worth is {total:.2f}."
        basis = (
            "Validated cash flow plus investment and property values, "
            "minus loan balances."
        )
    else:
        transaction_type = (
            "credit"
            if any(word in lower for word in ("income", "salary", "earned"))
            else "debit"
        )
        statement = select(Transaction).where(
            *base, Transaction.transaction_type == transaction_type
        )
        category = None
        for candidate in db.scalars(select(Category)).all():
            name = candidate.name.lower()
            variants = {name, f"{name}s"}
            if name.endswith("y"):
                variants.add(f"{name[:-1]}ies")
            if any(variant in lower for variant in variants):
                category = candidate
                break
        if category:
            statement = statement.where(Transaction.category_id == category.id)
        transactions = db.scalars(
            statement.order_by(Transaction.transaction_date.desc())
        ).all()
        total = sum((item.amount for item in transactions), Decimal("0"))
        label = (
            category.name.lower()
            if category
            else ("income" if transaction_type == "credit" else "expenses")
        )
        answer = f"You recorded {total:.2f} in {label} from {start} to {end}."
        basis = f"Sum of {len(transactions)} validated, non-duplicate transaction(s)."
        sources = [
            {
                "type": "transaction",
                "id": item.id,
                "date": str(item.transaction_date),
                "vendor": item.vendor,
                "amount": str(item.amount),
            }
            for item in transactions[:20]
        ]
        if not transactions:
            warning = "No matching validated transactions were found."
    return {
        "answer": answer,
        "calculation_basis": basis,
        "sources": sources,
        "confidence": 1.0 if sources else 0.7,
        "missing_data_warning": warning,
        "local_ai_used": False,
    }
