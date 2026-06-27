import { useEffect, useState } from "react";

import { api } from "../api";
import { AppIcon } from "../icons/IconRegistry";
import type { AdvisorDashboard } from "../types";

function money(value: string, currency: string) {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
  }).format(Number(value));
}

export function AdvisorDashboardPanel({
  period,
  refreshKey,
  compact = false,
  currency = "EUR",
}: {
  period: string;
  refreshKey?: number;
  compact?: boolean;
  currency?: string;
}) {
  const [year, month] = period.split("-").map(Number);
  const [advisor, setAdvisor] = useState<AdvisorDashboard | null>(null);
  const [showExplanation, setShowExplanation] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setAdvisor(await api.advisorDashboard(year, month));
      setError("");
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Advisor unavailable",
      );
    }
  }

  useEffect(() => {
    void load();
  }, [month, year, refreshKey]);

  async function refresh() {
    setRefreshing(true);
    try {
      setAdvisor(await api.refreshAdvisorDashboard(year, month));
      setError("");
    } catch (refreshError) {
      setError(
        refreshError instanceof Error
          ? refreshError.message
          : "Insight refresh failed",
      );
    } finally {
      setRefreshing(false);
    }
  }

  async function updateRecommendation(id: number, status: string) {
    await api.updateRecommendationStatus(id, status);
    await load();
  }

  async function updateAlert(id: number, status: string) {
    await api.updateAlertStatus(id, status);
    await load();
  }

  if (!advisor) {
    return (
      <article className="panel advisor-panel">
        <p className={error ? "danger-text" : "empty-state"}>
          {error || "Calculating local financial insights..."}
        </p>
      </article>
    );
  }

  const forecastItems = [
    ["Expected income", advisor.forecast.expected_income],
    ["Expected expenses", advisor.forecast.expected_expenses],
    ["Expected surplus", advisor.forecast.expected_surplus],
    ["Month-end balance", advisor.forecast.expected_month_end_balance],
  ];
  const selectedAlert =
    advisor.alerts.find((item) => item.id === selectedAlertId) ?? null;

  if (compact) {
    return (
      <article className="dashboard-advisor-banner">
        <span className="advisor-banner-icon">
          <AppIcon name="sparkles" size={23} />
        </span>
        <div className="advisor-banner-copy">
          <div>
            <span>AI Financial Advisor</span>
            <small>
              Updated {new Date(advisor.generated_at).toLocaleString()}
            </small>
          </div>
          <strong>{advisor.summary_sentence_1}</strong>
          <p>{advisor.summary_sentence_2}</p>
          {showExplanation && (
            <div className="advisor-banner-explanation">
              {advisor.explanation}
              <small>Sources: {advisor.source_basis.join(" · ")}</small>
            </div>
          )}
          {showWhy && (
            <div className="advisor-why">
              <strong>Why?</strong>
              <ul>
                {advisor.alerts.slice(0, 3).map((alert) => (
                  <li key={alert.id}>{alert.reason}</li>
                ))}
                {!advisor.alerts.length && <li>{advisor.summary_sentence_2}</li>}
              </ul>
            </div>
          )}
        </div>
        <div className="advisor-banner-actions">
          <button
            className="secondary-button"
            onClick={() => setShowExplanation((value) => !value)}
          >
            {showExplanation ? "Hide" : "Explain"}
          </button>
          <button
            className="secondary-button"
            onClick={() => setShowWhy((value) => !value)}
          >
            Why?
          </button>
          <button disabled={refreshing} onClick={refresh} type="button">
            <AppIcon name="sparkles" size={15} />
            {refreshing ? "Refreshing..." : "Refresh insights"}
          </button>
        </div>
      </article>
    );
  }

  return (
    <section className="advisor-dashboard">
      <article className="panel advisor-panel">
        <div className="advisor-heading">
          <div>
            <p className="eyebrow">Local intelligence</p>
            <h2>AI Financial Advisor</h2>
          </div>
          <div className="advisor-actions">
            <button
              className="secondary-button"
              onClick={() => setShowExplanation((value) => !value)}
            >
              {showExplanation ? "Hide explanation" : "Explain"}
            </button>
            <button disabled={refreshing} onClick={refresh} type="button">
              {refreshing ? "Refreshing..." : "Refresh insights"}
            </button>
          </div>
        </div>
        <div className="advisor-sentences">
          <strong>{advisor.summary_sentence_1}</strong>
          <p>{advisor.summary_sentence_2}</p>
        </div>
        {showExplanation && (
          <div className="advisor-explanation">
            <p>{advisor.explanation}</p>
            <small>Sources: {advisor.source_basis.join(" · ")}</small>
          </div>
        )}
        <div className="advisor-meta">
          <span>
            Updated {new Date(advisor.generated_at).toLocaleString()}
          </span>
          <span>
            {advisor.local_ai_used
              ? "Wording by local Ollama"
              : "Deterministic local wording"}
          </span>
        </div>
        <div className="advisor-position">
          <div>
            <span>Investments</span>
            <strong>{money(advisor.financial_position.investment_value, currency)}</strong>
          </div>
          <div>
            <span>Debt balance</span>
            <strong>{money(advisor.financial_position.debt_balance, currency)}</strong>
          </div>
          <div>
            <span>Loan payments</span>
            <strong>
              {money(advisor.financial_position.monthly_loan_payments, currency)}/month
            </strong>
          </div>
          <div>
            <span>Net worth context</span>
            <strong>{money(advisor.financial_position.net_worth, currency)}</strong>
          </div>
        </div>
        <small className="advisor-position-note">
          Financial position used by the local advisor
        </small>
      </article>

      <div className="advisor-detail-grid">
        <article className="panel forecast-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Next 30 days</p>
              <h2>Forecast</h2>
            </div>
            <span className="confidence-pill">
              {Math.round(Number(advisor.forecast.confidence_score) * 100)}%
              confidence
            </span>
          </div>
          <div className="forecast-grid">
            {forecastItems.map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong className={Number(value) < 0 ? "danger-text" : ""}>
                  {money(value, currency)}
                </strong>
              </div>
            ))}
          </div>
          <small>
            Known recurring payments:{" "}
            {money(advisor.forecast.recurring_payment_impact, currency)}
          </small>
        </article>

        <article className="panel advisor-list-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Top actions</p>
              <h2>Recommendations</h2>
            </div>
          </div>
          <div className="advisor-list">
            {advisor.recommendations.map((item) => (
              <div className="recommendation-item" key={item.id}>
                <div>
                  <span className={`priority ${item.priority.toLowerCase()}`}>
                    {item.priority}
                  </span>
                  <strong>{item.title}</strong>
                  <p>{item.description}</p>
                  <small>Potential impact: {money(item.estimated_impact_amount, currency)}</small>
                </div>
                <div className="inline-actions">
                  <button
                    className="secondary-button"
                    onClick={() => updateRecommendation(item.id, "completed")}
                  >
                    Mark done
                  </button>
                  <button
                    className="text-button"
                    onClick={() => updateRecommendation(item.id, "dismissed")}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
            {!advisor.recommendations.length && (
              <p className="empty-state">No active recommendations.</p>
            )}
          </div>
        </article>

        <article className="panel advisor-list-panel alert-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Important only</p>
              <h2>Risk alerts</h2>
            </div>
          </div>
          <div className="advisor-list">
            {advisor.alerts.map((item) => (
              <div className="alert-item" key={item.id}>
                <span className={`severity ${item.severity}`}>
                  {item.severity}
                </span>
                <strong>{item.message}</strong>
                <p>{item.reason}</p>
                <small>{item.recommended_action}</small>
                <div className="inline-actions alert-actions">
                  <button
                    className="secondary-button"
                    onClick={() => setSelectedAlertId(item.id)}
                  >
                    View transactions
                    {item.transactions.length > 0
                      ? ` (${item.transactions.length})`
                      : ""}
                  </button>
                  <button
                    className="text-button"
                    onClick={() => updateAlert(item.id, "dismissed")}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
            {!advisor.alerts.length && (
              <p className="empty-state">No important risks detected.</p>
            )}
          </div>
        </article>
      </div>
      {selectedAlert && (
        <div
          className="risk-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedAlertId(null);
          }}
          role="presentation"
        >
          <section
            aria-labelledby="risk-transactions-title"
            aria-modal="true"
            className="risk-modal"
            role="dialog"
          >
            <header>
              <div>
                <p className="eyebrow">Risk evidence</p>
                <h2 id="risk-transactions-title">{selectedAlert.message}</h2>
                <p>{selectedAlert.reason}</p>
              </div>
              <button
                aria-label="Close transaction details"
                className="risk-modal-close"
                onClick={() => setSelectedAlertId(null)}
              >
                ×
              </button>
            </header>
            {selectedAlert.transactions.length ? (
              <div className="risk-transaction-list">
                {selectedAlert.transactions.map((transaction) => (
                  <article key={transaction.id}>
                    <div>
                      <strong>{transaction.vendor}</strong>
                      <small>
                        {transaction.transaction_date} · {transaction.account}
                      </small>
                      {transaction.description && (
                        <p>{transaction.description}</p>
                      )}
                    </div>
                    <div className="risk-transaction-meta">
                      <span>{transaction.category}</span>
                      {transaction.is_duplicate && (
                        <span className="duplicate-badge">Duplicate</span>
                      )}
                      <strong>
                        {transaction.transaction_type === "debit" ? "−" : "+"}
                        {money(transaction.amount, transaction.currency)}
                      </strong>
                      <small>
                        {transaction.is_validated
                          ? "Validated"
                          : "Needs review"}
                      </small>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="risk-modal-empty">
                <strong>No single transaction caused this alert.</strong>
                <p>
                  This risk comes from the combined forecast, balance, or missing
                  expected activity.
                </p>
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
