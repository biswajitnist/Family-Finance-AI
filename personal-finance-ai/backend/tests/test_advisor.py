from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.transaction import Transaction
from app.services import advisor_service


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Advisor account",
            "type": "bank",
            "currency": "EUR",
            "country": "DE",
            "current_balance": "4000.00",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def add_transaction(
    client: TestClient,
    account_id: int,
    transaction_date: str,
    vendor: str,
    amount: str,
    transaction_type: str,
    category_id: int | None = None,
) -> int:
    response = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": transaction_date,
            "vendor": vendor,
            "amount": amount,
            "currency": "EUR",
            "transaction_type": transaction_type,
            "category_id": category_id,
            "is_validated": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_advisor_forecast_alerts_recommendations_and_status_actions(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    grocery = next(
        item
        for item in client.get("/api/categories").json()
        if item["name"] == "Grocery"
    )
    for month in (1, 2):
        add_transaction(
            client,
            account_id,
            f"2026-{month:02d}-01",
            "Employer",
            "3000.00",
            "credit",
        )
        add_transaction(
            client,
            account_id,
            f"2026-{month:02d}-05",
            "Market",
            "500.00",
            "debit",
            grocery["id"],
        )
        add_transaction(
            client,
            account_id,
            f"2026-{month:02d}-10",
            "Rent",
            "500.00",
            "debit",
        )
    add_transaction(
        client,
        account_id,
        "2026-03-01",
        "Employer",
        "3000.00",
        "credit",
    )
    duplicate_id = add_transaction(
        client,
        account_id,
        "2026-03-04",
        "Market",
        "800.00",
        "debit",
        grocery["id"],
    )
    add_transaction(
        client,
        account_id,
        "2026-03-10",
        "Rent",
        "500.00",
        "debit",
    )
    with SessionLocal() as db:
        duplicate = db.get(Transaction, duplicate_id)
        assert duplicate is not None
        db.add(
            Transaction(
                user_id=1,
                account_id=account_id,
                transaction_date=duplicate.transaction_date,
                vendor=duplicate.vendor,
                description="duplicate",
                original_description="duplicate",
                amount=Decimal("800.00"),
                currency="EUR",
                transaction_type="debit",
                category_id=grocery["id"],
                is_validated=False,
                is_duplicate=True,
            )
        )
        db.commit()

    response = client.post(
        "/api/dashboard/advisor/refresh?year=2026&month=3&use_local_ai=false"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["forecast"]["expected_income"] == "3000.00"
    assert data["forecast"]["expected_expenses"] == "1300.00"
    assert data["forecast"]["expected_surplus"] == "1700.00"
    assert data["forecast"]["expected_month_end_balance"] == "5700.00"
    assert data["financial_position"]["cash_balance"] == "4000.00"
    assert data["financial_position"]["investment_value"] == "0.00"
    assert data["financial_position"]["debt_balance"] == "0.00"
    assert data["financial_position"]["net_worth"] == "4000.00"
    assert "investment records" in data["source_basis"]
    assert "loan records" in data["source_basis"]
    assert data["forecast"]["category_risks"][0]["category"] == "Grocery"
    assert len(data["recommendations"]) <= 3
    duplicate_alert = next(
        item
        for item in data["alerts"]
        if item["alert_type"] == "duplicate_transactions"
    )
    assert duplicate_alert["transactions"][0]["is_duplicate"] is True
    assert duplicate_alert["transactions"][0]["vendor"] == "Market"
    category_alert = next(
        item for item in data["alerts"] if item["alert_type"] == "category_overspending"
    )
    assert category_alert["transactions"][0]["category"] == "Grocery"
    assert category_alert["transactions"][0]["amount"] == "800.00"
    assert (
        len(
            [
                data["summary_sentence_1"],
                data["summary_sentence_2"],
            ]
        )
        == 2
    )

    recommendation = data["recommendations"][0]
    dismissed = client.patch(
        f"/api/dashboard/recommendations/{recommendation['id']}",
        json={"status": "dismissed"},
    )
    assert dismissed.status_code == 200
    refreshed = client.get("/api/dashboard/advisor?year=2026&month=3").json()
    assert recommendation["id"] not in {
        item["id"] for item in refreshed["recommendations"]
    }


def test_advisor_regenerates_when_validated_data_changes(client: TestClient) -> None:
    account_id = create_account(client)
    first = client.get("/api/dashboard/advisor?year=2026&month=4")
    assert first.status_code == 200
    first_generated_at = first.json()["generated_at"]
    add_transaction(
        client,
        account_id,
        "2026-04-02",
        "Employer",
        "2500.00",
        "credit",
    )
    second = client.get("/api/dashboard/advisor?year=2026&month=4")
    assert second.status_code == 200
    assert second.json()["forecast"]["expected_income"] == "2500.00"
    assert second.json()["generated_at"] >= first_generated_at

    investment = client.post(
        "/api/investments",
        json={
            "asset_name": "Local ETF",
            "asset_type": "ETF",
            "current_value": "1200.00",
            "currency": "EUR",
        },
    )
    assert investment.status_code == 201
    third = client.get("/api/dashboard/advisor?year=2026&month=4")
    assert third.status_code == 200
    assert third.json()["financial_position"]["investment_value"] == "1200.00"
    assert third.json()["financial_position"]["net_worth"] == "5200.00"
    assert third.json()["generated_at"] >= second.json()["generated_at"]


def test_invalid_local_ai_json_falls_back_to_deterministic_wording(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        advisor_service,
        "generate_local_json",
        lambda _: '{"summary_sentence_1": "missing required fields"}',
    )
    sentence_1, sentence_2, explanation, local_ai_used = advisor_service._wording(
        {
            "expected_surplus": Decimal("100.00"),
            "category_risks": [],
            "sample_months": ["2026-01", "2026-02", "2026-03"],
        },
        use_local_ai=True,
    )
    assert "€100.00 surplus" in sentence_1
    assert "No category" in sentence_2
    assert "validated non-duplicate transactions" in explanation
    assert local_ai_used is False
