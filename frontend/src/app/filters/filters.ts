export type DateWindow = "7" | "30" | "90" | "365" | "custom";

export type FilterState = {
  start?: string;
  end?: string;
  window?: DateWindow;
  account?: string;
  category?: string;
  vendor?: string;
  q?: string;
  direction?: "inflow" | "outflow";
  anchor_source_event_id?: string;
};

const FILTER_KEYS = [
  "start",
  "end",
  "window",
  "account",
  "category",
  "vendor",
  "q",
  "direction",
  "anchor_source_event_id",
] as const;

export type DemoDateRange = {
  start_at?: string | null;
  end_at?: string | null;
};

export const DEFAULT_WINDOW: DateWindow = "30";

export function parseFilters(params: URLSearchParams): FilterState {
  const windowParam = params.get("window");
  const windowValue =
    windowParam === "7" || windowParam === "30" || windowParam === "90" || windowParam === "365" || windowParam === "custom"
      ? windowParam
      : undefined;

  const directionParam = params.get("direction");
  const direction =
    directionParam === "inflow" || directionParam === "outflow" ? directionParam : undefined;

  return {
    start: params.get("start") ?? undefined,
    end: params.get("end") ?? undefined,
    window: windowValue,
    account: params.get("account") ?? undefined,
    category: params.get("category") ?? undefined,
    vendor: params.get("vendor") ?? undefined,
    q: params.get("q") ?? undefined,
    direction,
    anchor_source_event_id: params.get("anchor_source_event_id") ?? undefined,
  };
}

export function buildSearchParams(filters: FilterState) {
  const params = new URLSearchParams();
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  if (filters.window) params.set("window", filters.window);
  if (filters.account) params.set("account", filters.account);
  if (filters.category) params.set("category", filters.category);
  if (filters.vendor) params.set("vendor", filters.vendor);
  if (filters.q) params.set("q", filters.q);
  if (filters.direction) params.set("direction", filters.direction);
  if (filters.anchor_source_event_id) {
    params.set("anchor_source_event_id", filters.anchor_source_event_id);
  }
  return params;
}

export function applyFilterSearchParams(params: URLSearchParams, filters: FilterState) {
  const next = new URLSearchParams(params);
  FILTER_KEYS.forEach((key) => next.delete(key));
  const built = buildSearchParams(filters);
  built.forEach((value, key) => next.set(key, value));
  return next;
}

function formatDate(date: Date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function getDateRangeForWindow(window: DateWindow) {
  const days = Number(window);
  if (window === "custom") {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 90);
    return { start: formatDate(start), end: formatDate(end) };
  }
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - days);
  return { start: formatDate(start), end: formatDate(end) };
}

export function normalizeDateInput(value?: string | null) {
  if (!value) return undefined;
  return value.split("T")[0];
}

export function isValidIsoDate(value?: string | null) {
  if (!value) return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!year || !month || !day) return false;
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export function clampFiltersToRange(filters: FilterState, range: DemoDateRange) {
  const startAt = normalizeDateInput(range.start_at);
  const endAt = normalizeDateInput(range.end_at);
  if (!startAt || !endAt) return null;

  const currentStart = filters.start ?? startAt;
  const currentEnd = filters.end ?? endAt;
  let nextStart = currentStart < startAt ? startAt : currentStart;
  let nextEnd = currentEnd > endAt ? endAt : currentEnd;

  if (nextStart > nextEnd) {
    nextStart = startAt;
    nextEnd = endAt;
  }

  if (
    filters.start === nextStart &&
    filters.end === nextEnd &&
    filters.window === undefined
  ) {
    return null;
  }

  return {
    ...filters,
    start: nextStart,
    end: nextEnd,
    window: undefined,
  };
}

export function resolveDateRange(filters: FilterState) {
  if (
    filters.start &&
    filters.end &&
    isValidIsoDate(filters.start) &&
    isValidIsoDate(filters.end) &&
    filters.start <= filters.end
  ) {
    return { start: filters.start, end: filters.end, window: filters.window };
  }
  const window = filters.window ?? DEFAULT_WINDOW;
  const range = getDateRangeForWindow(window);
  return { ...range, window };
}

export function monthBounds(month: string) {
  const [year, monthIndex] = month.split("-").map(Number);
  if (!year || !monthIndex) return null;
  const start = new Date(Date.UTC(year, monthIndex - 1, 1));
  const end = new Date(Date.UTC(year, monthIndex, 0));
  return {
    start: formatDate(start),
    end: formatDate(end),
  };
}

export function monthsBetween(start: string, end: string) {
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) return 12;
  const months =
    (endDate.getFullYear() - startDate.getFullYear()) * 12 +
    (endDate.getMonth() - startDate.getMonth()) +
    1;
  return Math.max(3, months);
}
