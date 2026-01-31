const STOPWORDS = new Set([
  "pos",
  "ach",
  "debit",
  "credit",
  "card",
  "purchase",
  "payment",
  "pmt",
  "online",
  "web",
  "www",
  "inc",
  "llc",
  "co",
  "company",
  "corp",
  "corporation",
  "the",
]);

function toNormalizedTokens(value: string) {
  const normalized = (value || "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s*]/g, " ")
    .replace(/\d+/g, " ")
    .replace(/\*/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  return normalized
    .split(" ")
    .filter((token) => token && !STOPWORDS.has(token))
    .slice(0, 6);
}

export function normalizeVendorKey(value?: string | null): string {
  if (!value) return "";
  return toNormalizedTokens(value).join(" ");
}

export function normalizeVendorDisplay(
  value?: string | null,
  canonical?: string | null
): string {
  const trimmed = (value || "").trim();
  const canonicalTrimmed = (canonical || "").trim();
  if (canonicalTrimmed) return canonicalTrimmed;
  if (trimmed) return trimmed;
  return "Unknown vendor";
}
