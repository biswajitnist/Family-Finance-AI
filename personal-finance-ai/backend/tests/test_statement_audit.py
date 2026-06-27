from fastapi.testclient import TestClient


def create_account(client: TestClient) -> int:
    response = client.post(
        "/api/accounts",
        json={
            "name": "Audit Account",
            "type": "checking",
            "country": "DE",
            "currency": "EUR",
            "opening_balance": "0",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def upload_csv(client: TestClient, account_id: int, name: str, row: str) -> int:
    response = client.post(
        "/api/documents/upload",
        data={
            "document_type": "bank_statement",
            "source_account_id": str(account_id),
        },
        files={
            "file": (
                name,
                "date,vendor,amount,currency,type\n" + row,
                "text/csv",
            )
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_batch_audit_counts_all_documents_and_confirms(client: TestClient) -> None:
    account_id = create_account(client)
    ids = [
        upload_csv(
            client,
            account_id,
            "one.csv",
            "2026-06-01,First Merchant,10.00,EUR,debit\n",
        ),
        upload_csv(
            client,
            account_id,
            "two.csv",
            "2026-06-02,Second Merchant,20.00,EUR,debit\n",
        ),
    ]
    processed = client.post(
        "/api/documents/process-batch",
        json={"document_ids": ids, "force_ocr": False, "use_local_ai": False},
    )
    assert processed.status_code == 200
    statement_set_id = processed.json()["statement_set_id"]

    audit = client.get(f"/api/statement-sets/{statement_set_id}")
    assert audit.status_code == 200
    assert audit.json()["expected_transaction_count"] == 2
    assert audit.json()["extracted_count"] == 2
    assert audit.json()["can_confirm"] is True

    confirmed = client.post(f"/api/statement-sets/{statement_set_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed"] == 2


def test_overlapping_rows_are_removed_from_statement_set(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    row = "2026-06-01,Repeated Merchant,10.00,EUR,debit\n"
    ids = [
        upload_csv(client, account_id, "one.csv", row),
        upload_csv(client, account_id, "two.csv", row),
    ]
    processed = client.post(
        "/api/documents/process-batch",
        json={"document_ids": ids, "force_ocr": False, "use_local_ai": False},
    )
    audit = client.get(
        f"/api/statement-sets/{processed.json()['statement_set_id']}"
    ).json()

    assert audit["overlap_count"] == 1
    assert audit["extracted_count"] == 1
    assert any(item["status"] == "overlap" for item in audit["candidates"])


def test_audit_flags_existing_validated_transaction_without_document(
    client: TestClient,
) -> None:
    account_id = create_account(client)
    transaction = client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "transaction_date": "2026-06-22",
            "vendor": "Allgemeiner Deutscher",
            "description": "Existing card transaction",
            "amount": "54.00",
            "currency": "EUR",
            "transaction_type": "debit",
            "is_validated": True,
        },
    )
    assert transaction.status_code == 201
    document_id = upload_csv(
        client,
        account_id,
        "statement.csv",
        "2026-06-22,Allgemeiner Deutscher,54.00,EUR,debit\n",
    )
    processed = client.post(
        f"/api/documents/{document_id}/process?force_ocr=false&use_local_ai=false"
    )
    assert processed.status_code == 200

    audit = client.get(
        f"/api/statement-sets/{processed.json()['statement_set_id']}"
    ).json()
    candidate = next(
        item
        for item in audit["candidates"]
        if item["vendor"] == "Allgemeiner Deutscher"
    )

    assert candidate["duplicate_matches"]
    assert candidate["duplicate_matches"][0]["vendor"] == "Allgemeiner Deutscher"
    assert candidate["duplicate_matches"][0]["merchant_similarity"] == 1.0
