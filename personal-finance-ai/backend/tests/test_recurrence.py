from fastapi.testclient import TestClient


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Recurring account",
            "type": "bank",
            "currency": "EUR",
            "country": "DE",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_transaction(
    client: TestClient,
    account_id: int,
    transaction_date: str,
    vendor: str = "School meals",
    amount: str = "75.00",
) -> dict:
    response = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": transaction_date,
            "vendor": vendor,
            "description": "Recurring payment",
            "amount": amount,
            "currency": "EUR",
            "transaction_type": "debit",
            "is_validated": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_detects_monthly_payment_and_confirms_budget_proposal(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    categories = {
        item["name"]: item["id"] for item in client.get("/api/categories").json()
    }
    rows = [
        create_transaction(client, account_id, "2026-01-02"),
        create_transaction(client, account_id, "2026-02-02"),
        create_transaction(client, account_id, "2026-03-02"),
    ]
    client.put(
        f"/api/transactions/{rows[-1]['id']}",
        json={"category_id": categories["Education"]},
    )

    detection = client.post("/api/recurrence/detect")
    assert detection.status_code == 200
    assert detection.json()["groups_detected"] == 1

    generated = client.post(
        "/api/budgets/proposals/generate?year=2026&month=4"
    )
    assert generated.status_code == 200
    proposals = generated.json()
    assert len(proposals) == 1
    assert proposals[0]["recurrence_frequency"] == "monthly"
    assert proposals[0]["expected_date"] == "2026-04-02"
    assert proposals[0]["status"] == "pending"

    regenerated = client.post(
        "/api/budgets/proposals/generate?year=2026&month=4"
    )
    assert len(regenerated.json()) == 1

    confirmed = client.post(
        f"/api/budgets/proposals/{proposals[0]['id']}/confirm"
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["amount"] == "75.00"
    assert confirmed.json()["category_id"] == categories["Education"]


def test_existing_transaction_suppresses_proposal(client: TestClient) -> None:
    account_id = create_account(client)
    for transaction_date in (
        "2026-01-02",
        "2026-02-02",
        "2026-03-02",
        "2026-04-02",
    ):
        create_transaction(client, account_id, transaction_date)

    response = client.post("/api/budgets/proposals/generate?year=2026&month=4")
    assert response.status_code == 200
    assert response.json() == []


def test_user_can_set_yearly_occurrence(client: TestClient) -> None:
    account_id = create_account(client)
    transaction = create_transaction(
        client,
        account_id,
        "2025-09-15",
        vendor="Annual insurance",
        amount="480.00",
    )

    updated = client.put(
        f"/api/transactions/{transaction['id']}",
        json={"recurrence_frequency": "yearly"},
    )
    assert updated.status_code == 200
    assert updated.json()["recurrence_frequency"] == "yearly"
    assert updated.json()["recurrence_source"] == "user"
    assert updated.json()["next_expected_date"] == "2026-09-15"

    proposals = client.post(
        "/api/budgets/proposals/generate?year=2026&month=9"
    ).json()
    assert len(proposals) == 1
    assert proposals[0]["detection_source"] == "user"
