import type { ComponentType, SVGProps } from "react";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  Bell,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  ChartNoAxesCombined,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  CreditCard,
  FileText,
  FolderOpen,
  Gauge,
  Globe2,
  HelpCircle,
  Home,
  Landmark,
  LayoutDashboard,
  ListChecks,
  LogOut,
  MessageCircle,
  PieChart,
  ReceiptText,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Database,
  LockKeyhole,
  Palette,
  CloudCog,
  ArchiveRestore,
  Car,
  Dumbbell,
  GraduationCap,
  HeartPulse,
  Plane,
  PlugZap,
  Plus,
  Repeat2,
  ShoppingBag,
  Tags,
  TrendingUp,
  Utensils,
  UserRound,
  WalletCards,
  X,
} from "lucide-react";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

const lucideRegistry = {
  accounts: WalletCards,
  alert: AlertCircle,
  bell: Bell,
  budgets: CircleDollarSign,
  calendar: CalendarDays,
  categories: Tags,
  chart: BarChart3,
  chat: MessageCircle,
  check: Check,
  chevronDown: ChevronDown,
  chevronLeft: ChevronLeft,
  chevronRight: ChevronRight,
  close: X,
  dashboard: LayoutDashboard,
  documents: FolderOpen,
  expense: ArrowUp,
  help: HelpCircle,
  income: ArrowDown,
  insurance: ShieldCheck,
  investments: PieChart,
  loans: Landmark,
  logout: LogOut,
  netCashFlow: TrendingUp,
  netWorth: CreditCard,
  properties: Home,
  add: Plus,
  refresh: RefreshCw,
  reports: ChartNoAxesCombined,
  review: ListChecks,
  rules: BookOpen,
  search: Search,
  settings: Settings,
  sparkles: Sparkles,
  transactions: ReceiptText,
  user: UserRound,
  watchlist: BriefcaseBusiness,
  institution: Building2,
  gauge: Gauge,
  file: FileText,
  globe: Globe2,
  controls: SlidersHorizontal,
  database: Database,
  security: LockKeyhole,
  themes: Palette,
  providers: CloudCog,
  backup: ArchiveRestore,
  category: Tags,
  shopping: ShoppingBag,
  grocery: ShoppingBag,
  utilities: PlugZap,
  transport: Car,
  restaurant: Utensils,
  health: HeartPulse,
  education: GraduationCap,
  travel: Plane,
  sports: Dumbbell,
  subscription: Repeat2,
  currency: CircleDollarSign,
} satisfies Record<string, IconComponent>;

export type IconName = keyof typeof lucideRegistry;

let activeRegistry: Record<IconName, IconComponent> = lucideRegistry;

export function configureIconRegistry(
  overrides: Partial<Record<IconName, IconComponent>>,
) {
  activeRegistry = { ...activeRegistry, ...overrides };
}

export function AppIcon({
  name,
  size = 18,
  strokeWidth = 1.8,
  ...props
}: SVGProps<SVGSVGElement> & {
  name: IconName;
  size?: number;
  strokeWidth?: number;
}) {
  const Icon = activeRegistry[name];
  return (
    <Icon
      aria-hidden={props["aria-label"] ? undefined : true}
      height={size}
      strokeWidth={strokeWidth}
      width={size}
      {...props}
    />
  );
}
