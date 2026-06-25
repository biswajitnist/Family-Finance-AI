from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import String, and_, asc, cast, desc, func, literal, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.models.account import Account
from app.models.category import Category
from app.models.document import Document
from app.models.finance import Insurance, Investment, Loan, MonthlyBudget, Property
from app.models.transaction import Transaction
from app.schemas.custom_report import ReportConfig, ReportResult
from app.services.dashboard import dashboard_summary


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    label: str
    description: str
    fields: dict[str, dict[str, Any]]
    build: Callable[[], Select[Any]] | None = None
    default_order: ColumnElement[Any] | None = None
    calculated: bool = False


def _field(
    label: str,
    field_type: str,
    expression: ColumnElement[Any],
) -> dict[str, Any]:
    return {"label": label, "type": field_type, "expression": expression}


def _transaction_query(validated: bool | None = True) -> Select[Any]:
    statement = (
        select()
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .join(Account, Transaction.account_id == Account.id)
        .where(Transaction.user_id == 1, Transaction.is_duplicate.is_(False))
    )
    if validated is not None:
        statement = statement.where(Transaction.is_validated.is_(validated))
    return statement


TRANSACTION_FIELDS = {
    "transaction_date": _field(
        "Transaction Date",
        "date",
        Transaction.transaction_date,
    ),
    "month": _field(
        "Month",
        "date",
        func.strftime("%Y-%m", Transaction.transaction_date),
    ),
    "vendor": _field("Merchant", "text", Transaction.vendor),
    "description": _field("Description", "text", Transaction.description),
    "amount": _field("Amount", "number", Transaction.amount),
    "currency": _field("Currency", "text", Transaction.currency),
    "transaction_type": {
        **_field("Transaction Type", "text", Transaction.transaction_type),
        "options": [
            {"label": "Expense", "value": "debit"},
            {"label": "Income", "value": "credit"},
        ],
    },
    "category": _field(
        "Category",
        "text",
        func.coalesce(Category.name, literal("Uncategorized")),
    ),
    "account": _field("Account", "text", Account.name),
    "payment_method": _field("Payment Method", "text", Transaction.payment_method),
    "recurrence_frequency": _field(
        "Recurrence",
        "text",
        Transaction.recurrence_frequency,
    ),
}


