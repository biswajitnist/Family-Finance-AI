from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.finance import FxRate
from app.services.ai_service import ExtractionResult
from app.services.document_processor import _rows_from_statement_text


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Household",
            "type": "bank",
            "currency": "EUR",
            "country": "DE",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_document_pipeline_rules_reports_and_chat(client: TestClient) -> None:
    account_id = create_account(client)
    rule = client.post(
        "/api/rules",
        json={
            "name": "REWE groceries",
            "condition_type": "vendor",
            "condition_value": "REWE",
            "action_type": "category",
            "action_value": "Grocery",
            "priority": 1,
            "is_active": True,
        },
    )
    assert rule.status_code == 201
    invalid_rule = client.post(
        "/api/rules",
        json={
            "name": "Typo category",
            "condition_type": "vendor",
            "condition_value": "Example",
            "action_type": "category",
            "action_value": "Grocey",
        },
    )
    assert invalid_rule.status_code == 422
    assert "existing category" in invalid_rule.json()["detail"]

    csv_content = (
        "date,vendor,description,amount,currency,type\n"
        "2026-06-03,REWE,Weekly shop,42.35,EUR,debit\n"
    )
    uploaded = client.post(
        "/api/documents/upload",
        data={
            "document_type": "bank_statement",
            "source_account_id": str(account_id),
        },
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]

    processed = client.post(f"/api/documents/{document_id}/process")
    assert processed.status_code == 200
    assert processed.json()["transactions_created"] == 1

    pending = client.get("/api/transactions?validated=false").json()
    assert len(pending) == 1
    assert pending[0]["classification_source"] == "rule"
    transaction_id = pending[0]["id"]
    validation = client.post(
        "/api/transactions/validate",
        json={"transaction_ids": [transaction_id], "is_validated": True},
    )
    assert validation.status_code == 200

    report = client.post(
        "/api/reports",
        json={
            "report_type": "monthly",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "format": "xlsx",
        },
    )
    assert report.status_code == 201
    download = client.get(f"/api/reports/{report.json()['id']}/download")
    assert download.status_code == 200

    chat = client.post(
        "/api/ai/chat",
        json={"question": "How much did I spend on groceries in June 2026?"},
    )
    assert chat.status_code == 200
    assert "42.35" in chat.json()["answer"]
    assert "1 validated" in chat.json()["calculation_basis"]
    assert chat.json()["sources"][0]["type"] == "transaction"


def test_type_rule_does_not_block_category_classification(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    categories = {
        item["name"]: item["id"] for item in client.get("/api/categories").json()
    }
    history = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-01",
            "vendor": "Picnic",
            "amount": "25.00",
            "currency": "EUR",
            "transaction_type": "debit",
            "category_id": categories["Grocery"],
            "is_validated": True,
        },
    )
    assert history.status_code == 201
    rule = client.post(
        "/api/rules",
        json={
            "name": "Picnic is an expense",
            "condition_type": "vendor",
            "condition_value": "Picnic",
            "action_type": "transaction_type",
            "action_value": "debit",
        },
    )
    assert rule.status_code == 201
    pending = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-11",
            "vendor": "Picnic",
            "amount": "68.26",
            "currency": "EUR",
            "transaction_type": "credit",
            "is_validated": False,
        },
    )
    assert pending.status_code == 201

    classified = client.post(
        f"/api/ai/classify-transaction/{pending.json()['id']}"
    )

    assert classified.status_code == 200
    assert classified.json()["transaction_type"] == "debit"
    assert classified.json()["category_id"] == categories["Grocery"]
    assert classified.json()["classification_source"] == "merchant_history"


def test_bulk_classification_reports_when_ollama_is_offline(
    client: TestClient, monkeypatch
) -> None:
    account_id = create_account(client)
    pending = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-11",
            "vendor": "Unique Unmatched Merchant",
            "amount": "19.95",
            "currency": "EUR",
            "transaction_type": "debit",
            "is_validated": False,
        },
    )
    assert pending.status_code == 201
    monkeypatch.setattr(
        "app.api.full_routes.ollama_status",
        lambda: {
            "available": False,
            "model_installed": False,
            "model": "qwen2.5:3b",
        },
    )

    result = client.post(
        "/api/ai/classify-pending",
        json={"transaction_ids": [pending.json()["id"]]},
    )

    assert result.status_code == 200
    assert result.json()["classified"] == 0
    assert result.json()["unresolved"] == ["Unique Unmatched Merchant"]
    assert result.json()["ollama_available"] is False


