import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { categoryPresentation } from "../categoryPresentation";
import { confirmAction } from "../confirmAction";
import { AppIcon } from "../icons/IconRegistry";
import type { DocumentRecord, ResourceRecord } from "../types";
import { DateField } from "./DateField";
import { DocumentViewer } from "./DocumentsPanel";

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
  baseCurrency?: string;
}

function formValues(formData: FormData, fields: ResourceField[]) {
  const values: Record<string, unknown> = {};
  for (const field of fields) {
    const value = formData.get(field.name);
    if (field.type === "checkbox") values[field.name] = value === "on";
    else if (value === null) continue;
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
  baseCurrency = "EUR",
) {
  if (path === "loans" && field.name === "currency" && !editingItem) {
    return baseCurrency;
  }
  const value =
    path === "loans" &&
    field.name === "current_balance" &&
    editingItem?.recorded_balance !== undefined
      ? editingItem.recorded_balance
      : editingItem?.[field.name] ?? field.defaultValue ?? "";
  if (field.type === "number" && Number(value) === 0) return "0";
  return String(value);
}

function loanSettingDefaults(values: Record<string, unknown>) {
  return {
    interest_calculation_basis: "daily_balance",
    interest_posting_frequency: "manual",
    payment_allocation_rule: "interest_first",
    monthly_payment: "0",
    end_date: null,
    status: "active",
    ...values,
  };
}

function money(value: unknown, currency = "EUR") {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
  }).format(Number(value ?? 0));
}

function ledgerTypeLabel(value: unknown) {
  const labels: Record<string, string> = {
    opening_balance: "Opening Balance",
    loan_taken: "Loan Taken",
    drawdown: "Loan Taken",
    repayment: "Repayment",
    interest_posted: "Interest Posted",
    interest_accrued: "Interest Accrued",
    charge: "Charge",
    adjustment: "Adjustment",
    waiver: "Waiver",
    correction: "Correction",
  };
  const key = String(value ?? "");
  return labels[key] ?? key.replace(/_/g, " ");
}

function loanTypeLabel(value: unknown) {
  const key = String(value ?? "personal_running")
    .toLowerCase()
    .replaceAll("-", "_")
    .replaceAll(" ", "_");
  const labels: Record<string, string> = {
    personal: "Personal loan",
    personal_running: "Running personal loan",
    friend: "Friend loan",
    family: "Family loan",
    informal: "Informal loan",
    standard_emi: "Standard EMI loan",
    bank: "Bank loan",
    home: "Home loan",
    mortgage: "Mortgage loan",
    car: "Car loan",
    auto: "Auto loan",
  };
  return labels[key] ?? key.replaceAll("_", " ");
}

function ledgerRateForEntry(
  entry: ResourceRecord,
  rateChanges: ResourceRecord[],
) {
  return rateChanges
    .filter((rate) => String(rate.effective_date) <= String(entry.entry_date))
    .at(-1);
}

function effectiveRateOn(dateText: string, rateChanges: ResourceRecord[]) {
  const rate = rateChanges
    .filter((change) => String(change.effective_date) <= dateText)
    .at(-1);
  return Number(rate?.interest_rate ?? 0);
}

function isInterestEntry(entry: ResourceRecord) {
  return ["interest", "interest_posted", "interest_accrued"].includes(
    String(entry.entry_type),
  );
}

function isBalanceReducingEntry(entry: ResourceRecord) {
  const entryType = String(entry.entry_type);
  if (["repayment", "waiver"].includes(entryType)) return true;
  if (["opening_balance", "loan_taken", "drawdown"].includes(entryType)) {
    return false;
  }
  return (
    Number(entry.signed_amount ?? 0) < 0 || String(entry.direction) === "credit"
  );
}

function isLoanTakenEntry(entry: ResourceRecord) {
  return ["opening_balance", "loan_taken", "drawdown"].includes(
    String(entry.entry_type),
  );
}

function isLoanPaymentEntry(entry: ResourceRecord) {
  return ["repayment", "waiver"].includes(String(entry.entry_type));
}

function isoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function daysBetween(startText: string, endText: string) {
  const start = new Date(`${startText}T00:00:00Z`);
  const end = new Date(`${endText}T00:00:00Z`);
  return Math.max(0, Math.round((end.getTime() - start.getTime()) / 86400000));
}

function accruedInterestBetween(
  previousEntry: ResourceRecord | undefined,
  entry: ResourceRecord,
  rateChanges: ResourceRecord[],
) {
  if (!previousEntry) return 0;
  const startText = String(previousEntry.entry_date);
  const endText = String(entry.entry_date);
  const days = daysBetween(startText, endText);
  if (!days) return 0;
  const balance = Number(previousEntry.running_balance ?? 0);
  let total = 0;
  const cursor = new Date(`${startText}T00:00:00Z`);
  for (let index = 0; index < days; index += 1) {
    cursor.setUTCDate(cursor.getUTCDate() + 1);
    const rate = effectiveRateOn(isoDate(cursor), rateChanges);
    total += (balance * rate) / 36500;
  }
  return total;
}

function ledgerPeriodKey(entryDate: string, period: string) {
  const [year, monthText] = entryDate.split("-");
  const month = Number(monthText || "1");
  if (period === "annual") return year;
  if (period === "quarterly") return `${year} Q${Math.ceil(month / 3)}`;
  return `${year}-${monthText}`;
}

function summarizeLedgerByPeriod(
  entries: ResourceRecord[],
  period: string,
  rateChanges: ResourceRecord[],
) {
  const summaries: Array<{
    key: string;
    opening: number;
    increases: number;
    payments: number;
    interest: number;
    closing: number;
  }> = [];
  for (const [index, entry] of entries.entries()) {
    const key = ledgerPeriodKey(String(entry.entry_date), period);
    let summary = summaries.find((candidate) => candidate.key === key);
    if (!summary) {
      const previousClosing = summaries.at(-1)?.closing ?? 0;
      summary = {
        key,
        opening: previousClosing,
        increases: 0,
        payments: 0,
        interest: 0,
        closing: previousClosing,
      };
      summaries.push(summary);
    }
    const amount = Number(entry.amount ?? 0);
    if (isBalanceReducingEntry(entry)) summary.payments += amount;
    else summary.increases += amount;
    summary.interest += isInterestEntry(entry)
      ? amount
      : accruedInterestBetween(entries[index - 1], entry, rateChanges);
    summary.closing = Number(entry.running_balance ?? summary.closing);
  }
  return summaries;
}

