from fastapi.testclient import TestClient


def _account_and_categories(client: TestClient) -> tuple[int, dict[str, int]]:
    account = client.post(
        "/api/accounts",
        json={
            "name": "Current Account",
            "type": "bank",
            "country": "DE",
            "currency": "EUR",
            "opening_balance": "0",
            "current_balance": "0",
            "is_active": True,
        },
    ).json()
    categories = {
        item["name"]: item["id"] for item in client.get("/api/categories").json()
    }
    return account["id"], categories


def _seed_transactions(client: TestClient) -> None:
    account_id, categories = _account_and_categories(client)
    rows = [
        ("2026-06-01", "Market", "25.50", "debit", categories["Grocery"]),
        ("2026-06-02", "Market", "14.50", "debit", categories["Grocery"]),
        ("2026-06-03", "Rail", "30.00", "debit", categories["Transport"]),
        ("2026-06-04", "Employer", "2500.00", "credit", categories["Salary"]),
    ]
    for transaction_date, vendor, amount, transaction_type, category_id in rows:
        response = client.post(
            "/api/transactions",
            json={
                "account_id": account_id,
                "transaction_date": transaction_date,
                "vendor": vendor,
                "description": vendor,
                "amount": amount,
                "currency": "EUR",
                "transaction_type": transaction_type,
                "category_id": category_id,
                "is_validated": True,
            },
        )
        assert response.status_code == 201


def _payload() -> dict:
    return {
        "name": "Expense by Category",
        "description": "Validated spending grouped by category.",
        "data_source": "transactions",
        "chart_type": "bar",
        "config_json": {
            "fields": ["category", "amount"],
            "filters": [
                {
                    "field": "transaction_type",
                    "operator": "equals",
                    "value": "debit",
                }
            ],
            "groupBy": ["category"],
            "aggregation": {"field": "amount", "function": "sum"},
            "sort": {"field": "amount", "direction": "desc"},
            "limit": 10,
            "chart": {"type": "bar", "xAxis": "category", "yAxis": "amount"},
        },
    }


def _loan_payload() -> dict:
    return {
        "name": "Loan Balance Overview",
        "description": "Outstanding balance by lender.",
        "data_source": "loans",
        "chart_type": "bar",
        "config_json": {
            "fields": ["lender", "current_balance"],
            "filters": [],
            "groupBy": ["lender"],
            "aggregation": {"field": "current_balance", "function": "sum"},
            "sort": {"field": "current_balance", "direction": "desc"},
            "limit": 10,
            "chart": {
                "type": "bar",
                "xAxis": "lender",
                "yAxis": "current_balance",
            },
        },
    }


def test_custom_report_crud_preview_run_and_duplicate(client: TestClient) -> None:
    _seed_transactions(client)

    metadata = client.get("/api/reports/metadata")
    assert metadata.status_code == 200
    assert metadata.json()["data_sources"][0]["label"] == "Transactions"

    preview = client.post("/api/reports/preview", json=_payload())
    assert preview.status_code == 200
    assert preview.json()["rows"] == [
        {"category": "Grocery", "amount": 40.0},
        {"category": "Transport", "amount": 30.0},
    ]

    created = client.post("/api/reports", json=_payload())
    assert created.status_code == 201
    report_id = created.json()["id"]

    assert client.get("/api/reports").json()[0]["name"] == "Expense by Category"
    assert client.get(f"/api/reports/{report_id}").status_code == 200
    assert client.post(f"/api/reports/{report_id}/run").json()["total_rows"] == 2

    update = _payload()
    update["name"] = "Updated Expense Report"
    updated = client.put(f"/api/reports/{report_id}", json=update)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Expense Report"

    duplicate = client.post(f"/api/reports/{report_id}/duplicate")
    assert duplicate.status_code == 201
    assert duplicate.json()["name"] == "Updated Expense Report (Copy)"

    deleted = client.delete(f"/api/reports/{report_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/reports/{report_id}").status_code == 404


def test_custom_report_rejects_unlisted_fields(client: TestClient) -> None:
    payload = _payload()
    payload["config_json"]["fields"] = ["raw_sql"]
    response = client.post("/api/reports/preview", json=payload)
    assert response.status_code == 422
    assert "not available" in response.json()["detail"]


def test_phase_two_and_three_report_features(client: TestClient) -> None:
    response = client.post(
        "/api/loans",
        json={
            "lender": "Sparkasse",
            "loan_type": "personal",
            "original_amount": "12000",
            "current_balance": "8000",
            "interest_rate": "4.5",
            "monthly_payment": "300",
            "currency": "EUR",
        },
    )
    assert response.status_code == 201

    metadata = client.get("/api/reports/metadata").json()
    sources = {source["key"] for source in metadata["data_sources"]}
    chart_types = {chart["key"] for chart in metadata["chart_types"]}
    assert {"investments", "loans", "budgets", "net_worth"} <= sources
    assert {"kpi", "trend", "donut", "area", "horizontal_bar"} <= chart_types

    preview = client.post("/api/reports/preview", json=_loan_payload())
    assert preview.status_code == 200
    assert preview.json()["rows"] == [
        {"lender": "Sparkasse", "current_balance": 8000.0}
    ]

    created = client.post("/api/reports", json=_loan_payload())
    assert created.status_code == 201
    report_id = created.json()["id"]

    dashboard = client.post(
        f"/api/reports/{report_id}/dashboard",
        json={"section": "overview", "widget_size": "large", "position": 2},
    )
    assert dashboard.status_code == 200
    assert dashboard.json()["dashboard_section"] == "overview"

    scheduled = client.post(
        f"/api/reports/{report_id}/schedule",
        json={"frequency": "monthly"},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["schedule_frequency"] == "monthly"

    widgets = client.get("/api/reports/dashboard/widgets")
    assert widgets.status_code == 200
    assert widgets.json()[0]["id"] == report_id

    scheduled_reports = client.get("/api/reports/scheduled")
    assert scheduled_reports.status_code == 200
    assert scheduled_reports.json()[0]["id"] == report_id

    run = client.post(f"/api/reports/{report_id}/run")
    assert run.status_code == 200
    assert client.get(f"/api/reports/{report_id}").json()["last_run_at"] is not None

    for export_format in ("csv", "xlsx", "pdf"):
        exported = client.get(f"/api/reports/{report_id}/export/{export_format}")
        assert exported.status_code == 200
        assert exported.content

    ai_draft = client.post("/api/reports/ai-draft", json={"prompt": "loan balance"})
    assert ai_draft.status_code == 200
    assert ai_draft.json()["data_source"] == "loans"

    net_worth = client.post(
        "/api/reports/preview",
        json={
            "data_source": "net_worth",
            "chart_type": "kpi",
            "config_json": {
                "fields": ["metric", "value", "currency"],
                "filters": [],
                "groupBy": [],
                "aggregation": None,
                "sort": None,
                "limit": 10,
                "chart": {"type": "kpi", "xAxis": "metric", "yAxis": "value"},
            },
        },
    )
    assert net_worth.status_code == 200
    assert net_worth.json()["value"] is not None
