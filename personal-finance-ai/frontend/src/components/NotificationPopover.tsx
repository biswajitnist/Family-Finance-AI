import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { AppIcon } from "../icons/IconRegistry";
import type { AdvisorDashboard } from "../types";

type Alert = AdvisorDashboard["alerts"][number];

export function NotificationPopover({
  period,
  refreshKey,
}: {
  period: string;
  refreshKey?: number;
}) {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selected, setSelected] = useState<Alert | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [year, month] = period.split("-").map(Number);

  async function load() {
    try {
      const advisor = await api.advisorDashboard(year, month);
      setAlerts(advisor.alerts);
    } catch {
      setAlerts([]);
    }
  }

  useEffect(() => {
    void load();
  }, [month, year, refreshKey]);

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setSelected(null);
      }
    }
    function closeWithEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        setSelected(null);
      }
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", closeWithEscape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", closeWithEscape);
    };
  }, [open]);

  async function markRead(alert: Alert) {
    await api.updateAlertStatus(alert.id, "resolved");
    setAlerts((items) => items.filter((item) => item.id !== alert.id));
    if (selected?.id === alert.id) setSelected(null);
  }

  return (
    <div className="notification-anchor" ref={rootRef}>
      <button
        aria-label="Notifications"
        className="round-action notification-trigger"
        onClick={() => setOpen((value) => !value)}
      >
        <AppIcon name="bell" size={18} />
        {alerts.length > 0 && <b>{alerts.length}</b>}
      </button>
      {open && (
        <section className="notification-popover" aria-label="Notifications">
          <header>
            <div>
              <strong>Notifications</strong>
              <small>{alerts.length} unread</small>
            </div>
            <button
              aria-label="Close notifications"
              className="icon-button"
              onClick={() => setOpen(false)}
            >
              <AppIcon name="close" size={17} />
            </button>
          </header>
          {selected ? (
            <div className="notification-details">
              <button className="text-button" onClick={() => setSelected(null)}>
                <AppIcon name="chevronLeft" size={15} /> Back
              </button>
              <span className={`severity ${selected.severity}`}>
                {selected.severity}
              </span>
              <h3>{selected.message}</h3>
              <p>{selected.reason}</p>
              <small>{selected.recommended_action}</small>
              <div className="notification-transactions">
                {selected.transactions.map((transaction) => (
                  <article key={transaction.id}>
                    <div>
                      <strong>{transaction.vendor}</strong>
                      <small>{transaction.transaction_date}</small>
                    </div>
                    <strong>
                      {transaction.transaction_type === "debit" ? "−" : "+"}
                      {transaction.amount} {transaction.currency}
                    </strong>
                  </article>
                ))}
                {!selected.transactions.length && (
                  <p>No individual transaction is attached to this alert.</p>
                )}
              </div>
              <button onClick={() => void markRead(selected)}>Mark as read</button>
            </div>
          ) : (
            <div className="notification-list">
              {alerts.map((alert) => (
                <article className={`notification-item ${alert.severity}`} key={alert.id}>
                  <span className="notification-severity-dot" />
                  <button onClick={() => setSelected(alert)}>
                    <strong>{alert.message}</strong>
                    <small>{alert.reason}</small>
                  </button>
                  <button
                    aria-label={`Mark ${alert.message} as read`}
                    className="notification-read"
                    onClick={() => void markRead(alert)}
                  >
                    <AppIcon name="check" size={15} />
                  </button>
                </article>
              ))}
              {!alerts.length && (
                <div className="notification-empty">
                  <AppIcon name="check" size={22} />
                  <strong>You are all caught up</strong>
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
