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
            "linked_loan_id": loan.json()["id"],
            "loan_ledger_type": "repayment",
            "loan_balance_effect": "credit",
            "loan_principal_component": "500",
            "loan_interest_component": "0",
            "loan_mapping_confidence": "1",
            "loan_user_confirmed": True,
            "is_validated": False,
        },
    )
    assert transaction.status_code == 201

    before = client.get("/api/loans").json()[0]
    assert before["current_balance"] == "7500.00"
    assert before["ledger_entries"][1]["entry_type"] == "repayment"

    validated = client.post(
        "/api/transactions/validate",
        json={
            "transaction_ids": [transaction.json()["id"]],
            "is_validated": True,
        },
    )
    assert validated.status_code == 200

    adjusted = client.get("/api/loans").json()[0]
    assert adjusted["recorded_balance"] == "7500.00"
    assert adjusted["current_balance"] == "7500.00"
    assert adjusted["ledger_entries"][-1]["running_balance"] == "7500.00"

    payments = client.get(f"/api/loans/{adjusted['id']}/transactions")
    assert payments.status_code == 200

    dashboard = client.get("/api/dashboard?year=2026&month=6").json()
    assert dashboard["debt_balance"] == "7500.00"

    analytics = client.get("/api/analytics/debt").json()
    assert analytics["total_balance"] == "7500.00"
    assert analytics["loans"][0]["adjusted_balance"] == "7500.00"


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


def test_loan_interest_rate_history_updates_effective_rate(
    client: TestClient,
) -> None:
    loan = client.post(
        "/api/loans",
        json={
            "lender": "Kuldeep",
            "direction": "borrowed",
            "loan_type": "friend",
            "original_amount": "4968839.69",
            "current_balance": "3799999.69",
            "interest_rate": "9",
            "monthly_payment": "0",
            "currency": "INR",
            "start_date": "2021-12-16",
        },
    )
    assert loan.status_code == 201

    change = client.post(
        f"/api/loans/{loan.json()['id']}/interest-rates",
        json={
            "effective_date": "2026-06-01",
            "interest_rate": "10.5",
            "notes": "Revised agreement",
        },
    )
    assert change.status_code == 201

    refreshed = client.get("/api/loans").json()[0]
    assert refreshed["effective_interest_rate"] == "10.5000"
    assert refreshed["monthly_interest_estimate"] == "33250.00"
    assert refreshed["interest_rate_changes"][0]["notes"] == "Revised agreement"


def test_lent_money_is_reported_as_receivable_not_debt(client: TestClient) -> None:
    borrowed = client.post(
        "/api/loans",
        json={
            "lender": "Bank",
            "direction": "borrowed",
            "loan_type": "personal",
            "original_amount": "1000",
            "current_balance": "900",
            "interest_rate": "5",
            "monthly_payment": "100",
            "currency": "EUR",
        },
    )
    assert borrowed.status_code == 201
    lent = client.post(
        "/api/loans",
        json={
            "lender": "Friend",
            "direction": "lent",
            "loan_type": "personal",
            "original_amount": "500",
            "current_balance": "500",
            "interest_rate": "3",
            "monthly_payment": "50",
            "currency": "EUR",
        },
    )
    assert lent.status_code == 201

    analytics = client.get("/api/analytics/debt").json()
    assert analytics["total_balance"] == "900.00"
    assert analytics["receivable_balance"] == "500.00"


def test_loan_ledger_entries_are_returned_with_loan(client: TestClient) -> None:
    loan = client.post(
        "/api/loans",
        json={
            "lender": "Kuldeep",
            "direction": "borrowed",
            "loan_type": "friend loan",
            "original_amount": "4968839",
            "current_balance": "3799999.69",
            "interest_rate": "9",
            "monthly_payment": "0",
            "currency": "INR",
            "start_date": "2021-12-16",
        },
    )
    assert loan.status_code == 201

    entry = client.post(
        f"/api/loans/{loan.json()['id']}/ledger-entries",
        json={
            "entry_date": "2021-12-16",
            "description": "Fund Trf to SBI",
            "entry_type": "drawdown",
            "amount": "400000",
            "currency": "INR",
        },
    )
    assert entry.status_code == 201

    refreshed = client.get("/api/loans").json()[0]
    assert refreshed["ledger_total"] == "4199999.69"
    assert refreshed["ledger_entries"][1]["description"] == "Fund Trf to SBI"

    entries = client.get(f"/api/loans/{loan.json()['id']}/ledger-entries")
    assert entries.status_code == 200
    assert entries.json()[1]["amount"] == "400000.00"


def test_interest_as_of_uses_daily_balance_segments(client: TestClient) -> None:
    loan = client.post(
        "/api/loans",
        json={
            "lender": "Family",
            "direction": "borrowed",
            "loan_type": "personal",
            "original_amount": "10000",
            "current_balance": "10000",
            "interest_rate": "10",
            "interest_mode": "automatic",
            "monthly_payment": "0",
            "currency": "EUR",
            "start_date": "2026-01-01",
        },
    )
    assert loan.status_code == 201
    client.post(
        f"/api/loans/{loan.json()['id']}/ledger-entries",
        json={
            "entry_date": "2026-01-06",
            "description": "Part repayment",
            "entry_type": "repayment",
            "direction": "credit",
            "amount": "5000",
            "currency": "EUR",
        },
    )

    response = client.get(
        f"/api/loans/{loan.json()['id']}/interest-as-of?as_of=2026-01-10"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outstanding_principal"] == "5000.00"
    assert body["posted_interest"] == "0.00"
    assert body["unposted_accumulated_interest"] == "17.81"
    assert body["total_payable"] == "5017.81"
    assert len(body["segments"]) == 2
    assert body["segments"][0]["days"] == 4
    assert body["segments"][1]["days"] == 5
