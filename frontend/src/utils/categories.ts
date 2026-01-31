import type { CategoryOut } from "../api/categorize";

export function hasValidCategoryMapping(category?: CategoryOut | null): boolean {
  if (!category) return false;
  if (!category.account_id) return false;
  const name = (category.name || "").trim().toLowerCase();
  const systemKey = (category.system_key || "").trim().toLowerCase();
  if (name === "uncategorized" || systemKey === "uncategorized") return false;
  return true;
}
