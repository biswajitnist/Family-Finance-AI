from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.transaction import Transaction
from app.services.duplicate_detection import reconcile_duplicate_flags


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Main account",
            "type": "bank",
            "currency": "EUR",
            "country": "DE",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_manual_transaction_appears_in_dashboard(client: TestClient) -> None:
    account_id = create_account(client)
    response = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-02",
            "vendor": "Employer",
            "description": "June salary",
            "amount": "3200.00",
            "currency": "EUR",
            "transaction_type": "credit",
            "is_validated": True,
        },
    )
    assert response.status_code == 201

    dashboard = client.get("/api/dashboard?year=2026&month=6")
    assert dashboard.status_code == 200
    assert dashboard.json()["income"] == "3200.00"
    assert dashboard.json()["net_cash_flow"] == "3200.00"


def test_transaction_list_includes_older_months_beyond_first_100(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    with SessionLocal() as db:
        db.add(
            Transaction(
                user_id=1,
                account_id=account_id,
                transaction_date=date(2026, 1, 15),
                vendor="January merchant",
                description="Older visible transaction",
                original_description="Older visible transaction",
                amount=Decimal("10.00"),
                currency="EUR",
                transaction_type="debit",
                is_validated=True,
                is_duplicate=False,
            )
        )
        for index in range(105):
            db.add(
                Transaction(
                    user_id=1,
                    account_id=account_id,
                    transaction_date=date(2026, 4, 15),
                    vendor=f"Recent merchant {index}",
                    description="Recent transaction",
                    original_description="Recent transaction",
                    amount=Decimal("1.00"),
                    currency="EUR",
                    transaction_type="debit",
                    is_validated=True,
                    is_duplicate=False,
                )
            )
        db.commit()

    transactions = client.get("/api/transactions?validated=true").json()
    assert len(transactions) == 106
    assert any(item["vendor"] == "January merchant" for item in transactions)


def test_csv_import_requires_review_and_marks_duplicates(client: TestClient) -> None:
    account_id = create_account(client)
    csv_content = (
        "date,vendor,description,amount,currency,type,category\n"
        "2026-06-03,REWE,Weekly shop,42.35,EUR,debit,Grocery\n"
        "2026-06-03,REWE,Weekly shop,42.35,EUR,debit,Grocery\n"
    )
    response = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json() == {"imported": 2, "duplicates": 1}

    pending = client.get("/api/transactions?validated=false")
    assert pending.status_code == 200
    assert len(pending.json()) == 2
    assert pending.json()[0]["is_validated"] is False


def test_recurring_equal_payments_are_not_duplicates(client: TestClient) -> None:
    account_id = create_account(client)
    csv_content = (
        "date,vendor,description,amount,currency,type,reference_number\n"
        "2026-02-02,Stadt Wolfsburg,SCHULESSEN JAN26,75.00,EUR,debit,2226011841\n"
        "2026-03-02,Stadt Wolfsburg,SCHULESSEN FEB26,75.00,EUR,debit,2226056007\n"
        "2026-03-02,Stadt Wolfsburg,SCHULESSEN FEB26 child 2,"
        "75.00,EUR,debit,2226055524\n"
    )
    response = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={"file": ("school-meals.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["duplicates"] == 0
    rows = client.get("/api/transactions?validated=false").json()
    assert all(not item["is_duplicate"] for item in rows)


def test_same_reference_and_description_are_real_duplicates(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    csv_content = (
        "date,vendor,description,amount,currency,type,reference_number\n"
        "2026-04-02,School,Meal fee,75.00,EUR,debit,REF-123\n"
        "2026-04-02,School,Meal fee,75.00,EUR,debit,REF-123\n"
    )
    response = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={"file": ("duplicate.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["duplicates"] == 1


def test_import_flags_same_date_amount_and_similar_merchant_as_duplicate(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    existing = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-22",
            "vendor": "Allgemeiner Deutscher",
            "description": "Confirmed restaurant expense",
            "amount": "54.00",
            "currency": "EUR",
            "transaction_type": "debit",
            "is_validated": True,
        },
    )
    assert existing.status_code == 201
    csv_content = (
        "date,vendor,description,amount,currency,type\n"
        "2026-06-22,Allgemeiner Deutscher,Statement card row,54.00,EUR,debit\n"
    )
    response = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["duplicates"] == 1
    pending = client.get("/api/transactions?validated=false").json()
    assert pending[0]["is_duplicate"] is True


def test_duplicate_reconciliation_clears_historical_false_flags(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    with SessionLocal() as db:
        db.add_all(
            [
                Transaction(
                    user_id=1,
                    account_id=account_id,
                    transaction_date=date(2026, 4, 7),
                    vendor="Card merchant",
                    description="Card payment 18:36:55",
                    original_description="Card payment 18:36:55",
                    amount=Decimal("1.00"),
                    currency="EUR",
                    transaction_type="debit",
                    is_validated=True,
                    is_duplicate=False,
                ),
                Transaction(
                    user_id=1,
                    account_id=account_id,
                    transaction_date=date(2026, 4, 7),
                    vendor="Card merchant",
                    description="Card payment 18:42:55",
                    original_description="Card payment 18:42:55",
                    amount=Decimal("1.00"),
                    currency="EUR",
                    transaction_type="debit",
                    is_validated=True,
                    is_duplicate=True,
                ),
            ]
        )
        db.commit()
        result = reconcile_duplicate_flags(db)
        rows = list(
            db.query(Transaction)
            .filter(Transaction.vendor == "Card merchant")
            .order_by(Transaction.id)
        )
    assert result["changed"] == 1
    assert all(not item.is_duplicate for item in rows)


def test_duplicate_reconciliation_marks_existing_pending_statement_duplicate(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    with SessionLocal() as db:
        db.add_all(
            [
                Transaction(
                    user_id=1,
                    account_id=account_id,
                    transaction_date=date(2026, 6, 22),
                    vendor="Allgemeiner Deutscher",
                    description="Confirmed transaction",
                    original_description="Confirmed transaction",
                    amount=Decimal("54.00"),
                    currency="EUR",
                    transaction_type="debit",
                    is_validated=True,
                    is_duplicate=False,
                ),
                Transaction(
                    user_id=1,
                    account_id=account_id,
                    transaction_date=date(2026, 6, 22),
                    vendor="Allgemeiner Deutscher",
                    description="Statement import row",
                    original_description="Statement import row",
                    amount=Decimal("54.00"),
                    currency="EUR",
                    transaction_type="debit",
                    is_validated=False,
                    is_duplicate=False,
                ),
            ]
        )
        db.commit()
        result = reconcile_duplicate_flags(db)
        rows = list(
            db.query(Transaction)
            .filter(Transaction.vendor == "Allgemeiner Deutscher")
            .order_by(Transaction.is_validated.desc())
        )

    assert result["changed"] == 1
    assert rows[0].is_duplicate is False
    assert rows[1].is_duplicate is True


def test_csv_import_learns_category_from_validated_merchant_history(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    categories = {
        item["name"]: item["id"] for item in client.get("/api/categories").json()
    }
    first_import = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={
            "file": (
                "first.csv",
                "date,vendor,amount,type,category\n"
                "2026-05-01,REWE Markt 123,42.00,debit,Grocery\n",
                "text/csv",
            )
        },
    )
    assert first_import.status_code == 200
    first = client.get("/api/transactions?validated=false").json()[0]
    client.post(
        "/api/transactions/validate",
        json={"transaction_ids": [first["id"]], "is_validated": True},
    )

    learned_import = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={
            "file": (
                "second.csv",
                "date,vendor,amount,type\n2026-05-08,rewe-markt-123,38.00,debit\n",
                "text/csv",
            )
        },
    )
    assert learned_import.status_code == 200
    learned = client.get("/api/transactions?validated=false").json()[0]
    assert learned["category_id"] == categories["Grocery"]
    assert learned["classification_source"] == "merchant_history"
    assert learned["confidence"] == "0.9000"

    corrected = client.put(
        f"/api/transactions/{first['id']}",
        json={"category_id": categories["Shopping"]},
    )
    assert corrected.status_code == 200
    corrected_import = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={
            "file": (
                "third.csv",
                "date,vendor,amount,type\n2026-05-15,REWE MARKT 123,25.00,debit\n",
                "text/csv",
            )
        },
    )
    assert corrected_import.status_code == 200
    pending = client.get("/api/transactions?validated=false").json()
    newest = next(item for item in pending if item["amount"] == "25.00")
    assert newest["category_id"] == categories["Shopping"]
    assert newest["classification_source"] == "merchant_history"


def test_merchant_history_does_not_guess_when_categories_conflict(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    categories = {
        item["name"]: item["id"] for item in client.get("/api/categories").json()
    }
    for day, category in (("01", "Grocery"), ("08", "Shopping")):
        response = client.post(
            "/api/transactions",
            json={
                "account_id": account_id,
                "transaction_date": f"2026-05-{day}",
                "vendor": "Local Market",
                "amount": "20.00",
                "currency": "EUR",
                "transaction_type": "debit",
                "category_id": categories[category],
                "is_validated": True,
            },
        )
        assert response.status_code == 201

    response = client.post(
        f"/api/transactions/import?account_id={account_id}",
        files={
            "file": (
                "ambiguous.csv",
                "date,vendor,amount,type\n2026-05-15,local-market,30.00,debit\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200
    pending = client.get("/api/transactions?validated=false").json()[0]
    assert pending["category_id"] is None
    assert pending["classification_source"] == "import"


def test_cash_flow_report_compares_validated_months(client: TestClient) -> None:
    account_id = create_account(client)
    grocery = next(
        item
        for item in client.get("/api/categories").json()
        if item["name"] == "Grocery"
    )
    transactions = [
        ("2026-03-02", "Previous salary", "2000.00", "credit", None, True),
        ("2026-03-03", "Previous shop", "500.00", "debit", grocery["id"], True),
        ("2026-04-01", "April salary", "2500.00", "credit", None, True),
        ("2026-04-02", "April shop", "100.00", "debit", grocery["id"], True),
        ("2026-04-04", "Pending shop", "999.00", "debit", grocery["id"], False),
    ]
    for day, vendor, amount, transaction_type, category_id, validated in transactions:
        response = client.post(
            "/api/transactions",
            json={
                "account_id": account_id,
                "transaction_date": day,
                "vendor": vendor,
                "amount": amount,
                "currency": "EUR",
                "transaction_type": transaction_type,
                "category_id": category_id,
                "is_validated": validated,
            },
        )
        assert response.status_code == 201

    response = client.get("/api/reports/cash-flow/comparison?year=2026&month=4")
    assert response.status_code == 200
    report = response.json()
    assert report["current_month"] == "2026-04"
    assert report["previous_month"] == "2026-03"
    assert report["current"] == {
        "income": "2500.00",
        "expense": "100.00",
        "cash_flow": "2400.00",
    }
    assert report["previous"] == {
        "income": "2000.00",
        "expense": "500.00",
        "cash_flow": "1500.00",
    }
    assert report["expense_categories"][0] == {
        "category": "Grocery",
        "amount": "100.00",
    }
    assert report["daily"][1]["current_expense"] == "100.00"
    assert report["daily"][-1]["previous_expense"] == "500.00"
