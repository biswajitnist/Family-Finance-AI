from datetime import date

from fastapi.testclient import TestClient


def _create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Insurance Account",
            "type": "bank",
            "country": "DE",
            "currency": "EUR",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _insurance_category_id(client: TestClient) -> int:
    return next(
        item["id"]
        for item in client.get("/api/categories").json()
        if item["name"] == "Insurance"
    )


def _create_policy(
    client: TestClient,
    policy_type: str,
    premium: str,
) -> int:
    response = client.post(
        "/api/insurance",
        json={
            "provider": "Allianz Versicherungs-AG",
            "policy_type": policy_type,
            "premium_amount": premium,
            "premium_frequency": "monthly",
            "currency": "EUR",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_payment(
    client: TestClient,
    account_id: int,
    category_id: int,
    amount: str,
    description: str,
    *,
    duplicate: bool = False,
) -> int:
    response = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": date.today().isoformat(),
            "vendor": "Allianz Versicherungs-AG",
            "description": description,
            "amount": amount,
            "currency": "EUR",
            "transaction_type": "debit",
            "category_id": category_id,
            "is_validated": True,
        },
    )
    assert response.status_code == 201
    transaction_id = response.json()["id"]
    if duplicate:
        updated = client.put(
            f"/api/transactions/{transaction_id}",
            json={"is_duplicate": True},
        )
        assert updated.status_code == 200
    return transaction_id


def test_insurance_analytics_and_policy_transactions(client: TestClient) -> None:
    account_id = _create_account(client)
    category_id = _insurance_category_id(client)
    liability_id = _create_policy(client, "Liability", "12.16")
    household_id = _create_policy(client, "Household", "20.99")

    liability_payment = _create_payment(
        client,
        account_id,
        category_id,
        "12.16",
        "Privat-Haftpflichtversicherung",
    )
    household_payment = _create_payment(
        client,
        account_id,
        category_id,
        "20.99",
        "Hausratversicherung",
    )
    _create_payment(
        client,
        account_id,
        category_id,
        "12.16",
        "Duplicate Privat-Haftpflichtversicherung",
        duplicate=True,
    )
    _create_payment(
        client,
        account_id,
        category_id,
        "99.00",
        "Unrecognized insurance charge",
    )

    analytics = client.get("/api/analytics/protection")
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["scheduled_monthly"] == "33.15"
    assert body["scheduled_annual"] == "397.80"
    assert body["actual_month"] == "33.15"
    assert body["actual_year"] == "33.15"
    assert body["unmatched_transaction_count"] == 1
    assert body["unmatched_transactions"][0]["amount"] == "99.00"

    liability = client.get(f"/api/insurance/{liability_id}/transactions")
    assert liability.status_code == 200
    assert [item["id"] for item in liability.json()] == [liability_payment]

    household = client.get(f"/api/insurance/{household_id}/transactions")
    assert household.status_code == 200
    assert [item["id"] for item in household.json()] == [household_payment]
