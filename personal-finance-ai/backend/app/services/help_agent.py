import json
import re
from datetime import date
from decimal import Decimal

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.transaction import Transaction
from app.services.ai_service import generate_local_json, generate_local_text
from app.services.chat_service import _period, answer_finance_question
from app.services.local_vector_store import search_local_knowledge
from app.services.report_service import generate_report

INTENTS = {
    "app_help",
    "finance_query",
    "document_query",
    "report_request",
    "troubleshooting",
}


class IntentResult(BaseModel):
    intent: str = Field(
        pattern=(
            "^(app_help|finance_query|document_query|report_request|troubleshooting)$"
        )
    )


def _fallback_intent(message: str) -> str:
    lower = message.casefold()
    if any(word in lower for word in ("report", "export", "pdf", "xlsx", "csv")):
        if any(word in lower for word in ("create", "generate", "download", "make")):
            return "report_request"
    if any(
        word in lower
        for word in (
            "statement",
            "document",
            "invoice",
            "uploaded",
            "payslip",
            "receipt",
        )
    ):
        return "document_query"
    if any(
        word in lower
        for word in (
            "error",
            "failed",
            "not working",
            "cannot",
            "can't",
            "offline",
            "stuck",
            "problem",
        )
    ):
        return "troubleshooting"
    if any(
        word in lower
        for word in (
            "spend",
            "expense",
            "income",
            "salary",
            "debt",
            "loan",
            "net worth",
            "transaction",
            "budget",
            "balance",
        )
    ):
        return "finance_query"
    return "app_help"


def _classify(message: str) -> tuple[str, bool]:
    lower = message.casefold()
    deterministic = _fallback_intent(message)
    app_help_signal = any(
        phrase in lower
        for phrase in (
            "how do i",
            "how to",
            "where is",
            "where can i",
            "help me use",
            "what does this app",
        )
    )
    if app_help_signal:
        return "app_help", False
    if deterministic != "app_help":
        return deterministic, False
    prompt = (
        "Classify this Ledger Local request. Return only JSON matching "
        '{"intent":"app_help|finance_query|document_query|report_request|'
        'troubleshooting"}. '
        "app_help means how to use the application; finance_query means values "
        "from validated finance records; document_query means uploaded document "
        "contents; report_request means create an export; troubleshooting means "
        f"diagnose a problem.\nRequest: {message}"
    )
    try:
        result = IntentResult.model_validate_json(generate_local_json(prompt))
        return result.intent, True
    except (
        httpx.HTTPError,
        RuntimeError,
        ValidationError,
        json.JSONDecodeError,
        KeyError,
    ):
        return _fallback_intent(message), False


def _answer_from_context(
    message: str, matches: list[dict], kind: str
) -> tuple[str, bool]:
    if not matches:
        return "", False
    fallback = _extractive_answer(matches, kind)
    context = "\n\n".join(f"[{item['file_name']}]\n{item['text']}" for item in matches)
    prompt = (
        "You are Ledger Local's offline help agent. Answer only from the supplied "
        f"{kind} context. Do not invent facts. If the context is insufficient, "
        "state exactly what is missing. Keep the answer concise.\n"
        f"Question: {message}\nContext:\n{context[:6000]}"
    )
    try:
        return generate_local_text(prompt), True
    except (httpx.HTTPError, RuntimeError):
        return fallback, False


def _extractive_answer(matches: list[dict], kind: str) -> str:
    excerpts = []
    for item in matches[:3]:
        text = " ".join(item["text"].split())
        excerpts.append(f"{item['file_name']}: {text[:420]}")
    if kind == "help guide":
        return "Local help guide: " + " ".join(excerpts)
    return "Relevant uploaded document text: " + " ".join(excerpts)


def _plain_help_answer(message: str, matches: list[dict]) -> str | None:
    if "rule" not in message.casefold() or not any(
        item["file_name"] == "rules-guide.md" for item in matches
    ):
        return None
    return (
        "Rules automatically classify familiar transactions during statement "
        "imports. Open Rules, give the rule a clear name, then choose Merchant "
        "name contains or Description contains. Enter the text to find, such as "
        "REWE or Netflix. Choose Set category and enter an existing category, or "
        "choose it from the saved category dropdown. Alternatively, choose Set "
        "income or expense type and select Income or Expense. Save the "
        "rule. It will run on new extracted rows; use Apply all rules for existing "
        "rows that are still waiting for review. Validated transactions are not "
        "changed."
    )


def _knowledge_answer(db: Session, message: str, basis: str) -> dict:
    matches = search_local_knowledge(db, message, basis, limit=3)
    plain_answer = (
        _plain_help_answer(message, matches) if basis == "help guide" else None
    )
    if plain_answer:
        answer, local_ai_used = plain_answer, False
    else:
        answer, local_ai_used = _answer_from_context(message, matches, basis)
    missing = (
        []
        if matches
        else [
            (
                "No processed uploaded document matched the question."
                if basis == "document"
                else "No local help guide matched the question."
            )
        ]
    )
    return {
        "answer": answer or missing[0],
        "source_basis": [basis],
        "sources": [
            {
                "basis": basis,
                "file_name": item["file_name"],
                "source_id": item["source_id"],
                "excerpt": item["text"][:240],
            }
            for item in matches
        ],
        "missing_data": missing,
        "local_ai_used": local_ai_used,
    }