SOURCES: dict[str, SourceDefinition] = {
    "transactions": SourceDefinition(
        key="transactions",
        label="Transactions",
        description="Validated, non-duplicate income and expense records.",
        fields=TRANSACTION_FIELDS,
        build=lambda: _transaction_query(validated=True),
        default_order=Transaction.transaction_date,
    ),
    "review_queue": SourceDefinition(
        key="review_queue",
        label="Review Queue",
        description="Imported transactions waiting for validation.",
        fields=TRANSACTION_FIELDS,
        build=lambda: _transaction_query(validated=False),
        default_order=Transaction.transaction_date,
    ),
    "accounts": SourceDefinition(
        key="accounts",
        label="Accounts",
        description="Bank, cash, and asset accounts with balances.",
        fields={
            "name": _field("Account", "text", Account.name),
            "type": _field("Type", "text", Account.type),
            "institution": _field("Institution", "text", Account.institution),
            "country": _field("Country", "text", Account.country),
            "opening_balance": _field(
                "Opening Balance",
                "number",
                Account.opening_balance,
            ),
            "current_balance": _field(
                "Current Balance",
                "number",
                Account.current_balance,
            ),
            "currency": _field("Currency", "text", Account.currency),
            "created_at": _field("Created", "date", Account.created_at),
        },
        build=lambda: select().select_from(Account).where(Account.user_id == 1),
        default_order=Account.created_at,
    ),
    "categories": SourceDefinition(
        key="categories",
        label="Categories",
        description="Income, expense, and transfer classification vocabulary.",
        fields={
            "name": _field("Category", "text", Category.name),
            "type": _field("Type", "text", Category.type),
            "icon": _field("Icon", "text", Category.icon),
            "color": _field("Color", "text", Category.color),
        },
        build=lambda: select().select_from(Category),
        default_order=Category.name,
    ),
    "vendors": SourceDefinition(
        key="vendors",
        label="Vendors",
        description="Merchants and payees derived from validated transactions.",
        fields={
            "vendor": TRANSACTION_FIELDS["vendor"],
            "category": TRANSACTION_FIELDS["category"],
            "amount": TRANSACTION_FIELDS["amount"],
            "transaction_type": TRANSACTION_FIELDS["transaction_type"],
            "transaction_date": TRANSACTION_FIELDS["transaction_date"],
        },
        build=lambda: _transaction_query(validated=True).where(
            Transaction.vendor.is_not(None),
        ),
        default_order=Transaction.transaction_date,
    ),
    "recurring_payments": SourceDefinition(
        key="recurring_payments",
        label="Recurring Payments",
        description="Transactions detected as recurring bills, income, or transfers.",
        fields={
            "vendor": TRANSACTION_FIELDS["vendor"],
            "amount": TRANSACTION_FIELDS["amount"],
            "category": TRANSACTION_FIELDS["category"],
            "recurrence_frequency": TRANSACTION_FIELDS["recurrence_frequency"],
            "transaction_type": TRANSACTION_FIELDS["transaction_type"],
            "transaction_date": TRANSACTION_FIELDS["transaction_date"],
        },
        build=lambda: _transaction_query(validated=True).where(
            Transaction.recurrence_frequency.is_not(None),
        ),
        default_order=Transaction.transaction_date,
    ),
    "investments": SourceDefinition(
        key="investments",
        label="Investments",
        description="Portfolio holdings and market values.",
        fields={
            "asset_name": _field("Asset", "text", Investment.asset_name),
            "asset_type": _field("Asset Type", "text", Investment.asset_type),
            "ticker": _field("Ticker", "text", Investment.ticker),
            "broker": _field("Broker", "text", Investment.broker),
            "country": _field("Country", "text", Investment.country),
            "quantity": _field("Quantity", "number", Investment.quantity),
            "average_price": _field(
                "Average Price",
                "number",
                Investment.average_price,
            ),
            "current_value": _field(
                "Current Value",
                "number",
                Investment.current_value,
            ),
            "currency": _field("Currency", "text", Investment.currency),
            "updated_at": _field("Updated", "date", Investment.updated_at),
        },
        build=lambda: select().select_from(Investment).where(Investment.user_id == 1),
        default_order=Investment.updated_at,
    ),
    "loans": SourceDefinition(
        key="loans",
        label="Loans",
        description="Loan balances, rates, and monthly payments.",
        fields={
            "lender": _field("Lender", "text", Loan.lender),
            "loan_type": _field("Loan Type", "text", Loan.loan_type),
            "current_balance": _field(
                "Outstanding Balance",
                "number",
                Loan.current_balance,
            ),
            "original_amount": _field(
                "Original Amount",
                "number",
                Loan.original_amount,
            ),
            "interest_rate": _field("Interest Rate", "number", Loan.interest_rate),
            "monthly_payment": _field(
                "Monthly Payment",
                "number",
                Loan.monthly_payment,
            ),
            "currency": _field("Currency", "text", Loan.currency),
            "start_date": _field("Start Date", "date", Loan.start_date),
            "end_date": _field("End Date", "date", Loan.end_date),
        },
        build=lambda: select().select_from(Loan).where(Loan.user_id == 1),
        default_order=Loan.id,
    ),
    "budgets": SourceDefinition(
        key="budgets",
        label="Budgets",
        description="Monthly budget limits by category.",
        fields={
            "period": _field(
                "Period",
                "date",
                func.printf("%04d-%02d", MonthlyBudget.year, MonthlyBudget.month),
            ),
            "year": _field("Year", "number", MonthlyBudget.year),
            "month": _field("Month", "number", MonthlyBudget.month),
            "category": _field(
                "Category",
                "text",
                func.coalesce(Category.name, literal("General")),
            ),
            "amount": _field("Budget Amount", "number", MonthlyBudget.amount),
            "currency": _field("Currency", "text", MonthlyBudget.currency),
            "notes": _field("Notes", "text", MonthlyBudget.notes),
        },
        build=lambda: (
            select()
            .select_from(MonthlyBudget)
            .outerjoin(Category, MonthlyBudget.category_id == Category.id)
            .where(MonthlyBudget.user_id == 1)
        ),
        default_order=MonthlyBudget.id,
    ),
    "properties": SourceDefinition(
        key="properties",
        label="Properties",
        description="Real-estate values, rent, and costs.",
        fields={
            "name": _field("Property", "text", Property.name),
            "country": _field("Country", "text", Property.country),
            "current_value": _field("Current Value", "number", Property.current_value),
            "purchase_price": _field(
                "Purchase Price",
                "number",
                Property.purchase_price,
            ),
            "monthly_rental_income": _field(
                "Monthly Rent",
                "number",
                Property.monthly_rental_income,
            ),
            "monthly_costs": _field("Monthly Costs", "number", Property.monthly_costs),
            "currency": _field("Currency", "text", Property.currency),
        },
        build=lambda: select().select_from(Property).where(Property.user_id == 1),
        default_order=Property.id,
    ),
    "insurance": SourceDefinition(
        key="insurance",
        label="Insurance",
        description="Policies, coverage, and premiums.",
        fields={
            "provider": _field("Provider", "text", Insurance.provider),
            "policy_type": _field("Policy Type", "text", Insurance.policy_type),
            "coverage_amount": _field(
                "Coverage",
                "number",
                Insurance.coverage_amount,
            ),
            "premium_amount": _field("Premium", "number", Insurance.premium_amount),
            "premium_frequency": _field(
                "Frequency",
                "text",
                Insurance.premium_frequency,
            ),
            "currency": _field("Currency", "text", Insurance.currency),
            "is_active": _field("Active", "text", Insurance.is_active),
        },
        build=lambda: select().select_from(Insurance).where(Insurance.user_id == 1),
        default_order=Insurance.id,
    ),
    "documents": SourceDefinition(
        key="documents",
        label="Documents",
        description="Uploaded source documents and processing status.",
        fields={
            "file_name": _field("File", "text", Document.file_name),
            "document_type": _field("Document Type", "text", Document.document_type),
            "status": _field("Status", "text", Document.status),
            "validation_status": _field(
                "Validation",
                "text",
                Document.validation_status,
            ),
            "uploaded_at": _field("Uploaded", "date", Document.uploaded_at),
        },
        build=lambda: select().select_from(Document).where(Document.user_id == 1),
        default_order=Document.uploaded_at,
    ),
    "net_worth": SourceDefinition(
        key="net_worth",
        label="Net Worth",
        description="Calculated from accounts, investments, loans, and properties.",
        fields={
            "metric": _field("Metric", "text", literal("metric")),
            "value": _field("Value", "number", literal(0)),
            "currency": _field("Currency", "text", literal("EUR")),
        },
        calculated=True,
    ),
}

