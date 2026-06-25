import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api";
import { AppIcon } from "../icons/IconRegistry";
import type { CashFlowComparison } from "../types";
import { DashboardPeriodPicker } from "./DashboardPeriodPicker";

type View = "cash_flow" | "income" | "expense";

const COLORS = [
  "#cf4567",
  "#f48a43",
  "#eab83f",
  "#2e9185",
  "#537dd1",
  "#7a61b3",
  "#657586",
  "#bd5c91",
  "#61a85d",
  "#a06b4f",
];

function money(value: string | number, currency: string) {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
  }).format(Number(value));
}

const VIEW_LABELS: Record<View, string> = {
  cash_flow: "Cash Flow",
  income: "Income",
  expense: "Expense",
};

export function CashFlowReport({ initialPeriod }: { initialPeriod: string }) {
  const [period, setPeriod] = useState(initialPeriod);
  const [view, setView] = useState<View>("expense");
  const [report, setReport] = useState<CashFlowComparison | null>(null);
  const [error, setError] = useState("");
  const [year, month] = period.split("-").map(Number);

  useEffect(() => {
    setError("");
    void api
      .cashFlowComparison(year, month)
      .then(setReport)
      .catch((loadError) =>
        setError(loadError instanceof Error ? loadError.message : "Report failed"),
      );
  }, [month, year]);

  const selected = useMemo(() => {
    if (!report) return null;
    const current = Number(report.current[view]);
    const previous = Number(report.previous[view]);
    const difference = current - previous;
    const rawCategories =
      view === "expense"
        ? report.expense_categories
        : view === "income"
          ? report.income_categories
          : [
              { category: "Income", amount: report.current.income },
              { category: "Expenses", amount: report.current.expense },
            ];
    const categories = rawCategories.map((item) => ({
      ...item,
      amount: Number(item.amount),
    }));
    return {
      current,
      previous,
      difference,
      categories,
      currentKey: `current_${view}` as const,
      previousKey: `previous_${view}` as const,
    };
  }, [report, view]);

  if (!report || !selected) {
    return (
      <article className="panel cash-flow-report">
        <p className={error ? "danger-text" : "empty-state"}>
          {error || "Loading cash flow report..."}
        </p>
      </article>
    );
  }

  const chartData = report.daily.map((item) => ({
    ...item,
    current_income: Number(item.current_income),
    current_expense: Number(item.current_expense),
    current_cash_flow: Number(item.current_cash_flow),
    previous_income: Number(item.previous_income),
    previous_expense: Number(item.previous_expense),
    previous_cash_flow: Number(item.previous_cash_flow),
  }));
  const direction = selected.difference <= 0 ? "less than" : "more than";
  const favorable =
    view === "expense"
      ? selected.difference <= 0
      : view === "income"
        ? selected.difference >= 0
        : selected.current >= selected.previous;
  const donutTotal = selected.categories.reduce(
    (total, item) => total + Math.max(0, item.amount),
    0,
  );
  let donutOffset = 0;
  const donutGradient =
    donutTotal > 0
      ? `conic-gradient(${selected.categories
          .map((item, index) => {
            const start = donutOffset;
            donutOffset += (Math.max(0, item.amount) / donutTotal) * 100;
            return `${COLORS[index % COLORS.length]} ${start}% ${donutOffset}%`;
          })
          .join(", ")})`
      : "conic-gradient(#e7e9ec 0% 100%)";

  return (
    <article className="panel cash-flow-report">
      <header className="cash-flow-header">
        <div>
          <p className="eyebrow">Interactive monthly report</p>
          <h2><AppIcon name="chart" size={22} /> Cash Flow</h2>
          <p>
            Calendar month {report.current_month} compared with{" "}
            {report.previous_month}
          </p>
        </div>
        <div className="cash-flow-controls">
          <div className="module-period-picker">
            <span>Report month</span>
            <DashboardPeriodPicker period={period} onChange={setPeriod} />
          </div>
          <div className="segmented-control">
            {(Object.keys(VIEW_LABELS) as View[]).map((item) => (
              <button
                className={view === item ? "active" : ""}
                key={item}
                onClick={() => setView(item)}
              >
                {VIEW_LABELS[item]}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="cash-flow-body">
        <section className="cash-flow-breakdown">
          <div className="cash-flow-section-title">
            <h2>{VIEW_LABELS[view]} categories</h2>
            <strong>{money(selected.current, report.currency)}</strong>
          </div>
          <div className="cash-flow-category-content">
            <div className="donut-wrap">
              <div
                aria-label={`${VIEW_LABELS[view]} category chart`}
                className="donut-ring"
                role="img"
                style={{ background: donutGradient }}
              />
              <div className="donut-center">
                <span>{VIEW_LABELS[view]}</span>
                <strong>{money(selected.current, report.currency)}</strong>
              </div>
            </div>
            <div className="cash-flow-categories">
              {selected.categories.slice(0, 9).map((item, index) => (
                <div key={item.category}>
                  <i style={{ background: COLORS[index % COLORS.length] }} />
                  <span>{item.category}</span>
                  <strong>{money(item.amount, report.currency)}</strong>
                </div>
              ))}
              {!selected.categories.length && (
                <p className="empty-state">No records in this month.</p>
              )}
            </div>
          </div>
        </section>

        <section className="cash-flow-chart">
          <div className="cash-flow-section-title">
            <h2>Cumulative {VIEW_LABELS[view].toLowerCase()}</h2>
            <strong className={favorable ? "positive-text" : "danger-text"}>
              {money(Math.abs(selected.difference), report.currency)} {direction}{" "}
              previous
            </strong>
          </div>
          <div className="cash-flow-legend">
            <span className="current">{report.current_month}</span>
            <span className="previous">{report.previous_month}</span>
          </div>
          <ResponsiveContainer width="100%" height={360}>
            <ComposedChart data={chartData}>
              <defs>
                <linearGradient id="cashFlowFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#cf4567" stopOpacity={0.2} />
                  <stop offset="100%" stopColor="#cf4567" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#e4e7e3" vertical={false} />
              <XAxis dataKey="day" tickLine={false} axisLine={false} />
              <YAxis
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) =>
                  new Intl.NumberFormat("en-DE", {
                    notation: "compact",
                    maximumFractionDigits: 1,
                  }).format(value)
                }
              />
              <Tooltip
                formatter={(value) => money(Number(value), report.currency)}
                labelFormatter={(day) => `Day ${day}`}
              />
              <Area
                dataKey={selected.currentKey}
                type="monotone"
                fill="url(#cashFlowFill)"
                stroke="#cf4567"
                strokeWidth={4}
                dot={false}
              />
              <Line
                dataKey={selected.previousKey}
                type="monotone"
                stroke="#e49a28"
                strokeWidth={3}
                strokeDasharray="7 7"
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="cash-flow-caption">
            {VIEW_LABELS[view]} for {report.current_month}:{" "}
            <strong>{money(selected.current, report.currency)}</strong>. Previous
            month: <strong>{money(selected.previous, report.currency)}</strong>.
          </p>
        </section>
      </div>
    </article>
  );
}
