import { useEffect, useState, type FormEvent } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import { AppIcon } from "../icons/IconRegistry";
import type { ResourceRecord } from "../types";

const emptyProperty = {
  name: "",
  address: "",
  country: "IN",
  currency: "INR",
  purchase_price: "0",
  current_value: "0",
  monthly_rental_income: "0",
  monthly_costs: "0",
  afa_rate: "0",
  land_share_percentage: "0",
};

function money(value: unknown, currency: unknown) {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency: String(currency || "EUR"),
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

export function RealEstatePanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [items, setItems] = useState<ResourceRecord[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>(emptyProperty);
  const [editing, setEditing] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(
    null,
  );
  const [baseCurrency, setBaseCurrency] = useState("EUR");

  async function load() {
    const [properties, summary, profile] = await Promise.all([
      api.resources("properties"),
      api.analytics("properties"),
      api.profile(),
    ]);
    setItems(properties);
    setAnalytics(summary);
    setBaseCurrency(profile.base_currency);
  }

  useEffect(() => {
    void load();
  }, [refreshKey]);

  function edit(item?: ResourceRecord) {
    setEditing(item ? Number(item.id) : null);
    setDraft(
      item
        ? Object.fromEntries(
            Object.keys(emptyProperty).map((key) => [
              key,
              String(item[key] ?? emptyProperty[key as keyof typeof emptyProperty]),
            ]),
          )
        : emptyProperty,
    );
    setOpen(true);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (editing) await api.updateResource("properties", editing, draft);
    else await api.createResource("properties", draft);
    setOpen(false);
    setMessage(editing ? "Property updated." : "Property added.");
    await load();
  }

  async function remove(item: ResourceRecord) {
    const confirmed = await confirmAction({
      title: "Delete property?",
      message: `Delete ${String(item.name)} from Real Estate?`,
      confirmLabel: "Delete property",
    });
    if (!confirmed) return;
    await api.deleteResource("properties", Number(item.id));
    await load();
  }

  const convertedProperties = (analytics?.properties ?? []) as Array<
    Record<string, unknown>
  >;

  return (
    <section className="asset-module-page">
      <header className="module-page-heading">
        <div>
          <p className="eyebrow">Property module</p>
          <h1>Real Estate</h1>
          <p>Track property values, rental income, yield, and location.</p>
        </div>
        <button onClick={() => edit()}><AppIcon name="properties" size={17} /> Add property</button>
      </header>
      <section className="module-summary-grid">
        <article><span><AppIcon name="properties" /> Properties</span><strong>{items.length}</strong><small>Saved real-estate assets</small></article>
        <article><span><AppIcon name="netWorth" /> Current value</span><strong>{money(analytics?.total_value, baseCurrency)}</strong><small>Converted to {baseCurrency}</small></article>
        <article><span><AppIcon name="income" /> Annual rental income</span><strong>{money(analytics?.annual_rental_income, baseCurrency)}</strong><small>Converted to {baseCurrency}</small></article>
      </section>
      {message && <p className="form-message">{message}</p>}
      <section className="asset-group-grid">
        {items.map((item) => {
          const converted = convertedProperties.find(
            (entry) => Number(entry.id) === Number(item.id),
          );
          const annual = Number(item.monthly_rental_income || 0) * 12;
          const yieldValue = Number(item.current_value)
            ? (annual / Number(item.current_value)) * 100
            : 0;
          return (
            <article className="asset-record-card" key={String(item.id)}>
              <header>
                <span><AppIcon name="properties" /></span>
                <div><h2>{String(item.name)}</h2><p>{String(item.address || item.country)}</p></div>
                <b>{String(item.country)}</b>
              </header>
              <dl>
                <div><dt>Purchase price</dt><dd>{money(item.purchase_price, item.currency)}</dd></div>
                <div><dt>Current value</dt><dd>{money(item.current_value, item.currency)}</dd></div>
                {String(item.currency).toUpperCase() !== baseCurrency && (
                  <div>
                    <dt>Value in {baseCurrency}</dt>
                    <dd>
                      {converted?.current_value_base === null ||
                      converted?.current_value_base === undefined
                        ? "FX rate missing"
                        : money(converted.current_value_base, baseCurrency)}
                    </dd>
                  </div>
                )}
                <div><dt>Rental income</dt><dd>{money(item.monthly_rental_income, item.currency)}/mo</dd></div>
                <div><dt>Gross yield</dt><dd>{yieldValue.toFixed(2)}%</dd></div>
              </dl>
              <footer>
                <button className="secondary-button" onClick={() => edit(item)}>Edit</button>
                <button className="text-button danger" onClick={() => void remove(item)}>Delete</button>
              </footer>
            </article>
          );
        })}
        {!items.length && <div className="panel empty-module"><AppIcon name="properties" size={30} /><h2>No properties yet</h2><p>Add Pune property, Ranaghat house, or commercial land.</p></div>}
      </section>
      {Boolean((analytics?.missing_fx_rates as string[] | undefined)?.length) && (
        <p className="market-warning">
          Missing FX rate:{" "}
          {(analytics?.missing_fx_rates as string[]).join(", ")}. Native property
          values remain saved and are excluded from converted totals until a
          rate is available.
        </p>
      )}
      {open && (
        <div className="investment-modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setOpen(false)}>
          <form className="investment-modal asset-modal" onSubmit={save}>
            <header><div><p className="eyebrow">Real-estate record</p><h2>{editing ? "Edit property" : "Add property"}</h2></div><button className="risk-modal-close" onClick={() => setOpen(false)} type="button"><AppIcon name="close" /></button></header>
            <div className="investment-field-grid">
              {[
                ["name", "Property name", "text"],
                ["address", "Address or description", "text"],
                ["country", "Country code", "text"],
                ["currency", "Currency", "text"],
                ["purchase_price", "Purchase price", "number"],
                ["current_value", "Current value", "number"],
                ["monthly_rental_income", "Monthly rental income", "number"],
                ["monthly_costs", "Monthly costs", "number"],
              ].map(([name, label, type]) => (
                <label className={name === "name" || name === "address" ? "wide" : ""} key={name}>{label}<input required={name === "name"} type={type} value={draft[name]} onChange={(event) => setDraft((current) => ({...current, [name]: event.target.value}))} /></label>
              ))}
            </div>
            <footer><button type="submit">Save property</button><button className="secondary-button" onClick={() => setOpen(false)} type="button">Cancel</button></footer>
          </form>
        </div>
      )}
    </section>
  );
}