function LoanMovementTable({
  entries,
  allEntries,
  rateChanges,
  currency,
  emptyText,
  variant = "full",
  interestMode = "automatic",
}: {
  entries: ResourceRecord[];
  allEntries?: ResourceRecord[];
  rateChanges: ResourceRecord[];
  currency: string;
  emptyText: string;
  variant?: "full" | "credits" | "debits" | "interest";
  interestMode?: string;
}) {
  if (!entries.length) return <p className="empty-state">{emptyText}</p>;
  const timeline = allEntries ?? entries;
  const isFull = variant === "full";
  const isInterestOnly = variant === "interest";
  const showInterestRate = isInterestOnly && interestMode === "automatic";
  return (
    <div className="loan-ledger-table-wrap">
      <table className="loan-ledger-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Description</th>
            {isInterestOnly && <th>Interest charged type</th>}
            {!isInterestOnly && variant !== "debits" && <th>Credit / taken</th>}
            {!isInterestOnly && variant !== "credits" && <th>Debit / payment</th>}
            {showInterestRate && <th>Interest %</th>}
            {isInterestOnly && <th>Interest amount</th>}
            {isFull && <th>Interest %</th>}
            {isFull && <th>Interest amount</th>}
            {isFull && <th>Balance</th>}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const entryCurrency = String(entry.currency ?? currency);
            const isTaken = isLoanTakenEntry(entry);
            const isPayment = isLoanPaymentEntry(entry);
            const interestEntry = isInterestEntry(entry);
            const entryIndex = timeline.findIndex(
              (candidate) => String(candidate.id) === String(entry.id),
            );
            const previousEntry =
              entryIndex > 0 ? timeline[entryIndex - 1] : undefined;
            const rateForEntry = effectiveRateOn(
              String(entry.entry_date),
              rateChanges,
            );
            const accruedInterest = accruedInterestBetween(
              previousEntry,
              entry,
              rateChanges,
            );
            const interestAmount = interestEntry
              ? Number(entry.amount ?? 0)
              : accruedInterest;
            return (
              <tr key={String(entry.id)}>
                <td>{String(entry.entry_date)}</td>
                <td>{ledgerTypeLabel(entry.entry_type)}</td>
                <td>{String(entry.description)}</td>
                {isInterestOnly && (
                  <td>
                    {interestMode === "automatic"
                      ? "Automatic calculation"
                      : interestMode === "none"
                        ? "No interest"
                        : "Manual posting"}
                  </td>
                )}
                {!isInterestOnly && variant !== "debits" && (
                  <td>
                    {variant === "credits" || isTaken
                      ? money(entry.amount, entryCurrency)
                      : "—"}
                  </td>
                )}
                {!isInterestOnly && variant !== "credits" && (
                  <td>
                    {variant === "debits" || isPayment
                      ? money(entry.amount, entryCurrency)
                      : "—"}
                  </td>
                )}
                {showInterestRate && (
                  <td>
                    {rateForEntry ? `${rateForEntry.toFixed(2)}%` : "—"}
                  </td>
                )}
                {isInterestOnly && <td>{money(interestAmount, entryCurrency)}</td>}
                {isFull && (
                  <td>
                    {rateForEntry ? `${rateForEntry.toFixed(2)}%` : "—"}
                  </td>
                )}
                {isFull && <td>{money(interestAmount, entryCurrency)}</td>}
                {isFull && <td>{money(entry.running_balance, entryCurrency)}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PlanningAnalysis({
  path,
  analytics,
  items,
  insuranceTransactions,
  onEditItem,
  onDeleteItem,
  onUploadLoanDocument,
  onUnlinkLoanDocument,
  onUploadInsuranceDocument,
  onUnlinkInsuranceDocument,
  onViewLoanDocument,
  onSaveLoanRate,
  onDeleteLoanRate,
  onSaveLoanSettings,
}: {
  path: string;
  analytics: Record<string, unknown>;
  items: ResourceRecord[];
  insuranceTransactions: Record<number, ResourceRecord[]>;
  onEditItem?: (item: ResourceRecord) => void;
  onDeleteItem?: (id: number) => void;
  onUploadLoanDocument?: (loanId: number, formData: FormData) => Promise<void>;
  onUnlinkLoanDocument?: (loanId: number, documentId: number) => Promise<void>;
  onUploadInsuranceDocument?: (
    policyId: number,
    formData: FormData,
  ) => Promise<void>;
  onUnlinkInsuranceDocument?: (
    policyId: number,
    documentId: number,
  ) => Promise<void>;
  onViewLoanDocument?: (documentId: number) => Promise<void>;
  onSaveLoanRate?: (
    loanId: number,
    body: Record<string, unknown>,
    rateId?: number,
  ) => Promise<void>;
  onDeleteLoanRate?: (loanId: number, rateId: number) => Promise<void>;
  onSaveLoanSettings?: (
    loan: ResourceRecord,
    values: Record<string, unknown>,
  ) => Promise<void>;
}) {
  const [loanTabsById, setLoanTabsById] = useState<Record<number, string>>({});
  const [expandedLoans, setExpandedLoans] = useState<Record<number, boolean>>({});
  const [ledgerPeriodsById, setLedgerPeriodsById] = useState<
    Record<number, string>
  >({});
  const [interestAsOfDate, setInterestAsOfDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [interestSummaries, setInterestSummaries] = useState<
    Record<number, ResourceRecord>
  >({});
  const [interestMessage, setInterestMessage] = useState("");

  async function loadInterestSummary(loanId: number, asOf = interestAsOfDate) {
    try {
      const summary = await api.loanInterestAsOf(loanId, asOf);
      setInterestSummaries((current) => ({ ...current, [loanId]: summary }));
      setInterestMessage("");
    } catch (error) {
      setInterestMessage(
        error instanceof Error ? error.message : "Could not calculate interest",
      );
    }
  }
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
    const reportingCurrency = String(analytics.base_currency ?? "EUR");
    const loanTotalFromRows = loans.reduce(
      (sum, loan) => sum + Number(loan.total_loan_base ?? 0),
      0,
    );
    const repaidTotalFromRows = loans.reduce(
      (sum, loan) => sum + Number(loan.total_repaid_base ?? 0),
      0,
    );
    const interestTotalFromRows = loans.reduce(
      (sum, loan) => sum + Number(loan.total_interest_posted_base ?? 0),
      0,
    );
    const totalLoanBase =
      Number(analytics.total_loan ?? 0) || loanTotalFromRows;
    const totalRepaidBase =
      Number(analytics.total_repaid ?? 0) || repaidTotalFromRows;
    const totalInterestBase =
      Number(analytics.total_interest_posted ?? 0) || interestTotalFromRows;
    return (
      <>
      <section className="planning-analysis debt-summary-panel">
        <div className="planning-heading">
          <div>
            <p className="eyebrow">Planning analysis</p>
            <h3>Debt summary</h3>
          </div>
          <span className="analysis-status">
            {items.length} loan{items.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="analysis-metrics debt-summary-metrics">
          <div className="analysis-metric">
            <span>Total loan</span>
            <strong>{money(totalLoanBase, reportingCurrency)}</strong>
            <small>All loan taken amounts converted</small>
          </div>
          <div className="analysis-metric">
            <span>Total repaid</span>
            <strong>{money(totalRepaidBase, reportingCurrency)}</strong>
            <small>All repayments converted</small>
          </div>
          <div className="analysis-metric">
            <span>Total interest paid</span>
            <strong>
              {money(totalInterestBase, reportingCurrency)}
            </strong>
            <small>Posted interest converted</small>
          </div>
          <div className="analysis-metric">
            <span>Total balance</span>
            <strong>{money(analytics.total_balance, reportingCurrency)}</strong>
            <small>Remaining debt converted</small>
          </div>
        </div>
      </section>
      <section className="planning-analysis loan-accounts-panel">
        <div className="analysis-section">
          <h4>Loan Accounts</h4>
          <div className="loan-outlook-list">
            {loans.map((loan) => {
              const item = items.find(
                (candidate) => Number(candidate.id) === Number(loan.id),
              );
              const rateChanges = (
                Array.isArray(item?.interest_rate_changes)
                  ? item?.interest_rate_changes
                  : []
              ) as ResourceRecord[];
              const ledgerEntries = (
                Array.isArray(item?.ledger_entries) ? item?.ledger_entries : []
              ) as ResourceRecord[];
              const balanceIncreaseEntries = ledgerEntries.filter(
                (entry) => isLoanTakenEntry(entry),
              );
              const balanceReductionEntries = ledgerEntries.filter((entry) =>
                isLoanPaymentEntry(entry),
              );
              const postedInterestEntries = ledgerEntries.filter((entry) =>
                isInterestEntry(entry),
              );
              const linkedDocuments = (
                Array.isArray(item?.documents) ? item?.documents : []
              ) as ResourceRecord[];
              const direction =
                String(item?.direction ?? loan.direction ?? "borrowed") === "lent"
                  ? "Lent out"
                  : "Borrowed";
              const currency = String(item?.currency ?? "EUR");
              const interestSummary =
                interestSummaries[Number(item?.id ?? loan.id)];
              const interestSegments = (
                Array.isArray(interestSummary?.segments)
                  ? interestSummary?.segments
                  : []
              ) as ResourceRecord[];
              const loanId = Number(item?.id ?? loan.id);
              const loanTab = loanTabsById[loanId] ?? "overview";
              const interestMode = String(item?.interest_mode ?? "manual");
              const usesAutomaticInterest = interestMode === "automatic";
              const ledgerPeriod = ledgerPeriodsById[loanId] ?? "monthly";
              const ledgerSummaries = summarizeLedgerByPeriod(
                ledgerEntries,
                ledgerPeriod,
                rateChanges,
              );
              const isExpanded = expandedLoans[loanId] ?? false;
              const loanKind = loanTypeLabel(item?.loan_type);
              const loanTabs = [
                ["overview", "Overview"],
                ["credits", "Credits / taken"],
                ["debits", "Debits / payments"],
                ["interest", "Interest"],
                ["ledger", "Ledger"],
                ["documents", "Documents"],
                ["reconciliation", "Reconciliation"],
                ["settings", "Settings"],
              ];
              return (
                <article
                  className={`loan-outlook-card ${
                    isExpanded ? "expanded" : "collapsed"
                  }`}
                  key={String(loan.id)}
                >
                  <div className="loan-outlook-title">
                    <div className="loan-name-cell">
                      <button
                        aria-expanded={isExpanded}
                        className="loan-name-button"
                        onClick={() =>
                          setExpandedLoans((current) => ({
                            ...current,
                            [loanId]: !(current[loanId] ?? false),
                          }))
                        }
                        type="button"
                      >
                        {String(loan.lender)}
                      </button>
                      <span>
                        {direction} · {loanKind}
                      </span>
                    </div>
                    <div className="loan-summary-metrics">
                      <span>
                        <small>Total loan</small>
                        <strong>
                          {money(item?.total_borrowed ?? loan.total_loan, currency)}
                        </strong>
                      </span>
                      <span>
                        <small>Total repaid</small>
                        <strong>
                          {money(item?.total_repaid ?? loan.total_repaid, currency)}
                        </strong>
                      </span>
                      <span>
                        <small>Interest paid</small>
                        <strong>
                          {money(
                            item?.total_interest_posted ??
                              loan.total_interest_posted,
                            currency,
                          )}
                        </strong>
                      </span>
                      <span>
                        <small>Balance</small>
                        <strong>{money(item?.current_balance, currency)}</strong>
                      </span>
                    </div>
                    {Number(item?.payments_applied ?? 0) > 0 && (
                      <small>
                        {money(item?.payments_applied, currency)} reduced by{" "}
                        {String(item?.matched_transaction_count ?? 0)} validated
                        payment(s)
                      </small>
                    )}
                    <div className="loan-row-actions">
                      {item && onEditItem && (
                        <button
                          className="secondary-button compact-action"
                          onClick={() => onEditItem(item)}
                          type="button"
                        >
                          Edit
                        </button>
                      )}
                      {item && onDeleteItem && (
                        <button
                          className="secondary-button compact-action danger"
                          onClick={() => onDeleteItem(Number(item.id))}
                          type="button"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                  {isExpanded && (
                  <>
                  <div className="loan-detail-tabs" role="tablist">
                    {loanTabs.map(([key, label]) => (
                      <button
                        className={loanTab === key ? "active" : ""}
                        key={key}
                        onClick={() =>
                          setLoanTabsById((current) => ({
                            ...current,
                            [loanId]: key,
                          }))
                        }
                        type="button"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {loanTab === "overview" && (
                  <div className="loan-outlook-details">
                    <span>
                      <small>Principal balance</small>
                      <strong>{money(item?.principal_balance, currency)}</strong>
                    </span>
                    <span>
                      <small>Posted interest balance</small>
                      <strong>{money(item?.posted_interest_balance, currency)}</strong>
                    </span>
                    <span>
                      <small>Unposted accumulated interest</small>
                      <strong>
                        {money(item?.accumulated_interest_as_of_today, currency)}
                      </strong>
                    </span>
                    <span>
                      <small>Total outstanding today</small>
                      <strong>{money(item?.total_payable_today, currency)}</strong>
                    </span>
                    <span>
                      <small>Total borrowed</small>
                      <strong>{money(item?.total_borrowed, currency)}</strong>
                    </span>
                    <span>
                      <small>Total repaid</small>
                      <strong>{money(item?.total_repaid, currency)}</strong>
                    </span>
                    <span>
                      <small>Total interest posted</small>
                      <strong>{money(item?.total_interest_posted, currency)}</strong>
                    </span>
                    <span>
                      <small>Effective rate</small>
                      <strong>
                        {usesAutomaticInterest
                          ? `${Number(item?.effective_interest_rate ?? 0).toFixed(2)}%`
                          : interestMode === "none"
                            ? "No interest"
                            : "Manual postings"}
                      </strong>
                    </span>
                  </div>
                  )}
                  {Boolean(loan.warning) && (
                    <p className="loan-warning">{String(loan.warning)}</p>
                  )}
                  {loanTab === "credits" && (
                  <details className="loan-payment-audit" open>
                    <summary>
                      Credits / money received
                      <span>{balanceIncreaseEntries.length}</span>
                    </summary>
                    <LoanMovementTable
                      entries={balanceIncreaseEntries}
                      allEntries={ledgerEntries}
                      rateChanges={rateChanges}
                      currency={currency}
                      emptyText="No loan-taken or balance-increasing entries have been added yet."
                      variant="credits"
                    />
                  </details>
                  )}
                  {loanTab === "debits" && (
                  <details className="loan-payment-audit" open>
                    <summary>
                      Debits / payments made
                      <span>{balanceReductionEntries.length}</span>
                    </summary>
                    <LoanMovementTable
                      entries={balanceReductionEntries}
                      allEntries={ledgerEntries}
                      rateChanges={rateChanges}
                      currency={currency}
                      emptyText="No payment or balance-reducing entries have been added yet."
                      variant="debits"
                    />
                  </details>
                  )}
                  {loanTab === "interest" && !usesAutomaticInterest && (
                    <p className="loan-warning">
                      {interestMode === "none"
                        ? "No interest is configured for this loan."
                        : "Manual interest mode is active. Posted interest entries below are used directly; automatic rate calculation is skipped."}
                    </p>
                  )}
                  {loanTab === "interest" && usesAutomaticInterest && (
                  <div className="loan-interest-asof-panel">
                    <div className="loan-interest-asof-header">
                      <div>
                        <strong>Accumulated interest as on date</strong>
                        <span>
                          Uses daily balance and rate history:
                          balance × annual rate × days / 365.
                        </span>
                      </div>
                      <form
                        action={async (formData) => {
                          const asOf = String(formData.get("as_of"));
                          setInterestAsOfDate(asOf);
                          await loadInterestSummary(
                            Number(item?.id ?? loan.id),
                            asOf,
                          );
                        }}
                      >
                        <DateField
                          name="as_of"
                          defaultValue={interestAsOfDate}
                          required
                        />
                        <button type="submit">Calculate</button>
                      </form>
                    </div>
                    {interestMessage && (
                      <span className="form-message">{interestMessage}</span>
                    )}
                    {interestSummary ? (
                      <>
                        <div className="loan-interest-metrics">
                          <span>
                            <small>Outstanding principal</small>
                            <strong>
                              {money(
                                interestSummary.outstanding_principal,
                                String(interestSummary.currency ?? currency),
                              )}
                            </strong>
                          </span>
                          <span>
                            <small>Posted interest</small>
                            <strong>
                              {money(
                                interestSummary.posted_interest,
                                String(interestSummary.currency ?? currency),
                              )}
                            </strong>
                          </span>
                          <span>
                            <small>Unposted accumulated interest</small>
                            <strong>
                              {money(
                                interestSummary.unposted_accumulated_interest,
                                String(interestSummary.currency ?? currency),
                              )}
                            </strong>
                          </span>
                          <span>
                            <small>Total payable as on date</small>
                            <strong>
                              {money(
                                interestSummary.total_payable,
                                String(interestSummary.currency ?? currency),
                              )}
                            </strong>
                          </span>
                        </div>
                        {interestSegments.length > 0 && (
                          <div className="loan-ledger-table-wrap">
                            <table className="loan-ledger-table">
                              <thead>
                                <tr>
                                  <th>Period</th>
                                  <th>Balance</th>
                                  <th>Days</th>
                                  <th>Rate</th>
                                  <th>Interest</th>
                                </tr>
                              </thead>
                              <tbody>
                                {interestSegments.map((segment) => (
                                  <tr
                                    key={`${String(segment.period_start)}-${String(
                                      segment.period_end,
                                    )}-${String(segment.balance)}`}
                                  >
                                    <td>
                                      {String(segment.period_start)} to{" "}
                                      {String(segment.period_end)}
                                    </td>
                                    <td>
                                      {money(
                                        segment.balance,
                                        String(interestSummary.currency ?? currency),
                                      )}
                                    </td>
                                    <td>{String(segment.days)}</td>
                                    <td>
                                      {Number(segment.annual_rate ?? 0).toFixed(2)}%
                                    </td>
                                    <td>
                                      {money(
                                        segment.interest,
                                        String(interestSummary.currency ?? currency),
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="empty-state">
                        Choose a date and calculate to see principal, posted
                        interest, unposted interest, and total payable.
                      </p>
                    )}
                  </div>
                  )}
                  {loanTab === "interest" && (
                  <details className="loan-payment-audit" open>
                    <summary>
                      Posted interest ledger entries
                      <span>{postedInterestEntries.length}</span>
                    </summary>
                    <LoanMovementTable
                      entries={postedInterestEntries}
                      allEntries={ledgerEntries}
                      rateChanges={rateChanges}
                      currency={currency}
                      emptyText="No posted interest entries have been added yet."
                      interestMode={interestMode}
                      variant="interest"
                    />
                  </details>
                  )}
                  {loanTab === "interest" && usesAutomaticInterest && (
                  <details className="loan-rate-audit" open>
                    <summary>
                      Interest rate changes
                      <span>{rateChanges.length}</span>
                    </summary>
                    <div className="loan-rate-list">
                      {rateChanges.map((rate) => (
                        <article className="loan-rate-row" key={String(rate.id)}>
                          <div>
                            <strong>{String(rate.effective_date)}</strong>
                            <span>{String(rate.notes || "No notes")}</span>
                          </div>
                          <strong>{Number(rate.interest_rate ?? 0).toFixed(2)}%</strong>
                          {onDeleteLoanRate && (
                            <button
                              className="text-button danger"
                              type="button"
                              onClick={() =>
                                onDeleteLoanRate(
                                  Number(item?.id ?? loan.id),
                                  Number(rate.id),
                                )
                              }
                            >
                              Delete
                            </button>
                          )}
                        </article>
                      ))}
                      {onSaveLoanRate && (
                        <form
                          className="loan-rate-form"
                          action={async (formData) => {
                            await onSaveLoanRate(Number(item?.id ?? loan.id), {
                              effective_date: formData.get("effective_date"),
                              interest_rate: formData.get("interest_rate"),
                              notes: formData.get("notes") || null,
                            });
                          }}
                        >
                          <label>
                            Effective date
                            <DateField name="effective_date" required />
                          </label>
                          <label>
                            Rate %
                            <input
                              name="interest_rate"
                              required
                              step="any"
                              type="number"
                            />
                          </label>
                          <label>
                            Notes
                            <input name="notes" placeholder="Agreed with lender" />
                          </label>
                          <button type="submit">Add rate change</button>
                        </form>
                      )}
                    </div>
                  </details>
                  )}
                  {loanTab === "ledger" && (
                  <details className="loan-ledger-audit" open>
                    <summary>
                      Loan ledger
                      <span>{ledgerEntries.length}</span>
                    </summary>
                    {ledgerEntries.length ? (
                      <div className="loan-ledger-stack">
                        <LoanMovementTable
                          entries={ledgerEntries}
                          allEntries={ledgerEntries}
                          rateChanges={rateChanges}
                          currency={currency}
                          emptyText="No loan ledger movements have been added yet."
                        />
                        <div className="loan-ledger-summary-header">
                          <strong>Balance summary</strong>
                          <select
                            value={ledgerPeriod}
                            onChange={(event) =>
                              setLedgerPeriodsById((current) => ({
                                ...current,
                                [loanId]: event.target.value,
                              }))
                            }
                          >
                            <option value="monthly">Monthly</option>
                            <option value="quarterly">Quarterly</option>
                            <option value="annual">Annual</option>
                          </select>
                        </div>
                        <div className="loan-ledger-table-wrap">
                          <table className="loan-ledger-table">
                            <thead>
                              <tr>
                                <th>Period</th>
                                <th>Opening</th>
                                <th>Credits / taken</th>
                                <th>Debits / payments</th>
                                <th>Interest</th>
                                <th>Closing balance</th>
                              </tr>
                            </thead>
                            <tbody>
                              {ledgerSummaries.map((summary) => (
                                <tr key={summary.key}>
                                  <td>{summary.key}</td>
                                  <td>{money(summary.opening, currency)}</td>
                                  <td>{money(summary.increases, currency)}</td>
                                  <td>{money(summary.payments, currency)}</td>
                                  <td>{money(summary.interest, currency)}</td>
                                  <td>{money(summary.closing, currency)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <div className="loan-ledger-total">
                          <span>Total taken / interest added</span>
                          <strong>{money(item?.ledger_total, currency)}</strong>
                        </div>
                      </div>
                    ) : (
                      <p className="empty-state">
                        No loan ledger movements have been added yet.
                      </p>
                    )}
                  </details>
                  )}
                  {loanTab === "documents" && (
                    <div className="loan-documents-panel">
                      <form
                        className="loan-document-upload"
                        action={async (formData) => {
                          if (!onUploadLoanDocument) return;
                          await onUploadLoanDocument(loanId, formData);
                        }}
                      >
                        <div>
                          <strong>Attach loan document</strong>
                          <span>
                            Upload loan agreements, payoff letters, or statements.
                            The file is also stored in the Documents library.
                          </span>
                        </div>
                        <label className="loan-file-field">
                          File
                          <input name="file" required type="file" />
                        </label>
                        <label>
                          Notes
                          <input name="notes" placeholder="Optional document note" />
                        </label>
                        <button type="submit">Upload and attach</button>
                      </form>
                      {linkedDocuments.length ? (
                        <div className="loan-document-list">
                          {linkedDocuments.map((document) => (
                            <article
                              className="loan-document-row"
                              key={String(document.id)}
                            >
                              <div>
                                <strong>{String(document.file_name)}</strong>
                                <span>
                                  {String(document.document_type)} ·{" "}
                                  {String(document.status)}
                                </span>
                              </div>
                              <div className="loan-row-actions">
                                <button
                                  className="secondary-button compact-action"
                                  onClick={() =>
                                    onViewLoanDocument?.(Number(document.id))
                                  }
                                  type="button"
                                >
                                  View
                                </button>
                                {onUnlinkLoanDocument && (
                                  <button
                                    className="secondary-button compact-action danger"
                                    onClick={() =>
                                      onUnlinkLoanDocument(
                                        loanId,
                                        Number(document.id),
                                      )
                                    }
                                    type="button"
                                  >
                                    Unlink
                                  </button>
                                )}
                              </div>
                            </article>
                          ))}
                        </div>
                      ) : (
                        <p className="empty-state">
                          No documents attached to this loan yet.
                        </p>
                      )}
                    </div>
                  )}
                  {loanTab === "reconciliation" && (
                    <div className="loan-placeholder-panel">
                      <strong>Reconciliation</strong>
                      <span>
                        System balance is {money(item?.current_balance, currency)}.
                        Compare this with the lender statement and add an adjustment
                        entry for any agreed difference.
                      </span>
                    </div>
                  )}
                  {loanTab === "settings" && (
                    <form
                      className="loan-rate-form loan-settings-form"
                      action={async (formData) => {
                        if (!item || !onSaveLoanSettings) return;
                        await onSaveLoanSettings(item, {
                          interest_calculation_basis: formData.get(
                            "interest_calculation_basis",
                          ),
                          interest_posting_frequency: formData.get(
                            "interest_posting_frequency",
                          ),
                          payment_allocation_rule: formData.get(
                            "payment_allocation_rule",
                          ),
                          monthly_payment: formData.get("monthly_payment") || "0",
                          end_date: formData.get("end_date") || null,
                          status: formData.get("status"),
                        });
                      }}
                    >
                      <label>
                        Interest basis
                        <select
                          name="interest_calculation_basis"
                          defaultValue={String(
                            item?.interest_calculation_basis ?? "daily_balance",
                          )}
                        >
                          <option value="daily_balance">Daily balance</option>
                          <option value="monthly_balance">Monthly balance</option>
                          <option value="flat">Flat</option>
                        </select>
                      </label>
                      <label>
                        Posting frequency
                        <select
                          name="interest_posting_frequency"
                          defaultValue={String(
                            item?.interest_posting_frequency ?? "manual",
                          )}
                        >
                          <option value="manual">Manual</option>
                          <option value="monthly">Monthly</option>
                          <option value="quarterly">Quarterly</option>
                          <option value="yearly">Yearly</option>
                        </select>
                      </label>
                      <label>
                        Payment allocation
                        <select
                          name="payment_allocation_rule"
                          defaultValue={String(
                            item?.payment_allocation_rule ?? "interest_first",
                          )}
                        >
                          <option value="interest_first">Interest first</option>
                          <option value="principal_first">Principal first</option>
                          <option value="manual_split">Manual split</option>
                        </select>
                      </label>
                      <label>
                        Monthly payment
                        <input
                          name="monthly_payment"
                          type="number"
                          step="any"
                          defaultValue={String(item?.monthly_payment ?? 0)}
                        />
                      </label>
                      <label>
                        End date
                        <DateField
                          name="end_date"
                          defaultValue={String(item?.end_date ?? "")}
                        />
                      </label>
                      <label>
                        Status
                        <select
                          name="status"
                          defaultValue={String(item?.status ?? "active")}
                        >
                          <option value="active">Active</option>
                          <option value="closed">Closed</option>
                          <option value="disputed">Disputed</option>
                        </select>
                      </label>
                      <button type="submit">Save settings</button>
                    </form>
                  )}
                  </>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      </section>
      </>
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
      <>
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
      </section>
      <section className="planning-analysis insurance-accounts-panel">
        <div className="analysis-section">
          <h4>Insurance Accounts</h4>
          <div className="loan-outlook-list">
            {policies.map((policy) => {
              const policyId = Number(policy.id);
              const item = items.find(
                (candidate) => Number(candidate.id) === policyId,
              );
              const payments =
                insuranceTransactions[policyId] ?? [];
              const linkedDocuments = (
                Array.isArray(item?.documents) ? item?.documents : []
              ) as ResourceRecord[];
              const isExpanded = expandedLoans[policyId] ?? false;
              const policyTab = loanTabsById[policyId] ?? "overview";
              const currency = String(policy.currency ?? item?.currency ?? "EUR");
              const policyBaseCurrency = reportingCurrency;
              const provider = String(policy.provider ?? item?.provider ?? "Policy");
              const policyType = String(
                policy.policy_type ?? item?.policy_type ?? "Insurance",
              );
              const policyTabs = [
                ["overview", "Overview"],
                ["payments", "Payments"],
                ["documents", "Documents"],
                ["settings", "Settings"],
              ];
              return (
                <article
                  className={`loan-outlook-card insurance-policy-card ${
                    isExpanded ? "expanded" : "collapsed"
                  }`}
                  key={String(policy.id)}
                >
                  <div className="loan-outlook-title">
                    <div className="loan-name-cell">
                      <button
                        aria-expanded={isExpanded}
                        className="loan-name-button"
                        onClick={() =>
                          setExpandedLoans((current) => ({
                            ...current,
                            [policyId]: !(current[policyId] ?? false),
                          }))
                        }
                        type="button"
                      >
                        {provider}
                      </button>
                      <span>
                        {policyType} ·{" "}
                        {item?.is_active === false ? "Inactive" : "Active policy"}
                      </span>
                    </div>
                    <div className="insurance-main-metrics">
                      <span>
                        <small>Expected annually</small>
                        <strong>
                          {money(
                            policy.scheduled_annual_base ??
                              policy.scheduled_annual,
                            policyBaseCurrency,
                          )}
                        </strong>
                        {currency !== policyBaseCurrency && (
                          <em>
                            {money(policy.scheduled_annual, currency)} native
                          </em>
                        )}
                      </span>
                      <span>
                        <small>Paid this month</small>
                        <strong>{money(policy.actual_month, currency)}</strong>
                      </span>
                      <span>
                        <small>Paid this year</small>
                        <strong>{money(policy.actual_year, currency)}</strong>
                      </span>
                    </div>
                    <div className="loan-row-actions">
                      {item && onEditItem && (
                        <button
                          className="secondary-button compact-action"
                          onClick={() => onEditItem(item)}
                          type="button"
                        >
                          Edit
                        </button>
                      )}
                      {onDeleteItem && (
                        <button
                          className="secondary-button compact-action danger"
                          onClick={() => onDeleteItem(policyId)}
                          type="button"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                  {isExpanded && (
                    <>
                    <div className="loan-tabs">
                      {policyTabs.map(([key, label]) => (
                        <button
                          className={policyTab === key ? "active" : ""}
                          key={key}
                          onClick={() =>
                            setLoanTabsById((current) => ({
                              ...current,
                              [policyId]: key,
                            }))
                          }
                          type="button"
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    {policyTab === "overview" && (
                      <div className="loan-overview-grid insurance-overview-grid">
                        <div>
                          <small>Coverage amount</small>
                          <strong>
                            {money(item?.coverage_amount ?? 0, currency)}
                          </strong>
                        </div>
                        <div>
                          <small>Premium amount</small>
                          <strong>
                            {money(item?.premium_amount ?? 0, currency)}
                          </strong>
                        </div>
                        <div>
                          <small>Frequency</small>
                          <strong>
                            {String(item?.premium_frequency ?? "monthly")}
                          </strong>
                        </div>
                        <div>
                          <small>Policy number</small>
                          <strong>{String(item?.policy_number ?? "—")}</strong>
                        </div>
                        <div>
                          <small>Start date</small>
                          <strong>{String(item?.start_date ?? "—")}</strong>
                        </div>
                        <div>
                          <small>End date</small>
                          <strong>{String(item?.end_date ?? "—")}</strong>
                        </div>
                      </div>
                    )}
                    {policyTab === "payments" && (
                      <div className="loan-payment-list">
                        {payments.length ? payments.map((payment) => (
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
                        )) : (
                          <p className="empty-state">
                            No validated transactions have been matched to this
                            policy.
                          </p>
                        )}
                      </div>
                    )}
                    {policyTab === "documents" && (
                      <div className="loan-documents-panel">
                        <form
                          className="loan-document-upload"
                          action={async (formData) => {
                            if (!onUploadInsuranceDocument) return;
                            await onUploadInsuranceDocument(policyId, formData);
                          }}
                        >
                          <div>
                            <strong>Attach insurance document</strong>
                            <span>
                              Upload policy contracts, premium notices, claim
                              documents, or insurer letters.
                            </span>
                          </div>
                          <label className="loan-file-field">
                            File
                            <input name="file" required type="file" />
                          </label>
                          <label>
                            Notes
                            <input name="notes" placeholder="Optional document note" />
                          </label>
                          <button type="submit">Upload and attach</button>
                        </form>
                        {linkedDocuments.length ? (
                          <div className="loan-document-list">
                            {linkedDocuments.map((document) => (
                              <article
                                className="loan-document-row"
                                key={String(document.id)}
                              >
                                <div>
                                  <strong>{String(document.file_name)}</strong>
                                  <span>
                                    {String(document.document_type)} ·{" "}
                                    {String(document.status)}
                                  </span>
                                </div>
                                <div className="loan-row-actions">
                                  <button
                                    className="secondary-button compact-action"
                                    onClick={() =>
                                      onViewLoanDocument?.(Number(document.id))
                                    }
                                    type="button"
                                  >
                                    View
                                  </button>
                                  {onUnlinkInsuranceDocument && (
                                    <button
                                      className="secondary-button compact-action danger"
                                      onClick={() =>
                                        onUnlinkInsuranceDocument(
                                          policyId,
                                          Number(document.id),
                                        )
                                      }
                                      type="button"
                                    >
                                      Unlink
                                    </button>
                                  )}
                                </div>
                              </article>
                            ))}
                          </div>
                        ) : (
                          <p className="empty-state">
                            No documents attached to this policy yet.
                          </p>
                        )}
                      </div>
                    )}
                    {policyTab === "settings" && (
                      <div className="loan-overview-grid insurance-overview-grid">
                        <div>
                          <small>Beneficiaries</small>
                          <strong>{String(item?.beneficiaries ?? "—")}</strong>
                        </div>
                        <div>
                          <small>Notes</small>
                          <strong>{String(item?.notes ?? "—")}</strong>
                        </div>
                        <div>
                          <small>Status</small>
                          <strong>
                            {item?.is_active === false ? "Inactive" : "Active"}
                          </strong>
                        </div>
                      </div>
                    )}
                    </>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      </section>
      </>
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
  baseCurrency = "EUR",
}: ResourceManagerProps) {
  const [items, setItems] = useState<ResourceRecord[]>([]);
  const [message, setMessage] = useState("");
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(null);
  const [insuranceTransactions, setInsuranceTransactions] = useState<
    Record<number, ResourceRecord[]>
  >({});
  const [editingItem, setEditingItem] = useState<ResourceRecord | null>(null);
  const [documentViewer, setDocumentViewer] = useState<DocumentRecord | null>(
    null,
  );
  const [showForm, setShowForm] = useState(false);
  const [loanInterestMode, setLoanInterestMode] = useState("manual");
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

  useEffect(() => {
    if (path === "loans") {
      setLoanInterestMode(String(editingItem?.interest_mode ?? "manual"));
    }
  }, [path, editingItem]);

  async function save(formData: FormData) {
    try {
      let values = formValues(formData, fields);
      if (path === "loans") {
        const interestMode = String(
          values.interest_mode ?? editingItem?.interest_mode ?? "manual",
        );
        const openingBalance = String(
          editingItem?.current_balance ?? values.current_balance ?? "0",
        );
        values = loanSettingDefaults({
          ...editingItem,
          ...values,
          interest_mode: interestMode,
          interest_rate:
            interestMode === "automatic"
              ? (values.interest_rate ?? editingItem?.interest_rate ?? "0")
              : "0",
          currency:
            values.currency ?? editingItem?.currency ?? baseCurrency,
          loan_type:
            values.loan_type ?? editingItem?.loan_type ?? "personal_running",
          current_balance: editingItem ? editingItem.current_balance : openingBalance,
          original_amount: editingItem
            ? (editingItem.original_amount ?? editingItem.recorded_balance ?? openingBalance)
            : openingBalance,
        });
      }
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

  async function saveLoanRate(
    loanId: number,
    body: Record<string, unknown>,
    rateId?: number,
  ) {
    try {
      if (rateId) {
        await api.updateLoanInterestRate(loanId, rateId, body);
        setMessage("Interest rate change updated.");
      } else {
        await api.createLoanInterestRate(loanId, body);
        setMessage("Interest rate change added.");
      }
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not save rate change",
      );
    }
  }

  async function deleteLoanRate(loanId: number, rateId: number) {
    try {
      const confirmed = await confirmAction({
        title: "Delete interest rate change?",
        message:
          "Delete this interest rate change? Loan projections will be recalculated.",
        confirmLabel: "Delete rate change",
      });
      if (!confirmed) return;
      await api.deleteLoanInterestRate(loanId, rateId);
      setMessage("Interest rate change deleted.");
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not delete rate change",
      );
    }
  }

  async function uploadLoanDocument(loanId: number, formData: FormData) {
    try {
      const file = formData.get("file");
      if (!(file instanceof File) || !file.name) {
        throw new Error("Choose a document file to attach.");
      }
      await api.uploadLoanDocument(
        loanId,
        file,
        String(formData.get("notes") || ""),
      );
      setMessage("Loan document uploaded and attached.");
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not attach document",
      );
    }
  }

  async function unlinkLoanDocument(loanId: number, documentId: number) {
    try {
      const confirmed = await confirmAction({
        title: "Unlink document?",
        message:
          "Remove this document from the loan? The uploaded file remains in the Documents library.",
        confirmLabel: "Unlink document",
      });
      if (!confirmed) return;
      await api.unlinkLoanDocument(loanId, documentId);
      setMessage("Document unlinked from loan.");
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not unlink document",
      );
    }
  }

  async function uploadInsuranceDocument(policyId: number, formData: FormData) {
    try {
      const file = formData.get("file");
      if (!(file instanceof File) || !file.name) {
        throw new Error("Choose an insurance document to attach.");
      }
      await api.uploadInsuranceDocument(
        policyId,
        file,
        String(formData.get("notes") || ""),
      );
      setMessage("Insurance document uploaded and attached.");
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not attach document",
      );
    }
  }

  async function unlinkInsuranceDocument(policyId: number, documentId: number) {
    try {
      const confirmed = await confirmAction({
        title: "Unlink document?",
        message:
          "Remove this document from the insurance policy? The uploaded file remains in the Documents library.",
        confirmLabel: "Unlink document",
      });
      if (!confirmed) return;
      await api.unlinkInsuranceDocument(policyId, documentId);
      setMessage("Document unlinked from insurance policy.");
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not unlink document",
      );
    }
  }

  async function viewLoanDocument(documentId: number) {
    try {
      setMessage("Opening document preview...");
      setDocumentViewer(await api.document(documentId));
      setMessage("");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not open document",
      );
    }
  }

  async function saveLoanSettings(
    loan: ResourceRecord,
    values: Record<string, unknown>,
  ) {
    try {
      const payload = loanSettingDefaults(values);
      await api.updateLoanSettings(Number(loan.id), payload);
      setMessage("Loan settings updated.");
      await load();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not update loan settings",
      );
    }
  }

  const visualAnalytics =
    analytics &&
    (path === "investments" || path === "loans" || path === "insurance") ? (
      <PlanningAnalysis
        path={path}
        analytics={analytics}
        items={items}
        insuranceTransactions={insuranceTransactions}
        onEditItem={
          path === "loans" || path === "insurance"
            ? (item) => {
                setEditingItem(item);
                setMessage("");
                setShowForm(true);
              }
            : undefined
        }
        onDeleteItem={
          path === "loans" || path === "insurance" ? remove : undefined
        }
        onUploadLoanDocument={
          path === "loans" ? uploadLoanDocument : undefined
        }
        onUnlinkLoanDocument={
          path === "loans" ? unlinkLoanDocument : undefined
        }
        onUploadInsuranceDocument={
          path === "insurance" ? uploadInsuranceDocument : undefined
        }
        onUnlinkInsuranceDocument={
          path === "insurance" ? unlinkInsuranceDocument : undefined
        }
        onViewLoanDocument={
          path === "loans" || path === "insurance" ? viewLoanDocument : undefined
        }
        onSaveLoanRate={path === "loans" ? saveLoanRate : undefined}
        onDeleteLoanRate={path === "loans" ? deleteLoanRate : undefined}
        onSaveLoanSettings={path === "loans" ? saveLoanSettings : undefined}
      />
    ) : null;

  const resourceForm = (
    <form
      key={editingItem ? `edit-${editingItem.id}` : "create"}
      ref={formRef}
      action={save}
      className="resource-form"
    >
      {fields.map((field) => {
        if (
          path === "loans" &&
          field.name === "interest_rate" &&
          loanInterestMode !== "automatic"
        ) {
          return null;
        }
        return (
        <label key={field.name}>
          {field.label}
          {field.type === "select" ? (
            <select
              name={field.name}
              required={field.required}
              onChange={
                path === "loans" && field.name === "interest_mode"
                  ? (event) => setLoanInterestMode(event.target.value)
                  : undefined
              }
              defaultValue={inputValue(field, editingItem, path, baseCurrency)}
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
              defaultValue={inputValue(field, editingItem, path, baseCurrency)}
            />
          ) : field.type === "date" ? (
            <DateField
              name={field.name}
              required={field.required}
              defaultValue={inputValue(field, editingItem, path, baseCurrency)}
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
              required={
                field.required ||
                (path === "loans" &&
                  field.name === "interest_rate" &&
                  loanInterestMode === "automatic")
              }
              readOnly={
                path === "loans" &&
                field.name === "current_balance" &&
                Boolean(editingItem)
              }
              defaultValue={inputValue(field, editingItem, path, baseCurrency)}
            />
          )}
          {field.helpText && (
            <small className="field-help">{field.helpText}</small>
          )}
        </label>
        );
      })}
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
                              isPlanningModule
                                ? ""
                                : `Editing ${String(item[columns[0].key])}.`,
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

  const documentViewerModal = documentViewer ? (
    <DocumentViewer
      document={documentViewer}
      onClose={() => setDocumentViewer(null)}
    />
  ) : null;

  if (isPlanningModule) {
    return (
      <>
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
        {path !== "loans" && path !== "insurance" && (
          <article className="panel planning-records-panel">{savedRecords}</article>
        )}
        {showForm && (
          <div
            className="investment-modal-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setShowForm(false);
                setEditingItem(null);
                setMessage("");
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
                    setMessage("");
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
      {documentViewerModal}
      </>
    );
  }

  return (
    <>
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
            insuranceTransactions={insuranceTransactions}
            onSaveLoanRate={path === "loans" ? saveLoanRate : undefined}
            onDeleteLoanRate={path === "loans" ? deleteLoanRate : undefined}
            onSaveLoanSettings={path === "loans" ? saveLoanSettings : undefined}
            onUploadInsuranceDocument={
              path === "insurance" ? uploadInsuranceDocument : undefined
            }
            onUnlinkInsuranceDocument={
              path === "insurance" ? unlinkInsuranceDocument : undefined
            }
            onViewLoanDocument={
              path === "insurance" ? viewLoanDocument : undefined
            }
          />
        )}
      </article>
    </section>
    {documentViewerModal}
    </>
  );
}
