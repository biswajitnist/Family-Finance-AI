# User Guide

1. Create accounts and enter current balances.
2. Add transactions manually or upload a statement.
3. Process uploaded documents locally.
4. Review extracted rows, edit errors, mark duplicates, and approve them.
5. Add rules for recurring vendors and preferred categories.
6. Maintain investments, loans, properties, and insurance policies.
7. Generate PDF, Excel, or CSV reports for the required period.
8. Ask Finance Chat about validated spending, income, debt, net worth, or
   processed documents.
9. Download a database backup from the Reports workspace.

Scanned image OCR requires the Tesseract executable. If it is not installed,
the document remains stored locally and displays a processing error without
losing the original file.

## Help Agent

Use the floating Help button in the lower-right corner from any page. The Help
Agent routes questions to local sources:

- App usage and navigation come from markdown help guides in `docs`.
- Financial totals come only from validated, non-duplicate SQLite records.
- Document questions search processed uploaded text and the local ChromaDB
  index.
- Report requests generate a PDF, Excel, or CSV file from validated records.
- Troubleshooting checks local guides and database workflow status.

Every answer shows its source basis and lists missing data when the available
local records are insufficient. The agent never sends application data to a
cloud model. Ollama runs on the configured loopback address.

## Statement Review

Select an account before uploading a statement. After processing, choose
**Review rows** in the document library. Correct dates, vendor, description,
amount, type, category, account, and duplicate status. Reject incorrect rows or
select rows and confirm them. Pending rows are excluded from dashboards,
reports, budgets, and finance answers until confirmation.

## Budgets

Open **Budgets**, select a month, and add one spending limit per category.
Budget usage includes only validated, non-duplicate debit transactions for that
month. Pending statement rows do not affect budget totals.

## Rules

Rules automatically classify familiar merchants and payment descriptions.
Choose **Merchant name contains** or **Description contains**, enter the text to
find, and select the category or income/expense type to apply. Use **Apply all
rules** for existing transactions that are still waiting for review. See
`rules-guide.md` for examples and troubleshooting.
