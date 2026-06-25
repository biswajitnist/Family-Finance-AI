import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { AppIcon, type IconName } from "../icons/IconRegistry";
import type { ResourceRecord } from "../types";

type SearchPage =
  | "transactions"
  | "documents"
  | "investments"
  | "properties"
  | "loans"
  | "insurance";

type SearchResult = {
  label: string;
  detail: string;
  page: SearchPage;
  icon: IconName;
};

export function CommandCenter({
  onNavigate,
}: {
  onNavigate: (page: SearchPage) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [records, setRecords] = useState<SearchResult[]>([]);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || records.length) return;
    void Promise.all([
      api.resources("investments"),
      api.resources("properties"),
      api.resources("loans"),
      api.resources("insurance"),
      api.transactions(),
      api.documents(),
    ]).then(([investments, properties, loans, insurance, transactions, documents]) => {
      const map = (
        items: ResourceRecord[],
        page: SearchPage,
        icon: IconName,
        name: string,
        detail: string,
      ) =>
        items.map((item) => ({
          label: String(item[name] ?? "Record"),
          detail: String(item[detail] ?? page),
          page,
          icon,
        }));
      setRecords([
        ...map(investments, "investments", "investments", "asset_name", "ticker"),
        ...map(properties, "properties", "properties", "name", "country"),
        ...map(loans, "loans", "loans", "lender", "loan_type"),
        ...map(insurance, "insurance", "insurance", "provider", "policy_type"),
        ...transactions.map((item) => ({
          label: item.vendor,
          detail: `${item.transaction_date} · ${item.description || item.amount}`,
          page: "transactions" as const,
          icon: "transactions" as const,
        })),
        ...documents.map((item) => ({
          label: item.file_name,
          detail: item.document_type,
          page: "documents" as const,
          icon: "documents" as const,
        })),
      ]);
    });
  }, [open, records.length]);

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const normalized = query.trim().toLowerCase();
  const results = normalized
    ? records
        .filter((item) =>
          `${item.label} ${item.detail}`.toLowerCase().includes(normalized),
        )
        .slice(0, 8)
    : [];

  return (
    <div className="command-center" ref={rootRef}>
      <button
        aria-expanded={open}
        className="command-search-trigger"
        onClick={() => setOpen((value) => !value)}
      >
        <AppIcon name="search" size={17} />
        <span>Search everything</span>
      </button>
      {open && (
        <section className="command-search-popover">
          <label>
            <AppIcon name="search" size={18} />
            <input
              autoFocus
              onChange={(event) => setQuery(event.target.value)}
              placeholder="NVIDIA, Commerzbank, property, insurance..."
              value={query}
            />
          </label>
          <div className="command-results">
            {results.map((item) => (
              <button
                key={`${item.page}-${item.label}`}
                onClick={() => {
                  onNavigate(item.page);
                  setOpen(false);
                  setQuery("");
                }}
              >
                <span><AppIcon name={item.icon} size={17} /></span>
                <span><strong>{item.label}</strong><small>{item.detail}</small></span>
                <AppIcon name="chevronRight" size={15} />
              </button>
            ))}
            {normalized && !results.length && (
              <p>No matching local record. Try a merchant, asset, property, or provider.</p>
            )}
            {!normalized && (
              <p>Search investments, real estate, loans, and insurance locally.</p>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
