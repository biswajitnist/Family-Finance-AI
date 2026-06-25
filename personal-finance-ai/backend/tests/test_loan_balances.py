from fastapi.testclient import TestClient


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Payment Account",
            "type": "checking",
            "country": "DE",
            "currency": "EUR",
            "opening_balance": "0",
            "current_balance": "0",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_validated_loan_repayment_reduces_effective_balance(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    loan = client.post(
        "/api/loans",
        json={
            "lender": "Example Bank",
            "loan_type": "personal",
            "original_amount": "10000",
            "current_balance": "8000",
            "interest_rate": "0",
            "monthly_payment": "500",
            "currency": "EUR",
            "start_date": "2026-01-01",
        },
    )
    assert loan.status_code == 201
    category = next(
        item
        for item in client.get("/api/categories").json()
        if item["name"] == "Loan Repayment"
    )
    transaction = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-01",
            "vendor": "Example Bank",
            "description": "Monthly loan payment",
            "amount": "500",
            "currency": "EUR",
            "transaction_type": "debit",
            "category_id": category["id"],
            "is_validated": False,
        },
    )
    assert transaction.status_code == 201

    before = client.get("/api/loans").json()[0]
    assert before["current_balance"] == "8000.00"
    assert before["payments_applied"] == "0.00"

    validated = client.post(
        "/api/transactions/validate",
        json={
            "transaction_ids": [transaction.json()["id"]],
            "is_validated": True,
        },
    )
    assert validated.status_code == 200

    adjusted = client.get("/api/loans").json()[0]
    assert adjusted["recorded_balance"] == "8000.00"
    assert adjusted["current_balance"] == "7500.00"
    assert adjusted["payments_applied"] == "500.00"
    assert adjusted["matched_transaction_count"] == 1

    payments = client.get(f"/api/loans/{adjusted['id']}/transactions")
    assert payments.status_code == 200
    assert payments.json() == [
        {
            "id": transaction.json()["id"],
            "transaction_date": "2026-06-01",
            "vendor": "Example Bank",
            "description": "Monthly loan payment",
            "reference_number": None,
            "amount": "500.00",
            "currency": "EUR",
            "applied_amount": "500.00",
            "applied_currency": "EUR",
            "is_validated": True,
        }
    ]

    dashboard = client.get("/api/dashboard?year=2026&month=6").json()
    assert dashboard["debt_balance"] == "7500.00"

    analytics = client.get("/api/analytics/debt").json()
    assert analytics["total_balance"] == "7500.00"
    assert analytics["loans"][0]["payments_applied"] == "500.00"


def test_non_loan_category_does_not_reduce_balance(client: TestClient) -> None:
    account_id = create_account(client)
    client.post(
        "/api/loans",
        json={
            "lender": "Example Bank",
            "loan_type": "personal",
            "original_amount": "10000",
            "current_balance": "8000",
            "monthly_payment": "500",
            "currency": "EUR",
        },
    )
    category = next(
        item
        for item in client.get("/api/categories").json()
        if item["name"] == "Grocery"
    )
    transaction = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-01",
            "vendor": "Example Bank",
            "description": "Not a loan repayment",
            "amount": "500",
            "currency": "EUR",
            "transaction_type": "debit",
            "category_id": category["id"],
            "is_validated": True,
        },
    )
    assert transaction.status_code == 201
    assert client.get("/api/loans").json()[0]["current_balance"] == "8000.00"
