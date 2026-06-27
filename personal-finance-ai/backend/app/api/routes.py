import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import extract, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models.account import Account
from app.models.category import Category
from app.models.document import Document
from app.models.finance import (
    AIRecommendation,
    BudgetProposal,
    FinancialAlert,
    Loan,
    LoanLedgerEntry,
    LoanTransactionLink,
    MonthlyBudget,
)
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate
from app.schemas.advisor import AdvisorDashboard, AdvisorStatusUpdate
from app.schemas.category import CategoryCreate, CategoryRead
from app.schemas.dashboard import DashboardSummary
from app.schemas.finance import (
    BudgetProposalRead,
    MonthlyBudgetCreate,
    MonthlyBudgetRead,
    MonthlyBudgetSummary,
)
from app.schemas.transaction import (
    TransactionCreate,
    TransactionRead,
    TransactionUpdate,
    TransactionWithBaseRead,
    ValidationRequest,
)
from app.schemas.user import UserProfileRead, UserProfileUpdate
from app.services.advisor_service import advisor_dashboard, refresh_advisor
from app.services.csv_import import import_transactions
from app.services.currency_service import base_currency, convert_amount
from app.services.dashboard import dashboard_summary
from app.services.loan_balance_service import recalculate_loan_ledger
from app.services.recurrence_service import (
    confirm_budget_proposal,
    detect_recurring_transactions,
    generate_budget_proposals,
    set_user_recurrence,
)

router = APIRouter()


def _loan_entry_type_for_transaction(
    transaction: Transaction,
    category: Category | None,
) -> str | None:
    if transaction.loan_ledger_type:
        return transaction.loan_ledger_type
    category_name = (category.name if category else "").strip().lower()
    if category_name == "loan repayment":
        return "repayment"
    if category_name == "loan interest":
        return "interest_posted"
    if category_name == "loan":
        return "loan_taken"
    return None


def _sync_transaction_loan_link(db: Session, transaction: Transaction) -> None:
    existing_links = db.scalars(
        select(LoanTransactionLink).where(
            LoanTransactionLink.transaction_id == transaction.id
        )
    ).all()
    if transaction.linked_loan_id is None:
        touched_loans = []
        for link in existing_links:
            touched_loans.append(link.loan_id)
            if link.ledger_entry_id:
                entry = db.get(LoanLedgerEntry, link.ledger_entry_id)
                if entry is not None:
                    db.delete(entry)
            db.delete(link)
        db.flush()
        for loan_id in touched_loans:
            loan = db.get(Loan, loan_id)
            if loan is not None:
                recalculate_loan_ledger(db, loan)
        return

    loan = db.get(Loan, transaction.linked_loan_id)
    if loan is None:
        raise HTTPException(404, "Linked loan not found")
    category = (
        db.get(Category, transaction.category_id)
        if transaction.category_id
        else None
    )
    entry_type = _loan_entry_type_for_transaction(transaction, category)
    if not entry_type:
        return
    effect = transaction.loan_balance_effect
    if not effect:
        effect = "credit" if entry_type in {"repayment", "waiver"} else "debit"
    amount = Decimal(transaction.amount).quantize(Decimal("0.01"))
    principal = transaction.loan_principal_component
    interest = transaction.loan_interest_component
    if principal is None and interest is None:
        if entry_type in {"interest_posted", "interest_accrued"}:
            principal = Decimal("0")
            interest = amount
        else:
            principal = amount
            interest = Decimal("0")
    principal = Decimal(principal or 0).quantize(Decimal("0.01"))
    interest = Decimal(interest or 0).quantize(Decimal("0.01"))
    link = existing_links[0] if existing_links else None
    entry = (
        db.get(LoanLedgerEntry, link.ledger_entry_id)
        if link and link.ledger_entry_id
        else None
    )
    if entry is None:
        entry = LoanLedgerEntry(loan_id=loan.id)
        db.add(entry)
    entry.loan_id = loan.id
    entry.transaction_id = transaction.id
    entry.entry_date = transaction.transaction_date
    entry.description = transaction.description or transaction.vendor
    entry.entry_type = entry_type
    entry.direction = effect
    entry.amount = amount
    entry.principal_component = principal
    entry.interest_component = interest
    entry.currency = transaction.currency
    entry.mapping_confidence = transaction.loan_mapping_confidence
    entry.user_confirmed = bool(transaction.loan_user_confirmed)
    entry.notes = "Linked from transaction module."
    db.flush()
    if link is None:
        link = LoanTransactionLink(
            loan_id=loan.id,
            transaction_id=transaction.id,
            ledger_entry_id=entry.id,
        )
        db.add(link)
    link.loan_id = loan.id
    link.ledger_entry_id = entry.id
    link.mapping_confidence = transaction.loan_mapping_confidence
    link.user_confirmed = bool(transaction.loan_user_confirmed)
    for extra in existing_links[1:]:
        db.delete(extra)
    recalculate_loan_ledger(db, loan)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/profile", response_model=UserProfileRead)
