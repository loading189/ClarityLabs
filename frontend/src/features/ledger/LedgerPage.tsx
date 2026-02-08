import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import { ErrorState } from "../../components/common/DataState";
import { assertBusinessId } from "../../utils/businessId";
import { useFilters } from "../../app/filters/useFilters";
import { resolveDateRange, type DateWindow } from "../../app/filters/filters";
import { useAppState } from "../../app/state/appState";
import {
  fetchLedgerAccountDimensions,
  fetchLedgerQuery,
  fetchLedgerVendorDimensions,
  type LedgerDimensionAccount,
  type LedgerDimensionVendor,
  type LedgerQueryResponse,
  type LedgerQueryRow,
} from "../../api/ledger";
import TransactionDetailDrawer from "../../components/transactions/TransactionDetailDrawer";
import styles from "./LedgerPage.module.css";

const SIDEBAR_TOP_N = 12;
const COLUMN_STORAGE_KEY = "ledger-column-visibility";
const ALL_COLUMNS = ["date", "description", "account", "vendor", "category", "amount", "balance"] as const;
type ColumnKey = (typeof ALL_COLUMNS)[number];

type ColumnVisibility = Record<ColumnKey, boolean>;
const DEFAULT_VISIBILITY: ColumnVisibility = {
  date: true,
  description: true,
  account: true,
  vendor: true,
  category: true,
  amount: true,
  balance: true,
};

function money(value: number) {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function fmtDate(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString();
}

function parseListParam(value?: string) {
  if (!value) return [] as string[];
  return value.split(",").map((v) => v.trim()).filter(Boolean);
}

function setListParam(values: string[]) {
  if (!values.length) return undefined;
  return values.slice().sort((a, b) => a.localeCompare(b)).join(",");
}

function readColumnVisibility(): ColumnVisibility {
  try {
    const raw = localStorage.getItem(COLUMN_STORAGE_KEY);
    if (!raw) return DEFAULT_VISIBILITY;
    const parsed = JSON.parse(raw) as Partial<ColumnVisibility>;
    return {
      date: parsed.date ?? true,
      description: parsed.description ?? true,
      account: parsed.account ?? true,
      vendor: parsed.vendor ?? true,
      category: parsed.category ?? true,
      amount: parsed.amount ?? true,
      balance: parsed.balance ?? true,
    };
  } catch {
    return DEFAULT_VISIBILITY;
  }
}

const DATE_PRESETS: Array<{ value: DateWindow | "this_month" | "last_month"; label: string }> = [
  { value: "7", label: "Last 7" },
  { value: "30", label: "Last 30" },
  { value: "90", label: "Last 90" },
  { value: "this_month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "custom", label: "Custom" },
];

function monthStartEnd(offsetMonths = 0) {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth() + offsetMonths, 1);
  const end = new Date(now.getFullYear(), now.getMonth() + offsetMonths + 1, 0);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end) };
}

