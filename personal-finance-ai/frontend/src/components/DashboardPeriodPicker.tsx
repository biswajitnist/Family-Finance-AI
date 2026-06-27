import { useEffect, useRef, useState } from "react";

import { AppIcon } from "../icons/IconRegistry";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

export function DashboardPeriodPicker({
  period,
  onChange,
  emptyLabel = "Select month",
  allowClear = false,
}: {
  period: string;
  onChange: (period: string) => void;
  emptyLabel?: string;
  allowClear?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const now = new Date();
  const [selectedYear, selectedMonth] = period
    ? period.split("-").map(Number)
    : [now.getFullYear(), 0];
  const [visibleYear, setVisibleYear] = useState(
    selectedMonth ? selectedYear : now.getFullYear(),
  );
  const yearOptions = Array.from(
    { length: 21 },
    (_, index) => visibleYear - 10 + index,
  );
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function closeWithEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", closeWithEscape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", closeWithEscape);
    };
  }, [open]);

  const label = period
    ? new Intl.DateTimeFormat("en-GB", {
        month: "long",
        year: "numeric",
      }).format(new Date(selectedYear, selectedMonth - 1, 1))
    : emptyLabel;

  return (
    <div className="dashboard-period" ref={rootRef}>
      <button
        aria-expanded={open}
        className="dashboard-period-trigger"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <AppIcon name="calendar" />
        <strong>{label}</strong>
        <AppIcon name="chevronDown" size={16} />
      </button>
      {open && (
        <div className="month-popover">
          <header>
            <button
              aria-label="Previous year"
              onClick={() => setVisibleYear((year) => year - 1)}
            >
              <AppIcon name="chevronLeft" size={16} />
            </button>
            <select
              aria-label="Period year"
              className="month-popover-year"
              value={visibleYear}
              onChange={(event) => setVisibleYear(Number(event.target.value))}
            >
              {yearOptions.map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
            <button
              aria-label="Next year"
              onClick={() => setVisibleYear((year) => year + 1)}
            >
              <AppIcon name="chevronRight" size={16} />
            </button>
          </header>
          <div className="month-grid">
            {MONTHS.map((month, index) => {
              const active =
                visibleYear === selectedYear && index + 1 === selectedMonth;
              return (
                <button
                  className={active ? "active" : ""}
                  key={month}
                  onClick={() => {
                    onChange(
                      `${visibleYear}-${String(index + 1).padStart(2, "0")}`,
                    );
                    setOpen(false);
                  }}
                >
                  {month}
                </button>
              );
            })}
          </div>
          {allowClear && period && (
            <button
              className="month-popover-clear"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
              type="button"
            >
              Show all months
            </button>
          )}
        </div>
      )}
    </div>
  );
}