def get_profile(db: Session = Depends(get_db)) -> User:
    profile = db.scalar(select(User).order_by(User.id))
    if profile is None:
        profile = User(name="Local User", base_currency="EUR", country="DE")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.put("/profile", response_model=UserProfileRead)
def update_profile(
    payload: UserProfileUpdate, db: Session = Depends(get_db)
) -> User:
    profile = db.scalar(select(User).order_by(User.id))
    if profile is None:
        profile = User(name=payload.name)
        db.add(profile)
    for field, value in payload.model_dump().items():
        if field in {"base_currency", "country", "tax_country"}:
            value = value.upper()
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)) -> list[Account]:
    return list(db.scalars(select(Account).order_by(Account.name)).all())


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> Account:
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.put("/accounts/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)
) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    if account.transactions or account.documents:
        raise HTTPException(409, "Archive accounts that have financial records")
    db.delete(account)
    db.commit()


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    statement = select(Category).order_by(Category.type, Category.name)
    return list(db.scalars(statement).all())


@router.post("/categories", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> Category:
    if db.scalar(select(Category.id).where(Category.name == payload.name)):
        raise HTTPException(409, "Category already exists")
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    payload: CategoryCreate,
    db: Session = Depends(get_db),
) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    for field, value in payload.model_dump().items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)) -> None:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(404, "Category not found")
    if category.transactions:
        raise HTTPException(409, "Category is used by transactions")
    db.delete(category)
    db.commit()


@router.get("/transactions", response_model=list[TransactionRead])
def list_transactions(
    validated: bool | None = None,
    document_id: int | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    search: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    statement = select(Transaction).order_by(
        Transaction.transaction_date.desc(), Transaction.id.desc()
    )
    if validated is not None:
        statement = statement.where(Transaction.is_validated == validated)
    if document_id is not None:
        statement = statement.where(Transaction.document_id == document_id)
    if account_id is not None:
        statement = statement.where(Transaction.account_id == account_id)
    if category_id is not None:
        statement = statement.where(Transaction.category_id == category_id)
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(Transaction.vendor.ilike(term), Transaction.description.ilike(term))
        )
    return list(db.scalars(statement.limit(limit)).all())


@router.get("/transactions/base", response_model=list[TransactionWithBaseRead])
def list_transactions_base(
    validated: bool | None = None,
    document_id: int | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    search: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[dict]:
    transactions = list_transactions(
        validated=validated,
        document_id=document_id,
        account_id=account_id,
        category_id=category_id,
        search=search,
        limit=limit,
        db=db,
    )
    reporting_currency = base_currency(db)
    rows = []
    for transaction in transactions:
        converted = convert_amount(
            db,
            transaction.amount,
            transaction.currency,
            reporting_currency,
        )
        row = TransactionRead.model_validate(transaction).model_dump()
        row["base_amount"] = converted
        row["base_currency"] = reporting_currency
        row["fx_rate_missing"] = converted is None
        rows.append(row)
    return rows


@router.post("/transactions", response_model=TransactionRead, status_code=201)
def create_transaction(
    payload: TransactionCreate, db: Session = Depends(get_db)
) -> Transaction:
    if db.get(Account, payload.account_id) is None:
        raise HTTPException(404, "Account not found")
    if payload.category_id and db.get(Category, payload.category_id) is None:
        raise HTTPException(404, "Category not found")
    if payload.linked_loan_id and db.get(Loan, payload.linked_loan_id) is None:
        raise HTTPException(404, "Linked loan not found")
    data = payload.model_dump()
    transaction = Transaction(
        **data, original_description=payload.description, is_duplicate=False
    )
    if payload.recurrence_frequency:
        set_user_recurrence(transaction, payload.recurrence_frequency)
    db.add(transaction)
    db.flush()
    _sync_transaction_loan_link(db, transaction)
    db.commit()
    db.refresh(transaction)
    if transaction.is_validated:
        detect_recurring_transactions(db, use_local_ai=False)
        db.refresh(transaction)
    return transaction


@router.put("/transactions/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
) -> Transaction:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    updates = payload.model_dump(exclude_unset=True)
    if "account_id" in updates and db.get(Account, updates["account_id"]) is None:
        raise HTTPException(404, "Account not found")
    if updates.get("category_id") and db.get(Category, updates["category_id"]) is None:
        raise HTTPException(404, "Category not found")
    if (
        updates.get("linked_loan_id")
        and db.get(Loan, updates["linked_loan_id"]) is None
    ):
        raise HTTPException(404, "Linked loan not found")
    recurrence_was_set = "recurrence_frequency" in updates
    recurrence_frequency = updates.pop("recurrence_frequency", None)
    changed = []
    for field, value in updates.items():
        if getattr(transaction, field) != value:
            changed.append(field)
        setattr(transaction, field, value)
    if recurrence_was_set:
        if transaction.recurrence_frequency != recurrence_frequency:
            changed.append("recurrence_frequency")
        set_user_recurrence(transaction, recurrence_frequency)
    previous = json.loads(transaction.edited_fields or "[]")
    transaction.edited_fields = json.dumps(sorted(set(previous + changed)))
    if changed:
        transaction.classification_source = "user_edit"
    _sync_transaction_loan_link(db, transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)) -> None:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(404, "Transaction not found")
    transaction.linked_loan_id = None
    _sync_transaction_loan_link(db, transaction)
    db.delete(transaction)
    db.commit()


