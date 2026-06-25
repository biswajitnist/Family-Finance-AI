import { useState } from "react";

import { api } from "../api";
import type { Account } from "../types";

interface CsvImportProps {
  accounts: Account[];
  onImported: () => void;
}

export function CsvImport({ accounts, onImported }: CsvImportProps) {
  const [message, setMessage] = useState("");

  async function submit(formData: FormData) {
    const file = formData.get("file");
    if (!(file instanceof File) || !file.size) return;
    try {
      const result = await api.importCsv(
        Number(formData.get("account_id")),
        file,
      );
      setMessage(
        `${result.imported} rows imported for review. ${result.duplicates} possible duplicate(s).`,
      );
      onImported();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Import failed");
    }
  }

  return (
    <form action={submit} className="import-form">
      <div>
        <h3>Import bank CSV</h3>
        <p>
          Required columns: date, vendor, amount, type. Imported rows stay
          pending until you approve them.
        </p>
      </div>
      <select name="account_id" required disabled={!accounts.length}>
        {accounts.map((account) => (
          <option key={account.id} value={account.id}>
            {account.name}
          </option>
        ))}
      </select>
      <input name="file" type="file" accept=".csv,text/csv" required />
      <button type="submit" disabled={!accounts.length}>
        Import CSV
      </button>
      {message && <span className="form-message">{message}</span>}
    </form>
  );
}
