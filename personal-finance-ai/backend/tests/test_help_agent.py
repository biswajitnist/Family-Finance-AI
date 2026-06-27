from fastapi.testclient import TestClient

from app.services.chat_service import _period
from app.services.help_agent import _classify


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Help Agent account",
            "type": "bank",
            "currency": "EUR",
            "country": "DE",
        },
    )
    return response.json()["id"]


def ask(client: TestClient, message: str) -> dict:
    response = client.post("/api/ai/help-agent", json={"message": message})
    assert response.status_code == 200
    return response.json()


def test_help_agent_finance_uses_only_validated_records(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.services.help_agent._classify", lambda _: ("finance_query", False)
    )
    account_id = create_account(client)
    for amount, validated in (("40.00", True), ("900.00", False)):
        response = client.post(
            "/api/transactions",
            json={
                "account_id": account_id,
                "transaction_date": "2026-06-03",
                "vendor": "Shop",
                "amount": amount,
                "currency": "EUR",
                "transaction_type": "debit",
                "is_validated": validated,
            },
        )
        assert response.status_code == 201

    result = ask(client, "How much did I spend in June 2026?")
    assert result["intent"] == "finance_query"
    assert "40.00" in result["answer"]
    assert "900.00" not in result["answer"]
    assert result["source_basis"] == ["database"]


def test_help_agent_document_searches_processed_text_and_chroma(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.services.help_agent._classify", lambda _: ("document_query", False)
    )
    monkeypatch.setattr(
        "app.services.help_agent.generate_local_text",
        lambda prompt: "The uploaded statement contains a Wolfsburg payment.",
    )
    account_id = create_account(client)
    uploaded = client.post(
        "/api/documents/upload",
        data={
            "document_type": "bank_statement",
            "source_account_id": str(account_id),
        },
        files={
            "file": (
                "local.txt",
                "2026-06-03 Stadt Wolfsburg school payment -75.00 EUR",
                "text/plain",
            )
        },
    )
    client.post(f"/api/documents/{uploaded.json()['id']}/process")

    result = ask(client, "What does the uploaded Wolfsburg statement contain?")
    assert result["intent"] == "document_query"
    assert result["source_basis"] == ["document"]
    assert result["sources"][0]["file_name"] == "local.txt"


def test_help_agent_app_help_troubleshooting_and_report(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.services.help_agent.generate_local_text",
        lambda prompt: "Use Documents, process the file, then review rows.",
    )
    intents = iter(("app_help", "troubleshooting", "report_request"))
    monkeypatch.setattr(
        "app.services.help_agent._classify", lambda _: (next(intents), False)
    )

    app_help = ask(client, "How do I review a statement?")
    assert app_help["intent"] == "app_help"
    assert "help guide" in app_help["source_basis"]

    troubleshooting = ask(client, "My import is stuck")
    assert troubleshooting["intent"] == "troubleshooting"
    assert set(troubleshooting["source_basis"]) == {"database", "help guide"}

    report = ask(client, "Generate a monthly PDF report for June 2026")
    assert report["intent"] == "report_request"
    assert report["report"]["download_url"].startswith("/api/reports/")
    assert set(report["source_basis"]) == {"database", "generated report"}
    assert report["missing_data"]


def test_relative_month_period() -> None:
    start, end = _period("How much did I spend this month?")
    assert start.day == 1
    assert start.year == end.year
    assert start.month == end.month


def test_how_to_statement_question_is_app_help() -> None:
    intent, local_ai_used = _classify(
        "How do I review and confirm an uploaded statement?"
    )
    assert intent == "app_help"
    assert local_ai_used is False


def test_rules_help_uses_plain_local_guide(client: TestClient) -> None:
    result = ask(client, "How do I use rules to categorize REWE transactions?")
    assert result["intent"] == "app_help"
    assert result["source_basis"] == ["help guide"]
    assert result["sources"][0]["file_name"] == "rules-guide.md"
    assert "Merchant name contains" in result["answer"]
    assert "IBAN" not in result["answer"]
