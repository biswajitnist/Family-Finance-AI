import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "./api";
import { BudgetPanel } from "./components/BudgetPanel";
import { AdvisorDashboardPanel } from "./components/AdvisorDashboardPanel";
import { ChatPanel } from "./components/ChatPanel";
import { CommandCenter } from "./components/CommandCenter";
import { DashboardPeriodPicker } from "./components/DashboardPeriodPicker";
import { DocumentsPanel } from "./components/DocumentsPanel";
import { HelpAgent } from "./components/HelpAgent";
import { MarketDataPanel } from "./components/MarketDataPanel";
import { NotificationPopover } from "./components/NotificationPopover";
import { InvestmentsPanel } from "./components/InvestmentsPanel";
import {
  ResourceManager,
  type ResourceField,
} from "./components/ResourceManager";
import { ReportsPanel } from "./components/ReportsPanel";
import { RealEstatePanel } from "./components/RealEstatePanel";
import { RetirementPanel } from "./components/RetirementPanel";
import { ReviewQueue } from "./components/ReviewQueue";
import { RulesPanel } from "./components/RulesPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { SummaryCard } from "./components/SummaryCard";
import { TransactionForm } from "./components/TransactionForm";
import { TransactionManager } from "./components/TransactionManager";
import type {
  Account,
  Category,
  DashboardSummary,
  MonthlyBudgetSummary,
  ResourceRecord,
  Transaction,
  UserProfile,
} from "./types";
import { AppIcon, type IconName } from "./icons/IconRegistry";
import {
  CATEGORY_COLOR_OPTIONS,
  CATEGORY_ICON_OPTIONS,
  categoryPresentation,
} from "./categoryPresentation";

type Page =
  | "dashboard"
  | "transactions"
  | "documents"
  | "budgets"
  | "accounts"
  | "categories"
  | "rules"
  | "investments"
  | "watchlist"
  | "loans"
  | "properties"
  | "retirement"
  | "insurance"
  | "reports"
  | "chat"
  | "settings";

const PAGES = new Set<Page>([
  "dashboard",
  "transactions",
  "documents",
  "budgets",
  "accounts",
  "categories",
  "rules",
  "investments",
  "watchlist",
  "loans",
  "properties",
  "retirement",
  "insurance",
  "reports",
  "chat",
  "settings",
]);

function pageFromLocation(): Page {
  const candidate = window.location.hash.slice(1);
  return PAGES.has(candidate as Page) ? (candidate as Page) : "dashboard";
}

const today = new Date();
const currentPeriod = `${today.getFullYear()}-${String(
  today.getMonth() + 1,
).padStart(2, "0")}`;
const spendingPalette = [
  "#e7684d",
  "#f4bdb3",
  "#29ad86",
  "#a8dbe5",
  "#f1d9cf",
  "#dfe5e2",
];

function money(value: string | number, currency = "EUR") {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
  }).format(Number(value));
}

function compactAxisMoney(value: number, currency = "EUR") {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
    notation: "compact",
    maximumFractionDigits: 0,
  }).format(value);
}

function numberField(record: ResourceRecord, field: string) {
  return Number(record[field] ?? 0);
}

function insuranceMonthlyPremium(record: ResourceRecord) {
  const premium = numberField(record, "premium_amount");
  const frequency = String(record.premium_frequency ?? "monthly").toLowerCase();
  if (frequency === "yearly" || frequency === "annual") return premium / 12;
  if (frequency === "quarterly") return premium / 3;
  return premium;
}

function timeGreeting(timeZone = "Europe/Berlin") {
  try {
    const hour = Number(
      new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        hourCycle: "h23",
        timeZone,
      }).format(new Date()),
    );
    if (hour < 12) return "Good morning";
    if (hour < 18) return "Good afternoon";
    return "Good evening";
  } catch {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 18) return "Good afternoon";
    return "Good evening";
  }
}

function shortMonthLabel(value: string) {
  const [year, month] = value.split("-");
  const parsedYear = Number(year);
  const monthIndex = Number(month) - 1;
  const shortYear = parsedYear % 100;
  if (
    !Number.isFinite(parsedYear) ||
    !Number.isFinite(monthIndex) ||
    !Number.isFinite(shortYear)
  ) {
    return value;
  }
  return new Intl.DateTimeFormat("en-GB", { month: "short" }).format(
    new Date(parsedYear, monthIndex, 1),
  ) + `-${String(shortYear).padStart(2, "0")}`;
}

function longMonthLabel(value: string) {
  const [year, month] = value.split("-");
  const parsedYear = Number(year);
  const monthIndex = Number(month) - 1;
  if (!Number.isFinite(parsedYear) || !Number.isFinite(monthIndex)) {
    return value;
  }
  return new Intl.DateTimeFormat("en-GB", {
    month: "long",
    year: "numeric",
  }).format(new Date(parsedYear, monthIndex, 1));
}

type TrendTooltipProps = {
  active?: boolean;
  label?: string;
  payload?: Array<{
    color?: string;
    dataKey?: string;
    value?: number;
  }>;
  currency?: string;
};

function TrendTooltip({
  active,
  label,
  payload,
  currency = "EUR",
}: TrendTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="trend-tooltip">
      <strong>{label ? longMonthLabel(label) : "Selected month"}</strong>
      {payload.map((item) => (
        <span key={item.dataKey}>
          <i style={{ background: item.color }} />
          {item.dataKey === "income" ? "Income" : "Expenses"}
          <b>{money(item.value ?? 0, currency)}</b>
        </span>
      ))}
    </div>
  );
}

