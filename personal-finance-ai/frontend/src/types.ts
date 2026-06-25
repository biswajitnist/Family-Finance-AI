export interface Account {
  id: number;
  name: string;
  type: string;
  institution?: string;
  country: string;
  currency: string;
  opening_balance: string;
  current_balance: string;
  notes?: string;
  is_active: boolean;
}

export interface Category {
  id: number;
  name: string;
  type: "income" | "expense" | "transfer";
  icon: string;
  color: string;
}

export interface UserProfile {
  id: number;
  name: string;
  email: string | null;
  base_currency: string;
  country: string;
  timezone: string;
  preferred_language: string;
  tax_country: string;
  date_format: string;
  number_format: string;
  financial_year_start: string;
  default_portfolio_view: string;
  default_refresh_frequency: string;
  setup_completed: boolean;
}

export interface MarketDataProvider {
  id: number;
  provider_name: string;
  provider_type: string;
  base_url: string | null;
  auth_method: string;
  api_key_parameter_name: string | null;
  api_key_header_name: string | null;
  api_key_masked: string | null;
  has_api_key: boolean;
  enabled: boolean;
  priority: number;
  supported_asset_classes: string | null;
  default_currency: string | null;
  default_exchange_code: string | null;
  symbol_format: string | null;
  test_symbol: string | null;
  timeout_seconds: number;
  retry_count: number;
  rate_limit_per_minute: number | null;
  last_test_status: string | null;
  last_tested_at: string | null;
  last_successful_refresh: string | null;
  last_error: string | null;
  notes: string | null;
}

export interface MarketDataStatus {
  provider: string;
  configured: boolean;
  credential_source: "app" | "environment" | null;
  providers: {
    finnhub: {
      configured: boolean;
      credential_source: "app" | "environment" | null;
    };
    twelve_data: {
      configured: boolean;
      credential_source: "app" | "environment" | null;
      tracked_symbols: number;
    };
  };
  status: string;
  status_label: string;
  online: boolean;
  using_cache: boolean;
  last_updated: string | null;
  last_attempt: string | null;
  last_error: string | null;
  warning: string | null;
  refresh_interval: string;
  next_refresh: string | null;
  refresh_due: boolean;
  symbols: string[];
  symbol_count: number;
  missing_ticker_count: number;
  prices: Array<{
    symbol: string;
    price: string;
    currency: string | null;
    quote_timestamp: string;
    fetched_at: string;
    provider: string;
  }>;
  cache_policy: {
    intraday_days: number;
    daily_retention: string;
    news_days: number;
  };
  refreshed_symbols?: string[];
  failed_symbols?: string[];
  investments_updated?: number;
  skipped_portfolio_updates?: string[];
}

export interface Transaction {
  id: number;
  account_id: number;
  document_id: number | null;
  transaction_date: string;
  booking_date: string | null;
  vendor: string;
  description: string;
  original_description: string;
  amount: string;
  currency: string;
  transaction_type: "debit" | "credit";
  category_id: number | null;
  reference_number: string | null;
  payment_method: string | null;
  iban: string | null;
  confidence: string | null;
  classification_source: string;
  recurrence_frequency:
    | "weekly"
    | "biweekly"
    | "monthly"
    | "quarterly"
    | "semiannual"
    | "yearly"
    | null;
  recurrence_confidence: string | null;
  recurrence_source: string | null;
  recurrence_group_key: string | null;
  next_expected_date: string | null;
  edited_fields: string | null;
  is_validated: boolean;
  is_duplicate: boolean;
  created_at: string;
}

export interface DashboardSummary {
  currency: string;
  income: string;
  expenses: string;
  net_cash_flow: string;
  savings_rate: string;
  pending_review: number;
  budget_total: string;
  budget_spent: string;
  budget_remaining: string;
  budget_percentage: string;
  account_balance: string;
  investments: string;
  debt_balance: string;
  property_value: string;
  net_worth: string;
  fx_warnings: string[];
  upcoming_bills: Array<{ name: string; match: string }>;
  spending_by_category: Array<{ category: string; amount: string }>;
  monthly_trend: Array<{ month: string; income: string; expenses: string }>;
}