@router.post("/transactions/validate")
def validate_transactions(
    payload: ValidationRequest, db: Session = Depends(get_db)
) -> dict[str, int]:
    transactions = list(
        db.scalars(
            select(Transaction).where(Transaction.id.in_(payload.transaction_ids))
        ).all()
    )
    if len(transactions) != len(set(payload.transaction_ids)):
        raise HTTPException(404, "One or more transactions were not found")
    for transaction in transactions:
        transaction.is_validated = payload.is_validated
        if payload.is_validated and transaction.document:
            transaction.document.validation_status = "partially_validated"
    db.commit()
    if payload.is_validated:
        detect_recurring_transactions(db, use_local_ai=False)
    document_ids = {
        item.document_id for item in transactions if item.document_id is not None
    }
    for document_id in document_ids:
        remaining = db.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.document_id == document_id,
                Transaction.is_validated.is_(False),
            )
        )
        document = db.get(Document, document_id)
        if document and not remaining:
            document.validation_status = "validated"
            document.status = "validated"
    db.commit()
    return {"updated": len(transactions)}


@router.post("/recurrence/detect")
def detect_recurrence(
    use_local_ai: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return detect_recurring_transactions(db, use_local_ai=use_local_ai)


@router.post("/transactions/import")
async def upload_csv(
    account_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return await import_transactions(db, file, account_id)


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    month: int = Query(default=date.today().month, ge=1, le=12),
    db: Session = Depends(get_db),
) -> dict:
    return dashboard_summary(db, year, month)


@router.get("/dashboard/advisor", response_model=AdvisorDashboard)
def get_dashboard_advisor(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    month: int = Query(default=date.today().month, ge=1, le=12),
    db: Session = Depends(get_db),
) -> dict:
    return advisor_dashboard(db, year, month)


@router.post("/dashboard/advisor/refresh", response_model=AdvisorDashboard)
def refresh_dashboard_advisor(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    month: int = Query(default=date.today().month, ge=1, le=12),
    use_local_ai: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    return refresh_advisor(db, year, month, use_local_ai=use_local_ai)


@router.patch("/dashboard/recommendations/{item_id}")
def update_dashboard_recommendation(
    item_id: int,
    payload: AdvisorStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    item = db.get(AIRecommendation, item_id)
    if item is None:
        raise HTTPException(404, "Recommendation not found")
    if payload.status not in {"active", "dismissed", "completed"}:
        raise HTTPException(422, "Invalid recommendation status")
    item.status = payload.status
    db.commit()
    return {"status": item.status}


@router.patch("/dashboard/alerts/{item_id}")
def update_dashboard_alert(
    item_id: int,
    payload: AdvisorStatusUpdate,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    item = db.get(FinancialAlert, item_id)
    if item is None:
        raise HTTPException(404, "Alert not found")
    if payload.status not in {"active", "dismissed", "resolved"}:
        raise HTTPException(422, "Invalid alert status")
    item.status = payload.status
    db.commit()
    return {"status": item.status}


def _budget_summary(db: Session, year: int, month: int) -> dict:
    reporting_currency = base_currency(db)
    budgets = list(
        db.scalars(
            select(MonthlyBudget)
            .where(MonthlyBudget.year == year, MonthlyBudget.month == month)
            .order_by(MonthlyBudget.id)
        ).all()
    )
    spent_rows: dict[int | None, Decimal] = {}
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.is_validated.is_(True),
            Transaction.is_duplicate.is_(False),
            Transaction.transaction_type == "debit",
            extract("year", Transaction.transaction_date) == year,
            extract("month", Transaction.transaction_date) == month,
        )
    ).all()
    for transaction in transactions:
        converted = convert_amount(
            db,
            transaction.amount,
            transaction.currency,
            reporting_currency,
        )
        if converted is None:
            continue
        spent_rows[transaction.category_id] = (
            spent_rows.get(transaction.category_id, Decimal("0")) + converted
        )
    category_names = {item.id: item.name for item in db.scalars(select(Category)).all()}
    categories = []
    total_budget = Decimal("0")
    total_spent = Decimal("0")
    for budget in budgets:
        amount = (
            convert_amount(db, budget.amount, budget.currency, reporting_currency)
            or Decimal("0")
        )
        spent = Decimal(spent_rows.get(budget.category_id, 0) or 0)
        total_budget += amount
        total_spent += spent
        categories.append(
            {
                "budget_id": budget.id,
                "category_id": budget.category_id,
                "category": category_names.get(budget.category_id, "General"),
                "budget": amount,
                "spent": spent,
                "remaining": amount - spent,
                "percentage": (
                    (spent / amount * 100).quantize(Decimal("0.01"))
                    if amount
                    else Decimal("0")
                ),
            }
        )
    return {
        "year": year,
        "month": month,
        "currency": reporting_currency,
        "total_budget": total_budget,
        "spent": total_spent,
        "remaining": total_budget - total_spent,
        "percentage": (
            (total_spent / total_budget * 100).quantize(Decimal("0.01"))
            if total_budget
            else Decimal("0")
        ),
        "categories": categories,
    }


@router.get("/budgets", response_model=list[MonthlyBudgetRead])
def list_budgets(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
) -> list[MonthlyBudget]:
    return list(
        db.scalars(
            select(MonthlyBudget)
            .where(MonthlyBudget.year == year, MonthlyBudget.month == month)
            .order_by(MonthlyBudget.id)
        ).all()
    )


@router.get("/budgets/summary", response_model=MonthlyBudgetSummary)
def budget_summary(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
) -> dict:
    return _budget_summary(db, year, month)


@router.get("/budgets/proposals", response_model=list[BudgetProposalRead])
def list_budget_proposals(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
) -> list[BudgetProposal]:
    return list(
        db.scalars(
            select(BudgetProposal)
            .where(
                BudgetProposal.year == year,
                BudgetProposal.month == month,
            )
            .order_by(BudgetProposal.status, BudgetProposal.expected_date)
        ).all()
    )


@router.post(
    "/budgets/proposals/generate", response_model=list[BudgetProposalRead]
)
def create_budget_proposals(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    use_local_ai: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[BudgetProposal]:
    return generate_budget_proposals(
        db, year, month, use_local_ai=use_local_ai
    )


@router.post(
    "/budgets/proposals/{proposal_id}/confirm",
    response_model=MonthlyBudgetRead,
)
def confirm_recurring_budget_proposal(
    proposal_id: int, db: Session = Depends(get_db)
) -> MonthlyBudget:
    proposal = db.get(BudgetProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Budget proposal not found")
    if proposal.status == "dismissed":
        raise HTTPException(409, "Dismissed proposals cannot be confirmed")
    try:
        return confirm_budget_proposal(db, proposal)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post(
    "/budgets/proposals/{proposal_id}/dismiss",
    response_model=BudgetProposalRead,
)
def dismiss_recurring_budget_proposal(
    proposal_id: int, db: Session = Depends(get_db)
) -> BudgetProposal:
    proposal = db.get(BudgetProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, "Budget proposal not found")
    if proposal.status == "confirmed":
        raise HTTPException(409, "Confirmed proposals cannot be dismissed")
    proposal.status = "dismissed"
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/budgets", response_model=MonthlyBudgetRead, status_code=201)
def create_budget(
    payload: MonthlyBudgetCreate, db: Session = Depends(get_db)
) -> MonthlyBudget:
    if payload.category_id and db.get(Category, payload.category_id) is None:
        raise HTTPException(404, "Category not found")
    budget = MonthlyBudget(**payload.model_dump())
    db.add(budget)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "A budget already exists for this category and month"
        ) from exc
    db.refresh(budget)
    return budget


@router.put("/budgets/{budget_id}", response_model=MonthlyBudgetRead)
def update_budget(
    budget_id: int,
    payload: MonthlyBudgetCreate,
    db: Session = Depends(get_db),
) -> MonthlyBudget:
    budget = db.get(MonthlyBudget, budget_id)
    if budget is None:
        raise HTTPException(404, "Budget not found")
    if payload.category_id and db.get(Category, payload.category_id) is None:
        raise HTTPException(404, "Category not found")
    for field, value in payload.model_dump().items():
        setattr(budget, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, "A budget already exists for this category and month"
        ) from exc
    db.refresh(budget)
    return budget


@router.delete("/budgets/{budget_id}", status_code=204)
def delete_budget(budget_id: int, db: Session = Depends(get_db)) -> None:
    budget = db.get(MonthlyBudget, budget_id)
    if budget is None:
        raise HTTPException(404, "Budget not found")
    db.delete(budget)
    db.commit()
