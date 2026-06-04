# Biswajit Finance Tracker v3

Local private finance tracker with:

- SQLite database
- Upload bank statements, CSV/Excel, PDFs, screenshots
- OCR for image screenshots
- Ollama AI extraction and categorization
- Merchant learning rules
- Grocery/Indian staples analysis
- Monthly cashflow, forecasting, anomaly detection
- Local privacy: your files stay on your machine

## Install

```bash
npm install
npm start
```

Open:

```text
http://localhost:3000
```

## Ollama

Install and start Ollama, then pull a model:

```bash
ollama pull llama3.2
ollama serve
```

Optional model override:

```bash
OLLAMA_MODEL=mistral npm start
```

## Workflow

1. Upload a bank PDF, CSV, Excel, or screenshot.
2. OCR/text extraction runs locally.
3. The extracted text is sent to your local Ollama model.
4. AI returns structured transactions.
5. The app saves them into SQLite.
6. Dashboard and analytics update automatically.

## Data

SQLite file:

```text
data/finance.db
```

Delete it only if you want to reset the app.
