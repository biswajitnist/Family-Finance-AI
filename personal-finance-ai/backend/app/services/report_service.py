import csv
from calendar import monthrange
from datetime import date
from decimal import Decimal
from uuid import uuid4

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import Category
from app.models.finance import Insurance, Investment, Loan, Property, Report
from app.models.transaction import Transaction
from app.services.loan_balance_service import loan_balance


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def cash_flow_comparison(db: Session, year: int, month: int) -> dict:
    previous_year, previous_month = _previous_month(year, month)
    current_start, current_end = _month_bounds(year, month)
    previous_start, previous_end = _month_bounds(previous_year, previous_month)
    base = (
        Transaction.is_validated.is_(True),
        Transaction.is_duplicate.is_(False),
    )

    def month_rows(start: date, end: date) -> list[Transaction]:
        return list(
            db.scalars(
                select(Transaction)
                .where(*base, Transaction.transaction_date.between(start, end))
                .order_by(Transaction.transaction_date, Transaction.id)
            ).all()
        )

    current_rows = month_rows(current_start, current_end)
    previous_rows = month_rows(previous_start, previous_end)

    def totals(rows: list[Transaction]) -> dict[str, Decimal]:
        income = sum(
            (item.amount for item in rows if item.transaction_type == "credit"),
            Decimal("0"),
        )
        expense = sum(
            (item.amount for item in rows if item.transaction_type == "debit"),
            Decimal("0"),
        )
        return {"income": income, "expense": expense, "cash_flow": income - expense}

    category_rows = db.execute(
        select(
            Transaction.transaction_type,
            func.coalesce(Category.name, "Uncategorized"),
            func.sum(Transaction.amount),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            *base,
            Transaction.transaction_date.between(current_start, current_end),
        )
        .group_by(Transaction.transaction_type, Category.name)
        .order_by(func.sum(Transaction.amount).desc())
    ).all()

    current_by_day: dict[int, dict[str, Decimal]] = {}
    previous_by_day: dict[int, dict[str, Decimal]] = {}
    for rows, target in (
        (current_rows, current_by_day),
        (previous_rows, previous_by_day),
    ):
        for item in rows:
            day = item.transaction_date.day
            values = target.setdefault(
                day, {"income": Decimal("0"), "expense": Decimal("0")}
            )
            key = "income" if item.transaction_type == "credit" else "expense"
            values[key] += item.amount

    daily = []
    current_income = current_expense = Decimal("0")
    previous_income = previous_expense = Decimal("0")
    for day in range(1, max(monthrange(year, month)[1], previous_end.day) + 1):
        current_income += current_by_day.get(day, {}).get("income", Decimal("0"))
        current_expense += current_by_day.get(day, {}).get("expense", Decimal("0"))
        previous_income += previous_by_day.get(day, {}).get("income", Decimal("0"))
        previous_expense += previous_by_day.get(day, {}).get("expense", Decimal("0"))
        daily.append(
            {
                "day": day,
                "current_income": current_income,
                "current_expense": current_expense,
                "current_cash_flow": current_income - current_expense,
                "previous_income": previous_income,
                "previous_expense": previous_expense,
                "previous_cash_flow": previous_income - previous_expense,
            }
        )

    return {
        "currency": "EUR",
        "current_month": f"{year:04d}-{month:02d}",
        "previous_month": f"{previous_year:04d}-{previous_month:02d}",
        "current": totals(current_rows),
        "previous": totals(previous_rows),
        "expense_categories": [
            {"category": category, "amount": Decimal(amount)}
            for transaction_type, category, amount in category_rows
            if transaction_type == "debit"
        ],
        "income_categories": [
            {"category": category, "amount": Decimal(amount)}
            for transaction_type, category, amount in category_rows
            if transaction_type == "credit"
        ],
        "daily": daily,
    }


def _report_rows(db: Session, start: date, end: date) -> list[list[str]]:
    transactions = db.execute(
        select(Transaction, Category.name)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.is_validated.is_(True),
            Transaction.is_duplicate.is_(False),
            Transaction.transaction_date.between(start, end),
        )
        .order_by(Transaction.transaction_date)
    ).all()
    return [
        [
            str(item.transaction_date),
            item.vendor,
            category or "Uncategorized",
            item.transaction_type,
            str(item.amount),
            item.currency,
            item.description,
        ]
        for item, category in transactions
    ]


