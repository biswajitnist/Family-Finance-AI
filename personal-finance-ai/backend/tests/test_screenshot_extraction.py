from datetime import date

from app.services.document_processor import _rows_from_statement_text


def test_extracts_mobile_transaction_cards_with_separate_lines() -> None:
    text = """Transactions Standing orders Details
Biswajit Biswas
-1.000,00
09.06.2026
einhundert Energie GmbH
9 -42,00
09.06.2026
Discover contract overview
PayPal Europe S.a.r.l. et Cie S.C.A -1.85
09.06.2026 ,
"""

    rows = _rows_from_statement_text(text)

    assert [(row["vendor"], row["amount"], row["date"]) for row in rows] == [
        ("Biswajit Biswas", "-1.000,00", "2026-06-09"),
        ("einhundert Energie GmbH", "-42,00", "2026-06-09"),
        ("PayPal Europe S.a.r.l. et Cie S.C.A", "-1.85", "2026-06-09"),
    ]


def test_extracts_yesterday_using_screenshot_capture_date() -> None:
    text = """June 2026
Backwerk Wolfsburg, Wolfsburg DE -7,80
Yesterday ,
Rossmann 2171, Wolfsburg DE
g -2,69
Yesterday
"""

    rows = _rows_from_statement_text(text, reference_date=date(2026, 6, 11))

    assert [(row["vendor"], row["amount"], row["date"]) for row in rows] == [
        ("Backwerk Wolfsburg, Wolfsburg DE", "-7,80", "2026-06-10"),
        ("Rossmann 2171, Wolfsburg DE", "-2,69", "2026-06-10"),
    ]


def test_does_not_guess_amount_without_decimal_separator() -> None:
    text = """Pending Merchant -68,26
June 2026
Backwerk Wolfsburg, Wolfsburg DE -780
Yesterday
"""

    assert (
        _rows_from_statement_text(text, reference_date=date(2026, 6, 11)) == []
    )


def test_extracts_sparse_ocr_when_date_precedes_amount() -> None:
    text = """Transactions
Biswajit Biswas
09.06.2026
-1.000,00
einhundert Energie GmbH
09.06.2026
-42,00
"""

    rows = _rows_from_statement_text(text)

    assert [(row["vendor"], row["amount"], row["date"]) for row in rows] == [
        ("Biswajit Biswas", "-1.000,00", "2026-06-09"),
        ("einhundert Energie GmbH", "-42,00", "2026-06-09"),
    ]


def test_extracts_credit_card_statement_table_rows() -> None:
    text = """Datum Karte Beschreibung Betrag
22.06.2026 ************3731 Allgemeiner Deutscher -54,00 €
20.06.2026 ************3731 Storck Outlet Wolfsbur -46,25 €
20.06.2026 ************3731 Chocoladefabriken Lind -6,05 €
20.06.2026 ************3731 LS Giovanni L -3,10 €
20.06.2026 ************3731 Hilfiger Stores German -164,20 €
20.06.2026 ************3731 adidas FO Wolfsburg 2 -116,80 €
19.06.2026 ************3731 EDEKA KLAMKA -4,64 €
"""

    rows = _rows_from_statement_text(text)

    assert [(row["vendor"], row["amount"], row["date"]) for row in rows] == [
        ("Allgemeiner Deutscher", "-54,00", "2026-06-22"),
        ("Storck Outlet Wolfsbur", "-46,25", "2026-06-20"),
        ("Chocoladefabriken Lind", "-6,05", "2026-06-20"),
        ("LS Giovanni L", "-3,10", "2026-06-20"),
        ("Hilfiger Stores German", "-164,20", "2026-06-20"),
        ("adidas FO Wolfsburg 2", "-116,80", "2026-06-20"),
        ("EDEKA KLAMKA", "-4,64", "2026-06-19"),
    ]
    assert rows[0]["type"] == "debit"
    assert rows[0]["payment_method"] == "************3731"


def test_extracts_vertical_credit_card_statement_pdf_text() -> None:
    text = """Amazon Visa - Umsätze
Datum
Karte
Beschreibung
Betrag
Punkte
22.06.2026
************3731
Allgemeiner Deutscher
-54,00 €
0
20.06.2026
************3731
Storck Outlet Wolfsbur
-46,25 €
+23
09.06.2026
************3731
Eingelöste Amazon Punkte
0,00 €
-114
05.06.2026
************3731
AMAZON CREDIT CARD
+125,99 €
+0
"""

    rows = _rows_from_statement_text(text)

    assert [(row["vendor"], row["amount"], row["date"]) for row in rows] == [
        ("Allgemeiner Deutscher", "-54,00", "2026-06-22"),
        ("Storck Outlet Wolfsbur", "-46,25", "2026-06-20"),
        ("AMAZON CREDIT CARD", "+125,99", "2026-06-05"),
    ]
    assert rows[0]["payment_method"] == "************3731"
    assert rows[-1]["type"] == "credit"
