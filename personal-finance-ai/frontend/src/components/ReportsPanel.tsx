import { useEffect, useState } from "react";

import { api } from "../api";
import { AppIcon } from "../icons/IconRegistry";
import type { ReportRecord } from "../types";
import { CashFlowReport } from "./CashFlowReport";
import { CustomReportsPanel } from "./CustomReportsPanel";
import { DateField } from "./DateField";

export function ReportsPanel({ initialPeriod }: { initialPeriod: string }) {
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [message, setMessage] = useState("");
  const [view, setView] = useState<"overview" | "custom">("overview");

  async function load() {
    setReports(await api.generatedReports());
  }

  useEffect(() => {
    void load();
  }, []);

  async function create(formData: FormData) {
    try {
      await api.createGeneratedReport({
        report_type: formData.get("report_type"),
        period_start: formData.get("period_start"),
        period_end: formData.get("period_end"),
        format: formData.get("format"),
      });
      setMessage("Report generated from validated database records.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Report failed");
    }
  }

  return (
    <section className="reports-page">
      <header className="module-page-heading report-page-heading">
        <div>
          <p className="eyebrow">Financial intelligence</p>
          <h1>Reports</h1>
          <p>Explore cash flow and create exports from validated local records.</p>
        </div>
        <span className="module-heading-icon"><AppIcon name="reports" size={23} /></span>
      </header>
      <nav className="report-subnav" aria-label="Reports navigation">
        <button
          className={view === "overview" ? "active" : ""}
          onClick={() => setView("overview")}
          type="button"
        >
          Overview & Exports
        </button>
        <button
          className={view === "custom" ? "active" : ""}
          onClick={() => setView("custom")}
          type="button"
        >
          Custom Reports
        </button>
      </nav>
      {view === "custom" ? (
        <CustomReportsPanel />
      ) : (
        <>
      <CashFlowReport initialPeriod={initialPeriod} />
      <section className="module-layout report-tools">
      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Reproducible exports</p>
            <h2>Generate report</h2>
            <p className="section-copy">
              Every export includes its period and uses validated,
              non-duplicate records.
            </p>
          </div>
        </div>
        <form action={create} className="resource-form">
          <label>
            Report
            <select name="report_type">
              {[
                "monthly",
                "yearly",
                "tax",
                "investment",
                "debt",
                "property",
                "protection",
              ].map((type) => (
                <option value={type} key={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
          <label>
            Start
            <DateField name="period_start" required />
          </label>
          <label>
            End
            <DateField name="period_end" required />
          </label>
          <label>
            Format
            <select name="format">
              <option value="pdf">PDF</option>
              <option value="xlsx">Excel</option>
              <option value="csv">CSV</option>
            </select>
          </label>
          <button type="submit"><AppIcon name="file" size={16} /> Generate report</button>
          {message && <span className="form-message">{message}</span>}
        </form>
        <a className="secondary-button backup-link" href={api.backupUrl()}>
          <AppIcon name="backup" size={15} /> Download database backup
        </a>
      </article>
      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Report archive</p>
            <h2>Generated files</h2>
          </div>
        </div>
        <div className="record-list">
          {reports.map((report) => (
            <div className="record-card" key={report.id}>
              <div>
                <strong>{report.report_type} report</strong>
                <small>
                  {report.period_start} to {report.period_end} ·{" "}
                  {report.format.toUpperCase()}
                </small>
              </div>
              <a
                className="secondary-button"
                href={api.reportDownloadUrl(report.id)}
              >
                <AppIcon name="file" size={14} /> Download
              </a>
            </div>
          ))}
          {!reports.length && (
            <p className="empty-state">No reports generated yet.</p>
          )}
        </div>
      </article>
      </section>
        </>
      )}
    </section>
  );
}
