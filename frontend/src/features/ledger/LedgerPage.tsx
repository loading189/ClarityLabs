import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Drawer from "../../components/common/Drawer";
import PageHeader from "../../components/common/PageHeader";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { assertBusinessId } from "../../utils/businessId";
import { useFilters } from "../../app/filters/useFilters";
import { resolveDateRange } from "../../app/filters/filters";
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
import styles from "./LedgerPage.module.css";

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

export default function LedgerPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "LedgerPage");
  const [filters, setFilters] = useFilters();
  const { setDateRange, activeBusinessId, setActiveBusinessId } = useAppState();
  const [sidebarTab, setSidebarTab] = useState<"accounts" | "vendors">("accounts");

  const range = useMemo(() => resolveDateRange(filters), [filters]);
  useEffect(() => {
    setDateRange(range);
  }, [range.start, range.end, setDateRange]);
  useEffect(() => {
    if (businessId && activeBusinessId !== businessId) setActiveBusinessId(businessId);
  }, [activeBusinessId, businessId, setActiveBusinessId]);

  const selectedAccounts = useMemo(() => parseListParam(filters.account), [filters.account]);
  const selectedVendors = useMemo(() => parseListParam((filters as any).vendor), [filters]);

  const [ledger, setLedger] = useState<LedgerQueryResponse | null>(null);
  const [accounts, setAccounts] = useState<LedgerDimensionAccount[]>([]);
  const [vendors, setVendors] = useState<LedgerDimensionVendor[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<LedgerQueryRow | null>(null);

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
          search: filters.q,
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
  }, [businessId, filters.q, range.end, range.start, selectedAccounts.join("|"), selectedVendors.join("|")]);

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

  return (
    <div className={styles.page}>
      <PageHeader
        title="Ledger"
        subtitle="Deterministic proof layer for transactions, balances, and categorization."
        actions={<div>{ledger?.summary.row_count ?? 0} rows</div>}
      />

      <div className={styles.topFilters}>
        <select
          aria-label="Date preset"
          value={filters.window ?? "90"}
          onChange={(e) => setFilters({ window: e.target.value as any })}
        >
          <option value="30">Last 30d</option>
          <option value="90">Last 90d</option>
          <option value="365">Last 365d</option>
          <option value="custom">Custom</option>
        </select>
        <input
          aria-label="Search"
          placeholder="Search description/vendor/account"
          value={filters.q ?? ""}
          onChange={(e) => setFilters({ q: e.target.value || undefined })}
        />
        <div className={styles.chips}>
          {selectedAccounts.map((a) => (
            <button key={`a-${a}`} className={styles.chip} onClick={() => toggleAccount(a)}>{a} ✕</button>
          ))}
          {selectedVendors.map((v) => (
            <button key={`v-${v}`} className={styles.chip} onClick={() => toggleVendor(v)}>{v} ✕</button>
          ))}
        </div>
      </div>

      <div className={styles.layout}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarTabs}>
            <button onClick={() => setSidebarTab("accounts")}>Accounts</button>
            <button onClick={() => setSidebarTab("vendors")}>Vendors</button>
          </div>
          <div className={styles.sidebarList}>
            {sidebarTab === "accounts" &&
              accounts.map((item) => (
                <button key={item.account} className={styles.sidebarItem} onClick={() => toggleAccount(item.account)}>
                  <span>{item.label}</span>
                  <span>{item.count} · {money(item.total)}</span>
                </button>
              ))}
            {sidebarTab === "vendors" &&
              vendors.map((item) => (
                <button key={item.vendor} className={styles.sidebarItem} onClick={() => toggleVendor(item.vendor)}>
                  <span>{item.vendor}</span>
                  <span>{item.count} · {money(item.total)}</span>
                </button>
              ))}
          </div>
        </aside>

        <section className={styles.main}>
          {loading && <LoadingState label="Loading ledger…" />}
          {err && <ErrorState label={err} />}
          {!loading && !err && (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Date</th><th>Description</th><th>Vendor</th><th>Account</th><th>Amount</th><th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {(ledger?.rows ?? []).map((row) => (
                  <tr key={row.source_event_id} onClick={() => setSelected(row)}>
                    <td>{fmtDate(row.occurred_at)}</td>
                    <td>{row.description}</td>
                    <td>{row.vendor}</td>
                    <td>{row.account}</td>
                    <td>{money(row.amount)}</td>
                    <td>{money(row.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <Drawer open={Boolean(selected)} title="Transaction detail" onClose={() => setSelected(null)}>
        {selected && (
          <div>
            <div>{selected.description}</div>
            <div>{selected.vendor} · {selected.account}</div>
            <div>Amount: {money(selected.amount)}</div>
            <div>Balance: {money(selected.balance)}</div>
            <div>Categorization reason: {(selected as any).categorization_reason ?? "—"}</div>
            <Link to={`/app/${businessId}/signals?search=${encodeURIComponent(selected.source_event_id)}&has_ledger_anchors=true`}>
              Open related signals
            </Link>
          </div>
        )}
      </Drawer>
    </div>
  );
}