AGGREGATIONS = {
    "sum": func.sum,
    "average": func.avg,
    "count": func.count,
    "minimum": func.min,
    "maximum": func.max,
}

CHART_TYPES = [
    ("table", "Table"),
    ("bar", "Bar Chart"),
    ("line", "Line Chart"),
    ("pie", "Pie Chart"),
    ("donut", "Donut Chart"),
    ("area", "Area Chart"),
    ("stacked_bar", "Stacked Bar Chart"),
    ("grouped_bar", "Grouped Bar Chart"),
    ("horizontal_bar", "Horizontal Bar Chart"),
    ("kpi", "KPI Card"),
    ("trend", "Trend Card"),
]

FILTER_OPERATORS = [
    ("equals", "Equals"),
    ("not_equals", "Not Equals"),
    ("contains", "Contains"),
    ("greater_than", "Greater Than"),
    ("less_than", "Less Than"),
    ("between", "Between"),
    ("date_range", "Date Range"),
    ("is_empty", "Is Empty"),
    ("is_not_empty", "Is Not Empty"),
]

REPORT_AGGREGATIONS = [
    ("sum", "Sum"),
    ("average", "Average"),
    ("count", "Count"),
    ("minimum", "Minimum"),
    ("maximum", "Maximum"),
    ("opening_balance", "Opening Balance"),
    ("closing_balance", "Closing Balance"),
    ("net_change", "Net Change"),
]


