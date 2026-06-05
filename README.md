# Family Finance AI

Private local finance tracker for uploading bank statements, extracting transactions with OCR and a local Ollama model, reviewing the extracted rows, and saving clean data into SQLite.

Everything runs on your machine. Files, OCR text, AI extraction results, and finance data stay local.

## Current Architecture

```text
Upload PDF / image / CSV / Excel
        |
        v
Local text extraction
  - PDF text extraction with pdf-parse
  - Image OCR with Tesseract.js
  - CSV / Excel text conversion
        |
        v
Local Ollama model
  - Extracts structured transactions
  - Classifies income / expense
  - Suggests category, subcategory, confidence
        |
        v
Review Import screen
  - Edit date, merchant, category, amount, description
  - Include / exclude rows
  - Remove bad rows
        |
        v
SQLite local database
  - Final transactions
  - Upload history
  - Merchant rules
  - AI insights
        |
        v
Dashboard and local AI assistant
```

## Features

- Local-first finance data storage with SQLite.
- Upload bank statements and transaction files.
- Supports PDF, CSV, Excel, PNG, JPG, JPEG, WEBP, BMP, TIFF, and TXT.
- OCR for scanned images and screenshots using Tesseract.js.
- PDF text extraction using pdf-parse.
- Local Ollama extraction and finance Q&A.
- Ollama model selector in the UI.
- Large statement chunking for better local model handling.
- Review-before-save workflow with a temporary pending transaction table.
- Manual correction of OCR or AI extraction issues before saving.
- Category dropdown editing for both pending and saved transactions.
- Merchant learning rules for repeat vendors.
- Duplicate protection using transaction fingerprints.
- Income, expense, and net cashflow summary.
- Category summary.
- Grocery and Indian staples shop analysis.
- Simple forecast based on historical monthly net cashflow.
- Basic anomaly API for category spend changes.

## Technology Stack

- Node.js
- Express
- JavaScript
- SQLite
- sqlite3
- Multer
- pdf-parse
- Tesseract.js
- xlsx
- Ollama

Chart.js is shown in the target architecture, but the current UI uses metric cards and tables. Chart.js visual dashboards are not implemented yet.

## Install

```bash
npm install
```

## Run

Start the application:

```bash
npm start
```

Open:

```text
http://localhost:3000
```

Development mode with automatic server restart:

```bash
npm run dev
```

## Ollama Setup

Install and start Ollama, then pull a model:

```bash
ollama pull llama3.2
ollama serve
```

The app checks Ollama at:

```text
http://127.0.0.1:11434
```

Default model:

```text
llama3.2
```

Optional server-side model override:

```bash
OLLAMA_MODEL=mistral npm start
```

You can also choose from locally installed Ollama models in the app header.

## Import Workflow

1. Start the app and confirm Ollama status is OK.
2. Choose an Ollama model.
3. Upload a statement or transaction file.
4. Select the statement year if the document uses dates without a year.
5. Leave `Save OCR fallback if AI fails` unchecked for safer imports.
6. Click `Scan -> AI -> Save`.
7. The app extracts local text from the file.
8. The extracted text is sent to your local Ollama model.
9. AI results are staged into `pending_transactions`.
10. Review rows in the `Review Import` table.
11. Edit date, merchant, category, amount, or description if needed.
12. Uncheck or remove bad rows.
13. Click `Save Selected`.
14. Selected rows are saved into the final `transactions` table.

## OCR Fallback

If Ollama fails or times out, the app can use a simpler OCR fallback parser.

By default, fallback rows are not saved or staged because fallback quality can be lower than AI extraction.

When `Save OCR fallback if AI fails` is checked:

- fallback rows are staged into the review table;
- you must inspect and correct them manually;
- they are only saved permanently after `Save Selected`.

This protects the final transaction table from bad extraction results.

## Review Import Screen

The review screen is the human validation step from the architecture.

You can:

- edit transaction date;
- edit merchant name;
- choose category from a dropdown;
- edit amount and fix debit or credit signs;
- edit description;
- include or exclude rows;
- remove unwanted rows;
- save selected rows into final transactions;
- discard all pending review rows.

## Categories

Current categories:

```text
Income
Housing
Utilities
Groceries
Indian Staples
Household
Family Food
Family Activity
Kids
Transport
Insurance
Pension
Investments
Loan / Banking
Telecom
India Transfer
Shopping
Health
Subscriptions
Misc / Review
Uncategorized
```

## Merchant Rules

Merchant rules help clean and categorize future imports.

Example:

```text
Pattern: VAGHANI
Clean name: GbR Vaghani Limbachiya
Category: Indian Staples
Subcategory: Indian Grocery
```

When a future transaction merchant contains the pattern, the app applies the clean merchant name and category automatically.

## Local Database

SQLite database file:

```text
data/finance.db
```

Main tables:

- `uploads`: uploaded file history, extracted text, and AI JSON.
- `pending_transactions`: temporary review rows before final save.
- `transactions`: final approved transactions.
- `merchant_rules`: learned merchant/category rules.
- `monthly_goals`: planned budget/goal storage.
- `ai_insights`: saved local AI answers.

## API Overview

Status:

```text
GET /api/status
```

Upload and stage transactions:

```text
POST /api/upload
```

Pending review:

```text
GET /api/pending
PATCH /api/pending/:id
DELETE /api/pending/:id
POST /api/pending/commit
POST /api/pending/discard
```

Final transactions:

```text
GET /api/transactions
PATCH /api/transactions/:id
DELETE /api/transactions/:id
```

Analytics:

```text
GET /api/summary
GET /api/forecast
GET /api/anomalies
POST /api/ask
```

Rules:

```text
GET /api/rules
POST /api/rules
```

Uploads:

```text
DELETE /api/uploads/:id
```

## Data Privacy

- No cloud database is used.
- No hosted AI API is used by the app.
- OCR runs locally.
- Ollama runs locally.
- SQLite stores data locally.
- Uploaded files are stored locally in the project `uploads` folder.
- Extracted text and AI JSON are stored locally in SQLite.

The app depends on your local Ollama installation. If Ollama is not running, AI extraction and AI assistant responses will be unavailable.

## Implemented vs Target Architecture

Implemented:

- upload and ingest;
- OCR/text extraction;
- local Ollama structured extraction;
- review-before-save validation;
- local SQLite storage;
- transaction category editing;
- merchant rules;
- income, expense, net cashflow summary;
- category and shop summaries;
- simple forecast;
- local AI finance assistant.

Partially implemented:

- recurring payment detection, currently covered only indirectly by merchant rules;
- financial health, currently limited to income, expenses, net, forecast, and category summaries;
- dashboards, currently table/card based rather than Chart.js charts.

Not implemented yet:

- scanner hardware integration;
- full receipt/invoice-specific extraction;
- investment portfolio tracking;
- asset allocation;
- net worth tracking;
- liabilities tracking;
- goal tracking UI;
- Chart.js visual dashboards.

## Resetting Data

To start fresh, stop the app and back up or remove:

```text
data/finance.db
```

Deleting this file removes uploads, pending transactions, final transactions, rules, goals, and AI insights. The app recreates the database tables on the next start.

For safer resets, make a copy of the database first.