def _summary(rows: list[list[str]]) -> dict[str, Decimal]:
    income = sum((Decimal(row[4]) for row in rows if row[3] == "credit"), Decimal("0"))
    expenses = sum((Decimal(row[4]) for row in rows if row[3] == "debit"), Decimal("0"))
    return {"income": income, "expenses": expenses, "net": income - expenses}


def _extra_sections(db: Session, report_type: str) -> list[list[str]]:
    if report_type == "investment":
        return [
            ["Asset", "Type", "Quantity", "Current value", "Currency"],
            *[
                [
                    item.asset_name,
                    item.asset_type,
                    str(item.quantity),
                    str(item.current_value),
                    item.currency,
                ]
                for item in db.scalars(select(Investment)).all()
            ],
        ]
    if report_type == "debt":
        loans = list(db.scalars(select(Loan)).all())
        return [
            [
                "Lender",
                "Type",
                "Adjusted balance",
                "Payments applied",
                "Rate",
                "Monthly payment",
            ],
            *[
                [
                    item.lender,
                    item.loan_type,
                    str(loan_balance(db, item, len(loans)).adjusted_balance),
                    str(loan_balance(db, item, len(loans)).payments_applied),
                    str(item.interest_rate),
                    str(item.monthly_payment),
                ]
                for item in loans
            ],
        ]
    if report_type == "property":
        return [
            ["Property", "Value", "Rent/month", "Costs/month", "Currency"],
            *[
                [
                    item.name,
                    str(item.current_value),
                    str(item.monthly_rental_income),
                    str(item.monthly_costs),
                    item.currency,
                ]
                for item in db.scalars(select(Property)).all()
            ],
        ]
    if report_type == "protection":
        return [
            ["Provider", "Policy type", "Coverage", "Premium", "Frequency"],
            *[
                [
                    item.provider,
                    item.policy_type,
                    str(item.coverage_amount),
                    str(item.premium_amount),
                    item.premium_frequency,
                ]
                for item in db.scalars(select(Insurance)).all()
            ],
        ]
    return []


def generate_report(
    db: Session, report_type: str, start: date, end: date, output_format: str
) -> Report:
    rows = _report_rows(db, start, end)
    totals = _summary(rows)
    filename = f"{report_type}_{start}_{end}_{uuid4().hex[:8]}.{output_format}"
    path = settings.reports_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "Date",
        "Vendor",
        "Category",
        "Type",
        "Amount",
        "Currency",
        "Description",
    ]
    extras = _extra_sections(db, report_type)
    if output_format == "csv":
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Report", report_type, "Period", start, end])
            writer.writerow(
                [
                    "Income",
                    totals["income"],
                    "Expenses",
                    totals["expenses"],
                    "Net",
                    totals["net"],
                ]
            )
            writer.writerow(headers)
            writer.writerows(rows)
            if extras:
                writer.writerow([])
                writer.writerows(extras)
    elif output_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Transactions"
        sheet.append(["Report", report_type, "Period", str(start), str(end)])
        sheet.append(
            [
                "Income",
                totals["income"],
                "Expenses",
                totals["expenses"],
                "Net",
                totals["net"],
            ]
        )
        sheet.append([])
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        if extras:
            extra_sheet = workbook.create_sheet("Details")
            for row in extras:
                extra_sheet.append(row)
        workbook.save(path)
    else:
        styles = getSampleStyleSheet()
        story = [
            Paragraph(f"Ledger Local - {report_type.title()} Report", styles["Title"]),
            Paragraph(f"Period: {start} to {end}", styles["Normal"]),
            Spacer(1, 12),
            Table(
                [
                    ["Income", "Expenses", "Net"],
                    [
                        str(totals["income"]),
                        str(totals["expenses"]),
                        str(totals["net"]),
                    ],
                ]
            ),
            Spacer(1, 16),
            Table([headers, *rows], repeatRows=1),
        ]
        if extras:
            story.extend(
                [
                    Spacer(1, 16),
                    Paragraph("Module details", styles["Heading2"]),
                    Table(extras, repeatRows=1),
                ]
            )
        SimpleDocTemplate(str(path), pagesize=A4).build(story)
    report = Report(
        user_id=1,
        report_type=report_type,
        period_start=start,
        period_end=end,
        format=output_format,
        file_path=str(path),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