export default function LedgerPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "LedgerPage");
  const [filters, setFilters] = useFilters();
  const { setDateRange, activeBusinessId, setActiveBusinessId, dataVersion } = useAppState();
  const [sidebarTab, setSidebarTab] = useState<"accounts" | "vendors">("accounts");
  const [sidebarSearch, setSidebarSearch] = useState({ accounts: "", vendors: "" });
  const [expandedList, setExpandedList] = useState({ accounts: false, vendors: false });
  const [searchDraft, setSearchDraft] = useState(filters.q ?? "");
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibility>(() => readColumnVisibility());

  const range = useMemo(() => resolveDateRange(filters), [filters]);
  useEffect(() => {
    setDateRange(range);
  }, [range.start, range.end, setDateRange]);
  useEffect(() => {
    if (businessId && activeBusinessId !== businessId) setActiveBusinessId(businessId);
  }, [activeBusinessId, businessId, setActiveBusinessId]);

  const selectedAccounts = useMemo(() => parseListParam(filters.account), [filters.account]);
  const selectedVendors = useMemo(() => parseListParam((filters as any).vendor), [filters]);
  const selectedCategories = useMemo(() => parseListParam(filters.category), [filters.category]);
  const highlightSourceEventIds = useMemo(
    () => parseListParam(filters.highlight_source_event_ids),
    [filters.highlight_source_event_ids]
  );

  const [ledger, setLedger] = useState<LedgerQueryResponse | null>(null);
  const [accounts, setAccounts] = useState<LedgerDimensionAccount[]>([]);
  const [vendors, setVendors] = useState<LedgerDimensionVendor[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [drawerSourceEventId, setDrawerSourceEventId] = useState<string | null>(null);
  const [highlightSourceEventId, setHighlightSourceEventId] = useState<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLTableRowElement | null>());
  // Ledger anchor semantics: anchor_source_event_id highlights + scrolls to the row.
  const anchorSourceEventId = filters.anchor_source_event_id ?? null;

  useEffect(() => {
    setSearchDraft(filters.q ?? "");
  }, [filters.q]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const normalized = searchDraft.trim();
      const next = normalized || undefined;
      if (next !== (filters.q ?? undefined)) {
        setFilters((f) => ({ ...f, q: next }));
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [filters.q, searchDraft, setFilters]);

  useEffect(() => {
    try {
      localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(columnVisibility));
    } catch {
      // noop
    }
  }, [columnVisibility]);

  const closeDrawer = useCallback(() => {
    setDrawerSourceEventId(null);
    setFilters((current) => ({ ...current, anchor_source_event_id: undefined }));
  }, [setFilters]);

  useEffect(() => {
    if (!drawerSourceEventId) return;
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDrawer();
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [closeDrawer, drawerSourceEventId]);

  useEffect(() => {
    const c = new AbortController();
    let alive = true;
    setLoading(true);
    setErr(null);
    Promise.all([
      fetchLedgerQuery(
        businessId,
        {
          start_date: range.start,
          end_date: range.end,
          account: selectedAccounts,
          vendor: selectedVendors,
          category: selectedCategories,
          search: filters.q,
          direction: filters.direction,
          highlight_source_event_id: highlightSourceEventIds.length
            ? highlightSourceEventIds
            : anchorSourceEventId
              ? [anchorSourceEventId]
              : undefined,
          limit: 500,
          offset: 0,
        },
        c.signal
      ),
      fetchLedgerAccountDimensions(businessId, { start_date: range.start, end_date: range.end }, c.signal),
      fetchLedgerVendorDimensions(businessId, { start_date: range.start, end_date: range.end }, c.signal),
    ])
      .then(([ledgerData, accountData, vendorData]) => {
        if (!alive) return;
        setLedger(ledgerData);
        setAccounts(accountData);
        setVendors(vendorData);
      })
      .catch((e: any) => {
        if (!alive) return;
        setErr(e?.message ?? "Failed to load ledger");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
      c.abort();
    };
  }, [
    businessId,
    dataVersion,
    filters.direction,
    filters.q,
    range.end,
    range.start,
    selectedAccounts.join("|"),
    selectedCategories.join("|"),
    selectedVendors.join("|"),
    highlightSourceEventIds.join("|"),
    anchorSourceEventId,
  ]);

  const visibleRows = useMemo(() => {
    const rows = ledger?.rows ?? [];
    if (filters.category === "uncategorized") {
      return rows.filter((row) => !row.category || row.category.toLowerCase() === "uncategorized");
    }
    return rows;
  }, [filters.category, ledger?.rows]);

  useEffect(() => {
    if (!anchorSourceEventId) return;
    const match = visibleRows.find((row) => row.source_event_id === anchorSourceEventId);
    if (!match) return;
    setHighlightSourceEventId(anchorSourceEventId);
    setDrawerSourceEventId(anchorSourceEventId);
    const node = rowRefs.current.get(anchorSourceEventId);
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [anchorSourceEventId, visibleRows]);

  useEffect(() => {
    if (anchorSourceEventId || highlightSourceEventIds.length === 0) return;
    const match = visibleRows.find((row) => row.is_highlighted);
    if (!match) return;
    const node = rowRefs.current.get(match.source_event_id);
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [anchorSourceEventId, highlightSourceEventIds.length, visibleRows]);

  useEffect(() => {
    if (!anchorSourceEventId) {
      setHighlightSourceEventId(null);
      setDrawerSourceEventId(null);
    }
  }, [anchorSourceEventId]);

  const filteredAccounts = useMemo(() => {
    const q = sidebarSearch.accounts.trim().toLowerCase();
    if (!q) return accounts;
    return accounts.filter((item) => `${item.label} ${item.account}`.toLowerCase().includes(q));
  }, [accounts, sidebarSearch.accounts]);

  const filteredVendors = useMemo(() => {
    const q = sidebarSearch.vendors.trim().toLowerCase();
    if (!q) return vendors;
    return vendors.filter((item) => item.vendor.toLowerCase().includes(q));
  }, [sidebarSearch.vendors, vendors]);

  function toggleAccount(label: string) {
    const next = selectedAccounts.includes(label)
      ? selectedAccounts.filter((v) => v !== label)
      : [...selectedAccounts, label];
    setFilters((f) => ({ ...f, account: setListParam(next) }));
  }

  function toggleVendor(label: string) {
    const next = selectedVendors.includes(label)
      ? selectedVendors.filter((v) => v !== label)
      : [...selectedVendors, label];
    setFilters((f) => ({ ...f, vendor: setListParam(next) } as any));
  }

  function updateDatePreset(value: string) {
    if (value === "this_month") {
      const next = monthStartEnd(0);
      setFilters((f) => ({ ...f, window: "custom", start: next.start, end: next.end }));
      return;
    }
    if (value === "last_month") {
      const next = monthStartEnd(-1);
      setFilters((f) => ({ ...f, window: "custom", start: next.start, end: next.end }));
      return;
    }
    setFilters((f) => ({ ...f, window: value as DateWindow }));
  }

  function removeChip(key: "account" | "vendor" | "q" | "category", value?: string) {
    if (key === "account" && value) toggleAccount(value);
    if (key === "vendor" && value) toggleVendor(value);
    if (key === "q") setFilters((f) => ({ ...f, q: undefined }));
    if (key === "category") setFilters((f) => ({ ...f, category: undefined }));
  }

  const activeFilterCount = selectedAccounts.length + selectedVendors.length + (filters.q ? 1 : 0) + (filters.category ? 1 : 0);

  const currentPresetValue =
    filters.window === "7" || filters.window === "30" || filters.window === "90" || filters.window === "custom"
      ? filters.window
      : "90";

  return (
    <div className={styles.page}>
      <PageHeader
        title="Ledger"
        subtitle="Deterministic proof layer for transactions, balances, and categorization."
        actions={<div className={styles.headerMeta}>{visibleRows.length} rows</div>}
      />

      <div className={styles.topFilters}>
        <div className={styles.filterGroup}>
          <label className={styles.label} htmlFor="ledger-date-preset">Date</label>
          <select
            id="ledger-date-preset"
            className={styles.select}
            aria-label="Date preset"
            value={currentPresetValue}
            onChange={(e) => updateDatePreset(e.target.value)}
          >
            {DATE_PRESETS.map((preset) => (
              <option key={preset.value} value={preset.value}>{preset.label}</option>
            ))}
          </select>
          {currentPresetValue === "custom" && (
            <>
              <input
                className={styles.input}
                type="date"
                aria-label="Start date"
                value={filters.start ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, start: e.target.value || undefined, window: "custom" }))}
              />
              <input
                className={styles.input}
                type="date"
                aria-label="End date"
                value={filters.end ?? ""}
                onChange={(e) => setFilters((f) => ({ ...f, end: e.target.value || undefined, window: "custom" }))}
              />
            </>
          )}
        </div>

        <div className={styles.filterGroup}>
          <input
            className={styles.input}
            aria-label="Search"
            placeholder="Search description/vendor/account"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
          />
          <button
            className={`${styles.button} ${filters.category === "uncategorized" ? styles.buttonActive : ""}`}
            type="button"
            onClick={() => setFilters((f) => ({ ...f, category: f.category === "uncategorized" ? undefined : "uncategorized" }))}
          >
            Uncategorized only
          </button>
          <select
            className={styles.select}
            aria-label="Row density"
            value={density}
            onChange={(e) => setDensity(e.target.value as "comfortable" | "compact")}
          >
            <option value="comfortable">Comfortable rows</option>
            <option value="compact">Compact rows</option>
          </select>
          <details className={styles.columnMenu}>
            <summary>Columns</summary>
            <div className={styles.columnList}>
              {ALL_COLUMNS.map((column) => (
                <label key={column}>
                  <input
                    type="checkbox"
                    checked={columnVisibility[column]}
                    onChange={() => setColumnVisibility((prev) => ({ ...prev, [column]: !prev[column] }))}
                  />
                  {column}
                </label>
              ))}
            </div>
          </details>
          <button
            className={styles.button}
            onClick={() => setFilters({ window: "90", account: undefined, vendor: undefined, q: undefined, category: undefined })}
            disabled={activeFilterCount === 0}
            type="button"
          >
            Reset all
          </button>
        </div>

        <div className={styles.chips}>
          {selectedAccounts.map((a) => (
            <button key={`a-${a}`} className={styles.chip} onClick={() => removeChip("account", a)}>{a} ✕</button>
          ))}
          {selectedVendors.map((v) => (
            <button key={`v-${v}`} className={styles.chip} onClick={() => removeChip("vendor", v)}>{v} ✕</button>
          ))}
          {filters.q && <button className={styles.chip} onClick={() => removeChip("q")}>Search: {filters.q} ✕</button>}
          {filters.category === "uncategorized" && <button className={styles.chip} onClick={() => removeChip("category")}>Uncategorized ✕</button>}
        </div>
      </div>

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <div className={styles.segmented} role="tablist" aria-label="Ledger dimensions">
            <button className={sidebarTab === "accounts" ? styles.segmentedActive : ""} onClick={() => setSidebarTab("accounts")}>Accounts</button>
            <button className={sidebarTab === "vendors" ? styles.segmentedActive : ""} onClick={() => setSidebarTab("vendors")}>Vendors</button>
          </div>

          <div className={styles.sidebarSearchRow}>
            <input
              className={styles.input}
              aria-label="Sidebar search"
              placeholder={`Search ${sidebarTab}`}
              value={sidebarSearch[sidebarTab]}
              onChange={(e) => setSidebarSearch((prev) => ({ ...prev, [sidebarTab]: e.target.value }))}
            />
            <button
              className={styles.buttonGhost}
              type="button"
              onClick={() => sidebarTab === "accounts" ? setFilters((f) => ({ ...f, account: undefined })) : setFilters((f) => ({ ...f, vendor: undefined } as any))}
            >
              Clear
            </button>
          </div>

          <div className={styles.sidebarList}>
            {loading && Array.from({ length: 8 }).map((_, idx) => <div key={idx} className={styles.skeletonItem} />)}
            {!loading && sidebarTab === "accounts" && (expandedList.accounts ? filteredAccounts : filteredAccounts.slice(0, SIDEBAR_TOP_N)).map((item) => (
              <button
                key={item.account}
                className={`${styles.sidebarItem} ${selectedAccounts.includes(item.account) ? styles.sidebarItemActive : ""}`}
                onClick={() => toggleAccount(item.account)}
              >
                <span>{item.label}</span>
                <span className={styles.badge}>{item.count}</span>
              </button>
            ))}
            {!loading && sidebarTab === "vendors" && (expandedList.vendors ? filteredVendors : filteredVendors.slice(0, SIDEBAR_TOP_N)).map((item) => (
              <button
                key={item.vendor}
                className={`${styles.sidebarItem} ${selectedVendors.includes(item.vendor) ? styles.sidebarItemActive : ""}`}
                onClick={() => toggleVendor(item.vendor)}
              >
                <span>{item.vendor}</span>
                <span className={styles.badge}>{item.count}</span>
              </button>
            ))}
          </div>
          {!loading && sidebarTab === "accounts" && filteredAccounts.length > SIDEBAR_TOP_N && (
            <button className={styles.buttonGhost} onClick={() => setExpandedList((s) => ({ ...s, accounts: !s.accounts }))}>
              {expandedList.accounts ? "Show less" : "Show more"}
            </button>
          )}
          {!loading && sidebarTab === "vendors" && filteredVendors.length > SIDEBAR_TOP_N && (
            <button className={styles.buttonGhost} onClick={() => setExpandedList((s) => ({ ...s, vendors: !s.vendors }))}>
              {expandedList.vendors ? "Show less" : "Show more"}
            </button>
          )}
        </aside>

        <section className={styles.main}>
          {err && <ErrorState label={err} />}
          {!err && (
            <div className={styles.tableWrap}>
              <table className={`${styles.table} ${density === "compact" ? styles.tableCompact : ""}`}>
                <thead>
                  <tr>
                    {columnVisibility.date && <th className={styles.stickyLeft}>Date</th>}
                    {columnVisibility.description && <th className={styles.stickySecond}>Description</th>}
                    {columnVisibility.account && <th>Account</th>}
                    {columnVisibility.vendor && <th>Vendor</th>}
                    {columnVisibility.category && <th>Category</th>}
                    {columnVisibility.amount && <th className={styles.numeric}>Amount</th>}
                    {columnVisibility.balance && <th className={styles.numeric}>Balance</th>}
                  </tr>
                </thead>
                <tbody>
                  {loading && Array.from({ length: 12 }).map((_, idx) => (
                    <tr key={`s-${idx}`}><td colSpan={7}><div className={styles.skeletonRow} /></td></tr>
                  ))}
                  {!loading && visibleRows.map((row) => (
                    <tr
                      key={row.source_event_id}
                      ref={(node) => rowRefs.current.set(row.source_event_id, node)}
                      className={[
                        row.is_highlighted ? styles.rowHighlighted : "",
                        (drawerSourceEventId ?? highlightSourceEventId) === row.source_event_id ? styles.rowSelected : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      onClick={() => {
                        setFilters((current) => {
                          if (current.anchor_source_event_id === row.source_event_id) {
                            return current;
                          }
                          return { ...current, anchor_source_event_id: row.source_event_id };
                        });
                        setHighlightSourceEventId(row.source_event_id);
                        setDrawerSourceEventId(row.source_event_id);
                      }}
                    >
                      {columnVisibility.date && <td className={styles.stickyLeft}>{fmtDate(row.occurred_at)}</td>}
                      {columnVisibility.description && <td className={styles.stickySecond}>{row.description}</td>}
                      {columnVisibility.account && <td>{row.account}</td>}
                      {columnVisibility.vendor && <td>{row.vendor || "—"}</td>}
                      {columnVisibility.category && <td>{row.category || "Uncategorized"}</td>}
                      {columnVisibility.amount && <td className={`${styles.numeric} ${row.amount < 0 ? styles.negative : ""}`}>{money(row.amount)}</td>}
                      {columnVisibility.balance && <td className={styles.numeric}>{money(row.balance)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <TransactionDetailDrawer
        open={Boolean(drawerSourceEventId)}
        businessId={businessId}
        sourceEventId={drawerSourceEventId}
        onClose={closeDrawer}
      />
    </div>
  );
}
