import { useEffect, useState, type FormEvent } from "react";

import { api } from "../api";
import { AppIcon } from "../icons/IconRegistry";
import type { UserProfile } from "../types";
import { MarketDataPanel } from "./MarketDataPanel";

const CURRENCIES = ["EUR", "USD", "GBP", "INR", "CHF", "JPY", "CAD", "AUD"];

export function SettingsPanel({
  profile,
  onSaved,
}: {
  profile: UserProfile | null;
  onSaved: (profile: UserProfile) => void;
}) {
  const [values, setValues] = useState<UserProfile | null>(profile);
  const [message, setMessage] = useState("");
  const [section, setSection] = useState("profile");

  useEffect(() => setValues(profile), [profile]);

  if (!values) return <p className="empty-state">Loading local profile...</p>;

  function change(name: keyof UserProfile, value: string | boolean) {
    setValues((current) => (current ? { ...current, [name]: value } : current));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!values) return;
    const { id: _id, ...payload } = values;
    const saved = await api.updateProfile(payload);
    setValues(saved);
    onSaved(saved);
    setMessage("Master configuration saved locally.");
  }

  return (
    <>
      <section className="page-heading settings-heading">
        <div>
          <p className="eyebrow">Local account</p>
          <h1>Settings</h1>
          <p>Manage your profile, display currency, locale, and portfolio defaults.</p>
        </div>
      </section>
      <div className="settings-workspace">
        <nav className="settings-navigation">
          {[
            ["profile", "user", "Profile"],
            ["master", "controls", "Master Configuration"],
            ["providers", "providers", "Market Data Providers"],
            ["ai", "sparkles", "AI Settings"],
            ["sources", "database", "Data Sources"],
            ["backup", "backup", "Backup & Restore"],
            ["security", "security", "Security"],
            ["themes", "themes", "Themes"],
          ].map(([value, icon, label]) => (
            <button
              className={section === value ? "active" : ""}
              key={value}
              onClick={() => setSection(value)}
            >
              <AppIcon name={icon as Parameters<typeof AppIcon>[0]["name"]} />
              {label}
            </button>
          ))}
        </nav>
        {(section === "profile" || section === "master") && (
          <form className="panel settings-panel" onSubmit={save}>
            <div className="panel-heading">
              <div>
                <p className="eyebrow">
                  {section === "profile" ? "Profile" : "Master configuration"}
                </p>
                <h2>
                  {section === "profile"
                    ? "Local user profile"
                    : "Regional and portfolio preferences"}
                </h2>
              </div>
              <span className="settings-local-badge">
                <AppIcon name="insurance" size={15} /> Stored locally
              </span>
            </div>
            <div className="settings-grid">
              {section === "profile" && (
                <>
          <label>
            Display name
            <input
              value={values.name}
              onChange={(event) => change("name", event.target.value)}
            />
          </label>
          <label>
            Email (optional)
            <input
              type="email"
              value={values.email ?? ""}
              onChange={(event) => change("email", event.target.value)}
            />
          </label>
                </>
              )}
              {section === "master" && (
                <>
          <label>
            Base currency
            <select
              value={values.base_currency}
              onChange={(event) => change("base_currency", event.target.value)}
            >
              {CURRENCIES.map((currency) => (
                <option key={currency}>{currency}</option>
              ))}
            </select>
            <small>Dashboard totals and reports use this display currency.</small>
          </label>
          <label>
            Country
            <input
              maxLength={2}
              value={values.country}
              onChange={(event) => change("country", event.target.value.toUpperCase())}
            />
          </label>
          <label>
            Tax country
            <input
              maxLength={2}
              value={values.tax_country}
              onChange={(event) =>
                change("tax_country", event.target.value.toUpperCase())
              }
            />
          </label>
          <label>
            Timezone
            <input
              value={values.timezone}
              onChange={(event) => change("timezone", event.target.value)}
            />
          </label>
          <label>
            Language
            <select
              value={values.preferred_language}
              onChange={(event) =>
                change("preferred_language", event.target.value)
              }
            >
              <option value="en">English</option>
              <option value="de">German</option>
            </select>
          </label>
          <label>
            Date format
            <select
              value={values.date_format}
              onChange={(event) => change("date_format", event.target.value)}
            >
              <option>DD-MM-YYYY</option>
              <option>MM-DD-YYYY</option>
              <option>YYYY-MM-DD</option>
            </select>
          </label>
          <label>
            Number format
            <select
              value={values.number_format}
              onChange={(event) => change("number_format", event.target.value)}
            >
              <option>1.234,56</option>
              <option>1,234.56</option>
            </select>
          </label>
          <label>
            Financial year starts
            <input
              placeholder="01-01"
              value={values.financial_year_start}
              onChange={(event) =>
                change("financial_year_start", event.target.value)
              }
            />
          </label>
          <label>
            Default portfolio view
            <select
              value={values.default_portfolio_view}
              onChange={(event) =>
                change("default_portfolio_view", event.target.value)
              }
            >
              <option value="overview">Overview</option>
              <option value="asset_class">By asset class</option>
              <option value="country">By country</option>
              <option value="currency">By currency</option>
            </select>
          </label>
          <label>
            Default refresh frequency
            <select
              value={values.default_refresh_frequency}
              onChange={(event) =>
                change("default_refresh_frequency", event.target.value)
              }
            >
              <option value="manual">Manual only</option>
              <option value="15_minutes">Every 15 minutes</option>
              <option value="30_minutes">Every 30 minutes</option>
              <option value="hourly">Every 1 hour</option>
              <option value="daily">Daily</option>
            </select>
          </label>
                </>
              )}
        </div>
        <div className="settings-actions">
          <span>{message}</span>
          <button type="submit">Save settings</button>
        </div>
          </form>
        )}
        {section === "providers" && <MarketDataPanel />}
        {section === "ai" && (
          <article className="panel settings-section-card">
            <span><AppIcon name="sparkles" /></span>
            <div><p className="eyebrow">AI settings</p><h2>Local Ollama assistant</h2><p>Finance AI, document help, and explanations remain local. Configure the Ollama model from the local runtime environment.</p></div>
          </article>
        )}
        {section === "sources" && (
          <article className="panel settings-section-card">
            <span><AppIcon name="database" /></span>
            <div><p className="eyebrow">Data sources</p><h2>Local financial sources</h2><p>SQLite records, uploaded documents, OCR text, and the local Chroma index supply the application.</p></div>
          </article>
        )}
        {section === "backup" && (
          <article className="panel settings-section-card">
            <span><AppIcon name="backup" /></span>
            <div><p className="eyebrow">Backup & restore</p><h2>Protect your local records</h2><p>Download a database backup containing your locally saved finance data.</p><a className="secondary-button" href={api.backupUrl()}>Download backup</a></div>
          </article>
        )}
        {section === "security" && (
          <article className="panel settings-section-card">
            <span><AppIcon name="security" /></span>
            <div><p className="eyebrow">Security</p><h2>Private by design</h2><p>Documents, transactions, and personal details stay on this machine. Only approved market symbols are sent to configured quote providers.</p></div>
          </article>
        )}
        {section === "themes" && (
          <article className="panel settings-section-card">
            <span><AppIcon name="themes" /></span>
            <div><p className="eyebrow">Themes</p><h2>Ledger Light</h2><p>The soft green local-finance theme is active across the dashboard, reports, planning, and management pages.</p></div>
          </article>
        )}
      </div>
    </>
  );
}
