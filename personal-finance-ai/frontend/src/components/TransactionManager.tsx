import { useMemo, useState } from "react";

import { api } from "../api";
import { categoryPresentation } from "../categoryPresentation";
import { confirmAction } from "../confirmAction";
import { AppIcon } from "../icons/IconRegistry";
import type { Account, Category, ResourceRecord, Transaction } from "../types";
import { DateField } from "./DateField";
import { DashboardPeriodPicker } from "./DashboardPeriodPicker";

type SortOrder =
  | "date_desc"
  | "date_asc"
  | "amount_desc"
  | "amount_asc"
  | "vendor_asc";

const LOAN_CATEGORY_NAMES = ["Loan", "Loan Repayment", "Loan Interest"];

function isLoanBalanceIncreaseCategory(categoryName: string | undefined) {
  return categoryName === "Loan" || categoryName === "Loan Interest";
}

function shiftMonth(period: string, offset: number) {
  const [year, month] = period.split("-").map(Number);
  const date = new Date(year, month - 1 + offset, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function money(value: number, currency: string) {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
  }).format(value);
}

function baseAmount(item: Transaction) {
  return Math.abs(Number(item.base_amount ?? item.amount));
}

export function TransactionManager({
  transactions,
  accounts,
  categories,
  loans,
  onChanged,
}: {
  transactions: Transaction[];
  accounts: Account[];
  categories: Category[];
  loans: ResourceRecord[];
  onChanged: () => void;
}) {
  const requestedTransaction = new URLSearchParams(window.location.search).get(
    "reviewTransaction",
  );
  const requestedTransactionId = requestedTransaction
    ? Number(requestedTransaction)
    : Number.NaN;
  const initialFocusedId =
    Number.isInteger(requestedTransactionId) && requestedTransactionId > 0
      ? requestedTransactionId
      : null;
  const [focusedTransactionId, setFocusedTransactionId] = useState<number | null>(
    initialFocusedId,
  );
  const [editing, setEditing] = useState<number | null>(initialFocusedId);
  const [search, setSearch] = useState("");
  const [month, setMonth] = useState("");
  const [accountId, setAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [loanId, setLoanId] = useState("");
  const [transactionType, setTransactionType] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("date_desc");
  const [message, setMessage] = useState("");
  const transactionAccounts = accounts.filter(
    (account) => account.type !== "loan",
  );
  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return transactions
      .filter(
        (item) =>
          item.is_validated &&
          (!focusedTransactionId || item.id === focusedTransactionId) &&
          (!term ||
            item.vendor.toLowerCase().includes(term) ||
            item.description.toLowerCase().includes(term)) &&
          (!month || item.transaction_date.startsWith(month)) &&
          (!accountId || item.account_id === Number(accountId)) &&
          (!categoryId ||
            (categoryId === "uncategorized"
              ? item.category_id === null
              : item.category_id === Number(categoryId))) &&
          (!loanId ||
            (loanId === "linked"
              ? item.linked_loan_id !== null
              : item.linked_loan_id === Number(loanId))) &&
          (!transactionType || item.transaction_type === transactionType),
      )
      .sort((left, right) => {
        if (sortOrder === "date_asc") {
          return left.transaction_date.localeCompare(right.transaction_date);
        }
        if (sortOrder === "amount_desc") {
          return Number(right.amount) - Number(left.amount);
        }
        if (sortOrder === "amount_asc") {
          return Number(left.amount) - Number(right.amount);
        }
        if (sortOrder === "vendor_asc") {
          return left.vendor.localeCompare(right.vendor);
        }
        return right.transaction_date.localeCompare(left.transaction_date);
      });
  }, [
    accountId,
    categoryId,
    focusedTransactionId,
    loanId,
    month,
    search,
    sortOrder,
    transactionType,
    transactions,
  ]);
  const filtersActive = Boolean(
    search ||
      month ||
      accountId ||
      categoryId ||
      loanId ||
      transactionType ||
      focusedTransactionId,
  );
  const currency =
    visible.find((item) => item.base_currency)?.base_currency ??
    transactions.find((item) => item.base_currency)?.base_currency ??
    accounts[0]?.currency ??
    "EUR";
  const totals = useMemo(
    () =>
      visible.reduce(
        (summary, item) => {
          const amount = baseAmount(item);
          if (item.transaction_type === "credit") {
            summary.income += amount;
          } else {
            summary.expenses += amount;
          }
          return summary;
        },
        { income: 0, expenses: 0 },
      ),
    [visible],
  );
  const expenseCategories = useMemo(() => {
    const totalsByCategory = new Map<
      string,
      { amount: number; category?: Category }
    >();
    visible
      .filter((item) => item.transaction_type === "debit")
      .forEach((item) => {
        const category = categories.find(
          (candidate) => candidate.id === item.category_id,
        );
        const name = category?.name ?? "Uncategorized";
        const current = totalsByCategory.get(name) ?? { amount: 0, category };
        current.amount += baseAmount(item);
        totalsByCategory.set(name, current);
      });
    return [...totalsByCategory.entries()]
      .map(([name, summary]) => ({ name, ...summary }))
      .sort((left, right) => right.amount - left.amount)
      .slice(0, 12);
  }, [categories, visible]);
  const maximumCategoryAmount = expenseCategories[0]?.amount ?? 1;
  const missingFxCount = visible.filter((item) => item.fx_rate_missing).length;

  function clearFocusedTransaction() {
    setFocusedTransactionId(null);
    setEditing(null);
    const target = new URL(window.location.href);
    target.searchParams.delete("reviewTransaction");
    window.history.replaceState(null, "", target);
  }

  function clearFilters() {
    setSearch("");
    setMonth("");
    setAccountId("");
    setCategoryId("");
    setLoanId("");
    setTransactionType("");
    setSortOrder("date_desc");
    clearFocusedTransaction();
  }

  async function save(item: Transaction, formData: FormData) {
    const categoryIdValue = Number(formData.get("category_id")) || null;
    const selectedCategory = categories.find(
      (category) => category.id === categoryIdValue,
    );
    const isLoanCategory = LOAN_CATEGORY_NAMES.includes(
      selectedCategory?.name ?? "",
    );
    const linkedLoanId = Number(formData.get("linked_loan_id")) || null;
    const transactionType = isLoanBalanceIncreaseCategory(selectedCategory?.name)
      ? "credit"
      : String(formData.get("transaction_type"));
    await api.updateTransaction(item.id, {
      account_id: Number(formData.get("account_id")),
      transaction_date: formData.get("transaction_date"),
      vendor: formData.get("vendor"),
      description: formData.get("description"),
      amount: formData.get("amount"),
      currency: formData.get("currency"),
      transaction_type: transactionType,
      category_id: categoryIdValue,
      recurrence_frequency: formData.get("recurrence_frequency") || null,
      linked_loan_id: linkedLoanId,
      loan_ledger_type: null,
      loan_balance_effect: null,
      loan_principal_component: null,
      loan_interest_component: null,
      loan_mapping_confidence: isLoanCategory && linkedLoanId ? "1" : null,
      loan_user_confirmed: Boolean(isLoanCategory && linkedLoanId),
    });
    setEditing(null);
    setMessage(`Saved ${item.vendor}.`);
    onChanged();
  }

  return (
    <>
      {focusedTransactionId && (
        <div className="focused-transaction-banner">
          <div>
            <strong>Reviewing insurance transaction #{focusedTransactionId}</strong>
            <span>
              Update its category, merchant, description, or amount, then save.
            </span>
          </div>
          <div className="inline-actions">
            <button
              className="secondary-button"
              onClick={clearFocusedTransaction}
              type="button"
            >
              Show all transactions
            </button>
            <button
              className="secondary-button"
              onClick={() => {
                const target = new URL(window.location.href);
                target.searchParams.delete("reviewTransaction");
                target.hash = "insurance";
                window.location.assign(target);
              }}
              type="button"
            >
              Back to Insurance
            </button>
          </div>
        </div>
      )}
      <div className="transaction-controls">
        <div className="manager-toolbar">
          <label className="transaction-search">
            Search
            <input
              aria-label="Search transactions"
              placeholder="Merchant or description"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label>
            Account
            <select
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
            >
              <option value="">All accounts</option>
              {transactionAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Category
            <select
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
            >
              <option value="">All categories</option>
              <option value="uncategorized">Uncategorized</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Type
            <select
              value={transactionType}
              onChange={(event) => setTransactionType(event.target.value)}
            >
              <option value="">Income and expense</option>
              <option value="credit">Income</option>
              <option value="debit">Expense</option>
            </select>
          </label>
          <label>
            Loan
            <select
              value={loanId}
              onChange={(event) => setLoanId(event.target.value)}
            >
              <option value="">All transactions</option>
              <option value="linked">All loan-linked transactions</option>
              {loans.map((loan) => (
                <option key={String(loan.id)} value={String(loan.id)}>
                  {String(loan.lender)} · {String(loan.currency)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sort by
            <select
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value as SortOrder)}
            >
              <option value="date_desc">Newest first</option>
              <option value="date_asc">Oldest first</option>
              <option value="amount_desc">Highest amount</option>
              <option value="amount_asc">Lowest amount</option>
              <option value="vendor_asc">Merchant A-Z</option>
            </select>
          </label>
        </div>
        <div className="month-calendar">
          <div>
            <span>Month calendar</span>
            <small>Select a month or move quickly between months.</small>
          </div>
          <div className="month-calendar-actions">
            <button
              aria-label="Previous month"
              className="month-step"
              disabled={!month}
              onClick={() => setMonth(shiftMonth(month, -1))}
              type="button"
            >
              ‹
            </button>
            <DashboardPeriodPicker
              allowClear
              emptyLabel="All months"
              onChange={setMonth}
              period={month}
            />
            <button
              aria-label="Next month"
              className="month-step"
              disabled={!month}
              onClick={() => setMonth(shiftMonth(month, 1))}
              type="button"
            >
              ›
            </button>
            <button
              className="secondary-button"
              onClick={() => setMonth(new Date().toISOString().slice(0, 7))}
              type="button"
            >
              This month
            </button>
            {filtersActive && (
              <button className="text-button" onClick={clearFilters} type="button">
                Clear filters
              </button>
            )}
          </div>
        </div>
        <div className="transaction-result-summary">
          <strong>{visible.length}</strong>
          <span>
            {visible.length === 1 ? "transaction" : "transactions"}
            {filtersActive ? " match the selected filters" : " available"}
          </span>
          {message && <span className="form-message">{message}</span>}
          {missingFxCount > 0 && (
            <span className="form-message">
              {missingFxCount} transaction{missingFxCount === 1 ? "" : "s"} could
              not be converted to {currency}; original amount used.
            </span>
          )}
        </div>
      </div>
      <section className="transaction-category-summary">
        <div className="transaction-summary-heading">
          <div>
            <p className="eyebrow">Filtered spending</p>
            <h3>Expense Categories</h3>
          </div>
          <span>{money(totals.expenses, currency)}</span>
        </div>
        {expenseCategories.length ? (
          <div className="transaction-category-cards">
            {expenseCategories.map((item) => {
              const presentation = categoryPresentation({
                name: item.name,
                icon: item.category?.icon,
                color: item.category?.color,
              });
              return (
                <article className="transaction-category-card" key={item.name}>
                  <span
                    className={`category-spend-icon ${presentation.color}`}
                  >
                    <AppIcon name={presentation.icon} size={15} />
                  </span>
                  <div>
                    <span>{item.name}</span>
                    <strong>{money(item.amount, currency)}</strong>
                    <div className="progress">
                      <span
                        style={{
                          width: `${(item.amount / maximumCategoryAmount) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="empty-state">
            No expenses match the selected filters.
          </p>
        )}
      </section>
      <div className="table-wrap transaction-table-scroll">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Vendor</th>
              <th>Category</th>
              <th>Type</th>
              <th>Occurrence</th>
              <th>Amount</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) =>
              editing === item.id ? (
                <tr key={item.id}>
                  <td colSpan={7}>
                    <form
                      className="transaction-edit-grid"
                      action={(formData) => save(item, formData)}
                    >
                      <label>
                        Account
                        <select name="account_id" defaultValue={item.account_id}>
                          {transactionAccounts.map((account) => (
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
                          defaultValue={item.transaction_date}
                        />
                      </label>
                      <label>
                        Vendor
                        <input name="vendor" defaultValue={item.vendor} />
                      </label>
                      <label>
                        Description
                        <input name="description" defaultValue={item.description} />
                      </label>
                      <label>
                        Amount
                        <input
                          name="amount"
                          type="number"
                          step="0.01"
                          defaultValue={item.amount}
                        />
                      </label>
                      <label>
                        Currency
                        <input name="currency" defaultValue={item.currency} />
                      </label>
                      <label>
                        Type
                        <select
                          name="transaction_type"
                          defaultValue={item.transaction_type}
                        >
                          <option value="debit">Expense</option>
                          <option value="credit">Income</option>
                        </select>
                      </label>
                      <label>
                        Category
                        <select
                          name="category_id"
                          defaultValue={item.category_id ?? ""}
                        >
                          <option value="">Uncategorized</option>
                          {categories.map((category) => (
                            <option key={category.id} value={category.id}>
                              {category.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <fieldset className="loan-link-fields wide">
                        <legend>Loan account</legend>
                        <label>
                          Linked loan account
                          <select
                            name="linked_loan_id"
                            defaultValue={item.linked_loan_id ?? ""}
                          >
                            <option value="">No loan link</option>
                            {loans.map((loan) => (
                              <option key={String(loan.id)} value={String(loan.id)}>
                                {String(loan.lender)} · {String(loan.currency)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <p className="loan-link-help">
                          The selected category decides how this is posted to the
                          loan ledger: Loan = taken/principal, Loan Repayment =
                          payment, Loan Interest = manual interest posted.
                        </p>
                      </fieldset>
                      <label>
                        Occurrence
                        <select
                          name="recurrence_frequency"
                          defaultValue={item.recurrence_frequency ?? ""}
                        >
                          <option value="">Not recurring</option>
                          <option value="weekly">Weekly</option>
                          <option value="biweekly">Every 2 weeks</option>
                          <option value="monthly">Monthly</option>
                          <option value="quarterly">Quarterly</option>
                          <option value="semiannual">Every 6 months</option>
                          <option value="yearly">Yearly</option>
                        </select>
                      </label>
                      <div className="inline-actions">
                        <button type="submit">Save</button>
                        <button
                          className="secondary-button"
                          type="button"
                          onClick={() => setEditing(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  </td>
                </tr>
              ) : (
                <tr key={item.id}>
                  <td>{item.transaction_date}</td>
                  <td>
                    <strong>{item.vendor}</strong>
                    <small>{item.description}</small>
                  </td>
                  <td>
                    {categories.find((category) => category.id === item.category_id)
                      ?.name ?? "Uncategorized"}
                  </td>
                  <td>{item.transaction_type}</td>
                  <td>
                    {item.recurrence_frequency ? (
                      <span className="recurrence-badge">
                        {item.recurrence_frequency === "semiannual"
                          ? "Every 6 months"
                          : item.recurrence_frequency === "biweekly"
                            ? "Every 2 weeks"
                            : item.recurrence_frequency}
                      </span>
                    ) : (
                      <span className="muted-value">One-time</span>
                    )}
                  </td>
                  <td>
                    {item.amount} {item.currency}
                  </td>
                  <td>
                    <div className="inline-actions">
                      <button
                        className="secondary-button"
                        onClick={() => setEditing(item.id)}
                      >
                        Edit
                      </button>
                      <button
                        className="text-button danger"
                        onClick={async () => {
                          if (!(await confirmAction({
                            title: "Delete transaction?",
                            message: `Delete "${item.vendor}" for ${item.amount} ${item.currency}? This cannot be undone.`,
                            confirmLabel: "Delete transaction",
                          }))) {
                            return;
                          }
                          await api.deleteTransaction(item.id);
                          setMessage(`Deleted ${item.vendor}.`);
                          onChanged();
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
        {!visible.length && <p className="empty-state">No matching transactions.</p>}
      </div>
      <footer className="transaction-totals">
        <div>
          <span>Filtered income</span>
          <strong className="positive-value">
            {money(totals.income, currency)}
          </strong>
        </div>
        <div>
          <span>Filtered expenses</span>
          <strong className="negative-value">
            {money(totals.expenses, currency)}
          </strong>
        </div>
        <div className="transaction-net-total">
          <span>Sum of transactions</span>
          <strong>
            {money(totals.income - totals.expenses, currency)}
          </strong>
        </div>
      </footer>
    </>
  );
}
