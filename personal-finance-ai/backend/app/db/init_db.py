from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.user import User
from app.services.provider_config_service import seed_market_providers

DEFAULT_CATEGORIES = [
    ("Salary", "income"),
    ("Bonus", "income"),
    ("Property Income", "income"),
    ("Grocery", "expense"),
    ("Utilities", "expense"),
    ("Insurance", "expense"),
    ("Transport", "expense"),
    ("Restaurants", "expense"),
    ("Shopping", "expense"),
    ("Healthcare", "expense"),
    ("Education", "expense"),
    ("Travel", "expense"),
    ("Subscriptions", "expense"),
    ("Loan", "transfer"),
    ("Loan Repayment", "expense"),
    ("Loan Interest", "expense"),
    ("Pension", "transfer"),
    ("Investment", "transfer"),
    ("Tax", "expense"),
    ("Other", "expense"),
]

CATEGORY_STYLES = {
    "Salary": ("income", "green"),
    "Bonus": ("sparkles", "green"),
    "Property Income": ("properties", "green"),
    "Grocery": ("grocery", "amber"),
    "Utilities": ("utilities", "orange"),
    "Insurance": ("insurance", "teal"),
    "Transport": ("transport", "blue"),
    "Restaurants": ("restaurant", "orange"),
    "Shopping": ("shopping", "blue"),
    "Healthcare": ("health", "red"),
    "Education": ("education", "violet"),
    "Travel": ("travel", "blue"),
    "Subscriptions": ("subscription", "violet"),
    "Loan": ("loans", "green"),
    "Loan Repayment": ("loans", "green"),
    "Loan Interest": ("loans", "orange"),
    "Pension": ("institution", "teal"),
    "Investment": ("investments", "green"),
    "Tax": ("institution", "red"),
    "Other": ("category", "slate"),
}


def seed_defaults(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)) is None:
        db.add(User(name="Local User", base_currency="EUR", country="DE"))

    existing = set(db.scalars(select(Category.name)).all())
    for name, category_type in DEFAULT_CATEGORIES:
        if name not in existing:
            icon, color = CATEGORY_STYLES.get(name, ("category", "green"))
            db.add(
                Category(name=name, type=category_type, icon=icon, color=color)
            )
    db.commit()
    seed_market_providers(db)
