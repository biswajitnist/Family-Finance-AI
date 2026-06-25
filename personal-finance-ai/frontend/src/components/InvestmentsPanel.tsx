import { useEffect, useState, type FormEvent } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import { AppIcon } from "../icons/IconRegistry";
import type { ResourceRecord } from "../types";

const ASSET_TYPES = ["Stock", "ETF", "Mutual Fund", "Crypto", "Other"];
const PROVIDERS = ["Finnhub", "Twelve Data", "MFAPI", "Manual"];

const emptyInvestment = {
  asset_name: "",
  asset_type: "Stock",
  isin: "",
  ticker: "",
  provider_symbol: "",
  exchange: "",
  broker: "",
  country: "DE",
  market_provider: "Finnhub",
  quantity: "0",
  average_price: "0",
  purchase_currency: "EUR",
  base_currency: "EUR",
  currency: "EUR",
  native_value: "0",
  current_value: "0",
};

function money(value: unknown, currency = "EUR") {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
  }).format(Number(value ?? 0));
}

function dateTime(value: unknown) {
  if (!value) return "Not refreshed";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(String(value)));
}

function valueOf(item: ResourceRecord, key: string) {
  return String(item[key] ?? "");
}

function quoteStatus(item: ResourceRecord) {
  const raw = String(item.quote_status ?? "").toLowerCase();
  const updatedAt = item.market_price_updated_at
    ? new Date(String(item.market_price_updated_at)).getTime()
    : 0;
  const ageDays = updatedAt ? (Date.now() - updatedAt) / 86_400_000 : null;
  if (raw === "fresh" && ageDays !== null && ageDays < 1) return "live";
  if ((raw === "fresh" || raw === "cached") && ageDays !== null) {
    return ageDays <= 7 ? "cached" : "stale";
  }
  if (raw.includes("missing") || raw === "failed") return "unavailable";
  if (raw) return raw;
  if (
    String(item.market_provider).toLowerCase() === "twelve data" &&
    !item.market_price
  ) {
    return "twelve_data_required";
  }
  return "cached";
}

function investmentPayload(
  values: Record<string, string>,
  baseCurrency: string,
) {
  return {
    ...values,
    provider_symbol: values.provider_symbol || values.ticker || null,
    isin: values.isin || null,
    ticker: values.ticker || null,
    exchange: values.exchange || null,
    broker: values.broker || null,
    country: values.country || "DE",
    market_provider: values.market_provider || null,
    quantity: values.quantity || "0",
    average_price: values.average_price || "0",
    current_value: values.current_value || "0",
    currency: baseCurrency,
    base_currency: baseCurrency,
  };
}

function InvestmentFields({
  values,
  onChange,
}: {
  values: Record<string, string>;
  onChange: (name: string, value: string) => void;
}) {
  return (
    <div className="investment-field-grid">
      <label className="wide">
        Asset name
        <input
          required
          value={values.asset_name}
          onChange={(event) => onChange("asset_name", event.target.value)}
        />
      </label>
      <label>
        Type
        <select
          value={values.asset_type}
          onChange={(event) => onChange("asset_type", event.target.value)}
        >
          {ASSET_TYPES.map((type) => (
            <option key={type}>{type}</option>
          ))}
        </select>
      </label>
      <label>
        Provider
        <select
          value={values.market_provider}
          onChange={(event) => onChange("market_provider", event.target.value)}
        >
          {PROVIDERS.map((provider) => (
            <option key={provider}>{provider}</option>
          ))}
        </select>
      </label>
      <label>
        Country
        <input
          maxLength={2}
          placeholder="DE"
          value={values.country}
          onChange={(event) => onChange("country", event.target.value.toUpperCase())}
        />
      </label>
      <label>
        Ticker
        <input
          placeholder="NVDA"
          value={values.ticker}
          onChange={(event) => onChange("ticker", event.target.value.toUpperCase())}
        />
      </label>
      <label>
        Provider symbol
        <input
          placeholder="SXR8.XETRA"
          value={values.provider_symbol}
          onChange={(event) =>
            onChange("provider_symbol", event.target.value.toUpperCase())
          }
        />
      </label>
      <label>
        ISIN
        <input
          placeholder="IE00B5BMR087"
          value={values.isin}
          onChange={(event) => onChange("isin", event.target.value.toUpperCase())}
        />
      </label>
      <label>
        Exchange
        <input
          placeholder="XETRA"
          value={values.exchange}
          onChange={(event) => onChange("exchange", event.target.value)}
        />
      </label>
      <label>
        Quantity
        <input
          min="0"
          step="any"
          type="number"
          value={values.quantity}
          onChange={(event) => onChange("quantity", event.target.value)}
        />
      </label>
      <label>
        Average price
        <input
          min="0"
          step="any"
          type="number"
          value={values.average_price}
          onChange={(event) => onChange("average_price", event.target.value)}
        />
      </label>
      <label>
        Purchase currency
        <select
          value={values.purchase_currency}
          onChange={(event) => onChange("purchase_currency", event.target.value)}
        >
          {["EUR", "USD", "INR", "GBP"].map((currency) => (
            <option key={currency}>{currency}</option>
          ))}
        </select>
      </label>
      {values.purchase_currency === "INR" ? (
        <label>
          Current value in INR
          <input
            min="0"
            step="any"
            type="number"
            value={values.native_value}
            onChange={(event) => onChange("native_value", event.target.value)}
          />
        </label>
      ) : (
        <label>
          Current value in EUR
          <input
            min="0"
            step="any"
            type="number"
            value={values.current_value}
            onChange={(event) => onChange("current_value", event.target.value)}
          />
        </label>
      )}
      <label className="wide">
        Broker
        <input
          placeholder="Scalable Capital"
          value={values.broker}
          onChange={(event) => onChange("broker", event.target.value)}
        />
      </label>
    </div>
  );
}

