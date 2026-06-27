import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import { AppIcon } from "../icons/IconRegistry";
import type {
  CustomReport,
  CustomReportChartType,
  CustomReportConfig,
  CustomReportFilter,
  CustomReportResult,
  ReportMetadata,
} from "../types";

const STEP_LABELS = [
  "Data Source",
  "Fields",
  "Filters",
  "Group & Aggregate",
  "Chart",
  "Preview",
  "Save",
];
const CHART_COLORS = [
  "var(--ledger-green)",
  "var(--ledger-coral)",
  "#d9a441",
  "#477fc2",
  "#8668bd",
];
const CHART_GRID_COLOR = "var(--ledger-border)";
const CHART_AREA_FILL = "var(--ledger-soft)";

const EMPTY_CONFIG: CustomReportConfig = {
  fields: ["transaction_date", "vendor", "category", "amount"],
  filters: [],
  groupBy: [],
  aggregation: null,
  sort: null,
  limit: 100,
  chart: { type: "table", xAxis: null, yAxis: null },
};

function chartWithDefaults(chart: CustomReportConfig["chart"]) {
  return {
    showLegend: true,
    showDataLabels: false,
    showTable: chart.type === "table",
    showFilters: true,
    ...chart,
  };
}

function defaultConfigForSource(sourceKey: string): CustomReportConfig {
  if (sourceKey === "loans") {
    return {
      fields: ["lender", "current_balance"],
      filters: [],
      groupBy: ["lender"],
      aggregation: { field: "current_balance", function: "sum" },
      sort: { field: "current_balance", direction: "desc" },
      limit: 20,
      chart: { type: "bar", xAxis: "lender", yAxis: "current_balance" },
    };
  }
  if (sourceKey === "investments") {
    return {
      fields: ["asset_name", "asset_type", "current_value"],
      filters: [],
      groupBy: ["asset_type"],
      aggregation: { field: "current_value", function: "sum" },
      sort: { field: "current_value", direction: "desc" },
      limit: 20,
      chart: { type: "donut", xAxis: "asset_type", yAxis: "current_value" },
    };
  }
  if (sourceKey === "net_worth") {
    return {
      fields: ["metric", "value", "currency"],
      filters: [],
      groupBy: [],
      aggregation: null,
      sort: null,
      limit: 10,
      chart: { type: "kpi", xAxis: "metric", yAxis: "value" },
    };
  }
  return { ...EMPTY_CONFIG, filters: [], groupBy: [], sort: null };
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
  }).format(new Date(value));
}

function fieldLabel(metadata: ReportMetadata | null, sourceKey: string, key: string) {
  return (
    metadata?.data_sources
      .find((source) => source.key === sourceKey)
      ?.fields.find((field) => field.key === key)?.label ??
    key
  );
}