const NAVIGATION: Array<{ page: Page; label: string; group: string }> = [
  { page: "dashboard", label: "Overview", group: "Core" },
  { page: "transactions", label: "Transactions", group: "Core" },
  { page: "documents", label: "Documents", group: "Core" },
  { page: "budgets", label: "Budgets", group: "Planning" },
  { page: "accounts", label: "Accounts", group: "Manage" },
  { page: "categories", label: "Categories", group: "Manage" },
  { page: "rules", label: "Rules", group: "Manage" },
  { page: "investments", label: "Investments", group: "Planning" },
  { page: "watchlist", label: "Watchlist", group: "Planning" },
  { page: "loans", label: "Loans", group: "Planning" },
  { page: "properties", label: "Properties", group: "Planning" },
  { page: "retirement", label: "Retirement", group: "Planning" },
  { page: "insurance", label: "Insurance", group: "Planning" },
  { page: "reports", label: "Reports", group: "Insights" },
  { page: "chat", label: "Finance chat", group: "Insights" },
  { page: "settings", label: "Settings", group: "Insights" },
];

const PRIMARY_NAVIGATION: Array<{ page: Page; label: string }> = [
  { page: "dashboard", label: "Dashboard" },
  { page: "reports", label: "Reports" },
  { page: "documents", label: "Documents" },
  { page: "transactions", label: "Transactions" },
  { page: "chat", label: "Finance AI" },
];

const NAV_ICONS: Record<Page, IconName> = {
  dashboard: "dashboard",
  transactions: "transactions",
  documents: "documents",
  budgets: "budgets",
  accounts: "accounts",
  categories: "categories",
  rules: "rules",
  investments: "investments",
  watchlist: "watchlist",
  loans: "loans",
  properties: "properties",
  retirement: "institution",
  insurance: "insurance",
  reports: "reports",
  chat: "chat",
  settings: "settings",
};

const RESOURCE_CONFIG: Partial<
  Record<
    Page,
    {
      path: string;
      title: string;
      description: string;
      fields: ResourceField[];
      columns: Array<{ key: string; label: string }>;
      analyticsPath?: string;
      editable?: boolean;
    }
  >
