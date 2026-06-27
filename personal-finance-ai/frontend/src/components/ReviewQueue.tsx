import { useEffect, useState } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import type { Account, Category, Transaction } from "../types";
import { DateField } from "./DateField";

interface ReviewQueueProps {
  transactions: Transaction[];
  accounts: Account[];
  categories: Category[];
  documentId?: number;
  onChanged: () => void | Promise<void>;
}

export function ReviewQueue({
  transactions,
  accounts,
  categories,
  documentId,
  onChanged,
}: ReviewQueueProps) {
  const [rows, setRows] = useState(transactions);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState("");
  const [rowMessages, setRowMessages] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<Record<number, string>>({});
  const [bulkClassifying, setBulkClassifying] = useState(false);
  const [classificationSeconds, setClassificationSeconds] = useState(0);
  const [validatedTransactions, setValidatedTransactions] = useState<Transaction[]>(
    [],
  );

  useEffect(() => {
    setRows(transactions);
  }, [transactions]);

  useEffect(() => {
    void api.transactions(true).then(setValidatedTransactions).catch(() => {
      setValidatedTransactions([]);
    });
  }, [transactions]);

  useEffect(() => {
    if (!bulkClassifying) return;
    const startedAt = Date.now();
    const timer = window.setInterval(
      () => setClassificationSeconds(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [bulkClassifying]);

  function setRowBusy(id: number, action: string | null) {
    setBusy((current) => {
      const next = { ...current };
      if (action) next[id] = action;
      else delete next[id];
      return next;
    });
  }

  function replaceRow(updated: Transaction) {
    setRows((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
  }

  function setRowMessage(id: number, value: string) {
    setRowMessages((current) => ({ ...current, [id]: value }));
  }

  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function approve() {
    setMessage("");
    try {
      if (documentId) await api.confirmDocument(documentId, [...selected]);
      else await api.validateTransactions([...selected]);
      setRows((current) => current.filter((item) => !selected.has(item.id)));
      setSelected(new Set());
      setMessage("Selected transactions approved.");
      await onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Approval failed.");
    }
  }

  async function save(transaction: Transaction, formData: FormData) {
    setRowBusy(transaction.id, "save");
    setRowMessage(transaction.id, "");
    setMessage("");
    try {
      const updated = await api.updateTransaction(transaction.id, {
        transaction_date: formData.get("transaction_date"),
        booking_date: formData.get("booking_date") || null,
        account_id: Number(formData.get("account_id")),
        vendor: formData.get("vendor"),
        description: formData.get("description"),
        amount: formData.get("amount"),
        currency: formData.get("currency"),
        transaction_type: formData.get("transaction_type"),
        category_id: Number(formData.get("category_id")) || null,
        payment_method: formData.get("payment_method") || null,
        is_duplicate: formData.get("is_duplicate") === "on",
      });
      replaceRow(updated);
      const savedMessage = `Saved changes to ${updated.vendor}.`;
      setMessage(savedMessage);
      setRowMessage(updated.id, savedMessage);
      await onChanged();
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Save failed.";
      setMessage(errorMessage);
      setRowMessage(transaction.id, errorMessage);
    } finally {
      setRowBusy(transaction.id, null);
    }
  }

  async function classify(id: number) {
    setRowBusy(id, "classify");
    setRowMessage(id, "");
    setMessage("");
    try {
      const updated = await api.classifyTransaction(id);
      replaceRow(updated);
      const category = categories.find((item) => item.id === updated.category_id);
      const classifiedMessage =
        category
          ? `Classified ${updated.vendor} as ${category.name} using ${updated.classification_source}.`
          : `No rule, merchant history, or Ollama category matched ${updated.vendor}.`;
      setMessage(classifiedMessage);
      setRowMessage(id, classifiedMessage);
      await onChanged();
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Classification failed.";
      setMessage(errorMessage);
      setRowMessage(id, errorMessage);
    } finally {
      setRowBusy(id, null);
    }
  }

  async function classifyAll() {
    const uncategorized = rows
      .filter((item) => item.category_id === null)
      .map((item) => item.id);
    if (!uncategorized.length) {
      setMessage("Every visible transaction already has a category.");
      return;
    }
    setBulkClassifying(true);
    setClassificationSeconds(0);
    setMessage(
      `Checking rules and merchant history, then asking local Ollama for ${uncategorized.length} transaction(s)...`,
    );
    try {
      const result = await api.classifyPending(uncategorized);
      if (!result.ollama_available) {
        setMessage(
          `Ollama is offline. Rules/merchant history classified ${result.classified} of ${result.total}; ${result.unresolved.length} remain unresolved.`,
        );
      } else if (!result.model_installed) {
        setMessage(
          `Ollama is running, but model ${result.model} is not installed. ${result.unresolved.length} transaction(s) remain unresolved.`,
        );
      } else {
        setMessage(
          `Finished: ${result.classified} of ${result.total} classified ` +
            `(rules ${result.by_source.rule}, history ${result.by_source.merchant_history}, Ollama ${result.by_source.ollama}).` +
            (result.unresolved.length
              ? ` Unresolved: ${result.unresolved.slice(0, 3).join(", ")}${result.unresolved.length > 3 ? "…" : ""}.`
              : ""),
        );
      }
      await onChanged();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Bulk classification failed.",
      );
    } finally {
      setBulkClassifying(false);
    }
  }

  function normalizeMerchant(value: string) {
    return value.toLowerCase().normalize("NFKC").match(/[a-z0-9]+/g)?.join(" ") ?? "";
  }

  function merchantSimilarity(left: string, right: string) {
    const a = normalizeMerchant(left);
    const b = normalizeMerchant(right);
    if (!a || !b) return 0;
    const matrix = Array.from({ length: a.length + 1 }, () =>
      Array<number>(b.length + 1).fill(0),
    );
    for (let i = 0; i <= a.length; i += 1) matrix[i][0] = i;
    for (let j = 0; j <= b.length; j += 1) matrix[0][j] = j;
    for (let i = 1; i <= a.length; i += 1) {
      for (let j = 1; j <= b.length; j += 1) {
        matrix[i][j] = Math.min(
          matrix[i - 1][j] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
        );
      }
    }
    return 1 - matrix[a.length][b.length] / Math.max(a.length, b.length);
  }

  function duplicateMatch(transaction: Transaction) {
    return validatedTransactions.find(
      (candidate) =>
        candidate.id !== transaction.id &&
        candidate.account_id === transaction.account_id &&
        candidate.transaction_date === transaction.transaction_date &&
        Number(candidate.amount) === Number(transaction.amount) &&
        candidate.transaction_type === transaction.transaction_type &&
        merchantSimilarity(candidate.vendor, transaction.vendor) >= 0.6,
    );
  }

  function formatAddedDate(value: string) {
    return new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(new Date(value));
  }

  if (!rows.length) {
    return <p className="empty-state">No imported transactions need review.</p>;
  }

  return (
    <>
      <div className="review-actions">
        <label>
          <input
            type="checkbox"
            checked={selected.size === rows.length}
            onChange={(event) =>
              setSelected(
                event.target.checked
                  ? new Set(rows.map((item) => item.id))
                  : new Set(),
              )
            }
          />
          Select all
        </label>
        <div className="inline-actions">
          {message && <span className="form-message">{message}</span>}
          <button
            className="secondary-button"
            disabled={bulkClassifying}
            type="button"
            onClick={classifyAll}
          >
            {bulkClassifying
              ? `Classifying… ${classificationSeconds}s`
              : "Classify all with Ollama"}
          </button>
          <button type="button" disabled={!selected.size} onClick={approve}>
            Approve selected
          </button>
        </div>
      </div>
      {bulkClassifying && (
        <div className="classification-progress" role="status">
          <span className="classification-spinner" />
          <div>
            <strong>Local classification is running</strong>
            <small>
              Rules and merchant history run first. Ollama can take several
              seconds per unresolved transaction.
            </small>
          </div>
        </div>
      )}
      <div className="review-cards" aria-live="polite">
        {rows.map((transaction) => {
          const match = transaction.is_duplicate
            ? duplicateMatch(transaction)
            : undefined;
          return (
          <form
            key={`${transaction.id}-${transaction.category_id}-${transaction.classification_source}-${transaction.confidence}`}
            action={(formData) => save(transaction, formData)}
            className="review-card"
          >
            <input
              aria-label={`Select ${transaction.vendor}`}
              type="checkbox"
              checked={selected.has(transaction.id)}
              onChange={() => toggle(transaction.id)}
            />
            <label>
              Account
              <select name="account_id" defaultValue={transaction.account_id}>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Date
              <DateField
                name="transaction_date"
                defaultValue={transaction.transaction_date}
              />
            </label>
            <label>
              Booking date
              <DateField
                name="booking_date"
                defaultValue={transaction.booking_date ?? ""}
              />
            </label>
            <label>
              Vendor
              <input name="vendor" defaultValue={transaction.vendor} />
            </label>
            <label>
              Description
              <input name="description" defaultValue={transaction.description} />
            </label>
            <label>
              Amount
              <input
                name="amount"
                type="number"
                step="0.01"
                defaultValue={transaction.amount}
              />
            </label>
            <label>
              Currency
              <input
                name="currency"
                defaultValue={transaction.currency}
                minLength={3}
                maxLength={3}
              />
            </label>
            <label>
              Type
              <select
                name="transaction_type"
                defaultValue={transaction.transaction_type}
              >
                <option value="debit">Expense</option>
                <option value="credit">Income</option>
              </select>
            </label>
            <label>
              Category
              <select
                name="category_id"
                defaultValue={transaction.category_id ?? ""}
              >
                <option value="">Uncategorized</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Payment method
              <input
                name="payment_method"
                defaultValue={transaction.payment_method ?? ""}
              />
            </label>
            <label className="checkbox-label">
              <input
                name="is_duplicate"
                type="checkbox"
                defaultChecked={transaction.is_duplicate}
              />
              Duplicate
              {transaction.is_duplicate && (
                <span className="review-duplicate-badge">
                  possible duplicate
                </span>
              )}
            </label>
            {match && (
              <div className="review-duplicate-detail">
                <strong>Original transaction already exists</strong>
                <span>Date: {match.transaction_date}</span>
                <span>Merchant: {match.vendor}</span>
                <span>Amount: {match.amount} {match.currency}</span>
                <span>
                  Category:{" "}
                  {categories.find((category) => category.id === match.category_id)
                    ?.name ?? "Uncategorized"}
                </span>
                <span>Added: {formatAddedDate(match.created_at)}</span>
              </div>
            )}
            <div className="inline-actions">
              <button
                className="secondary-button"
                type="button"
                disabled={Boolean(busy[transaction.id])}
                onClick={() => classify(transaction.id)}
              >
                {busy[transaction.id] === "classify"
                  ? "Classifying..."
                  : "Classify"}
              </button>
              <button type="submit" disabled={Boolean(busy[transaction.id])}>
                {busy[transaction.id] === "save" ? "Saving..." : "Save"}
              </button>
              <button
                className="text-button danger"
                type="button"
                disabled={Boolean(busy[transaction.id])}
                onClick={async () => {
                  if (
                    !(await confirmAction({
                      title: "Reject transaction?",
                      message: `This will delete "${transaction.vendor}" for ${transaction.amount} ${transaction.currency} from the review queue.`,
                      confirmLabel: "Reject and delete",
                    }))
                  ) {
                    return;
                  }
                  setRowBusy(transaction.id, "reject");
                  try {
                    await api.deleteTransaction(transaction.id);
                    setRows((current) =>
                      current.filter((item) => item.id !== transaction.id),
                    );
                    setMessage(`Removed ${transaction.vendor} from review.`);
                    await onChanged();
                  } catch (error) {
                    setMessage(
                      error instanceof Error ? error.message : "Reject failed.",
                    );
                    setRowBusy(transaction.id, null);
                  }
                }}
              >
                Reject
              </button>
            </div>
            <small>
              Source: {transaction.classification_source}
              {transaction.confidence
                ? ` · confidence ${Number(transaction.confidence) * 100}%`
                : ""}
            </small>
            {rowMessages[transaction.id] && (
              <small className="review-card-status" role="status">
                {rowMessages[transaction.id]}
              </small>
            )}
          </form>
          );
        })}
      </div>
    </>
  );
}
