import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { categoryPresentation } from "../categoryPresentation";
import { confirmAction } from "../confirmAction";
import { AppIcon } from "../icons/IconRegistry";
import type { ResourceRecord } from "../types";
import { DateField } from "./DateField";

export interface ResourceField {
  name: string;
  label: string;
  type?: "text" | "number" | "date" | "select" | "checkbox" | "textarea";
  required?: boolean;
  defaultValue?: string | number | boolean;
  helpText?: string;
  options?: Array<{ label: string; value: string }>;
}

interface ResourceManagerProps {
  path: string;
  title: string;
  description: string;
  fields: ResourceField[];
  columns: Array<{ key: string; label: string }>;
  refreshKey?: number;
  action?: {
    label: string;
    run: () => Promise<{ updated: number }>;
  };
  analyticsPath?: string;
  editable?: boolean;
}

function formValues(formData: FormData, fields: ResourceField[]) {
  const values: Record<string, unknown> = {};
  for (const field of fields) {
    const value = formData.get(field.name);
    if (field.type === "checkbox") values[field.name] = value === "on";
    else if (field.type === "number")
      values[field.name] = value === "" ? 0 : String(value);
    else values[field.name] = value === "" ? null : value;
  }
  return values;
}

function displayValue(
  path: string,
  column: { key: string; label: string },
  item: ResourceRecord,
) {
  const value = item[column.key];
  if (
    path === "investments" &&
    (column.key === "quantity" || column.key === "average_price") &&
    Number(value) === 0 &&
    item.source_document_id
  ) {
    return "Unknown";
  }
  return String(value ?? "—");
}

function inputValue(
  field: ResourceField,
  editingItem: ResourceRecord | null,
  path: string,
) {
  const value =
    path === "loans" &&
    field.name === "current_balance" &&
    editingItem?.recorded_balance !== undefined
      ? editingItem.recorded_balance
      : editingItem?.[field.name] ?? field.defaultValue ?? "";
  if (field.type === "number" && Number(value) === 0) return "0";
  return String(value);
}

function money(value: unknown, currency = "EUR") {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
  }).format(Number(value ?? 0));
}

function payoffDuration(months: unknown) {
  const value = Number(months);
  if (!Number.isFinite(value) || value <= 0) return "Not available";
  const years = Math.floor(value / 12);
  const remainingMonths = value % 12;
  if (!years) return `${remainingMonths} month${remainingMonths === 1 ? "" : "s"}`;
  if (!remainingMonths) return `${years} year${years === 1 ? "" : "s"}`;
  return `${years}y ${remainingMonths}m`;
}

