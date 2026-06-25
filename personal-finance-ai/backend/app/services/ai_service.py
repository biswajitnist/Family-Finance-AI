import json
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import Category
from app.models.transaction import Transaction


class ClassificationResult(BaseModel):
    category: str
    confidence: float = Field(ge=0, le=1)
    reason: str = ""


class ExtractedTransaction(BaseModel):
    transaction_date: date
    booking_date: date | None = None
    vendor: str = Field(min_length=1, max_length=180)
    description: str = ""
    amount: Decimal
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    transaction_type: str = Field(pattern="^(debit|credit)$")
    category: str | None = None
    payment_method: str | None = None
    reference_number: str | None = None
    iban: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, value: object) -> Decimal:
        normalized = str(value).replace(" ", "").replace(",", ".")
        try:
            return abs(Decimal(normalized)).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise ValueError("invalid amount") from exc

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ExtractionResult(BaseModel):
    transactions: list[ExtractedTransaction]


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.ollama_url,
        timeout=settings.ollama_timeout_seconds,
    )


def ollama_status() -> dict:
    result = {
        "enabled": settings.ollama_enabled,
        "available": False,
        "model": settings.ollama_model,
        "models": [],
        "model_installed": False,
        "url": settings.ollama_url,
        "external_cloud_enabled": False,
    }
    if not settings.ollama_enabled:
        return result
    try:
        with _client() as client:
            response = client.get("/api/tags")
            response.raise_for_status()
        models = [
            item.get("name", "")
            for item in response.json().get("models", [])
            if item.get("name")
        ]
        configured_base = settings.ollama_model.split(":")[0]
        result.update(
            {
                "available": True,
                "models": models,
                "model_installed": any(
                    model == settings.ollama_model
                    or model.split(":")[0] == configured_base
                    for model in models
                ),
            }
        )
    except (httpx.HTTPError, KeyError, TypeError):
        pass
    return result


def ollama_available() -> bool:
    status = ollama_status()
    return bool(status["available"] and status["model_installed"])


def _generate_json(prompt: str) -> str:
    status = ollama_status()
    if not status["available"]:
        raise RuntimeError("Ollama is not running")
    if not status["model_installed"]:
        raise RuntimeError(f"Ollama model '{settings.ollama_model}' is not installed")
    with _client() as client:
        response = client.post(
            "/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0,
                    "num_ctx": settings.ollama_context_length,
                },
            },
        )
        response.raise_for_status()
    return response.json()["response"]


def generate_local_json(prompt: str) -> str:
    return _generate_json(prompt)


def generate_local_text(prompt: str, timeout_seconds: int = 12) -> str:
    status = ollama_status()
    if not status["available"] or not status["model_installed"]:
        raise RuntimeError("Configured local Ollama model is unavailable")
    with httpx.Client(
        base_url=settings.ollama_url,
        timeout=timeout_seconds,
    ) as client:
        response = client.post(
            "/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_ctx": settings.ollama_context_length,
                },
            },
        )
        response.raise_for_status()
    return str(response.json()["response"]).strip()


def classify_transaction(db: Session, transaction: Transaction) -> bool:
    if not ollama_available():
        return False
    categories = list(db.scalars(select(Category.name)).all())
    prompt = (
        "You are a local personal-finance classifier. Return only valid JSON "
        'matching {"category": string, "confidence": number, "reason": string}. '
        f"Choose exactly one category from: {json.dumps(categories)}.\n"
        f"Vendor: {transaction.vendor}\n"
        f"Description: {transaction.description}\n"
        f"Type: {transaction.transaction_type}\n"
        f"Amount: {transaction.amount} {transaction.currency}"
    )
    try:
        result = ClassificationResult.model_validate_json(_generate_json(prompt))
    except (
        httpx.HTTPError,
        KeyError,
        RuntimeError,
        ValidationError,
        json.JSONDecodeError,
    ):
        return False
    category = db.scalar(select(Category).where(Category.name.ilike(result.category)))
    if category is None:
        return False
    transaction.category_id = category.id
    transaction.confidence = Decimal(str(result.confidence)).quantize(Decimal("0.0001"))
    transaction.classification_source = "ollama"
    db.commit()
    return True


def extract_transactions(text: str, document_type: str) -> list[dict[str, str]]:
    if not text.strip() or not ollama_available():
        return []
    prompt = (
        "You are a local financial document extraction engine. Extract only "
        "transactions explicitly present in the document. Never invent values. "
        "Return only valid JSON matching this shape:\n"
        '{"transactions":[{"transaction_date":"YYYY-MM-DD",'
        '"booking_date":"YYYY-MM-DD or null","vendor":"",'
        '"description":"","amount":"positive decimal","currency":"EUR",'
        '"transaction_type":"debit or credit","category":null,'
        '"payment_method":null,"reference_number":null,"iban":null,'
        '"confidence":0.0}]}\n'
        "Use debit for money leaving the account and credit for money entering. "
        f"Document type: {document_type}\nDocument text:\n{text[:30000]}"
    )
    try:
        result = ExtractionResult.model_validate_json(_generate_json(prompt))
    except (
        httpx.HTTPError,
        KeyError,
        RuntimeError,
        ValidationError,
        json.JSONDecodeError,
    ):
        return []
    return [
        {
            "date": str(item.transaction_date),
            "booking_date": str(item.booking_date) if item.booking_date else "",
            "vendor": item.vendor,
            "description": item.description,
            "amount": str(item.amount),
            "currency": item.currency,
            "type": item.transaction_type,
            "category": item.category or "",
            "payment_method": item.payment_method or "",
            "reference_number": item.reference_number or "",
            "iban": item.iban or "",
            "confidence": str(item.confidence),
        }
        for item in result.transactions
    ]