export interface AdvisorDashboard {
  month: string;
  summary_sentence_1: string;
  summary_sentence_2: string;
  explanation: string;
  confidence_score: string;
  generated_at: string;
  local_ai_used: boolean;
  source_basis: string[];
  financial_position: {
    cash_balance: string;
    investment_value: string;
    property_value: string;
    debt_balance: string;
    monthly_loan_payments: string;
    net_worth: string;
  };
  forecast: {
    expected_income: string;
    expected_expenses: string;
    expected_surplus: string;
    expected_month_end_balance: string;
    recurring_payment_impact: string;
    confidence_score: string;
    category_risks: Array<Record<string, string>>;
  };
  recommendations: Array<{
    id: number;
    title: string;
    description: string;
    priority: string;
    estimated_impact_amount: string;
    recommendation_type: string;
    explanation: string;
    related_data: Record<string, string>;
    status: string;
  }>;
  alerts: Array<{
    id: number;
    alert_type: string;
    severity: string;
    message: string;
    reason: string;
    recommended_action: string;
    status: string;
    transactions: Array<{
      id: number;
      transaction_date: string;
      vendor: string;
      description: string;
      amount: string;
      currency: string;
      transaction_type: "debit" | "credit";
      category: string;
      account: string;
      is_validated: boolean;
      is_duplicate: boolean;
    }>;
  }>;
}

export interface DocumentRecord {
  id: number;
  file_name: string;
  file_type: string;
  document_type: string;
  source_account_id: number | null;
  status: string;
  validation_status: string;
  processing_stage: string;
  processing_progress: number;
  processing_message: string | null;
  processing_error: string | null;
  processed_at: string | null;
  page_count: number | null;
  uploaded_at: string;
  extracted_text?: string | null;
}

export interface BatchProcessResult {
  statement_set_id: number;
  requested: number;
  completed: number;
  failed: number;
  transactions_created: number;
  investments_created: number;
  results: Array<{
    document_id: number;
    file_name: string;
    status: string;
    transactions_created: number;
    investments_created: number;
    record_type: string;
    message: string;
  }>;
}

export interface StatementCandidate {
  id: number;
  document_id: number;
  transaction_id: number | null;
  status: "extracted" | "needs_review" | "skipped" | "overlap";
  resolution: string | null;
  skip_reason: string | null;
  raw_text: string;
  transaction_date: string | null;
  vendor: string | null;
  amount: string | null;
  currency: string | null;
  transaction_type: "debit" | "credit" | null;
  field_confidence: Record<string, number>;
  warnings: string[];
  duplicate_matches: Array<{
    id: number;
    transaction_date: string;
    vendor: string;
    description: string;
    amount: string;
    currency: string;
    transaction_type: "debit" | "credit";
    category: string | null;
    account: string | null;
    merchant_similarity: number;
  }>;
  source_line: {
    id: number;
    document_id: number;
    page_number: number;
    line_number: number;
    raw_text: string;
    confidence: string | null;
    bbox: number[] | null;
  } | null;
}

export interface StatementAudit {
  id: number;
  name: string;
  status: string;
  completeness_status: "verified" | "needs_review" | "unverified";
  expected_transaction_count: number | null;
  expected_debit_total: string | null;
  expected_credit_total: string | null;
  detected_opening_balance: string | null;
  detected_closing_balance: string | null;
  candidate_count: number;
  extracted_count: number;
  skipped_count: number;
  overlap_count: number;
  low_confidence_count: number;
  debit_total: string;
  credit_total: string;
  reconciliation_difference: string | null;
  confirmation_blockers: string[];
  can_confirm: boolean;
  documents: Array<{
    id: number;
    file_name: string;
    file_type: string;
    sequence: number;
    preview_url: string;
    page_count: number | null;
  }>;
  candidates: StatementCandidate[];
}

export interface MonthlyBudget {
  id: number;
  category_id: number | null;
  year: number;
  month: number;
  amount: string;
  currency: string;
  notes: string | null;
  created_at: string;
}

export interface BudgetProposal {
  id: number;
  source_transaction_id: number;
  category_id: number | null;
  year: number;
  month: number;
  merchant: string;
  amount: string;
  currency: string;
  recurrence_frequency: string;
  expected_date: string;
  confidence: string | null;
  detection_source: string;
  status: "pending" | "confirmed" | "dismissed";
  created_at: string;
  confirmed_at: string | null;
}