def report_metadata() -> dict[str, Any]:
    return {
        "data_sources": [
            {
                "key": source.key,
                "label": source.label,
                "description": source.description,
                "fields": [
                    {
                        "key": key,
                        "label": value["label"],
                        "type": value["type"],
                        "options": value.get("options", []),
                        "aggregatable": _is_aggregatable(key, value),
                    }
                    for key, value in source.fields.items()
                ],
            }
            for source in SOURCES.values()
        ],
        "chart_types": [{"key": key, "label": label} for key, label in CHART_TYPES],
        "filter_operators": [
            {"key": key, "label": label} for key, label in FILTER_OPERATORS
        ],
        "aggregations": [
            {"key": key, "label": label} for key, label in REPORT_AGGREGATIONS
        ],
        "dashboard_sections": [
            {"key": "overview", "label": "Overview"},
            {"key": "planning", "label": "Planning"},
            {"key": "insights", "label": "Insights"},
        ],
        "widget_sizes": [
            {"key": "small", "label": "Small"},
            {"key": "medium", "label": "Medium"},
            {"key": "large", "label": "Large"},
        ],
        "schedule_frequencies": [
            {"key": "manual", "label": "Manual"},
            {"key": "weekly", "label": "Weekly"},
            {"key": "monthly", "label": "Monthly"},
            {"key": "quarterly", "label": "Quarterly"},
        ],
    }


def _is_aggregatable(key: str, value: dict[str, Any]) -> bool:
    return value["type"] == "number" or key in {
        "account",
        "asset_name",
        "category",
        "lender",
        "metric",
        "provider",
        "vendor",
    }


def _source(data_source: str) -> SourceDefinition:
    source = SOURCES.get(data_source)
    if source is None:
        raise HTTPException(422, f"Data source '{data_source}' is not available.")
    return source


def _source_field(source: SourceDefinition, key: str) -> ColumnElement[Any]:
    metadata = source.fields.get(key)
    if metadata is None:
        raise HTTPException(422, f"Field '{key}' is not available for {source.label}.")
    return metadata["expression"]


def _date_range(value: Any) -> tuple[date, date]:
    today = date.today()
    if isinstance(value, str):
        if value == "this_month":
            start = today.replace(day=1)
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            return start, next_month - timedelta(days=1)
        if value == "last_month":
            end = today.replace(day=1) - timedelta(days=1)
            return end.replace(day=1), end
        if value == "this_year":
            return date(today.year, 1, 1), date(today.year, 12, 31)
        months = {"last_3_months": 3, "last_6_months": 6, "last_12_months": 12}
        if value in months:
            return today - timedelta(days=months[value] * 31), today
    if isinstance(value, list) and len(value) == 2:
        try:
            return date.fromisoformat(str(value[0])), date.fromisoformat(str(value[1]))
        except ValueError as error:
            raise HTTPException(
                422,
                "Date range values must use YYYY-MM-DD.",
            ) from error
    raise HTTPException(422, "Choose a supported date range.")


def _filter_expression(
    source: SourceDefinition,
    field_key: str,
    operator: str,
    value: Any,
) -> ColumnElement[bool]:
    expression = _source_field(source, field_key)
    if operator == "equals":
        return expression == value
    if operator == "not_equals":
        return expression != value
    if operator == "contains":
        return cast(expression, String).ilike(f"%{value}%")
    if operator == "greater_than":
        return expression > value
    if operator == "less_than":
        return expression < value
    if operator == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise HTTPException(422, "Between requires two values.")
        return expression.between(value[0], value[1])
    if operator == "date_range":
        start, end = _date_range(value)
        return expression.between(start, end)
    if operator == "is_empty":
        return or_(expression.is_(None), cast(expression, String) == "")
    if operator == "is_not_empty":
        return and_(expression.is_not(None), cast(expression, String) != "")
    raise HTTPException(422, f"Filter operator '{operator}' is not supported.")


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _calculated_net_worth(db: Session, config: ReportConfig) -> ReportResult:
    now = datetime.now(UTC)
    summary = dashboard_summary(db, now.year, now.month)
    rows = [
        {
            "metric": "Accounts",
            "value": float(summary["account_balance"]),
            "currency": summary["currency"],
        },
        {
            "metric": "Investments",
            "value": float(summary["investments"]),
            "currency": summary["currency"],
        },
        {
            "metric": "Properties",
            "value": float(summary["property_value"]),
            "currency": summary["currency"],
        },
        {
            "metric": "Debt",
            "value": float(summary["debt_balance"]),
            "currency": summary["currency"],
        },
        {
            "metric": "Net Worth",
            "value": float(summary["net_worth"]),
            "currency": summary["currency"],
        },
    ]
    columns = [
        {"key": "metric", "label": "Metric"},
        {"key": "value", "label": "Value"},
        {"key": "currency", "label": "Currency"},
    ]
    return ReportResult(
        columns=columns,
        rows=rows,
        total_rows=len(rows),
        chart_type=config.chart.type,
        x_axis=config.chart.xAxis or "metric",
        y_axis=config.chart.yAxis or "value",
        value=float(summary["net_worth"]),
        subtitle=f"Current net worth in {summary['currency']}",
    )