> = {
  accounts: {
    path: "accounts",
    title: "Accounts",
    description:
      "Bank, credit card, cash, investment, loan, pension, and property accounts.",
    fields: [
      { name: "name", label: "Account name", required: true },
      {
        name: "type",
        label: "Type",
        type: "select",
        required: true,
        options: [
          "bank",
          "credit_card",
          "cash",
          "investment",
          "loan",
          "pension",
          "property",
        ].map((value) => ({ value, label: value.replaceAll("_", " ") })),
      },
      { name: "institution", label: "Institution" },
      { name: "country", label: "Country", defaultValue: "DE" },
      {
        name: "currency",
        label: "Currency",
        type: "select",
        defaultValue: "EUR",
        options: [
          { label: "EUR - Euro", value: "EUR" },
          { label: "INR - Indian rupee", value: "INR" },
          { label: "USD - US dollar", value: "USD" },
          { label: "GBP - British pound", value: "GBP" },
          { label: "CHF - Swiss franc", value: "CHF" },
        ],
      },
      {
        name: "opening_balance",
        label: "Opening balance",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "current_balance",
        label: "Current balance",
        type: "number",
        defaultValue: 0,
      },
    ],
    columns: [
      { key: "name", label: "Account" },
      { key: "type", label: "Type" },
      { key: "institution", label: "Institution" },
      { key: "current_balance", label: "Balance" },
      { key: "currency", label: "Currency" },
    ],
    editable: true,
  },
  categories: {
    path: "categories",
    title: "Categories",
    description: "Maintain the classification vocabulary used by rules and reports.",
    fields: [
      { name: "name", label: "Category name", required: true },
      {
        name: "type",
        label: "Type",
        type: "select",
        required: true,
        options: ["income", "expense", "transfer"].map((value) => ({
          value,
          label: value,
        })),
      },
      {
        name: "icon",
        label: "Category icon",
        type: "select",
        defaultValue: "category",
        options: CATEGORY_ICON_OPTIONS,
      },
      {
        name: "color",
        label: "Icon color",
        type: "select",
        defaultValue: "green",
        options: CATEGORY_COLOR_OPTIONS,
      },
    ],
    columns: [
      { key: "name", label: "Category" },
      { key: "type", label: "Type" },
      { key: "icon", label: "Icon" },
      { key: "color", label: "Color" },
    ],
    editable: true,
  },
  rules: {
    path: "rules",
    title: "Rules",
    description:
      "Automatically categorize familiar merchants and descriptions during statement imports.",
    fields: [
      {
        name: "name",
        label: "Rule name",
        required: true,
        helpText: "A name you will recognize, for example REWE groceries.",
      },
      {
        name: "condition_type",
        label: "What should be matched?",
        type: "select",
        required: true,
        defaultValue: "vendor",
        options: [
          { value: "vendor", label: "Merchant name contains" },
          { value: "keyword", label: "Description contains" },
        ],
      },
      {
        name: "condition_value",
        label: "Text to find",
        required: true,
        helpText: "Example: REWE, Netflix, Employer, or Stadt Wolfsburg.",
      },
      {
        name: "action_type",
        label: "What should happen?",
        type: "select",
        defaultValue: "category",
        options: [
          { value: "category", label: "Set category" },
          { value: "transaction_type", label: "Set income or expense type" },
        ],
      },
      {
        name: "action_value",
        label: "Category or type",
        required: true,
        helpText:
          "Enter an existing category such as Grocery, or enter debit/credit for transaction type.",
      },
    ],
    columns: [
      { key: "name", label: "Rule" },
      { key: "condition_type", label: "Matches" },
      { key: "condition_value", label: "Text" },
      { key: "action_value", label: "Then set" },
    ],
  },
  investments: {
    path: "investments",
    title: "Investments",
    description: "Track portfolio holdings, cost basis, allocation, and current value.",
    fields: [
      { name: "asset_name", label: "Asset", required: true },
      { name: "asset_type", label: "Type", required: true },
      {
        name: "ticker",
        label: "Ticker (market symbol)",
        helpText: "Examples: NVDA, GOOGL, IONQ. Optional for funds without a known symbol.",
      },
      { name: "quantity", label: "Quantity", type: "number", defaultValue: 0 },
      {
        name: "average_price",
        label: "Average price",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "current_value",
        label: "Current value",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "currency",
        label: "Currency",
        type: "select",
        defaultValue: "EUR",
        options: [
          { label: "EUR - Euro", value: "EUR" },
          { label: "INR - Indian rupee", value: "INR" },
          { label: "USD - US dollar", value: "USD" },
          { label: "GBP - British pound", value: "GBP" },
          { label: "CHF - Swiss franc", value: "CHF" },
        ],
      },
    ],
    columns: [
      { key: "asset_name", label: "Asset" },
      { key: "asset_type", label: "Type" },
      { key: "ticker", label: "Ticker" },
      { key: "quantity", label: "Quantity" },
      { key: "average_price", label: "Average price" },
      { key: "market_price", label: "Market price" },
      { key: "current_value", label: "Current value" },
      { key: "currency", label: "Currency" },
    ],
    analyticsPath: "investments",
    editable: true,
  },
  watchlist: {
    path: "watchlist",
    title: "Watchlist",
    description:
      "Track market symbols without adding them to your owned portfolio.",
    fields: [
      { name: "symbol", label: "Ticker", required: true },
      { name: "name", label: "Name" },
      { name: "asset_type", label: "Type", defaultValue: "Stock" },
      { name: "currency", label: "Market currency", defaultValue: "USD" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
    columns: [
      { key: "symbol", label: "Ticker" },
      { key: "name", label: "Name" },
      { key: "asset_type", label: "Type" },
      { key: "currency", label: "Currency" },
    ],
    editable: true,
  },
  loans: {
    path: "loans",
    title: "Loans",
    description: "Track running personal loans and standard EMI loans from ledger movements.",
    fields: [
      { name: "lender", label: "Lender / borrower", required: true },
      {
        name: "direction",
        label: "Direction",
        type: "select",
        defaultValue: "borrowed",
        options: [
          { label: "I borrowed money", value: "borrowed" },
          { label: "I lent money", value: "lent" },
        ],
      },
      {
        name: "loan_type",
        label: "Loan type",
        type: "select",
        defaultValue: "personal_running",
        options: [
          { label: "Running personal loan", value: "personal_running" },
          { label: "Personal loan", value: "personal" },
          { label: "Friend loan", value: "friend" },
          { label: "Family loan", value: "family" },
          { label: "Informal loan", value: "informal" },
          { label: "Standard EMI loan", value: "standard_emi" },
          { label: "Bank loan", value: "bank" },
        ],
      },
      {
        name: "currency",
        label: "Currency",
        type: "select",
        defaultValue: "EUR",
        options: [
          { label: "EUR - Euro", value: "EUR" },
          { label: "INR - Indian rupee", value: "INR" },
          { label: "USD - US dollar", value: "USD" },
          { label: "GBP - British pound", value: "GBP" },
          { label: "CHF - Swiss franc", value: "CHF" },
        ],
      },
      {
        name: "current_balance",
        label: "Opening balance",
        type: "number",
        required: true,
        helpText:
          "After creation, change this through adjustment ledger entries only.",
      },
      { name: "start_date", label: "Start date", type: "date" },
      {
        name: "interest_mode",
        label: "Interest charged type",
        type: "select",
        defaultValue: "manual",
        options: [
          { label: "Manual postings", value: "manual" },
          { label: "Automatic calculation", value: "automatic" },
          { label: "No interest", value: "none" },
        ],
      },
      {
        name: "interest_rate",
        label: "Interest rate % (automatic only)",
        type: "number",
        defaultValue: 0,
      },
    ],
    columns: [
      { key: "lender", label: "Lender" },
      { key: "direction", label: "Direction" },
      { key: "loan_type", label: "Type" },
      { key: "current_balance", label: "Ledger balance" },
      { key: "interest_rate", label: "Rate %" },
    ],
    analyticsPath: "debt",
    editable: true,
  },
  properties: {
    path: "properties",
    title: "Properties",
    description:
      "Track value, rental cash flow, financing, depreciation, and land share.",
    fields: [
      { name: "name", label: "Property name", required: true },
      { name: "address", label: "Address", type: "textarea" },
      { name: "country", label: "Country", defaultValue: "DE" },
      { name: "currency", label: "Currency", defaultValue: "EUR" },
      {
        name: "purchase_price",
        label: "Purchase price",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "current_value",
        label: "Current value",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "monthly_rental_income",
        label: "Monthly rent",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "monthly_costs",
        label: "Monthly costs",
        type: "number",
        defaultValue: 0,
      },
      { name: "afa_rate", label: "AfA rate %", type: "number", defaultValue: 0 },
      {
        name: "land_share_percentage",
        label: "Land share %",
        type: "number",
        defaultValue: 0,
      },
    ],
    columns: [
      { key: "name", label: "Property" },
      { key: "current_value", label: "Value" },
      { key: "monthly_rental_income", label: "Rent/month" },
      { key: "monthly_costs", label: "Costs/month" },
      { key: "currency", label: "Currency" },
    ],
    analyticsPath: "properties",
  },
  insurance: {
    path: "insurance",
    title: "Insurance",
    description:
      "Maintain policy coverage, premiums, beneficiaries, and protection gaps.",
    fields: [
      { name: "provider", label: "Provider", required: true },
      { name: "policy_type", label: "Policy type", required: true },
      { name: "policy_number", label: "Policy number" },
      {
        name: "coverage_amount",
        label: "Coverage amount",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "premium_amount",
        label: "Premium",
        type: "number",
        defaultValue: 0,
      },
      {
        name: "premium_frequency",
        label: "Frequency",
        type: "select",
        defaultValue: "monthly",
        options: ["monthly", "quarterly", "yearly"].map((value) => ({
          value,
          label: value,
        })),
      },
      {
        name: "currency",
        label: "Currency",
        type: "select",
        defaultValue: "EUR",
        options: [
          { label: "EUR - Euro", value: "EUR" },
          { label: "INR - Indian rupee", value: "INR" },
          { label: "USD - US dollar", value: "USD" },
          { label: "GBP - British pound", value: "GBP" },
          { label: "CHF - Swiss franc", value: "CHF" },
        ],
      },
      { name: "start_date", label: "Start date", type: "date" },
      { name: "end_date", label: "End date", type: "date" },
      { name: "beneficiaries", label: "Beneficiaries" },
    ],
    columns: [
      { key: "provider", label: "Provider" },
      { key: "policy_type", label: "Policy" },
      { key: "coverage_amount", label: "Coverage" },
      { key: "premium_amount", label: "Premium" },
      { key: "premium_frequency", label: "Frequency" },
    ],
    analyticsPath: "protection",
    editable: true,
  },
};

export default function App() {
  const [page, setPage] = useState<Page>(pageFromLocation);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [pending, setPending] = useState<Transaction[]>([]);
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [budgetSummary, setBudgetSummary] = useState<MonthlyBudgetSummary | null>(null);
  const [investmentHoldings, setInvestmentHoldings] = useState<ResourceRecord[]>([]);
  const [insurancePolicies, setInsurancePolicies] = useState<ResourceRecord[]>([]);
  const [protectionAnalytics, setProtectionAnalytics] =
    useState<Record<string, unknown> | null>(null);
  const [retirementPlans, setRetirementPlans] = useState<ResourceRecord[]>([]);
  const [loans, setLoans] = useState<ResourceRecord[]>([]);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [period, setPeriod] = useState(currentPeriod);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshingDashboard, setRefreshingDashboard] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [showTransactionForm, setShowTransactionForm] = useState(false);
  const [year, month] = period.split("-").map(Number);

  const loadData = useCallback(async () => {
    try {
      const [
        accountData,
        categoryData,
        transactionData,
        pendingData,
        summary,
        budgetTotals,
        profileData,
        investmentData,
        insuranceData,
        protectionData,
        retirementData,
        loanData,
      ] =
        await Promise.all([
          api.accounts(),
          api.categories(),
          api.transactions(),
          api.transactions(false),
          api.dashboard(year, month),
          api.budgetSummary(year, month),
          api.profile(),
          api.resources("investments"),
          api.resources("insurance"),
          api.analytics("protection"),
          api.resources("retirement"),
          api.resources("loans"),
        ]);
      setAccounts(accountData);
      setCategories(categoryData);
      setTransactions(transactionData);
      setPending(pendingData);
      setDashboard(summary);
      setBudgetSummary(budgetTotals);
      setProfile(profileData);
      setInvestmentHoldings(investmentData);
      setInsurancePolicies(insuranceData);
      setProtectionAnalytics(protectionData);
      setRetirementPlans(retirementData);
      setLoans(loanData);
      setError("");
      setRefreshKey((value) => value + 1);
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : "Backend unavailable",
      );
    }
  }, [month, year]);

  async function refreshDashboard() {
    setRefreshingDashboard(true);
    setRefreshMessage("Refreshing local dashboard data...");
    try {
      await loadData();
      setRefreshMessage(`Updated ${new Date().toLocaleTimeString()}`);
    } catch {
      setRefreshMessage("Refresh failed. Check the backend connection.");
    } finally {
      setRefreshingDashboard(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const restorePage = () => setPage(pageFromLocation());
    window.addEventListener("hashchange", restorePage);
    window.addEventListener("popstate", restorePage);
    return () => {
      window.removeEventListener("hashchange", restorePage);
      window.removeEventListener("popstate", restorePage);
    };
  }, []);

  const chartData = useMemo(
    () =>
      (dashboard?.monthly_trend ?? []).map((item) => ({
        ...item,
        income: Number(item.income),
        expenses: Number(item.expenses),
      })),
    [dashboard],
  );

  const cashFlowMaximum = Math.max(
    ...chartData.map((item) => Math.abs(item.income - item.expenses)),
    1,
  );
  const cashFlowTicks = [cashFlowMaximum, 0, -cashFlowMaximum];
  const spendingTotal = useMemo(
    () =>
      (dashboard?.spending_by_category ?? []).reduce(
        (sum, item) => sum + Number(item.amount),
        0,
      ),
    [dashboard?.spending_by_category],
  );
  const spendingDistribution = useMemo(() => {
    let offset = 0;
    return (dashboard?.spending_by_category ?? []).slice(0, 5).map((item, index) => {
      const amount = Number(item.amount);
      const percentage = spendingTotal > 0 ? (amount / spendingTotal) * 100 : 0;
      const start = offset;
      offset += percentage;
      return {
        ...item,
        amount,
        color: spendingPalette[index % spendingPalette.length],
        percentage,
        segment: `${spendingPalette[index % spendingPalette.length]} ${start}% ${offset}%`,
      };
    });
  }, [dashboard?.spending_by_category, spendingTotal]);
  const spendingDonut = spendingDistribution.length
    ? `conic-gradient(${spendingDistribution.map((item) => item.segment).join(", ")})`
    : "conic-gradient(#edf2ef 0 100%)";
  const budgetTotal = Number(dashboard?.budget_total ?? 0);
  const budgetSpent = Number(dashboard?.budget_spent ?? 0);
  const budgetRemaining = Number(dashboard?.budget_remaining ?? 0);
  const accountBalance = Number(dashboard?.account_balance ?? 0);
  const investmentsValue = Number(dashboard?.investments ?? 0);
  const debtBalance = Number(dashboard?.debt_balance ?? 0);
  const propertyValue = Number(dashboard?.property_value ?? 0);
  const assetBase = Math.max(accountBalance + investmentsValue + propertyValue, 1);
  const debtLoadPercentage = Math.min((debtBalance / assetBase) * 100, 100);
  const propertySharePercentage = Math.min((propertyValue / assetBase) * 100, 100);
  const fallbackInsuranceCoverage = insurancePolicies.reduce(
    (sum, item) => sum + numberField(item, "coverage_amount"),
    0,
  );
  const fallbackMonthlyInsurancePremium = insurancePolicies.reduce(
    (sum, item) => sum + insuranceMonthlyPremium(item),
    0,
  );
  const insuranceCoverage =
    Number(protectionAnalytics?.total_coverage ?? 0) ||
    fallbackInsuranceCoverage;
  const monthlyInsurancePremium =
    Number(protectionAnalytics?.scheduled_monthly ?? 0) ||
    fallbackMonthlyInsurancePremium;
  const annualInsurancePremium = monthlyInsurancePremium * 12;
  const insurancePremiumLoad = insuranceCoverage
    ? Math.min((annualInsurancePremium / insuranceCoverage) * 100, 100)
    : 0;
  const pensionCurrent = retirementPlans.reduce(
    (sum, item) => sum + numberField(item, "current_value"),
    0,
  );
  const pensionProjected = retirementPlans.reduce(
    (sum, item) => sum + numberField(item, "projected_value"),
    0,
  );
  const pensionProgress = pensionProjected
    ? Math.min((pensionCurrent / pensionProjected) * 100, 100)
    : 0;
  const debtToPropertyPercentage = propertyValue
    ? Math.min((debtBalance / propertyValue) * 100, 100)
    : 0;
  const propertyEquity = propertyValue - debtBalance;
  const budgetPlannerRows = (budgetSummary?.categories ?? []).map((item) => {
    const savedCategory = categories.find(
      (category) => category.id === item.category_id,
    );
    const presentation = categoryPresentation({
      name: item.category,
      icon: savedCategory?.icon,
      color: savedCategory?.color,
    });
    return {
      ...item,
      icon: presentation.icon,
      percentageValue: Number(item.percentage),
    };
  });
  const investmentTotal = investmentHoldings.reduce(
    (sum, item) => sum + numberField(item, "current_value"),
    0,
  );
  const investmentAllocation = Object.values(
    investmentHoldings.reduce<
      Record<string, { label: string; value: number }>
    >((groups, item) => {
      const rawType = String(item.asset_type ?? "Other");
      const label =
        rawType.charAt(0).toUpperCase() +
        rawType.slice(1).replace(/[_-]/g, " ");
      groups[label] = groups[label] ?? { label, value: 0 };
      groups[label].value += numberField(item, "current_value");
      return groups;
    }, {}),
  )
    .sort((left, right) => right.value - left.value)
    .slice(0, 5)
    .map((item) => ({
      ...item,
      percentage: investmentTotal > 0 ? (item.value / investmentTotal) * 100 : 0,
    }));
  const compactMetricCards: Array<{
    accent: "red" | "green" | "teal" | "blue";
    icon: IconName;
    label: string;
    meta: string;
    value: number;
    detail: string;
    progress: number;
    progressClass: string;
  }> = [
    {
      accent: "red",
      icon: "loans",
      label: "Debt",
      meta: `${debtLoadPercentage.toFixed(0)}% of asset base`,
      value: debtBalance,
      detail: `${debtToPropertyPercentage.toFixed(0)}% vs property`,
      progress: debtLoadPercentage,
      progressClass: "debt",
    },
    {
      accent: "green",
      icon: "properties",
      label: "Property",
      meta: `${propertySharePercentage.toFixed(0)}% of asset base`,
      value: propertyValue,
      detail: `${money(propertyEquity, dashboard?.currency)} equity`,
      progress: propertySharePercentage,
      progressClass: "property",
    },
    {
      accent: "teal",
      icon: "insurance",
      label: "Insurance",
      meta: `${insurancePolicies.length} active policies`,
      value: insuranceCoverage,
      detail: `${money(monthlyInsurancePremium, dashboard?.currency)} / month`,
      progress: insurancePremiumLoad,
      progressClass: "insurance",
    },
    {
      accent: "blue",
      icon: "institution",
      label: "Pension",
      meta: `${retirementPlans.length} retirement plans`,
      value: pensionCurrent,
      detail: `${pensionProgress.toFixed(0)}% funded`,
      progress: pensionProgress,
      progressClass: "pension",
    },
  ];

  const previousMonth = chartData.at(-2);
  function comparisonDetail(
    current: number,
    previous: number | undefined,
    empty: string,
  ) {
    if (!current) return empty;
    if (!previous) return "First recorded month";
    const change = ((current - previous) / previous) * 100;
    return `${change >= 0 ? "↑" : "↓"} ${Math.abs(change).toFixed(1)}% vs previous month`;
  }

  function navigate(nextPage: Page) {
    setPage(nextPage);
    setMenuOpen(false);
    const nextHash = `#${nextPage}`;
    if (window.location.hash !== nextHash) {
      window.history.pushState(null, "", nextHash);
    }
  }

  const resource =
    page === "rules" || page === "investments"
      ? undefined
      : RESOURCE_CONFIG[page];

  return (
    <div className="application">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand sidebar-brand">
          <span className="brand-mark">L</span>
          <div>
            <strong>Ledger Local</strong>
            <small>Private finance workspace</small>
          </div>
        </div>
        <nav className="main-navigation">
          {["Core", "Manage", "Planning", "Insights"].map((group) => (
            <div className="nav-group" key={group}>
              <span>{group}</span>
              {NAVIGATION.filter((item) => item.group === group).map((item) => (
                <button
                  className={page === item.page ? "active" : ""}
                  key={item.page}
                  onClick={() => navigate(item.page)}
                  title={item.label}
                >
                  <span className="nav-glyph">
                    <AppIcon name={NAV_ICONS[item.page]} size={17} />
                  </span>
                  <span className="nav-label">{item.label}</span>
                  {item.page === "transactions" && pending.length > 0 && (
                    <b>{pending.length}</b>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="local-status">
          <span />
          Local data only
          <small>No cloud AI enabled</small>
        </div>
      </aside>

      <div className="app-content">
        <header className="desktop-command-bar">
          <button
            className="command-brand"
            onClick={() => navigate("dashboard")}
            type="button"
          >
            <span className="brand-mark">L</span>
            <span>
              <strong>Ledger Local</strong>
              <small>Private finance, on this machine</small>
            </span>
          </button>
          <nav className="primary-navigation" aria-label="Primary navigation">
            {PRIMARY_NAVIGATION.map((item) => (
              <button
                className={page === item.page ? "active" : ""}
                key={item.page}
                onClick={() => navigate(item.page)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="command-actions">
            <CommandCenter onNavigate={navigate} />
            <NotificationPopover period={period} refreshKey={refreshKey} />
            <button
              className="profile-action"
              onClick={() => navigate("settings")}
            >
              <span>{profile?.name?.slice(0, 2).toUpperCase() || "LL"}</span>
              <small>Local</small>
            </button>
          </div>
        </header>
        <header className="mobile-header">
          <button onClick={() => setMenuOpen((value) => !value)}>Menu</button>
          <strong>Ledger Local</strong>
          <span />
        </header>
        <main className="workspace-main">
          {error && <div className="error-banner">{error}</div>}

          {page === "dashboard" && (
            <>
              <section className="hero compact-hero">
                <div>
                  <h1>
                    {timeGreeting(profile?.timezone)},{" "}
                    <span>{profile?.name || "Ledger owner"}</span>
                  </h1>
                  <p>Here&apos;s your financial overview.</p>
                </div>
                <div className="dashboard-date-actions">
                  <DashboardPeriodPicker period={period} onChange={setPeriod} />
                  <button
                    aria-label="Refresh dashboard"
                    className={`dashboard-refresh ${refreshingDashboard ? "loading" : ""}`}
                    disabled={refreshingDashboard}
                    onClick={() => void refreshDashboard()}
                  >
                    <AppIcon name="refresh" />
                  </button>
                  {refreshMessage && (
                    <span className="dashboard-refresh-status">
                      {refreshingDashboard && <i />}
                      {refreshMessage}
                    </span>
                  )}
                </div>
              </section>
              <section className="summary-grid dashboard-primary-summary">
                <SummaryCard
                  label="Net worth"
                  value={money(dashboard?.net_worth ?? 0, dashboard?.currency)}
                  tone="positive"
                  detail="Accounts + assets − debt"
                  icon="netWorth"
                  accent="blue"
                />
                <SummaryCard
                  label="Income"
                  value={money(dashboard?.income ?? 0, dashboard?.currency)}
                  tone="positive"
                  icon="income"
                  accent="green"
                  detail={comparisonDetail(
                    Number(dashboard?.income ?? 0),
                    previousMonth?.income,
                    "No income this month",
                  )}
                />
                <SummaryCard
                  label="Expenses"
                  value={money(dashboard?.expenses ?? 0, dashboard?.currency)}
                  tone="negative"
                  icon="expense"
                  accent="red"
                  detail={comparisonDetail(
                    Number(dashboard?.expenses ?? 0),
                    previousMonth?.expenses,
                    "No expenses this month",
                  )}
                />
                <SummaryCard
                  label="Net cash flow"
                  value={money(dashboard?.net_cash_flow ?? 0, dashboard?.currency)}
                  detail={`${dashboard?.savings_rate ?? 0}% savings rate`}
                  icon="netCashFlow"
                  accent={
                    Number(dashboard?.net_cash_flow ?? 0) < 0 ? "red" : "green"
                  }
                />
                <SummaryCard
                  label="Investments"
                  value={money(dashboard?.investments ?? 0, dashboard?.currency)}
                  icon="investments"
                  accent="green"
                  detail="Current portfolio value"
                />
              </section>
              <AdvisorDashboardPanel
                compact
                currency={dashboard?.currency}
                period={period}
                refreshKey={refreshKey}
              />
              <section className="dashboard-insights-grid">
                <article className="panel chart-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Income vs Expenses</h2>
                      <small>6-month overview</small>
                    </div>
                    <span className="soft-filter chart-period-filter">
                      Monthly
                      <AppIcon name="chevronDown" size={12} />
                    </span>
                  </div>
                  {chartData.length ? (
                    <>
                      <ResponsiveContainer width="100%" height={190}>
                        <LineChart
                          data={chartData}
                          margin={{ top: 8, right: 30, left: 4, bottom: 8 }}
                        >
                          <CartesianGrid stroke="#eef1ef" strokeDasharray="2 2" />
                          <XAxis
                            axisLine={false}
                            dataKey="month"
                            interval={0}
                            minTickGap={0}
                            tickFormatter={shortMonthLabel}
                            tickLine={false}
                            tickMargin={9}
                            tick={{ fill: "#5d6661", fontSize: 9 }}
                            padding={{ left: 8, right: 20 }}
                          />
                          <YAxis
                            axisLine={false}
                            tickFormatter={(value) =>
                              compactAxisMoney(Number(value), dashboard?.currency)
                            }
                            tickLine={false}
                            tick={{ fill: "#5d6661", fontSize: 9 }}
                            width={42}
                          />
                          <Tooltip
                            content={
                              <TrendTooltip currency={dashboard?.currency} />
                            }
                          />
                          <Line
                            type="monotone"
                            dataKey="income"
                            stroke="#29ad86"
                            strokeWidth={2}
                            dot={{ r: 3.8, fill: "#29ad86", strokeWidth: 0 }}
                            activeDot={{ r: 5, fill: "#29ad86", strokeWidth: 0 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="expenses"
                            stroke="#e7684d"
                            strokeWidth={2}
                            dot={{ r: 3.8, fill: "#e7684d", strokeWidth: 0 }}
                            activeDot={{ r: 5, fill: "#e7684d", strokeWidth: 0 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                      <div className="mini-legend">
                        <span><i className="income" /> Income</span>
                        <span><i className="expense" /> Expenses</span>
                      </div>
                    </>
                  ) : (
                    <p className="empty-state chart-empty">
                      Add validated transactions to reveal your trend.
                    </p>
                  )}
                </article>
                <article className="panel cashflow-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Cash Flow</h2>
                      <small>Monthly net cash flow</small>
                    </div>
                    <span className="soft-filter">Monthly</span>
                  </div>
                  {chartData.length ? (
                    <>
                      <div className="cashflow-chart">
                        <div className="cashflow-y-axis" aria-hidden="true">
                          {cashFlowTicks.map((tick) => (
                            <span key={tick}>{compactAxisMoney(tick, dashboard?.currency)}</span>
                          ))}
                        </div>
                        <div className="cashflow-bars" aria-label="Monthly cash flow">
                          {chartData.map((item) => {
                            const net = item.income - item.expenses;
                            const height = Math.max(
                              (Math.abs(net) / cashFlowMaximum) * 100,
                              8,
                            );
                            return (
                              <div className="cashflow-bar-item" key={item.month}>
                                <span className="cashflow-bar-track">
                                  <i
                                    className={net < 0 ? "negative" : "positive"}
                                    style={{ height: `${height}%` }}
                                    title={`${shortMonthLabel(item.month)}: ${money(net, dashboard?.currency)}`}
                                  />
                                </span>
                                <small>{shortMonthLabel(item.month)}</small>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                      <div className="mini-legend">
                        <span><i className="income" /> Positive cash flow</span>
                        <span><i className="expense" /> Negative cash flow</span>
                      </div>
                    </>
                  ) : (
                    <p className="empty-state chart-empty">
                      Add transactions to show cash flow.
                    </p>
                  )}
                </article>
                <article className="panel category-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Top Spending</h2>
                      <small>Expense distribution</small>
                    </div>
                    <span className="soft-filter">This month</span>
                  </div>
                  <div className="category-list">
                    {spendingDistribution.length ? (
                      <div className="spending-donut-card">
                        <div
                          className="spending-donut"
                          style={{ "--spending-donut": spendingDonut } as CSSProperties}
                        >
                          <strong>100%</strong>
                          <small>Total</small>
                        </div>
                        <div className="spending-donut-legend">
                          {spendingDistribution.map((item) => (
                            <div key={item.category}>
                              <span>
                                <i style={{ background: item.color }} />
                                {item.category}
                              </span>
                              <strong>{item.percentage.toFixed(0)}%</strong>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="empty-state">No expense data this month.</p>
                    )}
                  </div>
                  <button
                    className="dashboard-card-link"
                    type="button"
                    onClick={() => navigate("transactions")}
                  >
                    <span>View all expenses</span>
                    <AppIcon name="chevronRight" size={16} />
                  </button>
                </article>
              </section>
              <section className="dashboard-planning-grid">
                <div className="compact-metric-strip">
                  {compactMetricCards.map((item) => (
                    <article className="panel compact-metric-card" key={item.label}>
                      <div>
                        <span className={`category-spend-icon ${item.accent}`}>
                          <AppIcon name={item.icon} size={15} />
                        </span>
                        <div>
                          <h2>{item.label}</h2>
                          <small>{item.meta}</small>
                        </div>
                      </div>
                      <div>
                        <strong>{money(item.value, dashboard?.currency)}</strong>
                        <span>{item.detail}</span>
                      </div>
                      <div className={`progress metric-progress ${item.progressClass}`}>
                        <span style={{ width: `${Math.max(item.progress, 4)}%` }} />
                      </div>
                    </article>
                  ))}
                </div>
                <article className="panel budget-planner-card">
                  <div className="planner-card-heading">
                    <div>
                      <p className="eyebrow">Actual vs plan</p>
                      <h2>Category usage</h2>
                    </div>
                    <button
                      aria-label="View budget details"
                      onClick={() => navigate("budgets")}
                      type="button"
                    >
                      ...
                    </button>
                  </div>
                  <div className="budget-planner-list">
                    {budgetPlannerRows.length ? (
                      budgetPlannerRows.map((item) => (
                        <div className="budget-planner-row" key={item.budget_id}>
                          <span className="budget-planner-icon">
                            <AppIcon name={item.icon} size={13} />
                          </span>
                          <span>{item.category}</span>
                          <strong>{item.percentageValue.toFixed(0)}%</strong>
                          <div className="budget-planner-bar">
                            <i
                              className={item.percentageValue > 100 ? "over-budget" : ""}
                              style={{
                                width: `${Math.max(
                                  Math.min(item.percentageValue, 100),
                                  2,
                                )}%`,
                              }}
                            />
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="empty-state">No category budgets for this month.</p>
                    )}
                  </div>
                </article>
                <article className="panel investment-allocation-card">
                  <div className="planner-card-heading">
                    <div>
                      <h2>Investments</h2>
                      <small>Allocation by asset type</small>
                    </div>
                    <span className="soft-filter">{money(investmentTotal, dashboard?.currency)}</span>
                  </div>
                  <div className="investment-allocation-list">
                    {investmentAllocation.length ? (
                      investmentAllocation.map((item) => (
                        <div className="investment-allocation-row" key={item.label}>
                          <strong>{item.label}</strong>
                          <span>{money(item.value, dashboard?.currency)}</span>
                          <div className="investment-allocation-bar">
                            <i style={{ width: `${Math.max(item.percentage, 1.5)}%` }} />
                          </div>
                          <b>{item.percentage.toFixed(1)}%</b>
                        </div>
                      ))
                    ) : (
                      <p className="empty-state">No investment holdings yet.</p>
                    )}
                  </div>
                </article>
              </section>
            </>
          )}

          {page === "transactions" && (
            <>
              <section className="page-heading transaction-page-heading">
                <div>
                  <p className="eyebrow">Financial source of truth</p>
                  <h1>Transactions</h1>
                  <p>Classify, edit, validate, and analyse your financial records.</p>
                </div>
                <button
                  onClick={() => setShowTransactionForm(true)}
                  type="button"
                >
                  <AppIcon name="add" size={16} />
                  Manually Add Transaction
                </button>
              </section>
              <article className="panel section-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">User validation</p>
                    <h2>Review queue</h2>
                  </div>
                  <span className="count-pill">{pending.length}</span>
                </div>
                <ReviewQueue
                  transactions={pending}
                  accounts={accounts}
                  categories={categories}
                  onChanged={loadData}
                />
              </article>
              <article className="panel section-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Database records</p>
                    <h2>Recent transactions</h2>
                  </div>
                </div>
                <TransactionManager
                  transactions={transactions}
                  accounts={accounts}
                  categories={categories}
                  loans={loans}
                  onChanged={loadData}
                />
              </article>
              {showTransactionForm && (
                <div
                  className="investment-modal-backdrop"
                  onMouseDown={(event) => {
                    if (event.target === event.currentTarget) {
                      setShowTransactionForm(false);
                    }
                  }}
                >
                  <div
                    aria-labelledby="manual-transaction-title"
                    aria-modal="true"
                    className="investment-modal transaction-modal"
                    role="dialog"
                  >
                    <header>
                      <div>
                        <p className="eyebrow">Manual record</p>
                        <h2 id="manual-transaction-title">Add transaction</h2>
                      </div>
                      <button
                        aria-label="Close add transaction"
                        className="risk-modal-close"
                        onClick={() => setShowTransactionForm(false)}
                        type="button"
                      >
                        <AppIcon name="close" size={18} />
                      </button>
                    </header>
                    <TransactionForm
                      accounts={accounts}
                      categories={categories}
                      loans={loans}
                      onSaved={() => {
                        setShowTransactionForm(false);
                        void loadData();
                      }}
                    />
                  </div>
                </div>
              )}
            </>
          )}

          {page === "documents" && (
            <DocumentsPanel
              accounts={accounts}
              categories={categories}
              onChanged={loadData}
            />
          )}
          {page === "budgets" && (
            <BudgetPanel
              categories={categories}
              initialPeriod={period}
              onChanged={loadData}
            />
          )}
          {page === "reports" && <ReportsPanel initialPeriod={period} />}
          {page === "chat" && <ChatPanel />}
          {page === "settings" && (
            <SettingsPanel profile={profile} onSaved={setProfile} />
          )}
          {page === "properties" && <RealEstatePanel refreshKey={refreshKey} />}
          {page === "retirement" && <RetirementPanel refreshKey={refreshKey} />}
          {page === "rules" && (
            <RulesPanel categories={categories} refreshKey={refreshKey} />
          )}
          {page === "investments" && (
            <InvestmentsPanel refreshKey={refreshKey} />
          )}
          {resource && page !== "properties" && (
            <ResourceManager
              {...resource}
              key={resource.path}
              baseCurrency={profile?.base_currency ?? "EUR"}
              refreshKey={refreshKey}
            />
          )}
          {(page === "investments" || page === "watchlist") && (
            <MarketDataPanel onRefreshed={loadData} />
          )}
        </main>
      </div>
      <HelpAgent />
    </div>
  );
}