def _document_transaction_matches(db: Session, message: str) -> list[dict]:
    start, end = _period(message)
    ignored = {
        "what",
        "which",
        "show",
        "from",
        "about",
        "document",
        "statement",
        "uploaded",
        "payment",
        "payments",
        "transaction",
        "transactions",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
    terms = {
        term
        for term in re.findall(r"[\w.-]{3,}", message.casefold())
        if term not in ignored and not term.isdigit()
    }
    rows = db.execute(
        select(Transaction, Document.file_name)
        .join(Document, Transaction.document_id == Document.id)
        .where(Transaction.transaction_date.between(start, end))
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()
    matches = []
    for transaction, file_name in rows:
        searchable = f"{transaction.vendor} {transaction.description}".casefold()
        score = sum(term in searchable for term in terms)
        if terms and score == 0:
            continue
        matches.append(
            {
                "basis": "document",
                "document_id": transaction.document_id,
                "file_name": file_name,
                "transaction_id": transaction.id,
                "date": str(transaction.transaction_date),
                "vendor": transaction.vendor,
                "description": transaction.description,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "type": transaction.transaction_type,
                "score": score,
            }
        )
    ranked = sorted(matches, key=lambda item: (-item["score"], item["date"]))
    if ranked:
        best_score = ranked[0]["score"]
        if best_score > 1:
            ranked = [item for item in ranked if item["score"] == best_score]
    return ranked[:20]


def _document_answer(db: Session, message: str) -> dict:
    knowledge = _knowledge_answer(db, message, "document")
    matches = _document_transaction_matches(db, message)
    if not matches:
        return knowledge
    debits = sum(Decimal(item["amount"]) for item in matches if item["type"] == "debit")
    credits = sum(
        Decimal(item["amount"]) for item in matches if item["type"] == "credit"
    )
    rows = "; ".join(
        f"{item['date']} {item['vendor']} {item['amount']} {item['currency']} "
        f"({item['type']})"
        for item in matches[:10]
    )
    total_text = []
    if debits:
        total_text.append(f"debits {debits:.2f}")
    if credits:
        total_text.append(f"credits {credits:.2f}")
    knowledge["answer"] = (
        f"Found {len(matches)} matching extracted transaction(s)"
        + (f", totaling {', '.join(total_text)}" if total_text else "")
        + f": {rows}."
    )
    knowledge["sources"] = [*matches, *knowledge["sources"]]
    knowledge["missing_data"] = []
    return knowledge


def _report_parameters(message: str) -> tuple[str, date, date, str]:
    lower = message.casefold()
    report_type = next(
        (
            item
            for item in (
                "tax",
                "investment",
                "debt",
                "property",
                "protection",
                "yearly",
                "monthly",
            )
            if item in lower
        ),
        "monthly",
    )
    output_format = next(
        (item for item in ("xlsx", "csv", "pdf") if item in lower), "pdf"
    )
    period_message = message
    if report_type == "monthly" and not any(
        item in lower
        for item in (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
            "this month",
            "last month",
        )
    ):
        period_message += " this month"
    start, end = _period(period_message)
    return report_type, start, end, output_format


def _troubleshooting(db: Session, message: str) -> dict:
    guide = _knowledge_answer(db, message, "help guide")
    pending = db.scalar(
        select(func.count(Transaction.id)).where(Transaction.is_validated.is_(False))
    )
    unprocessed = db.scalar(
        select(func.count(Document.id)).where(
            Document.status.in_(("uploaded", "failed", "extraction_completed"))
        )
    )
    details = (
        f" Local status: {pending or 0} transaction(s) await review and "
        f"{unprocessed or 0} document(s) are unprocessed, failed, or produced no rows."
    )
    guide["answer"] += details
    guide["sources"].append(
        {
            "basis": "database",
            "pending_review": pending or 0,
            "documents_needing_attention": unprocessed or 0,
        }
    )
    guide["source_basis"] = sorted({*guide["source_basis"], "database"})
    return guide


def run_help_agent(db: Session, message: str) -> dict:
    intent, classifier_used = _classify(message)
    if intent not in INTENTS:
        intent = "app_help"

    if intent == "finance_query":
        result = answer_finance_question(db, message)
        payload = {
            "answer": result["answer"],
            "source_basis": ["database"],
            "sources": [
                {"basis": "database", **source} for source in result["sources"]
            ],
            "missing_data": (
                [result["missing_data_warning"]]
                if result["missing_data_warning"]
                else []
            ),
            "local_ai_used": classifier_used,
        }
    elif intent == "document_query":
        payload = _document_answer(db, message)
    elif intent == "report_request":
        report_type, start, end, output_format = _report_parameters(message)
        report = generate_report(db, report_type, start, end, output_format)
        transaction_count = db.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.is_validated.is_(True),
                Transaction.is_duplicate.is_(False),
                Transaction.transaction_date.between(start, end),
            )
        )
        payload = {
            "answer": (
                f"Generated the {report_type} {output_format.upper()} report for "
                f"{start} to {end}."
            ),
            "source_basis": ["generated report", "database"],
            "sources": [
                {
                    "basis": "generated report",
                    "report_id": report.id,
                    "report_type": report.report_type,
                    "period_start": str(start),
                    "period_end": str(end),
                }
            ],
            "missing_data": (
                []
                if transaction_count
                else ["No validated transactions exist for the requested period."]
            ),
            "local_ai_used": classifier_used,
            "report": {
                "id": report.id,
                "format": report.format,
                "download_url": f"/api/reports/{report.id}/download",
            },
        }
    elif intent == "troubleshooting":
        payload = _troubleshooting(db, message)
    else:
        payload = _knowledge_answer(db, message, "help guide")

    payload["intent"] = intent
    payload["local_ai_used"] = payload["local_ai_used"] or classifier_used
    payload.setdefault("report", None)
    return payload
