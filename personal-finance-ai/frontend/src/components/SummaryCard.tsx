import { AppIcon, type IconName } from "../icons/IconRegistry";

interface SummaryCardProps {
  label: string;
  value: string;
  tone?: "default" | "positive" | "negative";
  detail?: string;
  icon?: IconName;
  accent?: "blue" | "green" | "red" | "amber";
}

export function SummaryCard({
  label,
  value,
  tone = "default",
  detail,
  icon,
  accent = "green",
}: SummaryCardProps) {
  return (
    <article className={`summary-card ${tone} accent-${accent}`}>
      <div className="summary-card-label">
        {icon && (
          <span className="summary-card-icon">
            <AppIcon name={icon} size={17} />
          </span>
        )}
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      {detail && (
        <small
          className={
            detail.startsWith("↑")
              ? "trend-up"
              : detail.startsWith("↓")
                ? "trend-down"
                : ""
          }
        >
          {detail}
        </small>
      )}
    </article>
  );
}
