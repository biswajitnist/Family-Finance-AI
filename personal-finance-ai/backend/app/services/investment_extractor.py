import re
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.finance import Investment

PORTFOLIO_MARKERS = (
    "portfolio",
    "since purchase",
    "alphabet",
    "xtrackers",
    "nvidia",
    "ishares",
)
NOISE = {
    "home",
    "find",
    "profile",
    "portfolio",
    "since purchase",
}


def looks_like_portfolio(text: str) -> bool:
    normalized = text.casefold()
    return (
        "portfolio" in normalized
        and sum(marker in normalized for marker in PORTFOLIO_MARKERS) >= 3
    )


def _money(value: str) -> Decimal:
    compact = value.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(compact).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0")


def _clean_name(lines: list[str]) -> str:
    useful = [
        line
        for line in lines
        if not any(noise in line.casefold() for noise in NOISE)
        and not re.fullmatch(r"[\W\d]+", line)
        and not re.match(r"^\d{1,2}:\d{2}\b", line)
    ]
    joined = " ".join(useful)
    joined = re.sub(r"[{}©®@|]", " ", joined)
    joined = re.sub(r"^\W*[A-Z]\s+(?=[A-Z][a-z])", "", joined)
    joined = re.sub(r"^D:\s*", "", joined)
    joined = re.sub(r"\s+\d{1,4}(?:\s+\d{1,2})?\s*$", "", joined)
    joined = re.sub(r"\s+a6\s+Vak\s+", " ", joined, flags=re.IGNORECASE)
    joined = re.sub(r"\s+", " ", joined).strip(" .:-")
    if joined.startswith("lonQ"):
        joined = "IonQ" + joined[4:]
    return joined[:160]


def extract_holdings(text: str) -> list[dict[str, object]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    holdings: list[dict[str, object]] = []
    used_names: set[str] = set()
    previous_value_line = -1
    for index, line in enumerate(lines):
        amount_match = re.match(r'^["\']?(\d{1,3}(?:\.\d{3})*|\d{3,5})\s*€', line)
        if not amount_match:
            continue
        current_value = _money(amount_match.group(1))
        if current_value <= 0:
            continue
        name_lines = lines[previous_value_line + 1 : index]
        previous_value_line = index
        name = _clean_name(name_lines)
        if not name or name.casefold() in used_names:
            continue
        used_names.add(name.casefold())
        asset_type = (
            "ETF"
            if any(
                marker in name.casefold()
                for marker in ("xtrackers", "ishares", "acc", "etf")
            )
            else "Stock"
        )
        holdings.append(
            {
                "asset_name": name,
                "asset_type": asset_type,
                "quantity": Decimal("0"),
                "average_price": Decimal("0"),
                "current_value": current_value,
                "currency": "EUR",
            }
        )
    return holdings


def store_holdings(
    db: Session, document: Document, holdings: list[dict[str, object]]
) -> int:
    db.execute(delete(Investment).where(Investment.source_document_id == document.id))
    for holding in holdings:
        db.add(
            Investment(
                user_id=document.user_id,
                account_id=document.source_account_id,
                source_document_id=document.id,
                **holding,
            )
        )
    db.flush()
    return len(holdings)
