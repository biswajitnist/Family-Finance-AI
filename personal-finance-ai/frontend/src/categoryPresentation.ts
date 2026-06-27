import type { IconName } from "./icons/IconRegistry";
import type { Category } from "./types";

export const CATEGORY_ICON_OPTIONS: Array<{ value: IconName; label: string }> = [
  { value: "category", label: "General" },
  { value: "grocery", label: "Groceries" },
  { value: "shopping", label: "Shopping" },
  { value: "utilities", label: "Utilities" },
  { value: "transport", label: "Transport" },
  { value: "restaurant", label: "Restaurants" },
  { value: "health", label: "Healthcare" },
  { value: "education", label: "Education" },
  { value: "travel", label: "Travel" },
  { value: "sports", label: "Sports" },
  { value: "subscription", label: "Subscriptions" },
  { value: "loans", label: "Loan repayment" },
  { value: "insurance", label: "Insurance" },
  { value: "income", label: "Income" },
  { value: "investments", label: "Investments" },
  { value: "properties", label: "Property" },
  { value: "institution", label: "Institution" },
  { value: "sparkles", label: "Bonus" },
];

export const CATEGORY_COLOR_OPTIONS = [
  { value: "green", label: "Green" },
  { value: "blue", label: "Blue" },
  { value: "amber", label: "Amber" },
  { value: "orange", label: "Orange" },
  { value: "red", label: "Red" },
  { value: "violet", label: "Violet" },
  { value: "teal", label: "Teal" },
  { value: "slate", label: "Slate" },
];

const validIcons = new Set(CATEGORY_ICON_OPTIONS.map((item) => item.value));

export function categoryPresentation(
  category: Pick<Category, "name"> & Partial<Pick<Category, "icon" | "color">>,
) {
  const name = category.name.toLowerCase();
  let fallback: IconName = "category";
  if (name.includes("loan")) fallback = "loans";
  else if (name.includes("grocery") || name.includes("food")) fallback = "grocery";
  else if (name.includes("shop")) fallback = "shopping";
  else if (name.includes("utilit")) fallback = "utilities";
  else if (name.includes("transport")) fallback = "transport";
  else if (name.includes("restaurant")) fallback = "restaurant";
  else if (name.includes("health")) fallback = "health";
  else if (name.includes("education")) fallback = "education";
  else if (name.includes("travel")) fallback = "travel";
  else if (name.includes("sport")) fallback = "sports";
  else if (name.includes("subscription")) fallback = "subscription";
  else if (name.includes("insurance")) fallback = "insurance";
  else if (name.includes("salary") || name.includes("income")) fallback = "income";
  return {
    icon:
      category.icon && validIcons.has(category.icon as IconName)
        ? (category.icon as IconName)
        : fallback,
    color: category.color || "green",
  };
}
