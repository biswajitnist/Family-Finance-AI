import { useMemo, useState } from "react";

import { api } from "../api";
import type { Account, Category, ResourceRecord } from "../types";
import { DateField } from "./DateField";

const LOAN_CATEGORY_NAMES = ["Loan", "Loan Repayment", "Loan Interest"];

function isLoanBalanceIncreaseCategory(categoryName: string | undefined) {
  return categoryName === "Loan" || categoryName === "Loan Interest";
}

interface TransactionFormProps {
  accounts: Account[];
  categories: Category[];
  loans: ResourceRecord[];
  onSaved: () => void;
}

export function TransactionForm({
  accounts,
  categories,
  loans,
  onSaved,
}: TransactionFormProps) {
  const [type, setType] = useState<"debit" | "credit">("debit");
  const [categoryId, setCategoryId] = useState("");
  const [message, setMessage] = useState("");
  const selectedCategory = categories.find(
    (category) => String(category.id) === categoryId,
  );
  const showLoanFields = LOAN_CATEGORY_NAMES.includes(selectedCategory?.name ?? "");
  const visibleCategories = useMemo(
    () =>
      categories.filter((category) =>
        LOAN_CATEGORY_NAMES.includes(category.name) ||
        (type === "credit"
          ? category.type === "income"
          : category.type !== "income"),
      ),
    [categories, type],
  );

  async function submit(formData: FormData) {
    setMessage("");
    try {
      const linkedLoanId = Number(formData.get("linked_loan_id")) || null;
      const transactionType = isLoanBalanceIncreaseCategory(selectedCategory?.name)
        ? "credit"
        : type;
      await api.createTransaction({
        account_id: Number(formData.get("account_id")),
        transaction_date: formData.get("transaction_date"),
        vendor: formData.get("vendor"),
        description: formData.get("description"),
        amount: formData.get("amount"),
        currency: formData.get("currency"),
        transaction_type: transactionType,
        category_id: Number(formData.get("category_id")) || null,
        linked_loan_id: linkedLoanId,
        loan_ledger_type: null,
        loan_balance_effect: null,
        loan_principal_component: null,
        loan_interest_component: null,
        loan_mapping_confidence: showLoanFields && linkedLoanId ? "1" : null,
        loan_user_confirmed: Boolean(showLoanFields && linkedLoanId),
        is_validated: true,
      });
      setMessage("Transaction saved.");
      onSaved();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save");
    }
  }

  if (!accounts.length) {
    return <p className="empty-state">Create an account before adding transactions.</p>;
  }

  return (
    <form action={submit} className="form-grid">
      <label>
        Account
        <select name="account_id" required>
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
          defaultValue={new Date().toISOString().slice(0, 10)}
          required
        />
      </label>
      <label>
        Type
        <select
          value={type}
          onChange={(event) =>
            setType(event.target.value as "debit" | "credit")
          }
        >
          <option value="debit">Expense</option>
          <option value="credit">Income</option>
        </select>
      </label>
      <label>
        Vendor or payer
        <input name="vendor" placeholder="e.g. REWE" required />
      </label>
      <label>
        Amount
        <input name="amount" type="number" min="0.01" step="0.01" required />
      </label>
      <label>
        Currency
        <input name="currency" defaultValue="EUR" minLength={3} maxLength={3} />
      </label>
      <label>
        Category
        <select
          name="category_id"
          value={categoryId}
          onChange={(event) => {
            const nextCategoryId = event.target.value;
            const nextCategory = categories.find(
              (category) => String(category.id) === nextCategoryId,
            );
            setCategoryId(nextCategoryId);
            if (isLoanBalanceIncreaseCategory(nextCategory?.name)) {
              setType("credit");
            }
            if (nextCategory?.name === "Loan Repayment") setType("debit");
          }}
        >
          <option value="">Uncategorized</option>
          {visibleCategories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
      {showLoanFields && (
        <fieldset className="loan-link-fields wide">
          <legend>Loan account</legend>
          <label>
            Linked loan account
            <select name="linked_loan_id" required>
              <option value="">Select loan</option>
              {loans.map((loan) => (
                <option key={String(loan.id)} value={String(loan.id)}>
                  {String(loan.lender)} · {String(loan.currency)}
                </option>
              ))}
            </select>
          </label>
          <p className="loan-link-help">
            {selectedCategory?.name === "Loan"
              ? "This will be saved as loan taken and applied fully to principal."
              : selectedCategory?.name === "Loan Interest"
                ? "This will be saved as manually posted interest. Interest calculation is not triggered."
                : "This will be saved as a repayment against the selected loan."}
          </p>
        </fieldset>
      )}
      <label className="wide">
        Description
        <input name="description" placeholder="Optional note" />
      </label>
      <div className="form-footer wide">
        <button type="submit">Save transaction</button>
        <span className="form-message">{message}</span>
      </div>
    </form>
  );
}
