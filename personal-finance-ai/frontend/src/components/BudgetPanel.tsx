import { useEffect, useState } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import type {
  BudgetProposal,
  Category,
  MonthlyBudget,
  MonthlyBudgetSummary,
} from "../types";
import { DashboardPeriodPicker } from "./DashboardPeriodPicker";
import { AppIcon } from "../icons/IconRegistry";
import { SummaryCard } from "./SummaryCard";

export function BudgetPanel({
  categories,
  initialPeriod,
  onChanged,
}: {
  categories: Category[];
  initialPeriod: string;
  onChanged: () => void;
}) {
  const [period, setPeriod] = useState(initialPeriod);
  const [budgets, setBudgets] = useState<MonthlyBudget[]>([]);
  const [summary, setSummary] = useState<MonthlyBudgetSummary | null>(null);
  const [proposals, setProposals] = useState<BudgetProposal[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [message, setMessage] = useState("");
  const [editingBudget, setEditingBudget] = useState<MonthlyBudget | null>(null);
  const [showBudgetForm, setShowBudgetForm] = useState(false);
  const [year, month] = period.split("-").map(Number);

  async function load(generate = true) {
    if (generate) {
      await api.generateBudgetProposals(year, month);
    }
    const [records, totals, proposalRecords] = await Promise.all([
      api.budgets(year, month),
      api.budgetSummary(year, month),
      api.budgetProposals(year, month),
    ]);
    setBudgets(records);
    setSummary(totals);
    setProposals(proposalRecords);
  }

  useEffect(() => {
    void load();
  }, [period]);

  async function save(formData: FormData) {
    try {
      const payload = {
        year,
        month,
        category_id: Number(formData.get("category_id")) || null,
        amount: formData.get("amount"),
        currency: formData.get("currency"),
        notes: formData.get("notes") || null,
      };
      if (editingBudget) {
        await api.updateBudget(editingBudget.id, payload);
        setMessage("Monthly budget updated.");
      } else {
        await api.createBudget(payload);
        setMessage("Monthly budget added.");
      }
      setEditingBudget(null);
      setShowBudgetForm(false);
      await load();
      onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add budget");
    }
  }

  return (
    <>
      <section className="page-heading budget-heading">
        <div>
          <p className="eyebrow">Monthly planning</p>
          <h1>Budgets</h1>
          <p>Set category limits by month and compare them with confirmed spending.</p>
        </div>
        <div className="budget-heading-actions">
          <div className="module-period-picker">
            <span>Budget month</span>
            <DashboardPeriodPicker period={period} onChange={setPeriod} />
          </div>
          <button
            onClick={() => {
              setEditingBudget(null);
              setShowBudgetForm(true);
            }}
            type="button"
          >
            <AppIcon name="add" size={16} />
            Add budget
          </button>
        </div>
      </section>
      <section className="summary-grid budget-summary-grid">
        <SummaryCard
          label="Monthly budget"
          value={`${summary?.total_budget ?? "0.00"} ${summary?.currency ?? "EUR"}`}
          detail={`${summary?.categories.length ?? 0} category limits`}
          icon="budgets"
          accent="green"
        />
        <SummaryCard
          label="Confirmed spending"
          value={`${summary?.spent ?? "0.00"} ${summary?.currency ?? "EUR"}`}
          detail={`${summary?.percentage ?? "0"}% used`}
          icon="expense"
          accent="red"
        />
        <SummaryCard
          label="Remaining"
          value={`${summary?.remaining ?? "0.00"} ${summary?.currency ?? "EUR"}`}
          detail="Pending review is not included"
          icon="netCashFlow"
          accent="amber"
          tone={Number(summary?.remaining ?? 0) < 0 ? "negative" : "positive"}
        />
      </section>
      <section className="panel recurring-proposals">
        <div className="panel-heading recurring-proposal-heading">
          <div>
            <p className="eyebrow">Suggested from transaction history</p>
            <h2>Recurring budget proposals</h2>
            <p>
              Review expected payments for {period}. Nothing is added until you
              confirm it.
            </p>
          </div>
          <button
            className="secondary-button"
            disabled={detecting}
            onClick={async () => {
              setDetecting(true);
              try {
                const result = await api.detectRecurringTransactions(true);
                await load();
                setMessage(
                  `Detected ${result.groups_detected} recurring payment pattern(s).`,
                );
              } catch (error) {
                setMessage(
                  error instanceof Error
                    ? error.message
                    : "Could not detect recurring payments",
                );
              } finally {
                setDetecting(false);
              }
            }}
            type="button"
          >
            {detecting ? "Detecting..." : "Detect recurring payments"}
          </button>
        </div>
        <div className="proposal-list">
          {proposals
            .filter((proposal) => proposal.status === "pending")
            .map((proposal) => (
              <article className="proposal-card" key={proposal.id}>
                <div className="proposal-main">
                  <span className="recurrence-badge">
                    {proposal.recurrence_frequency}
                  </span>
                  <h3>{proposal.merchant}</h3>
                  <p>
                    Expected {proposal.expected_date} ·{" "}
                    {categories.find(
                      (category) => category.id === proposal.category_id,
                    )?.name ?? "General spending"}
                  </p>
                  <small>
                    {proposal.detection_source === "user"
                      ? "Set by you"
                      : proposal.detection_source === "ollama"
                        ? "Suggested by local Ollama"
                        : "Detected from validated transactions"}
                    {proposal.confidence
                      ? ` · ${Math.round(Number(proposal.confidence) * 100)}% confidence`
                      : ""}
                  </small>
                </div>
                <strong>
                  {proposal.amount} {proposal.currency}
                </strong>
                <div className="proposal-actions">
                  <button
                    onClick={async () => {
                      await api.confirmBudgetProposal(proposal.id);
                      setMessage(`${proposal.merchant} added to the budget.`);
                      await load(false);
                      onChanged();
                    }}
                    type="button"
                  >
                    Confirm
                  </button>
                  <button
                    className="secondary-button"
                    onClick={async () => {
                      await api.dismissBudgetProposal(proposal.id);
                      setMessage(`${proposal.merchant} proposal dismissed.`);
                      await load(false);
                    }}
                    type="button"
                  >
                    Dismiss
                  </button>
                </div>
              </article>
            ))}
          {!proposals.some((proposal) => proposal.status === "pending") && (
            <p className="empty-state">
              No recurring payments are due in this month. Use detection after
              confirming more transaction history, or set an occurrence while
              editing a transaction.
            </p>
          )}
        </div>
      </section>
      <article className="panel budget-usage-panel budget-usage-full">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Actual vs plan</p>
            <h2>Category usage</h2>
          </div>
        </div>
        <div className="category-list">
          {(summary?.categories ?? []).map((item) => (
            <div className="category-row" key={item.budget_id}>
              <div className="budget-category-summary">
                <span className="budget-category-name">{item.category}</span>
                <strong>
                  {item.spent} / {item.budget} {summary?.currency ?? "EUR"}
                </strong>
              </div>
              <div className="progress">
                <span
                  className={Number(item.percentage) > 100 ? "over-budget" : ""}
                  style={{ width: `${Math.min(Number(item.percentage), 100)}%` }}
                />
              </div>
              <div className="budget-row-actions">
                <small>{item.percentage}% used</small>
                <div className="budget-action-buttons">
                  <button
                    className="secondary-button"
                    onClick={() => {
                      const budget = budgets.find(
                        (record) => record.id === item.budget_id,
                      );
                      if (budget) {
                        setEditingBudget(budget);
                        setShowBudgetForm(true);
                      }
                    }}
                    type="button"
                  >
                    Edit
                  </button>
                  <button
                    className="secondary-button danger-outline"
                    onClick={async () => {
                      const confirmed = await confirmAction({
                        title: "Delete budget?",
                        message: `Delete the budget for ${item.category}?`,
                        confirmLabel: "Delete budget",
                      });
                      if (!confirmed) return;
                      await api.deleteBudget(item.budget_id);
                      await load();
                      onChanged();
                    }}
                    type="button"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
          {!budgets.length && (
            <p className="empty-state">No budgets set for this month.</p>
          )}
        </div>
      </article>
      {message && !showBudgetForm && <p className="success-message">{message}</p>}
      {showBudgetForm && (
        <div
          className="investment-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setShowBudgetForm(false);
              setEditingBudget(null);
            }
          }}
        >
          <div
            aria-modal="true"
            className="investment-modal budget-entry-modal"
            role="dialog"
          >
            <header>
              <div>
                <p className="eyebrow">
                  {editingBudget ? "Update a limit" : "Add a limit"}
                </p>
                <h2>
                  {editingBudget ? "Edit budget" : `Budget for ${period}`}
                </h2>
              </div>
              <button
                aria-label="Close budget form"
                className="risk-modal-close"
                onClick={() => {
                  setShowBudgetForm(false);
                  setEditingBudget(null);
                }}
                type="button"
              >
                <AppIcon name="close" size={18} />
              </button>
            </header>
            <form
              action={save}
              className="form-grid"
              key={editingBudget ? `edit-${editingBudget.id}` : "new-budget"}
            >
            <label>
              Category
              <select
                name="category_id"
                defaultValue={String(editingBudget?.category_id ?? "")}
                required
              >
                <option value="">General spending</option>
                {categories
                  .filter((category) => category.type !== "income")
                  .map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Amount
              <input
                defaultValue={editingBudget?.amount ?? ""}
                name="amount"
                type="number"
                min="0.01"
                step="0.01"
                required
              />
            </label>
            <label>
              Currency
              <input
                name="currency"
                defaultValue={editingBudget?.currency ?? summary?.currency ?? "EUR"}
              />
            </label>
            <label className="wide">
              Notes
              <input
                defaultValue={editingBudget?.notes ?? ""}
                name="notes"
                placeholder="Optional planning note"
              />
            </label>
            <div className="form-footer wide">
              <button type="submit">
                {editingBudget ? "Update monthly budget" : "Add monthly budget"}
              </button>
              <span className="form-message">{message}</span>
            </div>
          </form>
          </div>
        </div>
      )}
    </>
  );
}
