import { useMemo, useState } from "react";

import { api } from "../api";
import type { Account, Category } from "../types";
import { DateField } from "./DateField";

interface TransactionFormProps {
  accounts: Account[];
  categories: Category[];
  onSaved: () => void;
}

export function TransactionForm({
  accounts,
  categories,
  onSaved,
}: TransactionFormProps) {
  const [type, setType] = useState<"debit" | "credit">("debit");
  const [message, setMessage] = useState("");
  const visibleCategories = useMemo(
    () =>
      categories.filter((category) =>
        type === "credit"
          ? category.type === "income"
          : category.type !== "income",
      ),
    [categories, type],
  );

  async function submit(formData: FormData) {
    setMessage("");
    try {
      await api.createTransaction({
        account_id: Number(formData.get("account_id")),
        transaction_date: formData.get("transaction_date"),
        vendor: formData.get("vendor"),
        description: formData.get("description"),
        amount: formData.get("amount"),
        currency: formData.get("currency"),
        transaction_type: type,
        category_id: Number(formData.get("category_id")) || null,
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
        <select name="category_id">
          <option value="">Uncategorized</option>
          {visibleCategories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
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
