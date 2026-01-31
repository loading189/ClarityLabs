export type DateWindow = "7" | "30" | "90";

export type FilterState = {
  start?: string;
  end?: string;
  window?: DateWindow;
  account?: string;
  category?: string;
  q?: string;
  direction?: "inflow" | "outflow";
};

export type DemoDateRange = {
  start_at?: string | null;
  end_at?: string | null;
};

export const DEFAULT_WINDOW: DateWindow = "30";

export function parseFilters(params: URLSearchParams): FilterState {
  const windowParam = params.get("window");
  const windowValue =
    windowParam === "7" || windowParam === "30" || windowParam === "90"
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
    q: params.get("q") ?? undefined,
    direction,
  };
}

export function buildSearchParams(filters: FilterState) {
  const params = new URLSearchParams();
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  if (filters.window) params.set("window", filters.window);
  if (filters.account) params.set("account", filters.account);
  if (filters.category) params.set("category", filters.category);
  if (filters.q) params.set("q", filters.q);
  if (filters.direction) params.set("direction", filters.direction);
  return params;
}

function formatDate(date: Date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function getDateRangeForWindow(window: DateWindow) {
  const days = Number(window);
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - days);
  return { start: formatDate(start), end: formatDate(end) };
}

export function normalizeDateInput(value?: string | null) {
  if (!value) return undefined;
  return value.split("T")[0];
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
  if (filters.start && filters.end) {
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