def test_multiple_documents_can_be_processed_as_one_batch(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    document_ids = []
    for index, vendor in enumerate(("First Merchant", "Second Merchant"), start=1):
        uploaded = client.post(
            "/api/documents/upload",
            data={
                "document_type": "bank_statement",
                "source_account_id": str(account_id),
            },
            files={
                "file": (
                    f"statement-{index}.csv",
                    "date,vendor,amount,currency,type\n"
                    f"2026-06-0{index},{vendor},10.00,EUR,debit\n",
                    "text/csv",
                )
            },
        )
        assert uploaded.status_code == 201
        document_ids.append(uploaded.json()["id"])

    processed = client.post(
        "/api/documents/process-batch",
        json={
            "document_ids": document_ids,
            "force_ocr": False,
            "use_local_ai": False,
        },
    )
    assert processed.status_code == 200
    assert processed.json()["requested"] == 2
    assert processed.json()["completed"] == 2
    assert processed.json()["failed"] == 0
    assert processed.json()["transactions_created"] == 2
    assert len(processed.json()["results"]) == 2

    pending = client.get("/api/transactions?validated=false").json()
    assert {item["vendor"] for item in pending} == {
        "First Merchant",
        "Second Merchant",
    }


def test_finance_module_crud_and_net_worth(client: TestClient) -> None:
    account_id = create_account(client)
    resources = [
        (
            "investments",
            {
                "account_id": account_id,
                "asset_name": "World ETF",
                "asset_type": "ETF",
                "quantity": "10",
                "average_price": "80",
                "currency": "EUR",
                "current_value": "1000",
            },
        ),
        (
            "loans",
            {
                "lender": "Local Bank",
                "loan_type": "mortgage",
                "original_amount": "200000",
                "current_balance": "150000",
                "interest_rate": "2.5",
                "monthly_payment": "900",
                "currency": "EUR",
            },
        ),
        (
            "properties",
            {
                "name": "Rental flat",
                "country": "DE",
                "currency": "EUR",
                "purchase_price": "220000",
                "current_value": "250000",
                "monthly_rental_income": "1000",
                "monthly_costs": "250",
            },
        ),
        (
            "insurance",
            {
                "provider": "Example Insurance",
                "policy_type": "term_life",
                "coverage_amount": "300000",
                "premium_amount": "35",
                "premium_frequency": "monthly",
                "currency": "EUR",
            },
        ),
    ]
    created: dict[str, dict] = {}
    for path, payload in resources:
        response = client.post(f"/api/{path}", json=payload)
        assert response.status_code == 201
        created[path] = response.json()
        assert client.get(f"/api/{path}").status_code == 200

    investment_update = {
        **resources[0][1],
        "ticker": "VWCE",
        "average_price": "85",
        "current_value": "1050",
    }
    updated_investment = client.put(
        f"/api/investments/{created['investments']['id']}",
        json=investment_update,
    )
    assert updated_investment.status_code == 200
    assert updated_investment.json()["ticker"] == "VWCE"
    assert updated_investment.json()["average_price"] == "85.0000"

    loan_update = {
        **resources[1][1],
        "current_balance": "149000",
        "monthly_payment": "950",
    }
    updated_loan = client.put(
        f"/api/loans/{created['loans']['id']}",
        json=loan_update,
    )
    assert updated_loan.status_code == 200
    assert updated_loan.json()["current_balance"] == "149000.00"
    assert updated_loan.json()["monthly_payment"] == "950.00"

    dashboard = client.get("/api/dashboard?year=2026&month=6")
    assert dashboard.status_code == 200
    assert dashboard.json()["investments"] == "1050.00"
    assert dashboard.json()["debt_balance"] == "149000.00"
    assert dashboard.json()["property_value"] == "250000.00"
    assert client.get("/api/analytics/investments").status_code == 200
    assert client.get("/api/analytics/debt").status_code == 200
    assert client.get("/api/analytics/properties").status_code == 200
    assert client.get("/api/analytics/protection").status_code == 200
    projection = client.get("/api/analytics/net-worth-projection")
    assert projection.status_code == 200
    assert len(projection.json()["projection"]) == 11


def test_dashboard_converts_property_to_base_currency(client: TestClient) -> None:
    with SessionLocal() as db:
        db.add(
            FxRate(
                from_currency="INR",
                to_currency="EUR",
                rate=Decimal("0.01"),
                provider="Test FX",
                rate_date=date(2026, 6, 11),
            )
        )
        db.commit()

    response = client.post(
        "/api/properties",
        json={
            "name": "Pune property",
            "country": "IN",
            "currency": "INR",
            "purchase_price": "15000000",
            "current_value": "17800000",
            "monthly_rental_income": "50000",
            "monthly_costs": "5000",
        },
    )
    assert response.status_code == 201

    dashboard = client.get("/api/dashboard?year=2026&month=6")
    assert dashboard.status_code == 200
    assert dashboard.json()["currency"] == "EUR"
    assert dashboard.json()["property_value"] == "178000.00"
    assert dashboard.json()["fx_warnings"] == []

    analytics = client.get("/api/analytics/properties")
    assert analytics.status_code == 200
    assert analytics.json()["total_value"] == "178000.00"
    assert analytics.json()["properties"][0]["current_value_base"] == "178000.00"


def test_market_provider_crud_masks_credentials(client: TestClient) -> None:
    created = client.post(
        "/api/market-data/providers",
        json={
            "provider_name": "Test Provider",
            "provider_type": "Generic",
            "base_url": "https://api.twelvedata.com",
            "api_key": "test-secret-market-key-123",
            "auth_method": "API Key in Query Parameter",
            "api_key_parameter_name": "apikey",
            "enabled": True,
            "priority": 90,
            "test_symbol": "NVDA",
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["has_api_key"] is True
    assert "test-secret-market-key-123" not in payload["api_key_masked"]

    providers = client.get("/api/market-data/providers")
    assert providers.status_code == 200
    serialized = providers.text
    assert "test-secret-market-key-123" not in serialized

    updated = client.put(
        f"/api/market-data/providers/{payload['id']}",
        json={
            "provider_name": "Test Provider",
            "provider_type": "Generic",
            "base_url": "https://api.twelvedata.com",
            "auth_method": "API Key in Query Parameter",
            "api_key_parameter_name": "apikey",
            "enabled": False,
            "priority": 95,
            "test_symbol": "NVDA",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["has_api_key"] is True


def test_ocr_text_parser_and_ollama_schema() -> None:
    rows = _rows_from_statement_text("2026-06-03 REWE Weekly groceries -54.32 EUR")
    assert rows[0]["vendor"] == "REWE Weekly groceries"
    assert rows[0]["type"] == "debit"

    result = ExtractionResult.model_validate(
        {
            "transactions": [
                {
                    "transaction_date": "2026-06-03",
                    "vendor": "REWE",
                    "amount": "-54,32",
                    "currency": "eur",
                    "transaction_type": "debit",
                    "confidence": 0.91,
                }
            ]
        }
    )
    assert result.transactions[0].amount == Decimal("54.32")
    assert result.transactions[0].currency == "EUR"


def test_commerzbank_statement_parser_handles_german_amounts_and_credits() -> None:
    rows = _rows_from_statement_text(
        """
        Kontoauszug vom 27.02.2026
        Angaben zu den Umsätzen               Valuta
        Buchungsdatum: 02.02.2026
        Atul Gupta                             31.01            2.474,00-
        Ticket to India
        End-to-End-Ref.: MOB.031.EE.POS00015960
        Bundesagentur für Arbeit               02.02              518,00
        Kindergeld
        """
    )
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-02-02"
    assert rows[0]["booking_date"] == "2026-01-31"
    assert rows[0]["amount"] == "2474.00"
    assert rows[0]["type"] == "debit"
    assert rows[0]["description"] == (
        "Ticket to India End-to-End-Ref.: MOB.031.EE.POS00015960"
    )
    assert rows[1]["amount"] == "518.00"
    assert rows[1]["type"] == "credit"


def test_commerzbank_ocr_layout_with_single_space_columns() -> None:
    rows = _rows_from_statement_text(
        """
        Kontoauszug vom 30.04.2026
        Angaben zu den Umsätzen Valuta
        Buchungsdatum: 01.04.2026
        Allianz Versicherungs-AG 01.04 12,16-
        Vertrag AS-9174527481
        Volkswagen AG 01.04 5.095,38
        Salary
        """
    )
    assert len(rows) == 2
    assert rows[0]["amount"] == "12.16"
    assert rows[0]["type"] == "debit"
    assert rows[1]["amount"] == "5095.38"
    assert rows[1]["type"] == "credit"


def test_document_review_confirmation_editing_and_monthly_budget(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    grocery = next(
        item
        for item in client.get("/api/categories").json()
        if item["name"] == "Grocery"
    )
    uploaded = client.post(
        "/api/documents/upload",
        data={
            "document_type": "bank_statement",
            "source_account_id": str(account_id),
        },
        files={
            "file": (
                "statement.csv",
                "date,vendor,description,amount,currency,type\n"
                "2026-06-04,Market,Food,50.00,EUR,debit\n",
                "text/csv",
            )
        },
    )
    document_id = uploaded.json()["id"]
    assert uploaded.json()["processing_stage"] == "uploaded"

    processed = client.post(f"/api/documents/{document_id}/process")
    assert processed.status_code == 200
    document = client.get(f"/api/documents/{document_id}").json()
    assert document["processing_stage"] == "human_review"
    assert document["processing_progress"] == 100

    rows = client.get(f"/api/documents/{document_id}/transactions").json()
    assert len(rows) == 1
    transaction_id = rows[0]["id"]
    edited = client.put(
        f"/api/transactions/{transaction_id}",
        json={
            "vendor": "Local Market",
            "amount": "55.00",
            "category_id": grocery["id"],
        },
    )
    assert edited.status_code == 200
    assert edited.json()["classification_source"] == "user_edit"
    assert "vendor" in edited.json()["edited_fields"]

    confirmed = client.post(
        f"/api/documents/{document_id}/confirm", json=[transaction_id]
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["remaining"] == 0
    assert client.get(f"/api/documents/{document_id}").json()["status"] == "validated"

    budget = client.post(
        "/api/budgets",
        json={
            "year": 2026,
            "month": 6,
            "category_id": grocery["id"],
            "amount": "100.00",
            "currency": "EUR",
        },
    )
    assert budget.status_code == 201
    summary = client.get("/api/budgets/summary?year=2026&month=6").json()
    assert summary["total_budget"] == "100.00"
    assert summary["spent"] == "55.00"
    assert summary["remaining"] == "45.00"
    dashboard = client.get("/api/dashboard?year=2026&month=6").json()
    assert dashboard["budget_total"] == "100.00"
    assert dashboard["budget_remaining"] == "45.00"


def test_scalable_portfolio_is_imported_as_investment_holdings(
    client: TestClient,
) -> None:
    portfolio_text = """Portfolio Since purchase
A Alphabet A 318 35
2.547 € +77,05 % 1.108 €
Xtrackers Artificial Intelligence
& Big Data (Acc) 197 76
3.792 € +44,36 % 1.165 €
NVIDIA 177 90
4.625 € +42,80 % 1.386 €
Xtrackers Nasdaq 100 (Acc) 57 90
2.077 € +22,20 % 377 €
iShares Core S&P 500 (Acc) 686 81
3.236 € +18,38 % 502 €
VanEck Quantum Computing (Acc) 26 46
344 € +14,62 % 44 €
IonQ 48 52
194 € -15,85 % 37 €
D-Wave Quantum 20 46
205 € -17,94 % 45 €
"""
    uploaded = client.post(
        "/api/documents/upload",
        data={"document_type": "bank_statement"},
        files={"file": ("scalable.txt", portfolio_text, "text/plain")},
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]
    processed = client.post(f"/api/documents/{document_id}/process")
    assert processed.status_code == 200
    assert processed.json()["transactions_created"] == 0
    assert processed.json()["investments_created"] == 8
    assert processed.json()["record_type"] == "investment"
    document = client.get(f"/api/documents/{document_id}").json()
    assert document["document_type"] == "investment_statement"
    assert "8 portfolio holding(s)" in document["processing_message"]
    investments = client.get("/api/investments").json()
    assert len(investments) == 8
    assert {item["asset_name"] for item in investments} >= {
        "Alphabet A",
        "NVIDIA",
        "IonQ",
        "D-Wave Quantum",
    }
    assert sum(Decimal(item["current_value"]) for item in investments) == Decimal(
        "17020.00"
    )

    analytics = client.get("/api/analytics/investments").json()
    assert analytics["current_value"] == "17020.00"
    assert analytics["profit_loss"] is None
    assert analytics["cost_basis_complete"] is False
    assert analytics["value_missing_cost_basis"] == "17020.00"


def test_retirement_records_can_be_created_and_updated(client: TestClient) -> None:
    created = client.post(
        "/api/retirement",
        json={
            "name": "German Pension",
            "provider": "Deutsche Rentenversicherung",
            "country": "DE",
            "currency": "EUR",
            "current_value": "25000",
            "monthly_contribution": "500",
            "employer_contribution": "500",
            "projected_value": "420000",
            "retirement_age": 67,
        },
    )
    assert created.status_code == 201
    item_id = created.json()["id"]
    updated_payload = created.json()
    updated_payload.pop("id")
    updated_payload["projected_value"] = "450000"
    updated = client.put(f"/api/retirement/{item_id}", json=updated_payload)
    assert updated.status_code == 200
    assert updated.json()["projected_value"] == "450000.00"
    records = client.get("/api/retirement")
    assert records.status_code == 200
    assert records.json()[0]["name"] == "German Pension"
