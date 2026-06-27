import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import type { StatementAudit as Audit, StatementCandidate } from "../types";
import { DateField } from "./DateField";

type Filter = "all" | "needs_review" | "skipped" | "overlap";

export function StatementAudit({
  audit,
  onChanged,
}: {
  audit: Audit;
  onChanged: (audit: Audit) => void;
}) {
  const auditRef = useRef<HTMLElement | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState(audit.candidates[0]?.id ?? null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const selected =
    audit.candidates.find((candidate) => candidate.id === selectedId) ??
    audit.candidates[0];
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!selected) return;
    setDraft({
      transaction_date: selected.transaction_date ?? "",
      vendor: selected.vendor ?? "",
      amount: selected.amount ?? "",
      currency: selected.currency ?? "EUR",
      transaction_type: selected.transaction_type ?? "debit",
    });
  }, [selected?.id]);

  useEffect(() => {
    auditRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [audit.id]);

  const candidates = useMemo(
    () =>
      audit.candidates.filter((candidate) =>
        filter === "all" ? true : candidate.status === filter,
      ),
    [audit.candidates, filter],
  );
  const document = audit.documents.find(
    (item) => item.id === selected?.document_id,
  );
  const bbox = selected?.source_line?.bbox;

  async function resolve(resolution: string) {
    if (!selected) return;
    setSaving(true);
    setMessage("");
    try {
      const next = await api.updateStatementCandidate(selected.id, {
        ...draft,
        resolution,
      });
      onChanged(next);
      setMessage("Audit decision saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function saveCheckpoint(formData: FormData) {
    const value = (name: string) => String(formData.get(name) ?? "").trim();
    setSaving(true);
    setMessage("");
    try {
      const next = await api.updateStatementCheckpoint(audit.id, {
        expected_transaction_count: value("expected_transaction_count")
          ? Number(value("expected_transaction_count"))
          : null,
        expected_debit_total: value("expected_debit_total") || null,
        expected_credit_total: value("expected_credit_total") || null,
      });
      onChanged(next);
      setMessage("Checkpoint updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save checkpoint");
    } finally {
      setSaving(false);
    }
  }

  async function useExtractedCheckpoint() {
    setSaving(true);
    setMessage("");
    try {
      const next = await api.updateStatementCheckpoint(audit.id, {
        expected_transaction_count: audit.extracted_count,
        expected_debit_total: audit.debit_total,
        expected_credit_total: audit.credit_total,
      });
      onChanged(next);
      setMessage("Checkpoint filled from extracted totals.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update checkpoint");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="panel section-panel statement-audit" ref={auditRef}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Verifiable extraction</p>
          <h2>Statement Audit</h2>
          <p className="section-copy">
            Every candidate line is accounted for. Resolve warnings and match a
            statement checkpoint before posting transactions.
          </p>
          <p className="section-copy">
            Extracted totals can fill the checkpoint for you; edit only when the
            statement header says a different expected count or total.
          </p>
        </div>
        <span className={`audit-status ${audit.completeness_status}`}>
          {audit.completeness_status.replaceAll("_", " ")}
        </span>
      </div>

      <div className="audit-summary">
        <span><strong>{audit.candidate_count}</strong> candidate lines</span>
        <span><strong>{audit.extracted_count}</strong> transactions</span>
        <span><strong>{audit.skipped_count}</strong> skipped</span>
        <span><strong>{audit.overlap_count}</strong> overlaps</span>
        <span><strong>{audit.low_confidence_count}</strong> low confidence</span>
        <span><strong>{audit.debit_total}</strong> debits</span>
        <span><strong>{audit.credit_total}</strong> credits</span>
      </div>

      <div className="audit-filters">
        {(["all", "needs_review", "skipped", "overlap"] as Filter[]).map(
          (value) => (
            <button
              className={filter === value ? "active" : ""}
              key={value}
              onClick={() => setFilter(value)}
              type="button"
            >
              {value.replaceAll("_", " ")}
            </button>
          ),
        )}
      </div>

      <div className="audit-training-note">
        <strong>Training mode</strong>
        <span>
          Use skipped or low-confidence lines to teach this statement layout:
          select a line, fill the missing fields, then choose Accept changes.
          Possible existing transactions are shown before you accept.
        </span>
      </div>

      <div className="audit-workspace">
        <div className="audit-source">
          <div className="audit-preview">
            {document && ["pdf", "png", "jpg", "jpeg"].includes(document.file_type) ? (
              <img
                alt={`Source ${document.file_name}`}
                src={api.absoluteApiUrl(
                  `${document.preview_url}?page=${selected?.source_line?.page_number ?? 1}`,
                )}
              />
            ) : (
              <pre>{selected?.source_line?.raw_text ?? selected?.raw_text}</pre>
            )}
            {bbox && bbox.length === 4 && (
              <span
                className="source-highlight"
                style={{
                  left: `${bbox[0]}%`,
                  top: `${bbox[1]}%`,
                  width: `${bbox[2]}%`,
                  height: `${bbox[3]}%`,
                }}
              />
            )}
          </div>
          <small>{document?.file_name ?? "Select a candidate"}</small>
        </div>

        <div className="audit-review">
          <div className="audit-candidate-list">
            {candidates.map((candidate) => (
              <button
                className={candidate.id === selected?.id ? "selected" : ""}
                key={candidate.id}
                onClick={() => setSelectedId(candidate.id)}
                type="button"
              >
                <span className={`candidate-status ${candidate.status}`}>
                  {candidate.status.replaceAll("_", " ")}
                </span>
                {!!candidate.duplicate_matches.length && (
                  <span className="candidate-duplicate-flag">
                    Possible duplicate
                  </span>
                )}
                <strong>{candidate.vendor || "Unparsed line"}</strong>
                <small>{candidate.raw_text}</small>
              </button>
            ))}
            {!candidates.length && (
              <p className="empty-state">
                No matching lines. If this statement still has transactions,
                re-audit with OCR enabled or upload a clearer export/PDF.
              </p>
            )}
          </div>

          {selected && (
            <CandidateEditor
              candidate={selected}
              draft={draft}
              onDraft={setDraft}
              onResolve={resolve}
              saving={saving}
            />
          )}
        </div>
      </div>

      <div className="audit-footer">
        <form
          action={saveCheckpoint}
          className="checkpoint-form"
          key={`${audit.expected_transaction_count ?? ""}-${audit.expected_debit_total ?? ""}-${audit.expected_credit_total ?? ""}`}
        >
          <label>
            Expected count
            <input
              defaultValue={audit.expected_transaction_count ?? ""}
              min="0"
              name="expected_transaction_count"
              type="number"
            />
          </label>
          <label>
            Expected debits
            <input
              defaultValue={audit.expected_debit_total ?? ""}
              name="expected_debit_total"
              step="0.01"
              type="number"
            />
          </label>
          <label>
            Expected credits
            <input
              defaultValue={audit.expected_credit_total ?? ""}
              name="expected_credit_total"
              step="0.01"
              type="number"
            />
          </label>
          <button className="secondary-button" disabled={saving} type="submit">
            {saving ? "Updating..." : "Update checkpoint"}
          </button>
          <button
            className="secondary-button"
            disabled={saving}
            onClick={useExtractedCheckpoint}
            type="button"
          >
            Use extracted totals
          </button>
        </form>
        <div className="audit-checklist">
          <strong>Final checklist</strong>
          {audit.confirmation_blockers.length ? (
            audit.confirmation_blockers.map((blocker) => (
              <span className="blocked" key={blocker}>× {blocker}</span>
            ))
          ) : (
            <span className="passed">✓ All critical checks passed</span>
          )}
          <button
            disabled={!audit.can_confirm || saving}
            onClick={async () => {
              setSaving(true);
              try {
                const result = await api.confirmStatementSet(audit.id);
                setMessage(`${result.confirmed} transactions confirmed.`);
                onChanged(await api.statementAudit(audit.id));
              } finally {
                setSaving(false);
              }
            }}
            type="button"
          >
            Confirm statement
          </button>
        </div>
      </div>
      {message && <p className="form-message">{message}</p>}
    </article>
  );
}

function CandidateEditor({
  candidate,
  draft,
  onDraft,
  onResolve,
  saving,
}: {
  candidate: StatementCandidate;
  draft: Record<string, string>;
  onDraft: (draft: Record<string, string>) => void;
  onResolve: (resolution: string) => void;
  saving: boolean;
}) {
  const field = (name: string, value: string) =>
    onDraft({ ...draft, [name]: value });
  const [openMatchId, setOpenMatchId] = useState<number | null>(
    candidate.duplicate_matches[0]?.id ?? null,
  );
  useEffect(() => {
    setOpenMatchId(candidate.duplicate_matches[0]?.id ?? null);
  }, [candidate.id, candidate.duplicate_matches]);
  const openMatch =
    candidate.duplicate_matches.find((match) => match.id === openMatchId) ??
    candidate.duplicate_matches[0];
  return (
    <div className="candidate-editor">
      <div>
        <span className={`candidate-status ${candidate.status}`}>
          {candidate.status.replaceAll("_", " ")}
        </span>
        {candidate.source_line?.confidence && (
          <small>OCR confidence {candidate.source_line.confidence}</small>
        )}
      </div>
      <blockquote>{candidate.raw_text}</blockquote>
      {candidate.warnings.map((warning) => (
        <p className="audit-warning" key={warning}>{warning}</p>
      ))}
      {candidate.skip_reason && <p className="audit-warning">{candidate.skip_reason}</p>}
      {!!candidate.duplicate_matches.length && (
        <div className="audit-duplicate-panel">
          <div>
            <strong>Possible existing transaction</strong>
            <span>
              Same date and amount. Merchant similarity{" "}
              {Math.round(candidate.duplicate_matches[0].merchant_similarity * 100)}%.
            </span>
          </div>
          <div className="duplicate-match-list">
            {candidate.duplicate_matches.map((match) => (
              <button
                className={match.id === openMatch?.id ? "selected" : ""}
                key={match.id}
                onClick={() => setOpenMatchId(match.id)}
                type="button"
              >
                {match.vendor} · {match.transaction_date} · {match.amount}{" "}
                {match.currency}
              </button>
            ))}
          </div>
          {openMatch && (
            <div className="duplicate-match-detail">
              <span><strong>Merchant</strong>{openMatch.vendor}</span>
              <span><strong>Date</strong>{openMatch.transaction_date}</span>
              <span><strong>Amount</strong>{openMatch.amount} {openMatch.currency}</span>
              <span><strong>Account</strong>{openMatch.account ?? "Unknown"}</span>
              <span><strong>Category</strong>{openMatch.category ?? "Uncategorized"}</span>
              <span><strong>Similarity</strong>{Math.round(openMatch.merchant_similarity * 100)}%</span>
              {openMatch.description && (
                <p>{openMatch.description}</p>
              )}
            </div>
          )}
        </div>
      )}
      <div className="candidate-fields">
        <label>Date<DateField value={draft.transaction_date ?? ""} onChange={(value) => field("transaction_date", value)} /></label>
        <label>Merchant<input value={draft.vendor ?? ""} onChange={(e) => field("vendor", e.target.value)} /></label>
        <label>Amount<input step="0.01" type="number" value={draft.amount ?? ""} onChange={(e) => field("amount", e.target.value)} /></label>
        <label>Currency<input value={draft.currency ?? ""} onChange={(e) => field("currency", e.target.value.toUpperCase())} /></label>
        <label>Type<select value={draft.transaction_type ?? "debit"} onChange={(e) => field("transaction_type", e.target.value)}><option value="debit">Debit</option><option value="credit">Credit</option></select></label>
      </div>
      <div className="inline-actions">
        <button className="audit-primary-button" disabled={saving} onClick={() => onResolve("accepted")} type="button">
          {candidate.duplicate_matches.length ? "Accept anyway" : "Accept changes"}
        </button>
        {!!candidate.duplicate_matches.length && (
          <button className="secondary-button" disabled={saving} onClick={() => onResolve("duplicate_rejected")} type="button">
            Reject as duplicate
          </button>
        )}
        <button className="secondary-button" disabled={saving} onClick={() => onResolve("not_transaction")} type="button">Not a transaction</button>
        {candidate.status === "overlap" && (
          <button className="secondary-button" disabled={saving} onClick={() => onResolve("overlap_confirmed")} type="button">Confirm overlap</button>
        )}
      </div>
    </div>
  );
}
