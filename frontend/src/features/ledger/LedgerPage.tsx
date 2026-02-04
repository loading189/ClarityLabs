import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import FilterBar from "../../components/common/FilterBar";
import PageHeader from "../../components/common/PageHeader";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import Table, { type TableColumn } from "../../components/common/Table";
import Drawer from "../../components/common/Drawer";
import { useFilters } from "../../app/filters/useFilters";
import { resolveDateRange } from "../../app/filters/filters";
import { useDemoDateRange } from "../../app/filters/useDemoDateRange";
import { useDemoDashboard } from "../../hooks/useDemoDashboard";
import { useLedgerLines } from "./useLedgerLines";
import type { LedgerLine } from "../../api/ledger";
import { assertBusinessId } from "../../utils/businessId";
import { useAppState } from "../../app/state/appState";
import styles from "./LedgerPage.module.css";
import { getBrainVendors, type BrainVendor } from "../../api/categorize";
import { normalizeVendorDisplay, normalizeVendorKey } from "../../utils/vendors";
import { fetchSignals, type Signal } from "../../api/signals";
import { isValidIsoDate } from "../../app/filters/filters";

function formatMoney(value: number) {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })}`;
}

function formatDateTime(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function uniqueOptions(values: Array<string | null | undefined>) {
  return Array.from(
    new Set(values.filter((value): value is string => Boolean(value && value.trim())))
  ).map((value) => ({ label: value, value }));
}

export default function LedgerPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "LedgerPage");

  const [filters, setFilters] = useFilters();
  const { data: dashboard } = useDemoDashboard();
  const { dateRange, setDateRange, dataVersion, activeBusinessId, setActiveBusinessId } = useAppState();

  // Keep demo date range in sync with seeded metadata.
  useDemoDateRange(filters, setFilters, dashboard?.metadata);

  // Resolve date range from URL filters, then propagate to global app state.
  const range = useMemo(() => resolveDateRange(filters), [filters]);

  useEffect(() => {
    setDateRange(range);
  }, [range.start, range.end, setDateRange]);

  // Keep global active business in sync with the route param.
  useEffect(() => {
    if (businessId && activeBusinessId !== businessId) {
      setActiveBusinessId(businessId);
    }
  }, [activeBusinessId, businessId, setActiveBusinessId]);

  const { lines, loading, err } = useLedgerLines();

  // Vendor brain mappings (canonicalization).
  const [brainVendors, setBrainVendors] = useState<BrainVendor[]>([]);
  const [vendorErr, setVendorErr] = useState<string | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [signalsMeta, setSignalsMeta] = useState<Record<string, unknown>>({});
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [signalsErr, setSignalsErr] = useState<string | null>(null);

  // Fetch vendor mappings (brain vendors) when business or dataVersion changes.
  // NOTE: avoid depending on full dateRange object to reduce re-fetch churn.
  useEffect(() => {
    setVendorErr(null);
    getBrainVendors(businessId)
      .then((vendors) => setBrainVendors(vendors))
      .catch((e: any) => {
        console.error("[ledger] vendor fetch failed", {
          businessId,
          dateRange,
          url: `/categorize/business/${businessId}/brain/vendors`,
          error: e?.message ?? e,
        });
        setVendorErr(e?.message ?? "Failed to load vendor mappings");
      });
  }, [businessId, dataVersion]); // intentionally not dateRange

  useEffect(() => {
    if (!businessId) {
      setSignals([]);
      setSignalsMeta({});
      setSignalsErr("Select a business to load signals.");
      return;
    }
    if (!dateRange.start || !dateRange.end) {
      setSignals([]);
      setSignalsMeta({});
      setSignalsErr("Select a date range to load signals.");
      return;
    }
    if (!isValidIsoDate(dateRange.start) || !isValidIsoDate(dateRange.end)) {
      setSignals([]);
      setSignalsMeta({});
      setSignalsErr(`Invalid date range: ${dateRange.start} → ${dateRange.end}`);
      return;
    }

    const controller = new AbortController();
    let alive = true;

    setSignalsLoading(true);
    setSignalsErr(null);

    fetchSignals(
      businessId,
      { start_date: dateRange.start, end_date: dateRange.end },
      controller.signal
    )
      .then((payload) => {
        if (!alive) return;
        setSignals(payload.signals ?? []);
        setSignalsMeta(payload.meta ?? {});
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (e instanceof Error) setSignalsErr(e.message);
        else setSignalsErr("Failed to load signals");
      })
      .finally(() => {
        if (!alive) return;
        setSignalsLoading(false);
      });

    return () => {
      alive = false;
      controller.abort();
    };
  }, [businessId, dateRange.end, dateRange.start, dataVersion]);

  const vendorsByAlias = useMemo(() => {
    const map = new Map<string, BrainVendor>();
    brainVendors.forEach((vendor) => {
      vendor.alias_keys?.forEach((alias) => map.set(alias, vendor));
    });
    return map;
  }, [brainVendors]);

  // UI state
  const [selected, setSelected] = useState<LedgerLine | null>(null);
  const [page, setPage] = useState(1);




  // Options derived from the current dataset (not filtered) — keeps filter UX stable.
  const accounts = useMemo(
    () => uniqueOptions(lines.map((line) => line.account_name)),
    [lines]
  );
  const categories = useMemo(
    () => uniqueOptions(lines.map((line) => line.category_name)),
    [lines]
  );

  // Filter + sort (client-side)
  const filtered = useMemo(() => {
    const query = (filters.q ?? "").toLowerCase().trim();

    return lines
      .filter((line) => {
        if (filters.account && line.account_name !== filters.account) return false;
        if (filters.category && line.category_name !== filters.category) return false;
        if (filters.direction && line.direction !== filters.direction) return false;

        if (query) {
          const haystack = `${line.description ?? ""} ${line.counterparty_hint ?? ""}`.toLowerCase();
          if (!haystack.includes(query)) return false;
        }

        return true;
      })
      .sort((a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime());
  }, [filters.account, filters.category, filters.direction, filters.q, lines]);

  // Reset pagination when filtered result set changes (prevents “blank page” at end)
  useEffect(() => {
    setPage(1);
  }, [filters.account, filters.category, filters.direction, filters.q]);

  const pageSize = 50;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const paged = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const columns: Array<TableColumn<LedgerLine>> = useMemo(
    () => [
      {
        key: "occurred_at",
        header: "Date/Time",
        render: (row) => formatDateTime(row.occurred_at),
      },
      {
        key: "description",
        header: "Description",
        render: (row) => {
          const raw = row.counterparty_hint ?? row.description ?? "";
          const key = normalizeVendorKey(raw);
          const canonical = vendorsByAlias.get(key)?.canonical_name;

          return (
            <div className={styles.descriptionCell}>
              <div className={styles.descriptionTitle}>{row.description ?? "—"}</div>
              <div className={styles.descriptionMeta}>
                {normalizeVendorDisplay(raw, canonical)}
              </div>
            </div>
          );
        },
      },
      {
        key: "account",
        header: "Account",
        render: (row) => row.account_name ?? "—",
      },
      {
        key: "direction",
        header: "Direction",
        render: (row) => (
          <span className={row.direction === "inflow" ? styles.inflow : styles.outflow}>
            {row.direction}
          </span>
        ),
      },
      {
        key: "amount",
        header: "Amount",
        align: "right",
        render: (row) => formatMoney(row.signed_amount),
      },
      {
        key: "category",
        header: "Category",
        render: (row) => row.category_name ?? "Needs review",
      },
      {
        key: "confidence",
        header: "Confidence",
        render: (row) =>
          row.categorization?.confidence != null
            ? `${Math.round(row.categorization.confidence * 100)}%`
            : "Needs review",
      },
    ],
    [vendorsByAlias]
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title="Ledger"
        subtitle="Source-of-truth timeline with filters, search, and transaction drilldowns."
        actions={
          <div className={styles.summary}>
            <span>
              {dateRange.start} → {dateRange.end}
            </span>
            <span>{filtered.length} results</span>
          </div>
        }
      />

      <FilterBar
        filters={filters}
        onChange={(updates) => {
          setFilters(updates);
        }}
        accounts={accounts}
        categories={categories}
        showDirection
      />

      <section className={styles.signalsSection}>
        <div className={styles.signalsHeader}>
          <div>
            <div className={styles.signalsTitle}>Signals</div>
            <div className={styles.signalsSubtitle}>
              Deterministic alerts for the selected business and date window.
            </div>
          </div>
          {signalsMeta?.["reason"] && (
            <div className={styles.signalsMeta}>{String(signalsMeta["reason"])}</div>
          )}
        </div>

        {signalsLoading && <LoadingState label="Loading signals…" />}
        {signalsErr && <ErrorState label={`Signals unavailable: ${signalsErr}`} />}

        {!signalsLoading && !signalsErr && (
          <div className={styles.signalsGrid}>
            {signals.length === 0 && (
              <div className={styles.signalsEmpty}>No signals available for this window.</div>
            )}
            {signals.slice(0, 8).map((signal) => (
              <div key={signal.id} className={styles.signalCard}>
                <div className={styles.signalHeader}>
                  <span className={styles.signalType}>{signal.type}</span>
                  <span className={`${styles.signalSeverity} ${styles[signal.severity]}`}>
                    {signal.severity}
                  </span>
                </div>
                <div className={styles.signalBody}>
                  <div className={styles.signalMetric}>
                    <span>Baseline</span>
                    <strong>{signal.baseline_value ?? "—"}</strong>
                  </div>
                  <div className={styles.signalMetric}>
                    <span>Current</span>
                    <strong>{signal.current_value ?? "—"}</strong>
                  </div>
                  <div className={styles.signalMetric}>
                    <span>Delta</span>
                    <strong>{signal.delta ?? "—"}</strong>
                  </div>
                </div>
                <div className={styles.signalExplanation}>
                  {String((signal.explanation_seed as Record<string, unknown>)?.summary ?? "—")}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {loading && <LoadingState label="Loading ledger lines…" />}
      {err && <ErrorState label={`Failed to load ledger: ${err}`} />}
      {vendorErr && <ErrorState label={`Failed to load vendor mappings: ${vendorErr}`} />}

      {!loading && !err && (
        <>
          <Table
            columns={columns}
            rows={paged}
            getRowId={(row) => row.source_event_id}
            onRowClick={(row) => setSelected(row)}
            emptyMessage="No ledger lines match these filters."
            rowActions={(row) => (
              <button
                type="button"
                className={styles.rowAction}
                onClick={(event) => {
                  event.stopPropagation();
                  setSelected(row);
                }}
              >
                View
              </button>
            )}
          />

          <div className={styles.pagination}>
            <button
              type="button"
              className={styles.pageButton}
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
            >
              Prev
            </button>
            <span>
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              className={styles.pageButton}
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={currentPage >= totalPages}
            >
              Next
            </button>
          </div>
        </>
      )}

      <Drawer open={Boolean(selected)} title="Transaction detail" onClose={() => setSelected(null)}>
        {selected && (
          <>
            <div className={styles.drawerBlock}>
              <div className={styles.drawerLabel}>Occurred at</div>
              <div>{formatDateTime(selected.occurred_at)}</div>
            </div>

            <div className={styles.drawerBlock}>
              <div className={styles.drawerLabel}>Description</div>
              <div>{selected.description ?? "—"}</div>
              <div className={styles.drawerMeta}>Source ID: {selected.source_event_id}</div>
            </div>

            <div className={styles.drawerGrid}>
              <div>
                <div className={styles.drawerLabel}>Account</div>
                <div>{selected.account_name ?? "—"}</div>
              </div>
              <div>
                <div className={styles.drawerLabel}>Direction</div>
                <div>{selected.direction}</div>
              </div>
              <div>
                <div className={styles.drawerLabel}>Amount</div>
                <div>{formatMoney(selected.signed_amount)}</div>
              </div>
              <div>
                <div className={styles.drawerLabel}>Category</div>
                <div>{selected.category_name ?? "Needs review"}</div>
              </div>
            </div>

            <div className={styles.drawerBlock}>
              <div className={styles.drawerLabel}>Categorization</div>
              <div className={styles.drawerMeta}>
                Confidence:{" "}
                {selected.categorization?.confidence != null
                  ? `${Math.round(selected.categorization.confidence * 100)}%`
                  : "Needs review"}
              </div>
              <div className={styles.drawerMeta}>
                Source: {selected.categorization?.source ?? "—"}
              </div>
              <div className={styles.drawerMeta}>
                Reason: {selected.categorization?.reason ?? "—"}
              </div>
            </div>

            <div className={styles.drawerBlock}>
              <div className={styles.drawerLabel}>Payload snippet</div>
              <pre className={styles.payload}>
                {selected.payload ? JSON.stringify(selected.payload, null, 2) : "Payload not available."}
              </pre>
            </div>

            <div className={styles.drawerActions}>
              <button type="button" className={styles.primaryButton}>
                Set category
              </button>
              <button type="button" className={styles.secondaryButton}>
                Label vendor
              </button>
              <button type="button" className={styles.ghostButton}>
                Create rule from this
              </button>
            </div>
          </>
        )}
      </Drawer>
      {import.meta.env.DEV && (
        <div className={styles.debugOverlay}>
          <div className={styles.debugRow}>
            <span>business_id</span>
            <span>{activeBusinessId ?? "—"}</span>
          </div>
          <div className={styles.debugRow}>
            <span>date_range</span>
            <span>
              {dateRange.start} → {dateRange.end}
            </span>
          </div>
          <div className={styles.debugRow}>
            <span>ledger_rows</span>
            <span>{lines.length}</span>
          </div>
          <div className={styles.debugRow}>
            <span>filters</span>
            <span>
              {JSON.stringify(
                {
                  account: filters.account ?? null,
                  category: filters.category ?? null,
                  direction: filters.direction ?? null,
                  query: filters.q ?? null,
                },
                null,
                0
              )}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
