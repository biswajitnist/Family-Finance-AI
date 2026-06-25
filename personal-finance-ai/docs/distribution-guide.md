# Distributing Ledger Local

Ledger Local can be packaged as a clean macOS application. The package includes
the application code and default configuration only. It does not include the
developer's database, uploaded statements, extracted text, reports, ChromaDB
index, market-data credentials, or API keys.

## Build

From the project directory:

```bash
.venv/bin/pip install -r packaging/requirements-build.txt
chmod +x scripts/build_macos_app.sh
./scripts/build_macos_app.sh
```

The build creates:

```text
release/Ledger Local.app
release/Ledger-Local-macOS-arm64.zip
```

The ZIP file can be given to another user with an Apple Silicon Mac.

## Recipient Installation

1. Unzip `Ledger-Local-macOS-arm64.zip`.
2. Move `Ledger Local.app` to Applications.
3. Open the application.
4. For an unsigned test build, macOS may require Control-clicking the
   application and choosing **Open** the first time.

Ledger Local opens its interface in the user's default browser while the local
application process runs in the background. All application APIs bind only to
`127.0.0.1`.

## Fresh User Data

Every recipient starts with a new database and default categories. Runtime data
is created under:

```text
~/Library/Application Support/Ledger Local/
```

This directory contains the recipient's:

- SQLite database
- Uploaded documents
- Extracted document text
- Reports
- ChromaDB data
- Encrypted market-provider credentials

Deleting the application does not automatically delete this user data.

## Optional Local Integrations

Core finance, budgeting, transaction, report, and database functions are
packaged with the application.

For OCR, the recipient should install Tesseract:

```bash
brew install tesseract tesseract-lang
```

For local AI, the recipient should install Ollama and the configured model:

```bash
brew install ollama
ollama serve
ollama pull qwen2.5:3b
```

The application remains usable when either optional integration is unavailable.

## Security and Release Notes

- No current user data is included by the build script.
- No `.env` file is packaged.
- No API keys are packaged.
- The local server is not exposed to the network.
- The current package is unsigned and not notarized.
- Public distribution should use an Apple Developer ID certificate, hardened
  runtime signing, notarization, and a tested universal or Intel-specific build.
