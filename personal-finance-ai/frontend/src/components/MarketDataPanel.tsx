import { useEffect, useState, type FormEvent } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import type { MarketDataProvider, MarketDataStatus } from "../types";

const INTERVALS = [
  ["manual", "Manual only"],
  ["15_minutes", "Every 15 minutes"],
  ["30_minutes", "Every 30 minutes"],
  ["hourly", "Every 1 hour"],
  ["daily", "Daily"],
];

const emptyProvider = {
  provider_name: "",
  provider_type: "Generic",
  base_url: "",
  api_key: "",
  auth_method: "None",
  api_key_parameter_name: "",
  api_key_header_name: "",
  enabled: true,
  priority: 100,
  supported_asset_classes: "",
  default_currency: "",
  default_exchange_code: "",
  symbol_format: "",
  test_symbol: "",
  timeout_seconds: 10,
  retry_count: 2,
  rate_limit_per_minute: "",
  notes: "",
};

type ProviderDraft = typeof emptyProvider;

function dateTime(value: string | null) {
  if (!value) return "Never";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function money(value: string | number, currency = "USD") {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency: currency || "USD",
  }).format(Number(value));
}

export function MarketDataPanel({
  compact = false,
  onRefreshed,
}: {
  compact?: boolean;
  onRefreshed?: () => void | Promise<void>;
}) {
  const [status, setStatus] = useState<MarketDataStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [apiKeys, setApiKeys] = useState({
    finnhub: "",
    twelve_data: "",
  });
  const [savingKey, setSavingKey] = useState(false);
  const [editingProvider, setEditingProvider] = useState<
    "finnhub" | "twelve_data" | null
  >(null);
  const [credentialMessage, setCredentialMessage] = useState("");
  const [providers, setProviders] = useState<MarketDataProvider[]>([]);
  const [providerDraft, setProviderDraft] =
    useState<ProviderDraft>(emptyProvider);
  const [providerEditingId, setProviderEditingId] = useState<number | null>(
    null,
  );
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [providerBusy, setProviderBusy] = useState<number | null>(null);

  async function load() {
    const [nextStatus, configuredProviders] = await Promise.all([
      api.marketDataStatus(),
      api.marketDataProviders(),
    ]);
    setStatus(nextStatus);
    setProviders(configuredProviders);
  }

  useEffect(() => {
    void load();
  }, []);

  async function refresh() {
    setRefreshing(true);
    try {
      setStatus(await api.refreshMarketData());
      await onRefreshed?.();
    } finally {
      setRefreshing(false);
    }
  }

  async function changeInterval(refreshInterval: string) {
    setStatus(await api.updateMarketDataSettings(refreshInterval));
  }

  async function saveApiKey(
    event: FormEvent<HTMLFormElement>,
    provider: "finnhub" | "twelve_data",
  ) {
    event.preventDefault();
    setSavingKey(true);
    try {
      setStatus(await api.saveMarketDataApiKey(provider, apiKeys[provider]));
      setApiKeys((current) => ({ ...current, [provider]: "" }));
      setEditingProvider(null);
      setCredentialMessage(
        `${provider === "finnhub" ? "Finnhub" : "Twelve Data"} API key saved locally.`,
      );
    } catch (error) {
      setCredentialMessage(
        error instanceof Error ? error.message : "Could not save API key",
      );
    } finally {
      setSavingKey(false);
    }
  }

  function editProvider(provider?: MarketDataProvider) {
    if (!provider) {
      setProviderEditingId(null);
      setProviderDraft(emptyProvider);
    } else {
      setProviderEditingId(provider.id);
      setProviderDraft({
        provider_name: provider.provider_name,
        provider_type: provider.provider_type,
        base_url: provider.base_url ?? "",
        api_key: "",
        auth_method: provider.auth_method,
        api_key_parameter_name: provider.api_key_parameter_name ?? "",
        api_key_header_name: provider.api_key_header_name ?? "",
        enabled: provider.enabled,
        priority: provider.priority,
        supported_asset_classes: provider.supported_asset_classes ?? "",
        default_currency: provider.default_currency ?? "",
        default_exchange_code: provider.default_exchange_code ?? "",
        symbol_format: provider.symbol_format ?? "",
        test_symbol: provider.test_symbol ?? "",
        timeout_seconds: provider.timeout_seconds,
        retry_count: provider.retry_count,
        rate_limit_per_minute: provider.rate_limit_per_minute
          ? String(provider.rate_limit_per_minute)
          : "",
        notes: provider.notes ?? "",
      });
    }
    setShowProviderForm(true);
  }

  function providerPayload(draft: ProviderDraft) {
    return {
      ...draft,
      base_url: draft.base_url || null,
      api_key: draft.api_key || null,
      api_key_parameter_name: draft.api_key_parameter_name || null,
      api_key_header_name: draft.api_key_header_name || null,
      supported_asset_classes: draft.supported_asset_classes || null,
      default_currency: draft.default_currency || null,
      default_exchange_code: draft.default_exchange_code || null,
      symbol_format: draft.symbol_format || null,
      test_symbol: draft.test_symbol || null,
      rate_limit_per_minute: draft.rate_limit_per_minute
        ? Number(draft.rate_limit_per_minute)
        : null,
      notes: draft.notes || null,
    };
  }

  function providerToDraft(provider: MarketDataProvider): ProviderDraft {
    return {
      provider_name: provider.provider_name,
      provider_type: provider.provider_type,
      base_url: provider.base_url ?? "",
      api_key: "",
      auth_method: provider.auth_method,
      api_key_parameter_name: provider.api_key_parameter_name ?? "",
      api_key_header_name: provider.api_key_header_name ?? "",
      enabled: provider.enabled,
      priority: provider.priority,
      supported_asset_classes: provider.supported_asset_classes ?? "",
      default_currency: provider.default_currency ?? "",
      default_exchange_code: provider.default_exchange_code ?? "",
      symbol_format: provider.symbol_format ?? "",
      test_symbol: provider.test_symbol ?? "",
      timeout_seconds: provider.timeout_seconds,
      retry_count: provider.retry_count,
      rate_limit_per_minute: provider.rate_limit_per_minute
        ? String(provider.rate_limit_per_minute)
        : "",
      notes: provider.notes ?? "",
    };
  }

  async function saveProvider(event: FormEvent) {
    event.preventDefault();
    try {
      if (providerEditingId) {
        await api.updateMarketDataProvider(
          providerEditingId,
          providerPayload(providerDraft),
        );
        setCredentialMessage("Market data provider updated.");
      } else {
        await api.createMarketDataProvider(providerPayload(providerDraft));
        setCredentialMessage("Market data provider added.");
      }
      setShowProviderForm(false);
      await load();
    } catch (error) {
      setCredentialMessage(
        error instanceof Error ? error.message : "Could not save provider",
      );
    }
  }

  async function testConfiguredProvider(provider: MarketDataProvider) {
    setProviderBusy(provider.id);
    try {
      const result = await api.testMarketDataProvider(provider.id);
      setCredentialMessage(
        result.last_test_status === "online"
          ? `${provider.provider_name} is online.`
          : `${provider.provider_name} test failed: ${result.last_error}`,
      );
      await load();
    } finally {
      setProviderBusy(null);
    }
  }

  async function changePriority(
    provider: MarketDataProvider,
    direction: -1 | 1,
  ) {
    const ordered = [...providers].sort(
      (left, right) => left.priority - right.priority,
    );
    const index = ordered.findIndex((item) => item.id === provider.id);
    const other = ordered[index + direction];
    if (!other) return;
    await Promise.all([
      api.updateMarketDataProvider(provider.id, {
        ...providerPayload(providerToDraft(provider)),
        priority: other.priority,
      }),
      api.updateMarketDataProvider(other.id, {
        ...providerPayload(providerToDraft(other)),
        priority: provider.priority,
      }),
    ]);
    await load();
  }

  if (!status) {
    return (
      <article className="panel market-data-panel">
        <p className="empty-state">Loading cached market data...</p>
      </article>
    );
  }

  return (
    <article className={`panel market-data-panel ${compact ? "compact" : ""}`}>
      <div className="market-data-heading">
        <div>
          <p className="eyebrow">Hybrid local + online</p>
          <h2>Market Data Status</h2>
        </div>
        <span
          className={`market-status ${
            status.online ? "online" : status.using_cache ? "cached" : "offline"
          }`}
        >
          {status.online ? "✓" : "⚠"} {status.status_label}
        </span>
      </div>
      <div className="market-data-meta">
        <div>
          <span>Last updated</span>
          <strong>{dateTime(status.last_updated)}</strong>
        </div>
        <div>
          <span>Data source</span>
          <strong>{status.provider}</strong>
        </div>
        <div>
          <span>Tracked symbols</span>
          <strong>{status.symbol_count}</strong>
        </div>
        <label>
          <span>Auto refresh</span>
          <select
            value={status.refresh_interval}
            onChange={(event) => changeInterval(event.target.value)}
          >
            {INTERVALS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {status.warning && <p className="market-warning">{status.warning}</p>}
      {!status.configured && (
        <p className="market-warning">
          Add provider API keys below to enable online prices. The portfolio
          remains available offline.
        </p>
      )}
      <section className="market-provider-settings">
        {(
          [
            ["finnhub", "Finnhub", "US stocks such as NVDA and GOOGL"],
            [
              "twelve_data",
              "Twelve Data",
              `XETRA ETFs · ${status.providers.twelve_data.tracked_symbols} tracked`,
            ],
          ] as const
        ).map(([provider, label, description]) => {
          const providerStatus = status.providers[provider];
          const editing = editingProvider === provider;
          return (
            <div className="market-provider-card" key={provider}>
              <div>
                <strong>{label}</strong>
                <small>{description}</small>
              </div>
              {providerStatus.configured && !editing ? (
                <>
                  <span className="provider-configured">
                    ✓ Configured in{" "}
                    {providerStatus.credential_source === "app"
                      ? "local app storage"
                      : "local environment"}
                  </span>
                  <button
                    className="secondary-button"
                    onClick={() => {
                      setEditingProvider(provider);
                      setCredentialMessage("");
                    }}
                    type="button"
                  >
                    Replace key
                  </button>
                </>
              ) : (
                <form
                  className="market-provider-key-form"
                  onSubmit={(event) => saveApiKey(event, provider)}
                >
                  <input
                    aria-label={`${label} API key`}
                    autoComplete="off"
                    minLength={16}
                    onChange={(event) =>
                      setApiKeys((current) => ({
                        ...current,
                        [provider]: event.target.value,
                      }))
                    }
                    placeholder={`Paste ${label} API key`}
                    required
                    type="password"
                    value={apiKeys[provider]}
                  />
                  <button disabled={savingKey} type="submit">
                    {savingKey ? "Saving..." : "Save key"}
                  </button>
                  {providerStatus.configured && (
                    <button
                      className="secondary-button"
                      onClick={() => {
                        setEditingProvider(null);
                        setApiKeys((current) => ({
                          ...current,
                          [provider]: "",
                        }));
                      }}
                      type="button"
                    >
                      Cancel
                    </button>
                  )}
                </form>
              )}
            </div>
          );
        })}
        <small className="market-provider-privacy">
          Keys are stored only on this machine and are never displayed again.
        </small>
      </section>
      <section className="configured-provider-section">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Provider configuration</p>
            <h3>Market Data APIs</h3>
            <p>
              Enable, test, edit, and reorder approved local market-data
              connections.
            </p>
          </div>
          <button
            className="secondary-button"
            onClick={() => editProvider()}
            type="button"
          >
            Add provider
          </button>
        </div>
        <div className="configured-provider-list">
          {providers.map((provider, index) => (
            <article className="configured-provider-row" key={provider.id}>
              <div className="provider-priority-controls">
                <button
                  aria-label={`Move ${provider.provider_name} up`}
                  disabled={index === 0}
                  onClick={() => changePriority(provider, -1)}
                  type="button"
                >
                  ↑
                </button>
                <strong>{provider.priority}</strong>
                <button
                  aria-label={`Move ${provider.provider_name} down`}
                  disabled={index === providers.length - 1}
                  onClick={() => changePriority(provider, 1)}
                  type="button"
                >
                  ↓
                </button>
              </div>
              <div>
                <strong>{provider.provider_name}</strong>
                <span>
                  {provider.provider_type} ·{" "}
                  {provider.enabled ? "Enabled" : "Disabled"}
                </span>
                <small>
                  {provider.base_url || "No URL"} ·{" "}
                  {provider.api_key_masked || "No API key required"}
                </small>
              </div>
              <div className="provider-test-state">
                <span className={`quote-status ${provider.last_test_status ?? "manual"}`}>
                  {provider.last_test_status ?? "Not tested"}
                </span>
                <small>{provider.last_error}</small>
              </div>
              <div className="inline-actions provider-action-buttons">
                <button
                  className="secondary-button"
                  disabled={providerBusy === provider.id}
                  onClick={() => testConfiguredProvider(provider)}
                  type="button"
                >
                  {providerBusy === provider.id ? "Testing..." : "Test"}
                </button>
                <button
                  className="secondary-button"
                  onClick={() => editProvider(provider)}
                  type="button"
                >
                  Edit
                </button>
                <button
                  className="secondary-button danger-outline"
                  onClick={async () => {
                    const confirmed = await confirmAction({
                      title: "Delete market data provider?",
                      message: `Delete ${provider.provider_name}? Price refreshes using this provider will stop.`,
                      confirmLabel: "Delete provider",
                    });
                    if (!confirmed) return;
                    await api.deleteMarketDataProvider(provider.id);
                    await load();
                  }}
                  type="button"
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
      {credentialMessage && (
        <p className="form-message market-credential-message">
          {credentialMessage}
        </p>
      )}
      <div className="market-data-actions">
        <button
          className="secondary-button"
          disabled={refreshing || !status.configured}
          onClick={refresh}
        >
          {refreshing ? "Refreshing..." : "Refresh Market Data"}
        </button>
        {status.missing_ticker_count > 0 && (
          <small>
            {status.missing_ticker_count} investment(s) need a ticker before
            prices can be downloaded.
          </small>
        )}
      </div>
      {!compact && status.prices.length > 0 && (
        <div className="market-price-strip">
          {status.prices.map((price) => (
            <div key={price.symbol}>
              <strong>{price.symbol}</strong>
              <span>{money(price.price, price.currency ?? "USD")}</span>
              <small>{dateTime(price.fetched_at)}</small>
            </div>
          ))}
        </div>
      )}
      {showProviderForm && (
        <div
          className="investment-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowProviderForm(false);
          }}
        >
          <form
            className="investment-modal provider-config-modal"
            onSubmit={saveProvider}
            role="dialog"
            aria-modal="true"
          >
            <header>
              <div>
                <p className="eyebrow">Approved online source</p>
                <h2>{providerEditingId ? "Edit provider" : "Add provider"}</h2>
              </div>
              <button
                aria-label="Close provider form"
                className="risk-modal-close"
                onClick={() => setShowProviderForm(false)}
                type="button"
              >
                ×
              </button>
            </header>
            <div className="investment-field-grid">
              <label>
                Provider name
                <input
                  required
                  value={providerDraft.provider_name}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      provider_name: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Provider type
                <input
                  value={providerDraft.provider_type}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      provider_type: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="wide">
                Base URL
                <input
                  placeholder="https://api.example.com"
                  value={providerDraft.base_url}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      base_url: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Authentication
                <select
                  value={providerDraft.auth_method}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      auth_method: event.target.value,
                    }))
                  }
                >
                  <option>None</option>
                  <option>API Key in Query Parameter</option>
                  <option>API Key in Header</option>
                  <option>Bearer Token</option>
                  <option>Basic Auth</option>
                </select>
              </label>
              <label>
                API key
                <input
                  autoComplete="off"
                  placeholder={
                    providerEditingId
                      ? "Leave blank to keep saved key"
                      : "Optional"
                  }
                  type="password"
                  value={providerDraft.api_key}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      api_key: event.target.value,
                    }))
                  }
                />
              </label>
              {[
                ["api_key_parameter_name", "API key parameter"],
                ["api_key_header_name", "API key header"],
                ["supported_asset_classes", "Supported asset classes"],
                ["default_currency", "Default currency"],
                ["default_exchange_code", "Default exchange code"],
                ["symbol_format", "Symbol format"],
                ["test_symbol", "Test symbol"],
              ].map(([name, label]) => (
                <label key={name}>
                  {label}
                  <input
                    value={String(providerDraft[name as keyof ProviderDraft])}
                    onChange={(event) =>
                      setProviderDraft((current) => ({
                        ...current,
                        [name]: event.target.value,
                      }))
                    }
                  />
                </label>
              ))}
              <label>
                Priority
                <input
                  min="1"
                  type="number"
                  value={providerDraft.priority}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      priority: Number(event.target.value),
                    }))
                  }
                />
              </label>
              <label>
                Timeout seconds
                <input
                  min="1"
                  type="number"
                  value={providerDraft.timeout_seconds}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      timeout_seconds: Number(event.target.value),
                    }))
                  }
                />
              </label>
              <label>
                Retry count
                <input
                  min="0"
                  type="number"
                  value={providerDraft.retry_count}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      retry_count: Number(event.target.value),
                    }))
                  }
                />
              </label>
              <label>
                Rate limit / minute
                <input
                  min="1"
                  type="number"
                  value={providerDraft.rate_limit_per_minute}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      rate_limit_per_minute: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="wide">
                Notes
                <textarea
                  value={providerDraft.notes}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="provider-enabled-field">
                <input
                  checked={providerDraft.enabled}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      enabled: event.target.checked,
                    }))
                  }
                  type="checkbox"
                />
                Enabled
              </label>
            </div>
            <footer>
              <button type="submit">Save provider</button>
              <button
                className="secondary-button"
                onClick={() => setShowProviderForm(false)}
                type="button"
              >
                Cancel
              </button>
            </footer>
          </form>
        </div>
      )}
    </article>
  );
}
