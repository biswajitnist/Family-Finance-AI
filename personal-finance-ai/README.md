# Ledger Local

Ledger Local is a local-first personal finance application built with FastAPI,
SQLite, React, and TypeScript. The database is the source of truth. Imported or
AI-classified transactions remain outside calculations until the user validates
them.

## Features

- Dashboard with income, expenses, savings rate, cash flow, net worth, debt,
  investments, property value, category spending, and monthly trends
- Bank, credit card, cash, investment, loan, pension, and property accounts
- Manual transactions and deterministic CSV import
- Local PDF, CSV, Excel, image, screenshot, and text document storage
- PDF text extraction, scanned document OCR, Excel/CSV parsing, and statement
  line extraction
- Editable review queue, duplicate flags, bulk approval, and provenance
- Vendor, keyword, amount, account, IBAN, and recurring-payment rules
- Optional local Ollama classification after deterministic rules
- Investment, loan, property, and insurance modules
- Monthly, yearly, tax, investment, debt, property, and family-protection
  reports in PDF, Excel, or CSV
- Database-backed finance chat with calculation basis, source records,
  confidence, and missing-data warnings
- Local SQLite backup download

No cloud AI, analytics, telemetry, or remote file storage is enabled.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- npm 10 or newer
- [Tesseract OCR](https://tesseract-ocr.github.io/) for scanned images and PDFs
- [Ollama](https://ollama.com/) for local extraction and classification

## Setup

```bash
chmod +x scripts/*.sh
./scripts/setup_dev.sh
```

Start the backend:

```bash
./scripts/run_backend.sh
```

Start the frontend in another terminal:

```bash
./scripts/run_frontend.sh
```

Open `http://localhost:5173`. Interactive API documentation is at
`http://localhost:8000/docs`.

Existing Phase 1 databases are upgraded using additive SQLite migrations when
the backend starts.

## Installable macOS Application

An Apple Silicon macOS application can be built without including any current
database, documents, credentials, reports, or cached market data:

```bash
.venv/bin/pip install -r packaging/requirements-build.txt
./scripts/build_macos_app.sh
```

The distributable ZIP is created at:

```text
release/Ledger-Local-macOS-arm64.zip
```

Each recipient receives a clean database. Their private runtime data is stored
under `~/Library/Application Support/Ledger Local/`. See
`docs/distribution-guide.md` for installation, optional OCR/Ollama setup, and
code-signing notes.

## Document Workflow

```text
Upload locally
-> extract text or OCR
-> deterministic transaction parsing
-> rules
-> optional local Ollama classification
-> editable review queue
-> user validation
-> dashboard, reports, and chat
```

CSV/Excel transaction columns:

```text
date,vendor,amount,type
```

Optional columns:

```text
booking_date,description,currency,category,payment_method,reference_number,iban
```

Text-based statements can also use rows such as:

```text
2026-06-03 REWE Weekly groceries -54.32 EUR
```

## Local AI

Ollama is enabled for local use by default:

```env
FINANCE_OLLAMA_ENABLED=true
FINANCE_OLLAMA_MODEL=qwen2.5:3b
```

Ledger Local first applies deterministic parsing and rules. Ollama is used as a
fallback to convert difficult OCR text into structured transactions and to
classify uncategorized rows. It runs only on the configured loopback URL.
Numeric chat answers always use database queries.

On macOS:

```bash
brew install tesseract tesseract-lang
ollama serve
ollama pull qwen2.5:3b
```

The same checks are available through:

```bash
chmod +x scripts/setup_local_ai.sh
./scripts/setup_local_ai.sh
```

## Tests

```bash
cd backend
../.venv/bin/pytest
../.venv/bin/ruff check .

cd ../frontend
npm run build
```

## Storage

- SQLite database: configured by `FINANCE_DATABASE_URL`
- Original files: `data/uploads`
- Extracted text: `data/processed`
- Generated reports and backups: `data/reports`

File paths are never returned to the frontend.