function PlanningAnalysis({
  path,
  analytics,
  items,
  loanTransactions,
  insuranceTransactions,
}: {
  path: string;
  analytics: Record<string, unknown>;
  items: ResourceRecord[];
  loanTransactions: Record<number, ResourceRecord[]>;
  insuranceTransactions: Record<number, ResourceRecord[]>;
}) {
  if (path === "investments") {
    const allocation = (analytics.allocation ?? []) as Array<
      Record<string, unknown>
    >;
    const costBasisComplete = Boolean(analytics.cost_basis_complete);
    const profitLoss =
      analytics.profit_loss === null ? null : Number(analytics.profit_loss);
    return (
      <section className="planning-analysis">
        <div className="planning-heading">
          <div>
            <p className="eyebrow">Planning analysis</p>
            <h3>Portfolio summary</h3>
          </div>
          <span className="analysis-status">
            {items.length} holding{items.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="analysis-metrics">
          <div className="analysis-metric">
            <span>Current value</span>
            <strong>{money(analytics.current_value)}</strong>
            <small>Combined value of saved holdings</small>
          </div>
          <div className="analysis-metric">
            <span>Cost basis</span>
            <strong>
              {costBasisComplete ? money(analytics.cost_basis) : "Incomplete"}
            </strong>
            <small>
              {costBasisComplete
                ? "Quantity × average purchase price"
                : `${money(analytics.value_missing_cost_basis)} needs purchase data`}
            </small>
          </div>
          <div
            className={`analysis-metric ${
              profitLoss === null ? "" : profitLoss >= 0 ? "positive" : "negative"
            }`}
          >
            <span>Profit / loss</span>
            <strong>{profitLoss === null ? "Not available" : money(profitLoss)}</strong>
            <small>
              {profitLoss === null
                ? "Add quantity and average price to calculate"
                : "Based on holdings with complete cost data"}
            </small>
          </div>
        </div>
        <div className="analysis-section">
          <h4>Asset allocation</h4>
          {allocation.length ? (
            <div className="allocation-list">
              {allocation.map((entry) => {
                const percentage = Math.max(
                  0,
                  Math.min(100, Number(entry.percentage ?? 0)),
                );
                return (
                  <div className="allocation-row" key={String(entry.asset_type)}>
                    <div>
                      <strong>{String(entry.asset_type)}</strong>
                      <span>{money(entry.value)}</span>
                    </div>
                    <div className="allocation-track">
                      <span style={{ width: `${percentage}%` }} />
                    </div>
                    <small>{percentage.toFixed(2)}%</small>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="empty-state">Add investments to see allocation.</p>
          )}
        </div>
        {!costBasisComplete && items.length > 0 && (
          <p className="analysis-notice">
            Purchase quantity or average price is missing for some holdings.
            Complete those fields to calculate portfolio profit and loss.
          </p>
        )}
      </section>
    );
  }

  if (path === "loans") {
    const loans = (analytics.loans ?? []) as Array<Record<string, unknown>>;
    return (
      <section className="planning-analysis">
        <div className="planning-heading">
          <div>
            <p className="eyebrow">Planning analysis</p>
            <h3>Debt summary</h3>
          </div>
          <span className="analysis-status">
            {items.length} loan{items.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="analysis-metrics">
          <div className="analysis-metric">
            <span>Outstanding balance</span>
            <strong>{money(analytics.total_balance)}</strong>
            <small>Total remaining debt</small>
          </div>
          <div className="analysis-metric">
            <span>Monthly payments</span>
            <strong>{money(analytics.monthly_payments)}</strong>
            <small>Current monthly commitment</small>
          </div>
          <div className="analysis-metric">
            <span>Annual payments</span>
            <strong>{money(Number(analytics.monthly_payments ?? 0) * 12)}</strong>
            <small>Monthly payments × 12</small>
          </div>
        </div>
        <div className="analysis-section">
          <h4>Loan payoff outlook</h4>
          <div className="loan-outlook-list">
            {loans.map((loan) => {
              const item = items.find(
                (candidate) => Number(candidate.id) === Number(loan.id),
              );
              const payments = loanTransactions[Number(loan.id)] ?? [];
              return (
                <article className="loan-outlook-card" key={String(loan.id)}>
                  <div className="loan-outlook-title">
                    <div>
                      <strong>{String(loan.lender)}</strong>
                      <span>{String(item?.loan_type ?? "Loan")}</span>
                    </div>
                    <strong>{money(item?.current_balance)}</strong>
                    {Number(item?.payments_applied ?? 0) > 0 && (
                      <small>
                        {money(item?.payments_applied)} reduced by{" "}
                        {String(item?.matched_transaction_count ?? 0)} validated
                        payment(s)
                      </small>
                    )}
                  </div>
                  <div className="loan-outlook-details">
                    <span>
                      <small>Estimated payoff</small>
                      <strong>{payoffDuration(loan.months)}</strong>
                    </span>
                    <span>
                      <small>Estimated interest</small>
                      <strong>
                        {loan.interest === null ? "Not available" : money(loan.interest)}
                      </strong>
                    </span>
                    <span>
                      <small>Monthly payment</small>
                      <strong>{money(item?.monthly_payment)}</strong>
                    </span>
                  </div>
                  {Boolean(loan.warning) && (
                    <p className="loan-warning">{String(loan.warning)}</p>
                  )}
                  <details className="loan-payment-audit" open={payments.length > 0}>
                    <summary>
                      Applied transactions
                      <span>{payments.length}</span>
                    </summary>
                    {payments.length ? (
                      <div className="loan-payment-list">
                        {payments.map((payment) => {
                          const originalAmount = money(
                            payment.amount,
                            String(payment.currency ?? "EUR"),
                          );
                          const appliedAmount = money(
                            payment.applied_amount,
                            String(payment.applied_currency ?? "EUR"),
                          );
                          const converted =
                            String(payment.currency) !==
                            String(payment.applied_currency);
                          return (
                            <article
                              className="loan-payment-row"
                              key={String(payment.id)}
                            >
                              <time>{String(payment.transaction_date)}</time>
                              <div>
                                <strong>{String(payment.vendor)}</strong>
                                <span>
                                  {String(
                                    payment.description ||
                                      payment.reference_number ||
                                      "Loan repayment",
                                  )}
                                </span>
                              </div>
                              <div className="loan-payment-amount">
                                <strong>{appliedAmount}</strong>
                                {converted && <small>From {originalAmount}</small>}
                                <span>Validated</span>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="empty-state">
                        No validated loan repayment transactions are applied to
                        this balance.
                      </p>
                    )}
                  </details>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    );
  }

  if (path === "insurance") {
    const policies = (analytics.policies ?? []) as Array<Record<string, unknown>>;
    const unmatchedTransactions = (analytics.unmatched_transactions ?? []) as Array<
      Record<string, unknown>
    >;
    const reportingYear = String(analytics.reporting_year ?? "");
    const reportingMonth = Number(analytics.reporting_month ?? 0);
    const reportingMonthLabel = reportingMonth
      ? new Intl.DateTimeFormat("en", { month: "long" }).format(
          new Date(2026, reportingMonth - 1, 1),
        )
      : "This month";
    const reportingCurrency = String(analytics.base_currency ?? "EUR");
    return (
      <section className="planning-analysis insurance-analysis">
        <div className="planning-heading">
          <div>
            <p className="eyebrow">Insurance payments</p>
            <h3>Premium summary</h3>
          </div>
          <span className="analysis-status">
            {String(analytics.active_policies ?? 0)} active policies
          </span>
        </div>
        <div className="analysis-metrics insurance-metrics">
          <div className="analysis-metric">
            <span>Expected per month</span>
            <strong>
              {money(analytics.scheduled_monthly, reportingCurrency)}
            </strong>
            <small>Monthly equivalent of all saved premiums</small>
          </div>
          <div className="analysis-metric">
            <span>Expected per year</span>
            <strong>{money(analytics.scheduled_annual, reportingCurrency)}</strong>
            <small>Monthly, quarterly, and yearly policies combined</small>
          </div>
          <div className="analysis-metric">
            <span>Paid in {reportingMonthLabel}</span>
            <strong>{money(analytics.actual_month, reportingCurrency)}</strong>
            <small>Validated insurance transactions</small>
          </div>
          <div className="analysis-metric">
            <span>Paid in {reportingYear}</span>
            <strong>{money(analytics.actual_year, reportingCurrency)}</strong>
            <small>Year-to-date validated payments</small>
          </div>
        </div>
        {Number(analytics.unmatched_transaction_count ?? 0) > 0 && (
          <div className="insurance-unmatched">
            <p className="analysis-notice">
              {String(analytics.unmatched_transaction_count)} validated insurance
              transaction(s) could not be matched confidently to a saved policy.
              Review the provider, policy type, or premium amount.
            </p>
            <div className="loan-payment-list">
              {unmatchedTransactions.map((transaction) => (
                <article
                  className="loan-payment-row unmatched-payment-row"
                  key={String(transaction.id)}
                >
                  <time>{String(transaction.transaction_date)}</time>
                  <div>
                    <strong>{String(transaction.vendor)}</strong>
                    <span>
                      {String(transaction.description || "Insurance payment")}
                    </span>
                  </div>
                  <div className="loan-payment-amount">
                    <strong>
                      {money(
                        transaction.amount,
                        String(transaction.currency ?? "EUR"),
                      )}
                    </strong>
                    <span>Needs matching</span>
                    <button
                      className="secondary-button"
                      onClick={() => {
                        const target = new URL(window.location.href);
                        target.searchParams.set(
                          "reviewTransaction",
                          String(transaction.id),
                        );
                        target.hash = "transactions";
                        window.location.assign(target);
                      }}
                      type="button"
                    >
                      Review transaction
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
        <div className="analysis-section">
          <h4>Policies and payments</h4>
          <div className="loan-outlook-list">
            {policies.map((policy) => {
              const payments =
                insuranceTransactions[Number(policy.id)] ?? [];
              return (
                <article className="loan-outlook-card" key={String(policy.id)}>
                  <div className="loan-outlook-title">
                    <div>
                      <strong>{String(policy.provider)}</strong>
                      <span>{String(policy.policy_type)}</span>
                    </div>
                    <strong>
                      {money(policy.scheduled_monthly, String(policy.currency))}
                      <small className="premium-period"> / month</small>
                    </strong>
                  </div>
                  <div className="loan-outlook-details">
                    <span>
                      <small>Expected annually</small>
                      <strong>
                        {money(policy.scheduled_annual, String(policy.currency))}
                      </strong>
                    </span>
                    <span>
                      <small>Paid this month</small>
                      <strong>
                        {money(policy.actual_month, String(policy.currency))}
                      </strong>
                    </span>
                    <span>
                      <small>Paid this year</small>
                      <strong>
                        {money(policy.actual_year, String(policy.currency))}
                      </strong>
                    </span>
                  </div>
                  <details
                    className="loan-payment-audit"
                    open={payments.length > 0}
                  >
                    <summary>
                      Insurance transactions
                      <span>{payments.length}</span>
                    </summary>
                    {payments.length ? (
                      <div className="loan-payment-list">
                        {payments.map((payment) => (
                          <article
                            className="loan-payment-row"
                            key={String(payment.id)}
                          >
                            <time>{String(payment.transaction_date)}</time>
                            <div>
                              <strong>{String(payment.vendor)}</strong>
                              <span>
                                {String(
                                  payment.description ||
                                    payment.reference_number ||
                                    "Insurance premium",
                                )}
                              </span>
                            </div>
                            <div className="loan-payment-amount">
                              <strong>
                                {money(
                                  payment.applied_amount,
                                  String(payment.applied_currency ?? "EUR"),
                                )}
                              </strong>
                              <span>Validated</span>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <p className="empty-state">
                        No validated transactions have been matched to this
                        policy.
                      </p>
                    )}
                  </details>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    );
  }

  return (
    <details className="analytics-box">
      <summary>Planning analysis</summary>
      <pre>{JSON.stringify(analytics, null, 2)}</pre>
    </details>
  );
}

export function ResourceManager({
  path,
  title,
  description,
  fields,
  columns,
  refreshKey,
  action,
  analyticsPath,
  editable = false,
}: ResourceManagerProps) {
  const [items, setItems] = useState<ResourceRecord[]>([]);
  const [message, setMessage] = useState("");
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(null);
  const [loanTransactions, setLoanTransactions] = useState<
    Record<number, ResourceRecord[]>
  >({});
  const [insuranceTransactions, setInsuranceTransactions] = useState<
    Record<number, ResourceRecord[]>
  >({});
  const [editingItem, setEditingItem] = useState<ResourceRecord | null>(null);
  const [showForm, setShowForm] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const isPlanningModule = path === "loans" || path === "insurance";
  const itemLabel =
    title === "Rules"
      ? "rule"
      : title === "Watchlist"
        ? "watchlist item"
        : title === "Loans"
          ? "loan"
          : title === "Insurance"
            ? "insurance policy"
        : title.toLowerCase();

  async function load() {
    try {
      const loadedItems = await api.resources(path);
      setItems(loadedItems);
      if (path === "loans") {
        const paymentEntries = await Promise.all(
          loadedItems.map(async (loan) => [
            Number(loan.id),
            await api.loanTransactions(Number(loan.id)),
          ] as const),
        );
        setLoanTransactions(Object.fromEntries(paymentEntries));
      } else {
        setLoanTransactions({});
      }
      if (path === "insurance") {
        const paymentEntries = await Promise.all(
          loadedItems.map(async (policy) => [
            Number(policy.id),
            await api.insuranceTransactions(Number(policy.id)),
          ] as const),
        );
        setInsuranceTransactions(Object.fromEntries(paymentEntries));
      } else {
        setInsuranceTransactions({});
      }
      if (analyticsPath) setAnalytics(await api.analytics(analyticsPath));
      else setAnalytics(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load data");
    }
  }

  useEffect(() => {
    setMessage("");
    setEditingItem(null);
    setShowForm(false);
    void load();
  }, [path, refreshKey, analyticsPath]);

  async function save(formData: FormData) {
    try {
      const values = formValues(formData, fields);
      if (editingItem) {
        await api.updateResource(path, Number(editingItem.id), values);
        setMessage(`${title} record updated.`);
        setEditingItem(null);
      } else {
        await api.createResource(path, values);
        setMessage(`${title} record saved.`);
        formRef.current?.reset();
      }
      await load();
      if (isPlanningModule) setShowForm(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save");
    }
  }

  async function remove(id: number) {
    try {
      const confirmed = await confirmAction({
        title: `Delete ${itemLabel}?`,
        message: `Delete this ${itemLabel.toLowerCase()} record? This cannot be undone.`,
        confirmLabel: `Delete ${itemLabel.toLowerCase()}`,
      });
      if (!confirmed) return;
      await api.deleteResource(path, id);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not delete");
    }
  }

  const visualAnalytics =
    analytics &&
    (path === "investments" || path === "loans" || path === "insurance") ? (
      <PlanningAnalysis
        path={path}
        analytics={analytics}
        items={items}
        loanTransactions={loanTransactions}
        insuranceTransactions={insuranceTransactions}
      />
    ) : null;

  const resourceForm = (
    <form
      key={editingItem ? `edit-${editingItem.id}` : "create"}
      ref={formRef}
      action={save}
      className="resource-form"
    >
      {fields.map((field) => (
        <label key={field.name}>
          {field.label}
          {field.type === "select" ? (
            <select
              name={field.name}
              required={field.required}
              defaultValue={inputValue(field, editingItem, path)}
            >
              <option value="">Select</option>
              {field.options?.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : field.type === "textarea" ? (
            <textarea
              name={field.name}
              defaultValue={inputValue(field, editingItem, path)}
            />
          ) : field.type === "date" ? (
            <DateField
              name={field.name}
              required={field.required}
              defaultValue={inputValue(field, editingItem, path)}
            />
          ) : field.type === "checkbox" ? (
            <input
              name={field.name}
              type="checkbox"
              defaultChecked={Boolean(
                editingItem?.[field.name] ?? field.defaultValue,
              )}
            />
          ) : (
            <input
              name={field.name}
              type={field.type ?? "text"}
              step={field.type === "number" ? "any" : undefined}
              required={field.required}
              defaultValue={inputValue(field, editingItem, path)}
            />
          )}
          {field.helpText && (
            <small className="field-help">{field.helpText}</small>
          )}
        </label>
      ))}
      <div className="resource-form-actions">
        <button type="submit">
          {editingItem ? `Update ${itemLabel}` : `Add ${itemLabel}`}
        </button>
        {editingItem && !isPlanningModule && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setEditingItem(null);
              setMessage("Edit cancelled.");
            }}
          >
            Cancel
          </button>
        )}
      </div>
      {message && <span className="form-message">{message}</span>}
    </form>
  );

  const savedRecords = (
    <>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Structured records</p>
          <h2>Saved {title.toLowerCase()}</h2>
        </div>
        <span className="count-pill">{items.length}</span>
      </div>
      {!items.length ? (
        <p className="empty-state">No records yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={String(item.id)}>
                  {columns.map((column) => (
                    <td key={column.key}>
                      {path === "categories" && column.key === "icon" ? (
                        <span
                          className={`category-table-icon ${
                            categoryPresentation({
                              name: String(item.name),
                              icon: String(item.icon || ""),
                              color: String(item.color || ""),
                            }).color
                          }`}
                        >
                          <AppIcon
                            name={
                              categoryPresentation({
                                name: String(item.name),
                                icon: String(item.icon || ""),
                                color: String(item.color || ""),
                              }).icon
                            }
                            size={15}
                          />
                        </span>
                      ) : path === "categories" && column.key === "color" ? (
                        <span className={`category-color-label ${String(item.color)}`}>
                          {displayValue(path, column, item)}
                        </span>
                      ) : (
                        displayValue(path, column, item)
                      )}
                    </td>
                  ))}
                  <td>
                    <div className="inline-actions">
                      {editable && (
                        <button
                          className="text-button"
                          onClick={() => {
                            setEditingItem(item);
                            setMessage(
                              `Editing ${String(item[columns[0].key])}.`,
                            );
                            if (isPlanningModule) {
                              setShowForm(true);
                            } else {
                              formRef.current?.scrollIntoView({
                                behavior: "smooth",
                                block: "start",
                              });
                            }
                          }}
                        >
                          Edit
                        </button>
                      )}
                      <button
                        className="text-button danger"
                        onClick={() => remove(Number(item.id))}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );

  if (isPlanningModule) {
    return (
      <section className="asset-module-page planning-module-page">
        <section className="module-page-heading">
          <div>
            <p className="eyebrow">Finance module</p>
            <h1>{title}</h1>
            <p>{description}</p>
          </div>
          <button
            onClick={() => {
              setEditingItem(null);
              setMessage("");
              setShowForm(true);
            }}
            type="button"
          >
            <AppIcon name="add" size={16} />
            Add {title === "Loans" ? "loan" : "insurance policy"}
          </button>
        </section>
        {message && !showForm && <p className="success-message">{message}</p>}
        {visualAnalytics}
        <article className="panel planning-records-panel">{savedRecords}</article>
        {showForm && (
          <div
            className="investment-modal-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setShowForm(false);
                setEditingItem(null);
              }
            }}
          >
            <div
              aria-modal="true"
              className="investment-modal planning-entry-modal"
              role="dialog"
            >
              <header>
                <div>
                  <p className="eyebrow">
                    {editingItem ? "Update record" : "New record"}
                  </p>
                  <h2>
                    {editingItem
                      ? `Edit ${itemLabel}`
                      : `Add ${title === "Loans" ? "loan" : "insurance policy"}`}
                  </h2>
                </div>
                <button
                  aria-label={`Close ${itemLabel} form`}
                  className="risk-modal-close"
                  onClick={() => {
                    setShowForm(false);
                    setEditingItem(null);
                  }}
                  type="button"
                >
                  <AppIcon name="close" size={18} />
                </button>
              </header>
              {resourceForm}
            </div>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="module-layout">
      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Finance module</p>
            <h2>{title}</h2>
            <p className="section-copy">{description}</p>
          </div>
          {action && (
            <button
              className="secondary-button"
              onClick={async () => {
                const result = await action.run();
                setMessage(`${result.updated} record(s) updated.`);
                await load();
              }}
            >
              {action.label}
            </button>
          )}
        </div>
        {resourceForm}
      </article>
      <article className="panel">
        {visualAnalytics}
        {savedRecords}
        {analytics && !visualAnalytics && (
          <PlanningAnalysis
            path={path}
            analytics={analytics}
            items={items}
            loanTransactions={loanTransactions}
            insuranceTransactions={insuranceTransactions}
          />
        )}
      </article>
    </section>
  );
}