def _aggregate_expression(
    function_name: str,
    expression: ColumnElement[Any],
) -> ColumnElement[Any]:
    if function_name in {"opening_balance", "closing_balance", "net_change"}:
        return func.sum(expression)
    aggregate_function = AGGREGATIONS.get(function_name)
    if aggregate_function is None:
        raise HTTPException(
            422,
            f"Aggregation '{function_name}' is not supported for this source.",
        )
    return aggregate_function(expression)


def _validate_config(source: SourceDefinition, config: ReportConfig) -> None:
    for key in config.fields + config.groupBy:
        _source_field(source, key)
    if config.aggregation:
        _source_field(source, config.aggregation.field)
    if config.sort:
        _source_field(source, config.sort.field)


def _selected_fields(
    source: SourceDefinition,
    config: ReportConfig,
) -> list[tuple[str, ColumnElement[Any]]]:
    if config.aggregation:
        selected = [(key, _source_field(source, key)) for key in config.groupBy]
        selected.append(
            (
                config.aggregation.field,
                _aggregate_expression(
                    config.aggregation.function,
                    _source_field(source, config.aggregation.field),
                ),
            )
        )
        return selected
    return [(key, _source_field(source, key)) for key in config.fields]


def run_report(db: Session, data_source: str, config: ReportConfig) -> ReportResult:
    source = _source(data_source)
    if source.key == "net_worth":
        return _calculated_net_worth(db, config)
    if source.build is None:
        raise HTTPException(422, "This data source cannot be queried.")

    _validate_config(source, config)
    selected = _selected_fields(source, config)
    if not selected:
        raise HTTPException(422, "Select at least one report field.")

    labels = [expression.label(key) for key, expression in selected]
    statement = source.build().with_only_columns(*labels)
    for report_filter in config.filters:
        statement = statement.where(
            _filter_expression(
                source,
                report_filter.field,
                report_filter.operator,
                report_filter.value,
            )
        )
    if config.aggregation:
        statement = statement.group_by(
            *[_source_field(source, key) for key in config.groupBy]
        )

    selected_keys = [key for key, _ in selected]
    if config.sort and config.sort.field in selected_keys:
        sort_expression = next(
            label
            for key, label in zip(selected_keys, labels, strict=False)
            if key == config.sort.field
        )
        order = (
            desc(sort_expression)
            if config.sort.direction == "desc"
            else asc(sort_expression)
        )
        statement = statement.order_by(order)
    elif config.aggregation:
        statement = statement.order_by(desc(labels[-1]))
    elif source.default_order is not None:
        statement = statement.order_by(desc(source.default_order))

    result = db.execute(statement.limit(config.limit)).mappings().all()
    rows = [
        {key: _json_value(value) for key, value in dict(row).items()}
        for row in result
    ]
    columns = [
        {"key": key, "label": str(source.fields[key]["label"])}
        for key in selected_keys
    ]
    value = None
    subtitle = None
    if config.chart.type in {"kpi", "trend"} and rows and config.chart.yAxis:
        value = rows[0].get(config.chart.yAxis)
        subtitle = source.label
    return ReportResult(
        columns=columns,
        rows=rows,
        total_rows=len(rows),
        chart_type=config.chart.type,
        x_axis=config.chart.xAxis,
        y_axis=config.chart.yAxis,
        value=value,
        subtitle=subtitle,
    )
