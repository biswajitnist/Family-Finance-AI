import { useEffect, useState } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import type {
  Account,
  Category,
  DocumentRecord,
  StatementAudit as Audit,
  Transaction,
} from "../types";
import { ReviewQueue } from "./ReviewQueue";
import { StatementAudit } from "./StatementAudit";

export function DocumentsPanel({
  accounts,
  categories,
  onChanged,
}: {
  accounts: Account[];
  categories: Category[];
  onChanged: () => void;
}) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [message, setMessage] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [reviewRows, setReviewRows] = useState<Transaction[]>([]);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [viewer, setViewer] = useState<DocumentRecord | null>(null);
  const [processingIds, setProcessingIds] = useState<Set<number>>(new Set());
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [forceOcr, setForceOcr] = useState(false);
  const [useLocalAi, setUseLocalAi] = useState(true);
  const [ocrStatus, setOcrStatus] =
    useState<Awaited<ReturnType<typeof api.ocrStatus>> | null>(null);
  const [aiStatus, setAiStatus] =
    useState<Awaited<ReturnType<typeof api.aiStatus>> | null>(null);

  async function load() {
    const records = await api.documents();
    setDocuments(records);
    return records;
  }

  async function loadReview(documentId: number) {
    setBusyAction(`review-${documentId}`);
    setAudit(null);
    setSelectedId(documentId);
    try {
      setReviewRows(await api.documentTransactions(documentId));
    } finally {
      setBusyAction(null);
    }
  }

  async function loadAudit(documentId: number) {
    setBusyAction(`audit-${documentId}`);
    setSelectedId(documentId);
    setReviewRows([]);
    try {
      setAudit(await api.documentAudit(documentId));
    } catch (error) {
      setMessage(
        error instanceof Error
          ? `${error.message}. Click Train / re-audit to build an audit from the extracted text.`
          : "Audit not available",
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function viewDocument(documentId: number) {
    setBusyAction(`view-${documentId}`);
    try {
      setViewer(await api.document(documentId));
    } finally {
      setBusyAction(null);
    }
  }

  async function reaudit(documentId: number) {
    setBusyAction(`reaudit-${documentId}`);
    setProcessingIds(new Set([documentId]));
    setMessage("Re-auditing locally without changing validated transactions.");
    try {
      const result = await api.reauditDocument(documentId, true, useLocalAi);
      setAudit(await api.statementAudit(result.statement_set_id));
      setSelectedId(documentId);
      setReviewRows([]);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Re-audit failed");
    } finally {
      setProcessingIds(new Set());
      setBusyAction(null);
    }
  }

  useEffect(() => {
    void load();
    void Promise.all([api.ocrStatus(), api.aiStatus()]).then(([ocr, ai]) => {
      setOcrStatus(ocr);
      setAiStatus(ai);
    });
  }, []);

  async function upload(formData: FormData) {
    setBusyAction("upload");
    const files = formData
      .getAll("file")
      .filter((file): file is File => file instanceof File && file.size > 0);
    if (!files.length) {
      setBusyAction(null);
      return;
    }
    try {
      const uploaded = [];
      for (const file of files) {
        uploaded.push(
          await api.uploadDocument(
            file,
            String(formData.get("document_type")),
            Number(formData.get("source_account_id")) || null,
          ),
        );
      }
      setSelectedIds(new Set(uploaded.map((document) => document.id)));
      setMessage(
        `${uploaded.length} document(s) stored locally and selected for processing.`,
      );
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setBusyAction(null);
    }
  }

  function startPolling(ids: number[]) {
    return window.setInterval(async () => {
      const current = await Promise.all(
        ids.map((id) => api.document(id).catch(() => null)),
      );
      const updates = new Map(
        current
          .filter((item): item is DocumentRecord => item !== null)
          .map((item) => [item.id, item]),
      );
      setDocuments((items) =>
        items.map((item) => updates.get(item.id) ?? item),
      );
    }, 600);
  }

  async function process(id: number) {
    setBusyAction(`process-${id}`);
    setProcessingIds(new Set([id]));
    setSelectedId(id);
    setMessage("Processing started locally. Follow the stages below.");
    const poll = startPolling([id]);
    try {
      const result = await api.processDocument(id, forceOcr, useLocalAi);
      const isInvestment = result.record_type === "investment";
      setMessage(
        isInvestment
          ? `${result.investments_created ?? 0} holding(s) added to Investments. ${
              result.message ?? ""
            }`
          : `${result.transactions_created ?? 0} transaction(s) created for review. ${
              result.message ?? ""
            }`,
      );
      await load();
      if (!isInvestment) setAudit(await api.statementAudit(result.statement_set_id));
      else {
        setSelectedId(null);
        setReviewRows([]);
      }
      onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Processing failed");
      await load();
    } finally {
      window.clearInterval(poll);
      setProcessingIds(new Set());
      setBusyAction(null);
    }
  }

  async function processSelected() {
    const ids = [...selectedIds];
    if (!ids.length) return;
    setBusyAction("process-selected");
    setProcessingIds(new Set(ids));
    setMessage(
      `Processing ${ids.length} document(s) locally in sequence. Follow each file below.`,
    );
    const poll = startPolling(ids);
    try {
      const result = await api.processDocuments(ids, forceOcr, useLocalAi);
      setMessage(
        `${result.completed} of ${result.requested} document(s) processed. ` +
          `${result.transactions_created} transaction row(s) and ` +
          `${result.investments_created} investment holding(s) created.` +
          (result.failed ? ` ${result.failed} file(s) need attention.` : ""),
      );
      await load();
      const firstReview = result.results.find(
        (item) =>
          ["needs_review", "extraction_completed"].includes(item.status) &&
          item.record_type === "transaction",
      );
      if (firstReview) {
        setSelectedId(firstReview.document_id);
        setReviewRows([]);
        setAudit(await api.statementAudit(result.statement_set_id));
      }
      setSelectedIds(new Set());
      onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Batch processing failed");
      await load();
    } finally {
      window.clearInterval(poll);
      setProcessingIds(new Set());
      setBusyAction(null);
    }
  }

  async function deleteDocument(document: DocumentRecord) {
    const confirmed = await confirmAction({
      title: "Delete document?",
      message: `Delete "${document.file_name}" from Ledger Local? Existing confirmed transactions are kept, but detached from this document.`,
      confirmLabel: "Delete document",
    });
    if (!confirmed) return;
    setBusyAction(`delete-${document.id}`);
    try {
      await api.deleteDocument(document.id);
      setMessage(`${document.file_name} deleted.`);
      if (selectedId === document.id) {
        setSelectedId(null);
        setAudit(null);
        setReviewRows([]);
      }
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Delete failed");
    } finally {
      setBusyAction(null);
    }
  }

  const selectableDocuments = documents.filter((document) =>
    ["uploaded", "extraction_completed", "failed"].includes(document.status),
  );
  const allSelectableSelected =
    selectableDocuments.length > 0 &&
    selectableDocuments.every((document) => selectedIds.has(document.id));

  const canAudit = (document: DocumentRecord) =>
    document.document_type !== "investment_statement" &&
    ["needs_review", "validated", "extraction_completed", "failed"].includes(
      document.status,
    );

  return (
    <>
    {audit && (
      <StatementAudit
        audit={audit}
        onChanged={(next) => {
          setAudit(next);
          onChanged();
        }}
      />
    )}
    <section className="module-layout">
      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Local document pipeline</p>
            <h2>Upload financial documents</h2>
            <p className="section-copy">
              PDF, CSV, Excel, image, screenshot, and text files remain on this
              machine.
            </p>
          </div>
        </div>
        <form action={upload} className="resource-form">
          <label>
            Document type
            <select name="document_type" defaultValue="bank_statement">
              {[
                "bank_statement",
                "credit_card_statement",
                "salary_slip",
                "insurance_bill",
                "utility_bill",
                "investment_statement",
                "loan_statement",
                "property_rent_statement",
                "tax_document",
                "other",
              ].map((type) => (
                <option key={type} value={type}>
                  {type.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Source account
            <select name="source_account_id">
              <option value="">None</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            File
            <input
              className="ledger-file-input"
              name="file"
              type="file"
              accept=".pdf,.csv,.xlsx,.xls,.jpg,.jpeg,.png,.txt"
              multiple
              required
            />
          </label>
          <button disabled={busyAction === "upload"} type="submit">
            {busyAction === "upload" ? "Storing..." : "Store document"}
          </button>
          {message && <span className="form-message">{message}</span>}
        </form>
        <div className="runtime-grid">
          <div className={`runtime-card ${ocrStatus?.available ? "ready" : ""}`}>
            <strong>Tesseract OCR</strong>
            <span>{ocrStatus?.available ? "Ready" : "Not installed"}</span>
            <small>
              {ocrStatus?.version ?? "Install Tesseract locally"} ·{" "}
              {ocrStatus?.dpi ?? 300} DPI
            </small>
            {!!ocrStatus?.missing_languages.length && (
              <small>
                Missing language packs: {ocrStatus.missing_languages.join(", ")}
              </small>
            )}
          </div>
          <div
            className={`runtime-card ${
              aiStatus?.available && aiStatus.model_installed ? "ready" : ""
            }`}
          >
            <strong>Ollama extraction</strong>
            <span>
              {aiStatus?.available
                ? aiStatus.model_installed
                  ? "Ready"
                  : "Model missing"
                : "Service offline"}
            </span>
            <small>{aiStatus?.model ?? "qwen2.5:7b"} · local only</small>
          </div>
        </div>
        <div className="processing-options">
          <label>
            <input
              type="checkbox"
              checked={forceOcr}
              onChange={(event) => setForceOcr(event.target.checked)}
            />
            Force OCR even when PDF text exists
          </label>
          <label>
            <input
              type="checkbox"
              checked={useLocalAi}
              onChange={(event) => setUseLocalAi(event.target.checked)}
            />
            Use Ollama when deterministic extraction finds no rows
          </label>
        </div>
      </article>
      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Processing status</p>
            <h2>Document library</h2>
          </div>
          <span className="count-pill">{documents.length}</span>
        </div>
        {!!selectableDocuments.length && (
          <div className="document-batch-toolbar">
            <label>
              <input
                checked={allSelectableSelected}
                onChange={(event) =>
                  setSelectedIds(
                    event.target.checked
                      ? new Set(selectableDocuments.map((item) => item.id))
                      : new Set(),
                  )
                }
                type="checkbox"
              />
              Select all ready documents
            </label>
            <span>{selectedIds.size} selected</span>
            <button
              disabled={!selectedIds.size || processingIds.size > 0}
              onClick={processSelected}
              type="button"
            >
              {busyAction === "process-selected" || processingIds.size > 1
                ? `Processing ${processingIds.size} files...`
                : "Process selected"}
            </button>
          </div>
        )}
        <div className="record-list">
          {documents.map((document) => (
            <div
              className={`record-card ${
                selectedId === document.id ? "selected-record" : ""
              }`}
              key={document.id}
            >
              <label className="document-select">
                <input
                  aria-label={`Select ${document.file_name}`}
                  checked={selectedIds.has(document.id)}
                  disabled={
                    !["uploaded", "extraction_completed", "failed"].includes(
                      document.status,
                    ) || processingIds.size > 0
                  }
                  onChange={(event) =>
                    setSelectedIds((current) => {
                      const next = new Set(current);
                      if (event.target.checked) next.add(document.id);
                      else next.delete(document.id);
                      return next;
                    })
                  }
                  type="checkbox"
                />
              </label>
              <div className="document-record-info">
                <strong>{document.file_name}</strong>
                <small>
                  {document.document_type.replaceAll("_", " ")} ·{" "}
                  {document.status.replaceAll("_", " ")}
                </small>
                {document.status !== "extraction_completed" &&
                  document.processing_message && (
                    <small>{document.processing_message}</small>
                  )}
                {document.status === "extraction_completed" && (
                  <div className="document-extraction-reason">
                    <strong>Why no transactions?</strong>
                    <span>
                      {document.processing_message ??
                        "No transaction rows matched the known extraction patterns."}
                    </span>
                  </div>
                )}
                <div className="document-progress">
                  <span style={{ width: `${document.processing_progress}%` }} />
                </div>
                {document.processing_error && (
                  <small className="danger-text">{document.processing_error}</small>
                )}
              </div>
              <div className="inline-actions">
                <button
                  className="secondary-button"
                  disabled={!!busyAction || processingIds.size > 0}
                  onClick={() => viewDocument(document.id)}
                  type="button"
                >
                  {busyAction === `view-${document.id}` ? "Opening..." : "View"}
                </button>
                <button
                  className="secondary-button"
                  disabled={!!busyAction || processingIds.size > 0}
                  onClick={() => process(document.id)}
                >
                  {processingIds.has(document.id) ? "Processing..." : "Process"}
                </button>
                {canAudit(document) && (
                  <>
                    <button
                      className="secondary-button"
                      disabled={!!busyAction || processingIds.size > 0}
                      onClick={() => loadAudit(document.id)}
                    >
                      {busyAction === `audit-${document.id}`
                        ? "Loading..."
                        : "Audit / reason"}
                    </button>
                    <button
                      className="secondary-button"
                      disabled={!!busyAction || processingIds.size > 0}
                      onClick={() => reaudit(document.id)}
                    >
                      {busyAction === `reaudit-${document.id}`
                        ? "Re-auditing..."
                        : "Train / re-audit"}
                    </button>
                  </>
                )}
                <button
                  className="text-button danger"
                  disabled={!!busyAction || processingIds.size > 0}
                  onClick={() => deleteDocument(document)}
                >
                  {busyAction === `delete-${document.id}` ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          ))}
          {!documents.length && (
            <p className="empty-state">No documents uploaded yet.</p>
          )}
        </div>
      </article>
    </section>
    {viewer && (
      <DocumentViewer document={viewer} onClose={() => setViewer(null)} />
    )}
    {selectedId && !audit && (
      <article className="panel section-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Human review before posting</p>
            <h2>Extracted transactions</h2>
            <p className="section-copy">
              Adjust every field, reject incorrect rows, then confirm. Pending
              rows are excluded from the transaction database totals and reports.
            </p>
          </div>
          <span className="count-pill">
            {reviewRows.filter((item) => !item.is_validated).length}
          </span>
        </div>
        <ReviewQueue
          transactions={reviewRows.filter((item) => !item.is_validated)}
          accounts={accounts}
          categories={categories}
          documentId={selectedId}
          onChanged={async () => {
            await loadReview(selectedId);
            await load();
            onChanged();
          }}
        />
        {!!reviewRows.length &&
          reviewRows.every((item) => item.is_validated || item.is_duplicate) && (
            <p className="success-message">
              Review complete. Confirmed rows are now available under Transactions.
            </p>
          )}
      </article>
    )}
    </>
  );
}

function DocumentViewer({
  document,
  onClose,
}: {
  document: DocumentRecord;
  onClose: () => void;
}) {
  const originalUrl = api.documentFileUrl(document.id);
  const [page, setPage] = useState(1);
  const pageCount = document.page_count ?? 1;
  const previewUrl = api.documentPreviewUrl(document.id, page);
  const isImage = ["png", "jpg", "jpeg"].includes(document.file_type);
  const isPdf = document.file_type === "pdf";
  const isTextLike = ["txt", "csv"].includes(document.file_type);
  useEffect(() => {
    setPage(1);
  }, [document.id]);
  return (
    <div
      className="document-viewer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <article className="document-viewer panel" role="dialog" aria-modal="true">
        <header>
          <div>
            <p className="eyebrow">Uploaded document</p>
            <h2>{document.file_name}</h2>
            <p>
              {document.document_type.replaceAll("_", " ")} ·{" "}
              {document.status.replaceAll("_", " ")}
              {isPdf && pageCount > 1 ? ` · page ${page} of ${pageCount}` : ""}
            </p>
          </div>
          <div className="inline-actions">
            {isPdf && pageCount > 1 && (
              <div className="document-page-controls">
                <button
                  className="secondary-button"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  Previous
                </button>
                <span>{page} / {pageCount}</span>
                <button
                  className="secondary-button"
                  disabled={page >= pageCount}
                  onClick={() =>
                    setPage((current) => Math.min(pageCount, current + 1))
                  }
                  type="button"
                >
                  Next
                </button>
              </div>
            )}
            <a
              className="secondary-button"
              download
              href={originalUrl}
              rel="noreferrer"
              target="_blank"
            >
              Download original
            </a>
            <button className="text-button" onClick={onClose} type="button">
              Close
            </button>
          </div>
        </header>
        <div className="document-viewer-body">
          {isImage ? (
            <img alt={document.file_name} src={previewUrl} />
          ) : isPdf ? (
            <img alt={`${document.file_name} preview page 1`} src={previewUrl} />
          ) : isTextLike && document.extracted_text ? (
            <pre>{document.extracted_text}</pre>
          ) : (
            <div className="empty-state">
              Preview is limited for this file type. Use “Download original” to save it.
            </div>
          )}
        </div>
      </article>
    </div>
  );
}
