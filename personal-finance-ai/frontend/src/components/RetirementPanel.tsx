import { useEffect, useState, type FormEvent } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import { AppIcon } from "../icons/IconRegistry";
import type { ResourceRecord } from "../types";

const emptyRetirement = {
  name: "",
  provider: "",
  account_type: "pension",
  country: "DE",
  currency: "EUR",
  current_value: "0",
  monthly_contribution: "0",
  employer_contribution: "0",
  projected_value: "0",
  retirement_age: "67",
  notes: "",
};

function money(value: unknown, currency: unknown) {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency: String(currency || "EUR"),
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

export function RetirementPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [items, setItems] = useState<ResourceRecord[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>(emptyRetirement);
  const [editing, setEditing] = useState<number | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    setItems(await api.resources("retirement"));
  }
  useEffect(() => { void load(); }, [refreshKey]);

  function edit(item?: ResourceRecord) {
    setEditing(item ? Number(item.id) : null);
    setDraft(item ? Object.fromEntries(Object.keys(emptyRetirement).map((key) => [key, String(item[key] ?? emptyRetirement[key as keyof typeof emptyRetirement])])) : emptyRetirement);
    setOpen(true);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (editing) await api.updateResource("retirement", editing, draft);
    else await api.createResource("retirement", draft);
    setOpen(false);
    await load();
  }

  const current = items.reduce((sum, item) => sum + Number(item.current_value || 0), 0);
  const projected = items.reduce((sum, item) => sum + Number(item.projected_value || 0), 0);
  const monthly = items.reduce((sum, item) => sum + Number(item.monthly_contribution || 0) + Number(item.employer_contribution || 0), 0);

  return (
    <section className="asset-module-page">
      <header className="module-page-heading">
        <div><p className="eyebrow">Pension module</p><h1>Retirement</h1><p>German Pension, Swiss Life, VW Pension, and your total projection.</p></div>
        <button onClick={() => edit()}><AppIcon name="institution" size={17} /> Add retirement plan</button>
      </header>
      <section className="module-summary-grid">
        <article><span><AppIcon name="institution" /> Retirement accounts</span><strong>{items.length}</strong><small>Saved pension plans</small></article>
        <article><span><AppIcon name="netWorth" /> Current retirement value</span><strong>{money(current, items[0]?.currency)}</strong><small>Current accumulated value</small></article>
        <article className="highlight"><span><AppIcon name="chart" /> Total retirement projection</span><strong>{money(projected, items[0]?.currency)}</strong><small>{money(monthly, items[0]?.currency)} contributed monthly</small></article>
      </section>
      <section className="asset-group-grid">
        {items.map((item) => (
          <article className="asset-record-card" key={String(item.id)}>
            <header><span><AppIcon name="institution" /></span><div><h2>{String(item.name)}</h2><p>{String(item.provider || item.account_type)}</p></div><b>{String(item.country)}</b></header>
            <dl>
              <div><dt>Current value</dt><dd>{money(item.current_value, item.currency)}</dd></div>
              <div><dt>Monthly contribution</dt><dd>{money(item.monthly_contribution, item.currency)}</dd></div>
              <div><dt>Employer contribution</dt><dd>{money(item.employer_contribution, item.currency)}</dd></div>
              <div><dt>Projected value</dt><dd>{money(item.projected_value, item.currency)}</dd></div>
            </dl>
            <footer><button className="secondary-button" onClick={() => edit(item)}>Edit</button><button className="text-button danger" onClick={async () => { if (await confirmAction({ title: "Delete retirement plan?", message: `Delete ${String(item.name)} from Retirement?`, confirmLabel: "Delete plan" })) { await api.deleteResource("retirement", Number(item.id)); await load(); }}}>Delete</button></footer>
          </article>
        ))}
        {!items.length && <div className="panel empty-module"><AppIcon name="institution" size={30} /><h2>No retirement plans yet</h2><p>Add German Pension, Swiss Life, and VW Pension.</p></div>}
      </section>
      {open && (
        <div className="investment-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setOpen(false)}>
          <form className="investment-modal asset-modal" onSubmit={save}>
            <header><div><p className="eyebrow">Retirement record</p><h2>{editing ? "Edit retirement plan" : "Add retirement plan"}</h2></div><button className="risk-modal-close" onClick={() => setOpen(false)} type="button"><AppIcon name="close" /></button></header>
            <div className="investment-field-grid">
              {[
                ["name", "Plan name", "text"], ["provider", "Provider", "text"],
                ["account_type", "Plan type", "text"], ["country", "Country code", "text"],
                ["currency", "Currency", "text"], ["current_value", "Current value", "number"],
                ["monthly_contribution", "Monthly contribution", "number"], ["employer_contribution", "Employer contribution", "number"],
                ["projected_value", "Projected retirement value", "number"], ["retirement_age", "Retirement age", "number"],
              ].map(([name, label, type]) => <label className={name === "name" || name === "provider" ? "wide" : ""} key={name}>{label}<input required={name === "name"} type={type} value={draft[name]} onChange={(event) => setDraft((current) => ({...current, [name]: event.target.value}))} /></label>)}
            </div>
            <footer><button type="submit">Save plan</button><button className="secondary-button" onClick={() => setOpen(false)} type="button">Cancel</button></footer>
          </form>
        </div>
      )}
    </section>
  );
}