function FilterValueInput({
  filter,
  index,
  metadata,
  onChange,
  sourceKey,
}: {
  filter: CustomReportFilter;
  index: number;
  metadata: ReportMetadata | null;
  onChange: (filter: CustomReportFilter) => void;
  sourceKey: string;
}) {
  const fields =
    metadata?.data_sources.find((source) => source.key === sourceKey)?.fields ?? [];
  const selectedField = fields.find((field) => field.key === filter.field);
  const noValue = ["is_empty", "is_not_empty"].includes(filter.operator);
  if (noValue) return null;
  if (selectedField?.options.length) {
    return (
      <select
        aria-label={`Filter ${index + 1} value`}
        onChange={(event) => onChange({ ...filter, value: event.target.value })}
        value={String(filter.value ?? "")}
      >
        <option value="">Select value</option>
        {selectedField.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  if (filter.operator === "date_range") {
    return (
      <select
        aria-label={`Filter ${index + 1} date range`}
        onChange={(event) => onChange({ ...filter, value: event.target.value })}
        value={String(filter.value ?? "")}
      >
        <option value="">Select range</option>
        <option value="this_month">This Month</option>
        <option value="last_month">Last Month</option>
        <option value="this_year">This Year</option>
        <option value="last_3_months">Last 3 Months</option>
        <option value="last_6_months">Last 6 Months</option>
        <option value="last_12_months">Last 12 Months</option>
      </select>
    );
  }
  return (
    <input
      aria-label={`Filter ${index + 1} value`}
      onChange={(event) => onChange({ ...filter, value: event.target.value })}
      placeholder={filter.operator === "between" ? "Minimum, maximum" : "Filter value"}
      value={String(filter.value ?? "")}
    />
  );
}

function EditableFiltersPanel({
  config,
  metadata,
  onChange,
  sourceKey,
}: {
  config: CustomReportConfig;
  metadata: ReportMetadata | null;
  onChange: (config: CustomReportConfig) => void;
  sourceKey: string;
}) {
  const fields =
    metadata?.data_sources.find((source) => source.key === sourceKey)?.fields ?? [];
  const setFilter = (index: number, filter: CustomReportFilter) => {
    onChange({
      ...config,
      filters: config.filters.map((item, itemIndex) =>
        itemIndex === index ? filter : item,
      ),
    });
  };

  return (
    <article className="panel configured-report-filters">
      <div>
        <p className="eyebrow">Configured Filters</p>
        <h3>Edit report filters</h3>
      </div>
      {config.filters.length ? (
        <div className="report-view-filter-editor">
          {config.filters.map((filter, index) => (
            <div className="filter-row" key={`${filter.field}-${filter.operator}-${index}`}>
              <select
                aria-label={`Filter ${index + 1} field`}
                onChange={(event) =>
                  setFilter(index, { ...filter, field: event.target.value, value: "" })
                }
                value={filter.field}
              >
                {fields.map((field) => (
                  <option key={field.key} value={field.key}>
                    {field.label}
                  </option>
                ))}
              </select>
              <select
                aria-label={`Filter ${index + 1} operator`}
                onChange={(event) =>
                  setFilter(index, {
                    ...filter,
                    operator: event.target.value as CustomReportFilter["operator"],
                    value: "",
                  })
                }
                value={filter.operator}
              >
                {metadata?.filter_operators.map((operator) => (
                  <option key={operator.key} value={operator.key}>
                    {operator.label}
                  </option>
                ))}
              </select>
              <FilterValueInput
                filter={filter}
                index={index}
                metadata={metadata}
                onChange={(nextFilter) => setFilter(index, nextFilter)}
                sourceKey={sourceKey}
              />
              <button
                className="text-button danger"
                onClick={() =>
                  onChange({
                    ...config,
                    filters: config.filters.filter((_, itemIndex) => itemIndex !== index),
                  })
                }
                type="button"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p>No filters configured. This report uses all records from its data source.</p>
      )}
      <div className="configured-filter-actions">
        <button
          className="secondary-button"
          onClick={() =>
            onChange({
              ...config,
              filters: [
                ...config.filters,
                { field: fields[0]?.key ?? "vendor", operator: "equals", value: "" },
              ],
            })
          }
          type="button"
        >
          <AppIcon name="add" size={15} /> Add filter
        </button>
      </div>
    </article>
  );
}

function normalizeFilterValue(filter: CustomReportFilter) {
  if (
    (filter.operator === "between" || filter.operator === "date_range") &&
    typeof filter.value === "string" &&
    String(filter.value).includes(",")
  ) {
    return String(filter.value)
      .split(",")
      .map((value) => value.trim());
  }
  return filter.value;
}

function reportPayload(
  name: string,
  description: string,
  dataSource: string,
  config: CustomReportConfig,
  options: {
    dashboardSection?: string | null;
    widgetSize?: string | null;
    widgetPosition?: number | null;
    scheduleFrequency?: string | null;
  } = {},
) {
  const normalizedConfig = {
    ...config,
    filters: config.filters.map((filter) => ({
      ...filter,
      value: normalizeFilterValue(filter),
    })),
  };
  return {
    name,
    description: description || null,
    data_source: dataSource,
    chart_type: normalizedConfig.chart.type,
    config_json: normalizedConfig,
    dashboard_section: options.dashboardSection || null,
    widget_size: options.widgetSize || null,
    widget_position: options.widgetPosition ?? null,
    schedule_frequency: options.scheduleFrequency || null,
  };
}

function ReportResultView({
  config,
  result,
  title,
}: {
  config: CustomReportConfig;
  result: CustomReportResult;
  title: string;
}) {
  if (!result.rows.length) {
    return <p className="empty-state">No records match this report configuration.</p>;
  }
  const xAxis = result.x_axis ?? result.columns[0]?.key;
  const yAxis = result.y_axis ?? result.columns[1]?.key;
  const chart = chartWithDefaults(config.chart);
  const showLegend = chart.showLegend;
  const showDataLabels = chart.showDataLabels;
  const showTable = chart.type === "table" || chart.showTable;

  if (result.chart_type === "kpi" || result.chart_type === "trend") {
    return (
      <div className="custom-report-result-stack">
        <div className="custom-report-kpi-card">
          <span>{result.subtitle ?? title}</span>
          <strong>{String(result.value ?? result.rows[0]?.[yAxis] ?? "—")}</strong>
          <small>{result.rows[0]?.[xAxis] ? String(result.rows[0]?.[xAxis]) : "Report metric"}</small>
        </div>
        {showTable && <ReportDataTable result={result} />}
      </div>
    );
  }

  const chartContent = (() => {
  if (
    result.chart_type === "bar" ||
    result.chart_type === "stacked_bar" ||
    result.chart_type === "grouped_bar"
  ) {
    return (
      <div className="custom-report-chart" aria-label={`${title} bar chart`}>
        <ResponsiveContainer width="100%" height={330}>
          <BarChart data={result.rows}>
            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="4 4" vertical={false} />
            <XAxis dataKey={xAxis} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            {showLegend && <Legend />}
            <Bar dataKey={yAxis} fill="var(--ledger-green)" radius={[7, 7, 0, 0]}>
              {showDataLabels && <LabelList dataKey={yAxis} position="top" />}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (result.chart_type === "horizontal_bar") {
    return (
      <div className="custom-report-chart" aria-label={`${title} horizontal bar chart`}>
        <ResponsiveContainer width="100%" height={330}>
          <BarChart data={result.rows} layout="vertical">
            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="4 4" horizontal={false} />
            <XAxis tick={{ fontSize: 10 }} type="number" />
            <YAxis dataKey={xAxis} tick={{ fontSize: 10 }} type="category" width={110} />
            <Tooltip />
            {showLegend && <Legend />}
            <Bar dataKey={yAxis} fill="var(--ledger-green)" radius={[0, 7, 7, 0]}>
              {showDataLabels && <LabelList dataKey={yAxis} position="right" />}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (result.chart_type === "line") {
    return (
      <div className="custom-report-chart" aria-label={`${title} line chart`}>
        <ResponsiveContainer width="100%" height={330}>
          <LineChart data={result.rows}>
            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="4 4" vertical={false} />
            <XAxis dataKey={xAxis} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            {showLegend && <Legend />}
            <Line
              dataKey={yAxis}
              dot={{ r: 3 }}
              stroke="var(--ledger-green)"
              strokeWidth={3}
              type="monotone"
            >
              {showDataLabels && <LabelList dataKey={yAxis} position="top" />}
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (result.chart_type === "area") {
    return (
      <div className="custom-report-chart" aria-label={`${title} area chart`}>
        <ResponsiveContainer width="100%" height={330}>
          <AreaChart data={result.rows}>
            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="4 4" vertical={false} />
            <XAxis dataKey={xAxis} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            {showLegend && <Legend />}
            <Area
              dataKey={yAxis}
              fill={CHART_AREA_FILL}
              stroke="var(--ledger-green)"
              strokeWidth={3}
              type="monotone"
            >
              {showDataLabels && <LabelList dataKey={yAxis} position="top" />}
            </Area>
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  }
  if (result.chart_type === "pie" || result.chart_type === "donut") {
    return (
      <div className="custom-report-chart" aria-label={`${title} pie chart`}>
        <ResponsiveContainer width="100%" height={330}>
          <PieChart>
            <Pie
              data={result.rows}
              dataKey={yAxis}
              nameKey={xAxis}
              innerRadius={result.chart_type === "donut" ? 70 : 0}
              outerRadius={120}
              paddingAngle={2}
              label={showDataLabels}
            >
              {result.rows.map((_, index) => (
                <Cell
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                  key={index}
                />
              ))}
            </Pie>
            <Tooltip />
            {showLegend && <Legend />}
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }
  return <ReportDataTable result={result} />;
  })();

  return (
    <div className="custom-report-result-stack">
      {chartContent}
      {showTable && result.chart_type !== "table" && <ReportDataTable result={result} />}
    </div>
  );
}

function ReportDataTable({ result }: { result: CustomReportResult }) {
  return (
    <div className="table-wrap custom-report-table">
      <table>
        <thead>
          <tr>
            {result.columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, index) => (
            <tr key={index}>
              {result.columns.map((column) => (
                <td key={column.key}>{String(row[column.key] ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CustomReportsPanel() {
  const [reports, setReports] = useState<CustomReport[]>([]);
  const [metadata, setMetadata] = useState<ReportMetadata | null>(null);
  const [mode, setMode] = useState<"list" | "builder" | "view">("list");
  const [step, setStep] = useState(0);
  const [editing, setEditing] = useState<CustomReport | null>(null);
  const [selected, setSelected] = useState<CustomReport | null>(null);
  const [result, setResult] = useState<CustomReportResult | null>(null);
  const [config, setConfig] = useState<CustomReportConfig>(EMPTY_CONFIG);
  const [viewConfig, setViewConfig] = useState<CustomReportConfig | null>(null);
  const [viewDirty, setViewDirty] = useState(false);
  const [dataSource, setDataSource] = useState("transactions");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [dashboardSection, setDashboardSection] = useState("");
  const [widgetSize, setWidgetSize] = useState("medium");
  const [widgetPosition, setWidgetPosition] = useState(100);
  const [scheduleFrequency, setScheduleFrequency] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const selectedSource = metadata?.data_sources.find(
    (source) => source.key === dataSource,
  );
  const fields = selectedSource?.fields ?? [];
  const numericFields = fields.filter((field) => field.type === "number");
  const dataSourceLabel =
    selectedSource?.label ??
    metadata?.data_sources.find((source) => source.key === dataSource)?.label ??
    dataSource;
  const availableOutputFields = useMemo(
    () =>
      config.aggregation
        ? [...config.groupBy, config.aggregation.field]
        : config.fields,
    [config],
  );

  async function load() {
    const [saved, reportMetadata] = await Promise.all([
      api.customReports(),
      api.customReportMetadata(),
    ]);
    setReports(saved);
    setMetadata(reportMetadata);
  }

  useEffect(() => {
    void load();
  }, []);

  function startCreate() {
    setEditing(null);
    setName("");
    setDescription("");
    setDataSource("transactions");
    setConfig(defaultConfigForSource("transactions"));
    setDashboardSection("");
    setWidgetSize("medium");
    setWidgetPosition(100);
    setScheduleFrequency("");
    setResult(null);
    setMessage("");
    setStep(0);
    setMode("builder");
  }

  function startEdit(report: CustomReport) {
    setEditing(report);
    setName(report.name);
    setDescription(report.description ?? "");
    setDataSource(report.data_source);
    setConfig(report.config_json);
    setDashboardSection(report.dashboard_section ?? "");
    setWidgetSize(report.widget_size ?? "medium");
    setWidgetPosition(report.widget_position ?? 100);
    setScheduleFrequency(report.schedule_frequency ?? "");
    setResult(null);
    setMessage("");
    setStep(0);
    setMode("builder");
  }

  async function preview() {
    setBusy(true);
    setMessage(`Building preview from ${dataSourceLabel}...`);
    try {
      const previewResult = await api.previewCustomReport(
        reportPayload(name || "Preview", description, dataSource, config),
      );
      setResult(previewResult);
      setMessage(`${previewResult.total_rows} result row(s) generated.`);
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Preview failed.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function nextStep() {
    if (step === 1 && !config.fields.length) {
      setMessage("Select at least one field.");
      return;
    }
    if (
      step === 3 &&
      config.aggregation &&
      !config.groupBy.length &&
      config.chart.type !== "table"
    ) {
      setMessage("Choose a grouping field for a chart report.");
      return;
    }
    if (step === 4 && config.chart.type !== "table") {
      if (!config.chart.xAxis || !config.chart.yAxis) {
        setMessage("Choose both chart axes.");
        return;
      }
    }
    setMessage("");
    if (step === 4) {
      const ok = await preview();
      if (!ok) return;
    }
    setStep((current) => Math.min(6, current + 1));
  }

  async function saveReport() {
    if (!name.trim()) {
      setMessage("Enter a report name before saving.");
      return;
    }
    setBusy(true);
    try {
      const payload = reportPayload(
        name.trim(),
        description.trim(),
        dataSource,
        config,
        {
          dashboardSection,
          scheduleFrequency,
          widgetPosition,
          widgetSize,
        },
      );
      if (editing) {
        await api.updateCustomReport(editing.id, payload);
        setMessage("Custom report updated.");
      } else {
        await api.createCustomReport(payload);
        setMessage("Custom report saved locally.");
      }
      await load();
      setMode("list");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save report.");
    } finally {
      setBusy(false);
    }
  }

  async function createAiDraft() {
    if (!aiPrompt.trim()) {
      setMessage("Describe the report you want first.");
      return;
    }
    setBusy(true);
    try {
      const draft = await api.aiDraftCustomReport(aiPrompt.trim());
      setEditing(null);
      setName(draft.name);
      setDescription(draft.description ?? "");
      setDataSource(draft.data_source);
      setConfig(draft.config_json);
      setDashboardSection(draft.dashboard_section ?? "");
      setWidgetSize(draft.widget_size ?? "medium");
      setWidgetPosition(draft.widget_position ?? 100);
      setScheduleFrequency(draft.schedule_frequency ?? "");
      setResult(null);
      setMessage("Draft created. Review it, preview, then save.");
      setStep(0);
      setMode("builder");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create draft.");
    } finally {
      setBusy(false);
    }
  }

  async function viewReport(report: CustomReport) {
    setBusy(true);
    setSelected(report);
    setViewConfig(report.config_json);
    setViewDirty(false);
    setMode("view");
    try {
      setResult(await api.runCustomReport(report.id));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not run report.");
    } finally {
      setBusy(false);
    }
  }

  async function updateViewedReportConfig(nextConfig: CustomReportConfig) {
    if (!selected) return;
    setViewConfig(nextConfig);
    setViewDirty(true);
    setBusy(true);
    setMessage("Updating report preview...");
    try {
      const previewResult = await api.previewCustomReport(
        reportPayload(
          selected.name,
          selected.description ?? "",
          selected.data_source,
          nextConfig,
        ),
      );
      setResult(previewResult);
      setMessage(`${previewResult.total_rows} result row(s) generated.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update report.");
    } finally {
      setBusy(false);
    }
  }

  async function saveViewedReportConfig() {
    if (!selected || !viewConfig) return;
    setBusy(true);
    try {
      const updated = await api.updateCustomReport(
        selected.id,
        reportPayload(
          selected.name,
          selected.description ?? "",
          selected.data_source,
          viewConfig,
          {
            dashboardSection: selected.dashboard_section,
            scheduleFrequency: selected.schedule_frequency,
            widgetPosition: selected.widget_position,
            widgetSize: selected.widget_size,
          },
        ),
      );
      setSelected(updated);
      setViewConfig(updated.config_json);
      setViewDirty(false);
      setMessage("Report filters and display settings saved.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save report.");
    } finally {
      setBusy(false);
    }
  }

  function downloadReport(format: "csv" | "xlsx" | "pdf") {
    if (!selected) return;
    window.open(api.customReportExportUrl(selected.id, format), "_blank");
  }

  function reportSourceLabel(report: CustomReport) {
    return (
      metadata?.data_sources.find((source) => source.key === report.data_source)
        ?.label ?? report.data_source
    );
  }

  function configForMetadataSource(source: ReportMetadata["data_sources"][number]) {
    const defaultConfig = defaultConfigForSource(source.key);
    const sourceFields = new Set(source.fields.map((field) => field.key));
    if (defaultConfig.fields.every((field) => sourceFields.has(field))) {
      return defaultConfig;
    }
    return {
      fields: source.fields.slice(0, 4).map((field) => field.key),
      filters: [],
      groupBy: [],
      aggregation: null,
      sort: null,
      limit: 100,
      chart: { type: "table", xAxis: null, yAxis: null },
    } satisfies CustomReportConfig;
  }

  if (mode === "view" && selected) {
    const activeConfig = viewConfig ?? selected.config_json;
    const activeChart = chartWithDefaults(activeConfig.chart);
    return (
      <section className="custom-reports-workspace">
        <header className="custom-report-view-heading">
          <div>
            <button className="text-button" onClick={() => setMode("list")}>
              ← Custom Reports
            </button>
            <h2>{selected.name}</h2>
            <p>{selected.description || "Saved custom report"}</p>
          </div>
          <div className="inline-actions">
            <button
              className="secondary-button"
              onClick={() => downloadReport("csv")}
              type="button"
            >
              <AppIcon name="file" size={15} /> CSV
            </button>
            <button
              className="secondary-button"
              onClick={() => downloadReport("xlsx")}
              type="button"
            >
              Excel
            </button>
            <button
              className="secondary-button"
              onClick={() => downloadReport("pdf")}
              type="button"
            >
              PDF
            </button>
            <button onClick={() => startEdit(selected)} type="button">
              Edit report
            </button>
            <button
              disabled={!viewDirty || busy}
              onClick={saveViewedReportConfig}
              type="button"
            >
              Save changes
            </button>
          </div>
        </header>
        <article className="panel report-display-settings">
          <div>
            <p className="eyebrow">Display Settings</p>
            <h3>Chart controls</h3>
          </div>
          <label>
            <input
              checked={activeChart.showFilters}
              onChange={(event) =>
                updateViewedReportConfig({
                  ...activeConfig,
                  chart: { ...activeConfig.chart, showFilters: event.target.checked },
                })
              }
              type="checkbox"
            />
            Show filters
          </label>
          <label>
            <input
              checked={activeChart.showLegend}
              onChange={(event) =>
                updateViewedReportConfig({
                  ...activeConfig,
                  chart: { ...activeConfig.chart, showLegend: event.target.checked },
                })
              }
              type="checkbox"
            />
            Show legend
          </label>
          <label>
            <input
              checked={activeChart.showDataLabels}
              onChange={(event) =>
                updateViewedReportConfig({
                  ...activeConfig,
                  chart: {
                    ...activeConfig.chart,
                    showDataLabels: event.target.checked,
                  },
                })
              }
              type="checkbox"
            />
            Show data values
          </label>
          <label>
            <input
              checked={activeChart.showTable}
              onChange={(event) =>
                updateViewedReportConfig({
                  ...activeConfig,
                  chart: { ...activeConfig.chart, showTable: event.target.checked },
                })
              }
              type="checkbox"
            />
            Show table below chart
          </label>
        </article>
        {activeChart.showFilters && (
          <EditableFiltersPanel
            config={activeConfig}
            metadata={metadata}
            onChange={updateViewedReportConfig}
            sourceKey={selected.data_source}
          />
        )}
        <article className="panel custom-report-result-panel">
          {busy ? (
            <p className="empty-state">Running report...</p>
          ) : result ? (
            <ReportResultView
              config={activeConfig}
              result={result}
              title={selected.name}
            />
          ) : (
            <p className="empty-state">{message}</p>
          )}
        </article>
      </section>
    );
  }

  if (mode === "builder") {
    return (
      <section className="report-builder">
        <header className="report-builder-heading">
          <div>
            <button className="text-button" onClick={() => setMode("list")}>
              ← Custom Reports
            </button>
            <h2>{editing ? "Edit report" : "Create New Report"}</h2>
            <p>Configure a safe report without writing SQL.</p>
          </div>
          <span>Step {step + 1} of 7</span>
        </header>
        <ol className="report-builder-steps">
          {STEP_LABELS.map((label, index) => (
            <li className={index === step ? "active" : index < step ? "done" : ""} key={label}>
              <span>{index < step ? "✓" : index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
        <article className="panel report-builder-stage">
          {step === 0 && (
            <div className="builder-option-grid">
              {(metadata?.data_sources ?? []).map((source) => (
                <button
                  className={dataSource === source.key ? "selected" : ""}
                  key={source.key}
                  onClick={() => {
                    setDataSource(source.key);
                    setConfig(configForMetadataSource(source));
                    setResult(null);
                  }}
                  type="button"
                >
                  <AppIcon name="transactions" size={22} />
                  <strong>{source.label}</strong>
                  <span>{source.description}</span>
                </button>
              ))}
            </div>
          )}
          {step === 1 && (
            <div className="field-selector-grid">
              {fields.map((field) => (
                <label key={field.key}>
                  <input
                    checked={config.fields.includes(field.key)}
                    onChange={(event) =>
                      setConfig((current) => ({
                        ...current,
                        fields: event.target.checked
                          ? [...current.fields, field.key]
                          : current.fields.filter((key) => key !== field.key),
                      }))
                    }
                    type="checkbox"
                  />
                  <span>
                    <strong>{field.label}</strong>
                    <small>{field.type}</small>
                  </span>
                </label>
              ))}
            </div>
          )}
          {step === 2 && (
            <div className="filter-builder">
              {config.filters.map((filter, index) => {
                const selectedField = fields.find(
                  (field) => field.key === filter.field,
                );
                const noValue = ["is_empty", "is_not_empty"].includes(
                  filter.operator,
                );
                return (
                  <div className="filter-row" key={index}>
                    <select
                      aria-label={`Filter ${index + 1} field`}
                      value={filter.field}
                      onChange={(event) =>
                        setConfig((current) => ({
                          ...current,
                          filters: current.filters.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, field: event.target.value, value: "" }
                              : item,
                          ),
                        }))
                      }
                    >
                      {fields.map((field) => (
                        <option key={field.key} value={field.key}>
                          {field.label}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label={`Filter ${index + 1} operator`}
                      value={filter.operator}
                      onChange={(event) =>
                        setConfig((current) => ({
                          ...current,
                          filters: current.filters.map((item, itemIndex) =>
                            itemIndex === index
                              ? {
                                  ...item,
                                  operator: event.target
                                    .value as CustomReportFilter["operator"],
                                  value: "",
                                }
                              : item,
                          ),
                        }))
                      }
                    >
                      {metadata?.filter_operators.map((operator) => (
                        <option key={operator.key} value={operator.key}>
                          {operator.label}
                        </option>
                      ))}
                    </select>
                    {!noValue &&
                      (selectedField?.options.length ? (
                        <select
                          aria-label={`Filter ${index + 1} value`}
                          value={String(filter.value ?? "")}
                          onChange={(event) =>
                            setConfig((current) => ({
                              ...current,
                              filters: current.filters.map((item, itemIndex) =>
                                itemIndex === index
                                  ? { ...item, value: event.target.value }
                                  : item,
                              ),
                            }))
                          }
                        >
                          <option value="">Select value</option>
                          {selectedField.options.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      ) : filter.operator === "date_range" ? (
                        <select
                          aria-label={`Filter ${index + 1} date range`}
                          value={String(filter.value ?? "")}
                          onChange={(event) =>
                            setConfig((current) => ({
                              ...current,
                              filters: current.filters.map((item, itemIndex) =>
                                itemIndex === index
                                  ? { ...item, value: event.target.value }
                                  : item,
                              ),
                            }))
                          }
                        >
                          <option value="">Select range</option>
                          <option value="this_month">This Month</option>
                          <option value="last_month">Last Month</option>
                          <option value="this_year">This Year</option>
                          <option value="last_3_months">Last 3 Months</option>
                          <option value="last_6_months">Last 6 Months</option>
                          <option value="last_12_months">Last 12 Months</option>
                        </select>
                      ) : (
                        <input
                          aria-label={`Filter ${index + 1} value`}
                          onChange={(event) =>
                            setConfig((current) => ({
                              ...current,
                              filters: current.filters.map((item, itemIndex) =>
                                itemIndex === index
                                  ? { ...item, value: event.target.value }
                                  : item,
                              ),
                            }))
                          }
                          placeholder={
                            filter.operator === "between"
                              ? "Minimum, maximum"
                              : "Filter value"
                          }
                          value={String(filter.value ?? "")}
                        />
                      ))}
                    <button
                      aria-label={`Remove filter ${index + 1}`}
                      className="text-button danger"
                      onClick={() =>
                        setConfig((current) => ({
                          ...current,
                          filters: current.filters.filter(
                            (_, itemIndex) => itemIndex !== index,
                          ),
                        }))
                      }
                      type="button"
                    >
                      Remove
                    </button>
                  </div>
                );
              })}
              <button
                className="secondary-button add-filter-button"
                onClick={() =>
                  setConfig((current) => ({
                    ...current,
                    filters: [
                      ...current.filters,
                      { field: fields[0]?.key ?? "vendor", operator: "equals", value: "" },
                    ],
                  }))
                }
                type="button"
              >
                <AppIcon name="add" size={15} /> Add filter
              </button>
              {!config.filters.length && (
                <p className="empty-state">No filters. All validated transactions will be included.</p>
              )}
            </div>
          )}
          {step === 3 && (
            <div className="grouping-builder">
              <label>
                Group by
                <select
                  value={config.groupBy[0] ?? ""}
                  onChange={(event) =>
                    setConfig((current) => ({
                      ...current,
                      groupBy: event.target.value ? [event.target.value] : [],
                    }))
                  }
                >
                  <option value="">No grouping</option>
                  {fields.map((field) => (
                    <option key={field.key} value={field.key}>
                      {field.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Aggregation
                <select
                  value={config.aggregation?.function ?? ""}
                  onChange={(event) =>
                    setConfig((current) => ({
                      ...current,
                      aggregation: event.target.value
                        ? {
                            function: event.target.value as NonNullable<
                              CustomReportConfig["aggregation"]
                            >["function"],
                            field:
                              current.aggregation?.field ??
                              numericFields[0]?.key ??
                              "amount",
                          }
                        : null,
                    }))
                  }
                >
                  <option value="">No aggregation</option>
                  {metadata?.aggregations.map((aggregation) => (
                    <option key={aggregation.key} value={aggregation.key}>
                      {aggregation.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Metric field
                <select
                  disabled={!config.aggregation}
                  value={config.aggregation?.field ?? ""}
                  onChange={(event) =>
                    setConfig((current) => ({
                      ...current,
                      aggregation: current.aggregation
                        ? { ...current.aggregation, field: event.target.value }
                        : null,
                    }))
                  }
                >
                  {numericFields.map((field) => (
                    <option key={field.key} value={field.key}>
                      {field.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Sort
                <select
                  value={config.sort?.direction ?? ""}
                  onChange={(event) =>
                    setConfig((current) => ({
                      ...current,
                      sort: event.target.value
                        ? {
                            field:
                              current.aggregation?.field ??
                              current.groupBy[0] ??
                              current.fields[0],
                            direction: event.target.value as "asc" | "desc",
                          }
                        : null,
                    }))
                  }
                >
                  <option value="">Default</option>
                  <option value="desc">Highest first</option>
                  <option value="asc">Lowest first</option>
                </select>
              </label>
              <label>
                Result limit
                <input
                  max={500}
                  min={1}
                  onChange={(event) =>
                    setConfig((current) => ({
                      ...current,
                      limit: Number(event.target.value),
                    }))
                  }
                  type="number"
                  value={config.limit}
                />
              </label>
            </div>
          )}
          {step === 4 && (
            <>
              <div className="chart-type-grid">
                {metadata?.chart_types.map((chart) => (
                  <button
                    className={config.chart.type === chart.key ? "selected" : ""}
                    key={chart.key}
                    onClick={() =>
                      setConfig((current) => ({
                        ...current,
                        chart: {
                          type: chart.key,
                          xAxis:
                            chart.key === "table"
                              ? null
                              : current.groupBy[0] ?? availableOutputFields[0] ?? null,
                          yAxis:
                            chart.key === "table"
                              ? null
                              : current.aggregation?.field ??
                                availableOutputFields.find(
                                  (key) =>
                                    fields.find((field) => field.key === key)?.type ===
                                    "number",
                                ) ??
                                null,
                        },
                      }))
                    }
                    type="button"
                  >
                    <AppIcon
                      name={chart.key === "table" ? "file" : "chart"}
                      size={20}
                    />
                    {chart.label}
                  </button>
                ))}
              </div>
              {config.chart.type !== "table" && (
                <div className="chart-axis-grid">
                  <label>
                    X-Axis
                    <select
                      value={config.chart.xAxis ?? ""}
                      onChange={(event) =>
                        setConfig((current) => ({
                          ...current,
                          chart: { ...current.chart, xAxis: event.target.value },
                        }))
                      }
                    >
                      <option value="">Select field</option>
                      {availableOutputFields.map((key) => (
                        <option key={key} value={key}>
                          {fieldLabel(metadata, dataSource, key)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Y-Axis
                    <select
                      value={config.chart.yAxis ?? ""}
                      onChange={(event) =>
                        setConfig((current) => ({
                          ...current,
                          chart: { ...current.chart, yAxis: event.target.value },
                        }))
                      }
                    >
                      <option value="">Select field</option>
                      {availableOutputFields.map((key) => (
                        <option key={key} value={key}>
                          {fieldLabel(metadata, dataSource, key)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </>
          )}
          {step === 5 && (
            <div className="report-preview">
              <div className="report-preview-toolbar">
                <span>{message}</span>
                <button className="secondary-button" disabled={busy} onClick={preview}>
                  {busy ? "Refreshing..." : "Refresh preview"}
                </button>
              </div>
              {result && (
                <ReportResultView
                  config={config}
                  result={result}
                  title={name || "Report preview"}
                />
              )}
            </div>
          )}
          {step === 6 && (
            <div className="save-report-form">
              <label>
                Report Name
                <input
                  autoFocus
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Monthly Expense by Category"
                  value={name}
                />
              </label>
              <label>
                Description
                <textarea
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="What decision will this report support?"
                  value={description}
                />
              </label>
              <div className="save-report-summary">
                <span>{dataSourceLabel}</span>
                <span>{config.fields.length} fields</span>
                <span>{config.filters.length} filters</span>
                <span>
                  {fieldLabel(
                    metadata,
                    dataSource,
                    config.groupBy[0] ?? "No grouping",
                  )}
                </span>
                <span>{config.chart.type.replaceAll("_", " ")}</span>
              </div>
              <div className="report-save-options">
                <label>
                  Add to Dashboard
                  <select
                    onChange={(event) => setDashboardSection(event.target.value)}
                    value={dashboardSection}
                  >
                    <option value="">Do not add</option>
                    {metadata?.dashboard_sections.map((section) => (
                      <option key={section.key} value={section.key}>
                        {section.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Widget Size
                  <select
                    disabled={!dashboardSection}
                    onChange={(event) => setWidgetSize(event.target.value)}
                    value={widgetSize}
                  >
                    {metadata?.widget_sizes.map((size) => (
                      <option key={size.key} value={size.key}>
                        {size.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Position
                  <input
                    disabled={!dashboardSection}
                    min={1}
                    onChange={(event) =>
                      setWidgetPosition(Number(event.target.value))
                    }
                    type="number"
                    value={widgetPosition}
                  />
                </label>
                <label>
                  Schedule
                  <select
                    onChange={(event) => setScheduleFrequency(event.target.value)}
                    value={scheduleFrequency}
                  >
                    <option value="">Manual only</option>
                    {metadata?.schedule_frequencies.map((frequency) => (
                      <option key={frequency.key} value={frequency.key}>
                        {frequency.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          )}
          {message && step !== 5 && <p className="form-message">{message}</p>}
          <footer className="report-builder-actions">
            <button
              className="secondary-button"
              disabled={step === 0}
              onClick={() => setStep((current) => Math.max(0, current - 1))}
              type="button"
            >
              Back
            </button>
            {step < 6 ? (
              <button disabled={busy} onClick={nextStep} type="button">
                {step === 4 ? "Generate Preview" : "Continue"}
              </button>
            ) : (
              <button disabled={busy} onClick={saveReport} type="button">
                {busy ? "Saving..." : editing ? "Update Report" : "Save Report"}
              </button>
            )}
          </footer>
        </article>
      </section>
    );
  }

  return (
    <section className="custom-reports-workspace">
      <header className="custom-reports-heading">
        <div>
          <p className="eyebrow">Reports Builder</p>
          <h2>Custom Reports</h2>
          <p>Create reusable views from approved application data.</p>
        </div>
        <button onClick={startCreate} type="button">
          <AppIcon name="add" size={16} /> Create New Report
        </button>
      </header>
      <article className="panel report-ai-draft-panel">
        <div>
          <p className="eyebrow">AI-assisted setup</p>
          <h3>Describe a report</h3>
          <p>
            Try “top vendors by spending”, “loan balance overview”, or “net worth
            snapshot”.
          </p>
        </div>
        <input
          onChange={(event) => setAiPrompt(event.target.value)}
          placeholder="What report do you want?"
          value={aiPrompt}
        />
        <button disabled={busy} onClick={createAiDraft} type="button">
          Draft Report
        </button>
      </article>
      {message && <p className="success-message">{message}</p>}
      <div className="custom-report-list">
        {reports.map((report) => (
          <article className="custom-report-card" key={report.id}>
            <div className="custom-report-card-icon">
              <AppIcon
                name={report.chart_type === "table" ? "file" : "chart"}
                size={20}
              />
            </div>
            <div className="custom-report-card-copy">
              <h3>{report.name}</h3>
              <p>{report.description || "No description"}</p>
              <div>
                <span>{report.chart_type.replaceAll("_", " ")}</span>
                <span>{reportSourceLabel(report)}</span>
                <span>Created {formatDate(report.created_at)}</span>
                <span>Updated {formatDate(report.updated_at)}</span>
                {report.dashboard_section && <span>Dashboard</span>}
                {report.schedule_frequency && (
                  <span>{report.schedule_frequency}</span>
                )}
              </div>
            </div>
            <div className="custom-report-card-actions">
              <button onClick={() => viewReport(report)} type="button">View</button>
              <button className="secondary-button" onClick={() => startEdit(report)} type="button">Edit</button>
              <button
                className="secondary-button"
                onClick={async () => {
                  await api.duplicateCustomReport(report.id);
                  setMessage(`${report.name} duplicated.`);
                  await load();
                }}
                type="button"
              >
                Duplicate
              </button>
              <button
                className="text-button danger"
                onClick={async () => {
                  const confirmed = await confirmAction({
                    title: "Delete custom report?",
                    message: `Delete "${report.name}"? Saved report configuration will be removed.`,
                    confirmLabel: "Delete report",
                  });
                  if (!confirmed) return;
                  await api.deleteCustomReport(report.id);
                  setMessage(`${report.name} deleted.`);
                  await load();
                }}
                type="button"
              >
                Delete
              </button>
            </div>
          </article>
        ))}
        {!reports.length && (
          <div className="panel custom-report-empty">
            <AppIcon name="reports" size={28} />
            <h3>No custom reports yet</h3>
            <p>Build your first report from validated transaction data.</p>
            <button onClick={startCreate} type="button">Create New Report</button>
          </div>
        )}
      </div>
    </section>
  );
}
