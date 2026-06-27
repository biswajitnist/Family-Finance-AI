from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

ADDITIVE_COLUMNS = {
    "users": {
        "email": "VARCHAR(180)",
        "timezone": "VARCHAR(80) NOT NULL DEFAULT 'Europe/Berlin'",
        "preferred_language": "VARCHAR(10) NOT NULL DEFAULT 'en'",
        "tax_country": "VARCHAR(2) NOT NULL DEFAULT 'DE'",
        "date_format": "VARCHAR(30) NOT NULL DEFAULT 'DD-MM-YYYY'",
        "number_format": "VARCHAR(30) NOT NULL DEFAULT '1.234,56'",
        "financial_year_start": "VARCHAR(5) NOT NULL DEFAULT '01-01'",
        "default_portfolio_view": "VARCHAR(30) NOT NULL DEFAULT 'overview'",
        "default_refresh_frequency": "VARCHAR(20) NOT NULL DEFAULT 'hourly'",
        "setup_completed": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "accounts": {
        "is_active": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "categories": {
        "icon": "VARCHAR(40) NOT NULL DEFAULT 'category'",
        "color": "VARCHAR(20) NOT NULL DEFAULT 'green'",
    },
    "documents": {
        "processing_error": "TEXT",
        "processing_stage": "VARCHAR(40) NOT NULL DEFAULT 'uploaded'",
        "processing_progress": "INTEGER NOT NULL DEFAULT 0",
        "processing_message": "TEXT",
        "processed_at": "DATETIME",
        "page_count": "INTEGER",
        "checksum": "VARCHAR(64)",
    },
    "transactions": {
        "payment_method": "VARCHAR(40)",
        "iban": "VARCHAR(40)",
        "confidence": "NUMERIC(5, 4)",
        "classification_source": "VARCHAR(20) NOT NULL DEFAULT 'manual'",
        "recurrence_frequency": "VARCHAR(20)",
        "recurrence_confidence": "NUMERIC(5, 4)",
        "recurrence_source": "VARCHAR(20)",
        "recurrence_group_key": "VARCHAR(220)",
        "next_expected_date": "DATE",
        "edited_fields": "TEXT",
        "linked_loan_id": "INTEGER",
        "loan_ledger_type": "VARCHAR(30)",
        "loan_balance_effect": "VARCHAR(10)",
        "loan_principal_component": "NUMERIC(18, 2)",
        "loan_interest_component": "NUMERIC(18, 2)",
        "loan_mapping_confidence": "NUMERIC(5, 4)",
        "loan_user_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "financial_alerts": {
        "transaction_ids": "TEXT NOT NULL DEFAULT '[]'",
    },
    "investments": {
        "source_document_id": "INTEGER",
        "isin": "VARCHAR(20)",
        "provider_symbol": "VARCHAR(50)",
        "exchange": "VARCHAR(40)",
        "broker": "VARCHAR(80)",
        "market_provider": "VARCHAR(40)",
        "purchase_currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'",
        "base_currency": "VARCHAR(3) NOT NULL DEFAULT 'EUR'",
        "native_value": "NUMERIC(18, 2)",
        "market_price": "NUMERIC(18, 6)",
        "market_currency": "VARCHAR(3)",
        "fx_rate_to_eur": "NUMERIC(18, 8)",
        "price_eur": "NUMERIC(18, 6)",
        "quote_status": "VARCHAR(30)",
        "market_price_updated_at": "DATETIME",
        "market_data_source": "VARCHAR(40)",
        "country": "VARCHAR(2) NOT NULL DEFAULT 'DE'",
    },
    "loans": {
        "direction": "VARCHAR(20) NOT NULL DEFAULT 'borrowed'",
        "interest_mode": "VARCHAR(20) NOT NULL DEFAULT 'manual'",
        "interest_calculation_basis": "VARCHAR(30) NOT NULL DEFAULT 'daily_balance'",
        "interest_posting_frequency": "VARCHAR(20) NOT NULL DEFAULT 'manual'",
        "payment_allocation_rule": "VARCHAR(30) NOT NULL DEFAULT 'interest_first'",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'active'",
        "locked_before": "DATE",
        "lock_reason": "TEXT",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    },
    "loan_ledger_entries": {
        "direction": "VARCHAR(10) NOT NULL DEFAULT 'debit'",
        "signed_amount": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "running_balance": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "principal_component": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "interest_component": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "transaction_id": "INTEGER",
        "mapping_confidence": "NUMERIC(5, 4)",
        "user_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
        "is_locked": "BOOLEAN NOT NULL DEFAULT 0",
        "unlock_reason": "TEXT",
        "updated_at": "DATETIME",
    },
    "custom_reports": {
        "dashboard_section": "VARCHAR(80)",
        "widget_size": "VARCHAR(20)",
        "widget_position": "INTEGER",
        "schedule_frequency": "VARCHAR(40)",
        "last_run_at": "DATETIME",
    },
}


def run_additive_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "loan_document_links" not in tables:
            connection.execute(
                text(
                    """
                    CREATE TABLE loan_document_links (
                        id INTEGER NOT NULL PRIMARY KEY,
                        loan_id INTEGER NOT NULL,
                        document_id INTEGER NOT NULL,
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_loan_document_link
                            UNIQUE (loan_id, document_id),
                        FOREIGN KEY(loan_id) REFERENCES loans (id),
                        FOREIGN KEY(document_id) REFERENCES documents (id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_loan_document_links_loan_id "
                    "ON loan_document_links (loan_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_loan_document_links_document_id "
                    "ON loan_document_links (document_id)"
                )
            )
        if "insurance_document_links" not in tables:
            connection.execute(
                text(
                    """
                    CREATE TABLE insurance_document_links (
                        id INTEGER NOT NULL PRIMARY KEY,
                        insurance_id INTEGER NOT NULL,
                        document_id INTEGER NOT NULL,
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_insurance_document_link
                            UNIQUE (insurance_id, document_id),
                        FOREIGN KEY(insurance_id) REFERENCES insurance_policies (id),
                        FOREIGN KEY(document_id) REFERENCES documents (id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_insurance_document_links_insurance_id "
                    "ON insurance_document_links (insurance_id)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_insurance_document_links_document_id "
                    "ON insurance_document_links (document_id)"
                )
            )
        for table, columns in ADDITIVE_COLUMNS.items():
            if table not in tables:
                continue
            existing = {item["name"] for item in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
                    )
        if "investments" in tables:
            connection.execute(
                text(
                    """
                    UPDATE investments
                    SET country = 'IN'
                    WHERE UPPER(purchase_currency) = 'INR'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE investments
                    SET country = 'US'
                    WHERE UPPER(COALESCE(market_provider, '')) = 'FINNHUB'
                      AND UPPER(COALESCE(purchase_currency, 'EUR')) <> 'INR'
                    """
                )
            )
            stock_symbols = ("QBTS", "IONQ", "NVDA", "GOOGL")
            for symbol in stock_symbols:
                connection.execute(
                    text(
                        """
                        UPDATE investments
                        SET market_provider = COALESCE(market_provider, 'Finnhub'),
                            provider_symbol = COALESCE(provider_symbol, ticker)
                        WHERE UPPER(ticker) = :symbol
                        """
                    ),
                    {"symbol": symbol},
                )
            etf_mappings = (
                ("SXR8", "SXR8.XETRA", "IE00B5BMR087"),
                ("XNAS", "XNAS.XETRA", "IE00BMFKG444"),
                ("XAIX", "XAIX.XETRA", "IE00BGV5VN51"),
                ("QDVE", "QDVE.XETRA", "NL0015000IY2"),
            )
            for ticker, provider_symbol, isin in etf_mappings:
                connection.execute(
                    text(
                        """
                        UPDATE investments
                        SET market_provider = COALESCE(market_provider, 'Twelve Data'),
                            provider_symbol = COALESCE(
                                provider_symbol, :provider_symbol
                            ),
                            exchange = COALESCE(exchange, 'XETRA'),
                            isin = COALESCE(isin, :isin)
                        WHERE UPPER(ticker) = :ticker
                        """
                    ),
                    {
                        "ticker": ticker,
                        "provider_symbol": provider_symbol,
                        "isin": isin,
                    },
                )
        if "categories" in tables:
            category_styles = (
                ("Salary", "income", "green"),
                ("Bonus", "sparkles", "green"),
                ("Property Income", "properties", "green"),
                ("Grocery", "grocery", "amber"),
                ("Indian Grocery", "grocery", "amber"),
                ("Utilities", "utilities", "orange"),
                ("Insurance", "insurance", "teal"),
                ("Transport", "transport", "blue"),
                ("Restaurants", "restaurant", "orange"),
                ("Shopping", "shopping", "blue"),
                ("Healthcare", "health", "red"),
                ("Education", "education", "violet"),
                ("Travel", "travel", "blue"),
                ("Subscriptions", "subscription", "violet"),
                ("Loan Repayment", "loans", "green"),
                ("Pension", "institution", "teal"),
                ("Investment", "investments", "green"),
                ("Tax", "institution", "red"),
                ("Sports", "sports", "blue"),
                ("Other", "category", "slate"),
            )
            for category_name, icon, color in category_styles:
                connection.execute(
                    text(
                        """
                        UPDATE categories
                        SET icon = :icon, color = :color
                        WHERE name = :name
                          AND (icon = 'category' OR icon IS NULL)
                        """
                    ),
                    {"name": category_name, "icon": icon, "color": color},
                )