function PortfolioSummary({
  analytics,
  count,
  baseCurrency,
}: {
  analytics: Record<string, unknown> | null;
  count: number;
  baseCurrency: string;
}) {
  const allocation = (analytics?.allocation ?? []) as Array<
    Record<string, unknown>
  >;
  const indian = (analytics?.indian_investments ?? {}) as Record<
    string,
    unknown
  >;
  const profitLoss =
    analytics?.profit_loss === null || analytics?.profit_loss === undefined
      ? null
      : Number(analytics.profit_loss);
  return (
    <section className="planning-analysis investment-summary">
      <div className="planning-heading">
        <div>
          <p className="eyebrow">Planning analysis</p>
          <h3>Portfolio summary</h3>
        </div>
        <span className="analysis-status">
          {count} holding{count === 1 ? "" : "s"}
        </span>
      </div>
      <div className="analysis-metrics">
        <div className="analysis-metric">
          <span>Portfolio value</span>
          <strong>{money(analytics?.current_value, baseCurrency)}</strong>
          <small>Final locally stored value in {baseCurrency}</small>
        </div>
        <div className="analysis-metric">
          <span>Cost basis</span>
          <strong>
            {analytics?.cost_basis_complete
              ? money(analytics?.cost_basis, baseCurrency)
              : "Incomplete"}
          </strong>
          <small>Quantity × average purchase price</small>
        </div>
        <div
          className={`analysis-metric ${
            profitLoss === null ? "" : profitLoss >= 0 ? "positive" : "negative"
          }`}
        >
          <span>Profit / loss</span>
          <strong>
            {profitLoss === null
              ? "Not available"
              : money(profitLoss, baseCurrency)}
          </strong>
          <small>Calculated only from complete holdings</small>
        </div>
        <div className="analysis-metric indian-investment-tile">
          <span>Indian investments</span>
          <strong>{money(indian.value_inr, "INR")}</strong>
          <small>
            {money(indian.value_base, baseCurrency)} in portfolio ·{" "}
            {indian.fx_rate_to_base
              ? `1 INR = ${Number(indian.fx_rate_to_base).toFixed(6)} ${baseCurrency}`
              : "FX rate not refreshed"}
          </small>
        </div>
      </div>
      <div className="allocation-list compact-allocation">
        {allocation.map((entry) => {
          const percentage = Number(entry.percentage ?? 0);
          return (
            <div className="allocation-row" key={String(entry.asset_type)}>
              <div>
                <strong>{String(entry.asset_type)}</strong>
                <span>{money(entry.value, baseCurrency)}</span>
              </div>
              <div className="allocation-track">
                <span style={{ width: `${Math.min(100, percentage)}%` }} />
              </div>
              <small>{percentage.toFixed(1)}%</small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function InvestmentsPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [items, setItems] = useState<ResourceRecord[]>([]);
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(
    null,
  );
  const [showAdd, setShowAdd] = useState(false);
  const [newItem, setNewItem] =
    useState<Record<string, string>>(emptyInvestment);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [baseCurrency, setBaseCurrency] = useState("EUR");

  async function load() {
    const [holdings, summary, profile] = await Promise.all([
      api.resources("investments"),
      api.analytics("investments"),
      api.profile(),
    ]);
    setItems(holdings);
    setAnalytics(summary);
    setBaseCurrency(profile.base_currency);
  }

  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Could not load portfolio"),
    );
  }, [refreshKey]);

  async function addInvestment(event: FormEvent) {
    event.preventDefault();
    try {
      await api.createResource(
        "investments",
        investmentPayload(newItem, baseCurrency),
      );
      setShowAdd(false);
      setNewItem(emptyInvestment);
      setMessage("Investment added.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add investment");
    }
  }

  function beginEdit(item: ResourceRecord) {
    setEditingId(Number(item.id));
    setDraft(
      Object.fromEntries(
        Object.keys(emptyInvestment).map((key) => [
          key,
          valueOf(item, key) || String(emptyInvestment[key as keyof typeof emptyInvestment]),
        ]),
      ),
    );
  }

  async function saveEdit(item: ResourceRecord) {
    try {
      await api.updateResource(
        "investments",
        Number(item.id),
        investmentPayload(draft, baseCurrency),
      );
      setEditingId(null);
      setMessage(`${String(item.asset_name)} updated.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update investment");
    }
  }

  async function remove(item: ResourceRecord) {
    const confirmed = await confirmAction({
      title: "Delete investment?",
      message: `Delete ${String(item.asset_name)} from Investments?`,
      confirmLabel: "Delete investment",
    });
    if (!confirmed) return;
    await api.deleteResource("investments", Number(item.id));
    setMessage(`${String(item.asset_name)} deleted.`);
    await load();
  }

  function assetGroup(item: ResourceRecord) {
    const type = String(item.asset_type || "Other").toLowerCase();
    if (type.includes("stock")) return "Stocks";
    if (type.includes("etf")) return "ETFs";
    if (type.includes("mutual")) return "Mutual Funds";
    if (type.includes("crypto")) return "Crypto";
    return "Other";
  }

  function countryOf(item: ResourceRecord) {
    if (item.country) return String(item.country).toUpperCase();
    if (String(item.purchase_currency).toUpperCase() === "INR") return "IN";
    if (String(item.exchange).toUpperCase().includes("XETRA")) return "DE";
    return "US";
  }

  const assetGroups = ["Stocks", "ETFs", "Mutual Funds", "Crypto", "Other"]
    .map((name) => ({ name, items: items.filter((item) => assetGroup(item) === name) }))
    .filter((group) => group.items.length);

  const countries = (
    (analytics?.country_allocation ?? []) as Array<Record<string, unknown>>
  ).map((entry) => ({
    name: String(entry.country),
    value: Number(entry.value ?? 0),
    percentage: Number(entry.percentage ?? 0),
    count: items.filter((item) => countryOf(item) === String(entry.country))
      .length,
  }));
  const currencyAllocation = (
    (analytics?.currency_allocation ?? []) as Array<Record<string, unknown>>
  ).map((entry) => ({
    name: String(entry.currency),
    value: Number(entry.value ?? 0),
    percentage: Number(entry.percentage ?? 0),
  }));

  function renderHoldings(holdings: ResourceRecord[]) {
    return holdings.map((item) => {
      const editing = editingId === Number(item.id);
      const isIndian = String(item.purchase_currency).toUpperCase() === "INR";
      return (
        <article className="investment-row" key={String(item.id)}>
          {editing ? (
            <InvestmentFields
              values={draft}
              onChange={(name, value) =>
                setDraft((current) => ({ ...current, [name]: value }))
              }
            />
          ) : (
            <>
              <div className="investment-identity">
                <strong>{String(item.asset_name)}</strong>
                <span>
                  {String(item.asset_type)}
                  {item.ticker ? ` · ${String(item.ticker)}` : ""}
                  {item.isin ? ` · ${String(item.isin)}` : ""}
                </span>
                <small>
                  {String(item.market_provider ?? "Manual")}
                  {item.exchange ? ` · ${String(item.exchange)}` : ""}
                </small>
              </div>
              <div className="investment-stat">
                <span>Quantity</span>
                <strong>{String(item.quantity ?? "0")}</strong>
              </div>
              <div className="investment-stat">
                <span>Average price</span>
                <strong>
                  {money(
                    item.average_price,
                    String(item.purchase_currency ?? "EUR"),
                  )}
                </strong>
              </div>
              <div className="investment-stat">
                <span>{isIndian ? "Value INR" : "Raw market price"}</span>
                <strong>
                  {isIndian
                    ? money(item.native_value, "INR")
                    : item.market_price
                      ? money(
                          item.market_price,
                          String(item.market_currency ?? "EUR"),
                        )
                      : "Not refreshed"}
                </strong>
                <small>
                  {item.fx_rate_to_eur
                    ? `FX to ${baseCurrency} ${String(item.fx_rate_to_eur)}`
                    : "FX rate unavailable"}
                </small>
              </div>
              <div className="investment-stat value">
                <span>Value {baseCurrency}</span>
                <strong>{money(item.current_value, baseCurrency)}</strong>
                <small>{dateTime(item.market_price_updated_at)}</small>
              </div>
              <span
                className={`quote-status ${quoteStatus(item)}`}
              >
                {quoteStatus(item).replaceAll("_", " ")}
              </span>
            </>
          )}
          <div className="investment-row-actions">
            {editing ? (
              <>
                <button onClick={() => saveEdit(item)} type="button">
                  Save
                </button>
                <button
                  className="secondary-button"
                  onClick={() => setEditingId(null)}
                  type="button"
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button
                  className="secondary-button"
                  onClick={() => beginEdit(item)}
                  type="button"
                >
                  Edit
                </button>
                <button
                  className="text-button danger"
                  onClick={() => remove(item)}
                  type="button"
                >
                  Delete
                </button>
              </>
            )}
          </div>
        </article>
      );
    });
  }

  return (
    <section className="investments-page">
      <div className="investment-page-heading">
        <div>
          <p className="eyebrow">Finance module</p>
          <h1>Investments</h1>
          <p>
            Track cost basis, provider quotes, FX conversion, and final portfolio
            value in {baseCurrency}.
          </p>
        </div>
        <button onClick={() => setShowAdd(true)} type="button">
          Add investment
        </button>
      </div>

      <PortfolioSummary
        analytics={analytics}
        baseCurrency={baseCurrency}
        count={items.length}
      />

      <section className="country-portfolio">
        <div className="section-title-row">
          <div><p className="eyebrow">Geographic allocation</p><h2>Portfolio by country</h2></div>
          <AppIcon name="globe" size={22} />
        </div>
        <div className="country-tile-grid">
          {countries.map((entry) => (
            <article key={entry.name}>
              <span>{entry.name}</span>
              <strong>{money(entry.value, baseCurrency)}</strong>
              <small>
                {entry.count} holding{entry.count === 1 ? "" : "s"} ·{" "}
                {entry.percentage.toFixed(1)}%
              </small>
            </article>
          ))}
          {!countries.length && <p className="empty-state">Country allocation appears after adding holdings.</p>}
        </div>
      </section>

      <section className="country-portfolio currency-portfolio">
        <div className="section-title-row">
          <div>
            <p className="eyebrow">Currency exposure</p>
            <h2>Portfolio by original currency</h2>
          </div>
          <AppIcon name="currency" size={22} />
        </div>
        <div className="country-tile-grid">
          {currencyAllocation.map((entry) => (
            <article key={entry.name}>
              <span>{entry.name}</span>
              <strong>{money(entry.value, baseCurrency)}</strong>
              <small>{entry.percentage.toFixed(1)}% of portfolio</small>
            </article>
          ))}
        </div>
      </section>

      <article className="panel investment-holdings">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Portfolio records</p>
            <h2>Holdings</h2>
            <p className="investment-refresh-help">
              Use <strong>Refresh Market Data</strong> at the bottom of this page
              for Finnhub stock prices and FX rates. XETRA ETFs require a Twelve
              Data API connection.
            </p>
          </div>
          <span className="count-pill">{items.length}</span>
        </div>
        {message && <p className="form-message">{message}</p>}
        {!items.length ? (
          <p className="empty-state">Add your first investment to begin.</p>
        ) : (
          <div className="investment-sections asset-type-sections">
            {assetGroups.map((group) => (
              <section key={group.name}>
                <div className="investment-section-heading">
                  <div>
                    <h3>{group.name}</h3>
                    <p>
                      {group.name === "Stocks" && "Listed company shares such as NVIDIA, Alphabet, and IonQ."}
                      {group.name === "ETFs" && "Exchange-traded funds such as SXR8, XNAS, XAIX, and QDVE."}
                      {group.name === "Mutual Funds" && "Managed funds such as Parag Parikh and ICICI Bluechip."}
                      {group.name === "Crypto" && "Digital-asset holdings."}
                      {group.name === "Other" && "Other saved portfolio assets."}
                    </p>
                  </div>
                  <span>{group.items.length}</span>
                </div>
                <div className="investment-list">
                  {renderHoldings(group.items)}
                </div>
              </section>
            ))}
          </div>
        )}
      </article>

      {showAdd && (
        <div
          className="investment-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowAdd(false);
          }}
        >
          <form
            aria-modal="true"
            className="investment-modal"
            onSubmit={addInvestment}
            role="dialog"
          >
            <header>
              <div>
                <p className="eyebrow">New portfolio holding</p>
                <h2>Add investment</h2>
              </div>
              <button
                aria-label="Close add investment"
                className="risk-modal-close"
                onClick={() => setShowAdd(false)}
                type="button"
              >
                ×
              </button>
            </header>
            <InvestmentFields
              values={newItem}
              onChange={(name, value) =>
                setNewItem((current) => ({ ...current, [name]: value }))
              }
            />
            <footer>
              <button type="submit">Add investment</button>
              <button
                className="secondary-button"
                onClick={() => setShowAdd(false)}
                type="button"
              >
                Cancel
              </button>
            </footer>
          </form>
        </div>
      )}
    </section>
  );
}
