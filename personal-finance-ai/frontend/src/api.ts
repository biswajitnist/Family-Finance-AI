import type {
  Account,
  AdvisorDashboard,
  BatchProcessResult,
  BudgetProposal,
  Category,
  CashFlowComparison,
  ChatResponse,
  CustomReport,
  CustomReportResult,
  DashboardSummary,
  DocumentRecord,
  HelpAgentResponse,
  MonthlyBudget,
  MonthlyBudgetSummary,
  MarketDataStatus,
  MarketDataProvider,
  ReportRecord,
  ReportMetadata,
  ResourceRecord,
  StatementAudit,
  Transaction,
  UserProfile,
} from "./types";

const API_URL =
  import.meta.env.VITE_API_URL ??
  (import.meta.env.PROD ? "/api" : "http://localhost:8000/api");
const API_ORIGIN = API_URL.replace(/\/api\/?$/, "");

export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const jsonOptions = (method: string, body: unknown) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  profile: () => request<UserProfile>("/profile"),
  updateProfile: (profile: Omit<UserProfile, "id">) =>
    request<UserProfile>("/profile", jsonOptions("PUT", profile)),
  accounts: () => request<Account[]>("/accounts"),
  createAccount: (body: Record<string, unknown>) =>
    request<Account>("/accounts", jsonOptions("POST", body)),
  categories: () => request<Category[]>("/categories"),
  transactions: (validated?: boolean, documentId?: number) =>
    request<Transaction[]>(
      `/transactions?${new URLSearchParams({
        ...(validated === undefined ? {} : { validated: String(validated) }),
        ...(documentId === undefined ? {} : { document_id: String(documentId) }),
        limit: "500",
      })}`,
    ),
  createTransaction: (body: Record<string, unknown>) =>
    request<Transaction>("/transactions", jsonOptions("POST", body)),
  updateTransaction: (id: number, body: Record<string, unknown>) =>
    request<Transaction>(`/transactions/${id}`, jsonOptions("PUT", body)),
  deleteTransaction: (id: number) =>
    request<void>(`/transactions/${id}`, { method: "DELETE" }),
  classifyTransaction: (id: number) =>
    request<Transaction>(`/ai/classify-transaction/${id}`, { method: "POST" }),
  validateTransactions: (transactionIds: number[]) =>
    request<{ updated: number }>(
      "/transactions/validate",
      jsonOptions("POST", {
        transaction_ids: transactionIds,
        is_validated: true,
      }),
    ),
  detectRecurringTransactions: (useLocalAi = false) =>
    request<{
      groups_detected: number;
      transactions_updated: number;
      ollama_groups: number;
    }>(`/recurrence/detect?use_local_ai=${useLocalAi}`, { method: "POST" }),
  importCsv: (accountId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ imported: number; duplicates: number }>(
      `/transactions/import?account_id=${accountId}`,
      { method: "POST", body: form },
    );
  },
  dashboard: (year: number, month: number) =>
    request<DashboardSummary>(`/dashboard?year=${year}&month=${month}`),
  advisorDashboard: (year: number, month: number) =>
    request<AdvisorDashboard>(
      `/dashboard/advisor?year=${year}&month=${month}`,
    ),
  refreshAdvisorDashboard: (
    year: number,
    month: number,
    useLocalAi = true,
  ) =>
    request<AdvisorDashboard>(
      `/dashboard/advisor/refresh?year=${year}&month=${month}&use_local_ai=${useLocalAi}`,
      { method: "POST" },
    ),
  updateRecommendationStatus: (id: number, status: string) =>
    request<{ status: string }>(
      `/dashboard/recommendations/${id}`,
      jsonOptions("PATCH", { status }),
    ),
  updateAlertStatus: (id: number, status: string) =>
    request<{ status: string }>(
      `/dashboard/alerts/${id}`,
      jsonOptions("PATCH", { status }),
    ),
  documents: () => request<DocumentRecord[]>("/documents"),
  document: (id: number) => request<DocumentRecord>(`/documents/${id}`),
  documentFileUrl: (id: number) => `${API_URL}/documents/${id}/file`,
  documentPreviewUrl: (id: number, page = 1) =>
    `${API_URL}/documents/${id}/preview?page=${page}`,
  documentTransactions: (id: number) =>
    request<Transaction[]>(`/documents/${id}/transactions`),
  uploadDocument: (
    file: File,
    documentType: string,
    sourceAccountId: number | null,
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("document_type", documentType);
    if (sourceAccountId) form.append("source_account_id", String(sourceAccountId));
    return request<DocumentRecord>("/documents/upload", {
      method: "POST",
      body: form,
    });
  },
  processDocument: (id: number, forceOcr: boolean, useLocalAi: boolean) =>
    request<{
      document_id: number;
      status: string;
      transactions_created: number;
      investments_created: number;
      record_type: string;
      message: string;
      statement_set_id: number;
    }>(
      `/documents/${id}/process?force_ocr=${forceOcr}&use_local_ai=${useLocalAi}`,
      { method: "POST" },
    ),
  processDocuments: (
    documentIds: number[],
    forceOcr: boolean,
    useLocalAi: boolean,
  ) =>
    request<BatchProcessResult>(
      "/documents/process-batch",
      jsonOptions("POST", {
        document_ids: documentIds,
        force_ocr: forceOcr,
        use_local_ai: useLocalAi,
      }),
    ),
  confirmDocument: (id: number, transactionIds: number[]) =>
    request<{ confirmed: number; remaining: number; status: string }>(
      `/documents/${id}/confirm`,
      jsonOptions("POST", transactionIds),
    ),
  documentAudit: (id: number) =>
    request<StatementAudit>(`/documents/${id}/audit`),
  statementAudit: (id: number) =>
    request<StatementAudit>(`/statement-sets/${id}`),
  reauditDocument: (id: number, forceOcr: boolean, useLocalAi: boolean) =>
    request<{ statement_set_id: number }>(
      `/documents/${id}/reaudit?force_ocr=${forceOcr}&use_local_ai=${useLocalAi}`,
      { method: "POST" },
    ),
  updateStatementCheckpoint: (
    id: number,
    body: Record<string, unknown>,
  ) =>
    request<StatementAudit>(
      `/statement-sets/${id}/checkpoint`,
      jsonOptions("PUT", body),
    ),
  updateStatementCandidate: (
    id: number,
    body: Record<string, unknown>,
  ) =>
    request<StatementAudit>(
      `/statement-candidates/${id}`,
      jsonOptions("PUT", body),
    ),
  confirmStatementSet: (id: number) =>
    request<{ confirmed: number; status: string }>(
      `/statement-sets/${id}/confirm`,
      { method: "POST" },
    ),
  deleteDocument: (id: number) =>
    request<void>(`/documents/${id}`, { method: "DELETE" }),
  resources: (path: string) => request<ResourceRecord[]>(`/${path}`),
  loanTransactions: (loanId: number) =>
    request<ResourceRecord[]>(`/loans/${loanId}/transactions`),
  insuranceTransactions: (policyId: number) =>
    request<ResourceRecord[]>(`/insurance/${policyId}/transactions`),
  analytics: (path: string) =>
    request<Record<string, unknown>>(`/analytics/${path}`),
  createResource: (path: string, body: Record<string, unknown>) =>
    request<ResourceRecord>(`/${path}`, jsonOptions("POST", body)),
  updateResource: (
    path: string,
    id: number,
    body: Record<string, unknown>,
  ) => request<ResourceRecord>(`/${path}/${id}`, jsonOptions("PUT", body)),
  deleteResource: (path: string, id: number) =>
    request<void>(`/${path}/${id}`, { method: "DELETE" }),
  applyRules: () =>
    request<{ updated: number }>("/rules/apply", { method: "POST" }),
  marketDataStatus: () => request<MarketDataStatus>("/market-data/status"),
  refreshMarketData: () =>
    request<MarketDataStatus>("/market-data/refresh", { method: "POST" }),
  updateMarketDataSettings: (refreshInterval: string) =>
    request<MarketDataStatus>(
      "/market-data/settings",
      jsonOptions("PUT", { refresh_interval: refreshInterval }),
    ),
  saveMarketDataApiKey: (provider: "finnhub" | "twelve_data", apiKey: string) =>
    request<MarketDataStatus>(
      "/market-data/credentials",
      jsonOptions("PUT", { provider, api_key: apiKey }),
    ),
  marketDataProviders: () =>
    request<MarketDataProvider[]>("/market-data/providers"),
  createMarketDataProvider: (body: Record<string, unknown>) =>
    request<MarketDataProvider>(
      "/market-data/providers",
      jsonOptions("POST", body),
    ),
  updateMarketDataProvider: (id: number, body: Record<string, unknown>) =>
    request<MarketDataProvider>(
      `/market-data/providers/${id}`,
      jsonOptions("PUT", body),
    ),
  deleteMarketDataProvider: (id: number) =>
    request<void>(`/market-data/providers/${id}`, { method: "DELETE" }),
  testMarketDataProvider: (id: number) =>
    request<MarketDataProvider>(`/market-data/providers/${id}/test`, {
      method: "POST",
    }),
  classifyPending: (transactionIds: number[]) =>
    request<{
      classified: number;
      total: number;
      unresolved: string[];
      by_source: {
        rule: number;
        merchant_history: number;
        ollama: number;
      };
      ollama_available: boolean;
      model_installed: boolean;
      model: string;
    }>(
      "/ai/classify-pending",
      jsonOptions("POST", { transaction_ids: transactionIds }),
    ),
  generatedReports: () => request<ReportRecord[]>("/generated-reports"),
  cashFlowComparison: (year: number, month: number) =>
    request<CashFlowComparison>(
      `/reports/cash-flow/comparison?year=${year}&month=${month}`,
    ),
  createGeneratedReport: (body: Record<string, unknown>) =>
    request<ReportRecord>("/generated-reports", jsonOptions("POST", body)),
  reportDownloadUrl: (id: number) =>
    `${API_URL}/generated-reports/${id}/download`,
  customReportMetadata: () => request<ReportMetadata>("/reports/metadata"),
  customReports: () => request<CustomReport[]>("/reports"),
  customReport: (id: number) => request<CustomReport>(`/reports/${id}`),
  createCustomReport: (body: Record<string, unknown>) =>
    request<CustomReport>("/reports", jsonOptions("POST", body)),
  updateCustomReport: (id: number, body: Record<string, unknown>) =>
    request<CustomReport>(`/reports/${id}`, jsonOptions("PUT", body)),
  deleteCustomReport: (id: number) =>
    request<void>(`/reports/${id}`, { method: "DELETE" }),
  previewCustomReport: (body: Record<string, unknown>) =>
    request<CustomReportResult>(
      "/reports/preview",
      jsonOptions("POST", body),
    ),
  runCustomReport: (id: number) =>
    request<CustomReportResult>(`/reports/${id}/run`, { method: "POST" }),
  duplicateCustomReport: (id: number) =>
    request<CustomReport>(`/reports/${id}/duplicate`, { method: "POST" }),
  dashboardReportWidgets: () =>
    request<CustomReport[]>("/reports/dashboard/widgets"),
  scheduledCustomReports: () => request<CustomReport[]>("/reports/scheduled"),
  addCustomReportToDashboard: (
    id: number,
    body: { section: string; widget_size: string; position: number },
  ) => request<CustomReport>(`/reports/${id}/dashboard`, jsonOptions("POST", body)),
  scheduleCustomReport: (id: number, frequency: string | null) =>
    request<CustomReport>(
      `/reports/${id}/schedule`,
      jsonOptions("POST", { frequency }),
    ),
  aiDraftCustomReport: (prompt: string) =>
    request<CustomReport>("/reports/ai-draft", jsonOptions("POST", { prompt })),
  customReportExportUrl: (
    id: number,
    format: "csv" | "xlsx" | "pdf",
  ) => `${API_URL}/reports/${id}/export/${format}`,
  backupUrl: () => `${API_URL}/backup`,
  chat: (question: string) =>
    request<ChatResponse>("/ai/chat", jsonOptions("POST", { question })),
  helpAgent: (message: string) =>
    request<HelpAgentResponse>(
      "/ai/help-agent",
      jsonOptions("POST", { message }),
    ),
  absoluteApiUrl: (path: string) => `${API_ORIGIN}${path}`,
  aiStatus: () =>
    request<{
      enabled: boolean;
      available: boolean;
      model: string;
      models: string[];
      model_installed: boolean;
      url: string;
      external_cloud_enabled: boolean;
    }>("/ai/status"),
  ocrStatus: () =>
    request<{
      enabled: boolean;
      available: boolean;
      executable: string | null;
      version: string | null;
      installed_languages: string[];
      requested_languages: string[];
      missing_languages: string[];
      dpi: number;
    }>("/ocr/status"),
  budgets: (year: number, month: number) =>
    request<MonthlyBudget[]>(`/budgets?year=${year}&month=${month}`),
  budgetSummary: (year: number, month: number) =>
    request<MonthlyBudgetSummary>(
      `/budgets/summary?year=${year}&month=${month}`,
    ),
  budgetProposals: (year: number, month: number) =>
    request<BudgetProposal[]>(
      `/budgets/proposals?year=${year}&month=${month}`,
    ),
  generateBudgetProposals: (
    year: number,
    month: number,
    useLocalAi = false,
  ) =>
    request<BudgetProposal[]>(
      `/budgets/proposals/generate?year=${year}&month=${month}&use_local_ai=${useLocalAi}`,
      { method: "POST" },
    ),
  confirmBudgetProposal: (id: number) =>
    request<MonthlyBudget>(`/budgets/proposals/${id}/confirm`, {
      method: "POST",
    }),
  dismissBudgetProposal: (id: number) =>
    request<BudgetProposal>(`/budgets/proposals/${id}/dismiss`, {
      method: "POST",
    }),
  createBudget: (body: Record<string, unknown>) =>
    request<MonthlyBudget>("/budgets", jsonOptions("POST", body)),
  updateBudget: (id: number, body: Record<string, unknown>) =>
    request<MonthlyBudget>(`/budgets/${id}`, jsonOptions("PUT", body)),
  deleteBudget: (id: number) =>
    request<void>(`/budgets/${id}`, { method: "DELETE" }),
};
