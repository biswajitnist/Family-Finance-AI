import { useEffect, useRef, useState } from "react";

import { AppIcon } from "../icons/IconRegistry";

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function parseDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return year && month && day ? new Date(year, month - 1, day) : null;
}

function dateValue(date: Date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function displayDate(value: string) {
  const date = parseDate(value);
  return date
    ? new Intl.DateTimeFormat("en-GB", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }).format(date)
    : "Select date";
}

export function DateField({
  name,
  value,
  defaultValue = "",
  onChange,
  required = false,
}: {
  name?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  required?: boolean;
}) {
  const controlled = value !== undefined;
  const [internalValue, setInternalValue] = useState(defaultValue);
  const selectedValue = controlled ? value : internalValue;
  const selectedDate = parseDate(selectedValue);
  const today = new Date();
  const [visibleMonth, setVisibleMonth] = useState(
    new Date(
      selectedDate?.getFullYear() ?? today.getFullYear(),
      selectedDate?.getMonth() ?? today.getMonth(),
      1,
    ),
  );
  const [open, setOpen] = useState(false);
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

  function select(nextValue: string) {
    if (!controlled) setInternalValue(nextValue);
    onChange?.(nextValue);
    setOpen(false);
  }

  const firstWeekday = (visibleMonth.getDay() + 6) % 7;
  const yearOptions = Array.from(
    { length: 21 },
    (_, index) => visibleMonth.getFullYear() - 10 + index,
  );
  const daysInMonth = new Date(
    visibleMonth.getFullYear(),
    visibleMonth.getMonth() + 1,
    0,
  ).getDate();
  const days = Array.from({ length: firstWeekday + daysInMonth }, (_, index) =>
    index < firstWeekday ? null : index - firstWeekday + 1,
  );

  return (
    <div className="date-field" ref={rootRef}>
      {name && <input name={name} type="hidden" value={selectedValue} />}
      <button
        aria-expanded={open}
        className={`date-field-trigger ${selectedValue ? "" : "empty"}`}
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span>{displayDate(selectedValue)}</span>
        <AppIcon name="calendar" size={17} />
      </button>
      {required && !selectedValue && (
        <input
          aria-hidden="true"
          className="date-field-required"
          required
          tabIndex={-1}
          value=""
          onChange={() => undefined}
        />
      )}
      {open && (
        <div className="date-popover">
          <header>
            <button
              aria-label="Previous month"
              onClick={() =>
                setVisibleMonth(
                  new Date(
                    visibleMonth.getFullYear(),
                    visibleMonth.getMonth() - 1,
                    1,
                  ),
                )
              }
              type="button"
            >
              <AppIcon name="chevronLeft" size={16} />
            </button>
            <div className="date-popover-selectors">
              <select
                aria-label="Calendar month"
                value={visibleMonth.getMonth()}
                onChange={(event) =>
                  setVisibleMonth(
                    new Date(
                      visibleMonth.getFullYear(),
                      Number(event.target.value),
                      1,
                    ),
                  )
                }
              >
                {MONTHS.map((month, index) => (
                  <option key={month} value={index}>
                    {month}
                  </option>
                ))}
              </select>
              <select
                aria-label="Calendar year"
                value={visibleMonth.getFullYear()}
                onChange={(event) =>
                  setVisibleMonth(
                    new Date(
                      Number(event.target.value),
                      visibleMonth.getMonth(),
                      1,
                    ),
                  )
                }
              >
                {yearOptions.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>
            <button
              aria-label="Next month"
              onClick={() =>
                setVisibleMonth(
                  new Date(
                    visibleMonth.getFullYear(),
                    visibleMonth.getMonth() + 1,
                    1,
                  ),
                )
              }
              type="button"
            >
              <AppIcon name="chevronRight" size={16} />
            </button>
          </header>
          <div className="date-weekdays">
            {["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((day) => (
              <span key={day}>{day}</span>
            ))}
          </div>
          <div className="date-grid">
            {days.map((day, index) =>
              day ? (
                <button
                  className={
                    selectedValue ===
                    dateValue(
                      new Date(
                        visibleMonth.getFullYear(),
                        visibleMonth.getMonth(),
                        day,
                      ),
                    )
                      ? "active"
                      : ""
                  }
                  key={day}
                  onClick={() =>
                    select(
                      dateValue(
                        new Date(
                          visibleMonth.getFullYear(),
                          visibleMonth.getMonth(),
                          day,
                        ),
                      ),
                    )
                  }
                  type="button"
                >
                  {day}
                </button>
              ) : (
                <span key={`empty-${index}`} />
              ),
            )}
          </div>
          <footer>
            <button
              className="date-today"
              onClick={() => select(dateValue(today))}
              type="button"
            >
              Today
            </button>
            {selectedValue && !required && (
              <button
                className="date-clear"
                onClick={() => select("")}
                type="button"
              >
                Clear
              </button>
            )}
          </footer>
        </div>
      )}
    </div>
  );
}