export interface MonthlyBudgetSummary {
  year: number;
  month: number;
  currency: string;
  total_budget: string;
  spent: string;
  remaining: string;
  percentage: string;
  categories: Array<{
    budget_id: number;
    category_id: number | null;
    category: string;
    budget: string;
    spent: string;
    remaining: string;
    percentage: string;
  }>;
}

export interface ReportRecord {
  id: number;
  report_type: string;
  period_start: string;
  period_end: string;
  format: string;
  created_at: string;
}

export type CustomReportChartType =
  | "table"
  | "bar"
  | "line"
  | "pie"
  | "donut"
  | "area"
  | "stacked_bar"
  | "grouped_bar"
  | "horizontal_bar"
  | "kpi"
  | "trend";

export interface CustomReportFilter {
  field: string;
  operator:
    | "equals"
    | "not_equals"
    | "contains"
    | "greater_than"
    | "less_than"
    | "between"
    | "date_range"
    | "is_empty"
    | "is_not_empty";
  value?: unknown;
}

export interface CustomReportConfig {
  fields: string[];
  filters: CustomReportFilter[];
  groupBy: string[];
  aggregation: {
    field: string;
    function:
      | "sum"
      | "average"
      | "count"
      | "minimum"
      | "maximum"
      | "opening_balance"
      | "closing_balance"
      | "net_change";
  } | null;
  sort: { field: string; direction: "asc" | "desc" } | null;
  limit: number;
  chart: {
    type: CustomReportChartType;
    xAxis: string | null;
    yAxis: string | null;
    showLegend?: boolean;
    showDataLabels?: boolean;
    showTable?: boolean;
    showFilters?: boolean;
  };
}

export interface CustomReport {
  id: number;
  name: string;
  description: string | null;
  data_source: string;
  chart_type: CustomReportChartType;
  config_json: CustomReportConfig;
  dashboard_section: string | null;
  widget_size: string | null;
  widget_position: number | null;
  schedule_frequency: string | null;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
}

export interface ReportMetadata {
  data_sources: Array<{
    key: string;
    label: string;
    description: string;
    fields: Array<{
      key: string;
      label: string;
      type: "text" | "number" | "date";
      options: Array<{ label: string; value: string }>;
      aggregatable: boolean;
    }>;
  }>;
  chart_types: Array<{ key: CustomReportChartType; label: string }>;
  filter_operators: Array<{ key: CustomReportFilter["operator"]; label: string }>;
  aggregations: Array<{
    key: NonNullable<CustomReportConfig["aggregation"]>["function"];
    label: string;
  }>;
  dashboard_sections: Array<{ key: string; label: string }>;
  widget_sizes: Array<{ key: string; label: string }>;
  schedule_frequencies: Array<{ key: string; label: string }>;
}

export interface CustomReportResult {
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, string | number | null>>;
  total_rows: number;
  chart_type: CustomReportChartType;
  x_axis: string | null;
  y_axis: string | null;
  value: string | number | null;
  subtitle: string | null;
}

export interface CashFlowComparison {
  currency: string;
  current_month: string;
  previous_month: string;
  current: {
    income: string;
    expense: string;
    cash_flow: string;
  };
  previous: {
    income: string;
    expense: string;
    cash_flow: string;
  };
  expense_categories: Array<{ category: string; amount: string }>;
  income_categories: Array<{ category: string; amount: string }>;
  daily: Array<{
    day: number;
    current_income: string;
    current_expense: string;
    current_cash_flow: string;
    previous_income: string;
    previous_expense: string;
    previous_cash_flow: string;
  }>;
}

export interface ChatResponse {
  answer: string;
  calculation_basis: string;
  sources: Array<Record<string, unknown>>;
  confidence: number;
  missing_data_warning: string | null;
  local_ai_used: boolean;
}

export interface HelpAgentResponse {
  intent:
    | "app_help"
    | "finance_query"
    | "document_query"
    | "report_request"
    | "troubleshooting";
  answer: string;
  source_basis: Array<
    "database" | "document" | "help guide" | "generated report"
  >;
  sources: Array<Record<string, unknown>>;
  missing_data: string[];
  local_ai_used: boolean;
  report: {
    id: number;
    format: string;
    download_url: string;
  } | null;
}

export type ResourceRecord = Record<string, string | number | boolean | null>;
