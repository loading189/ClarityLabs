import { useMemo, useState } from "react";
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
import styles from "./LedgerPage.module.css";

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
  ).map((value) => ({
    label: value,
    value,
  }));
}

export default function LedgerPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "LedgerPage");
  const [filters, setFilters] = useFilters();
  const { data: dashboard } = useDemoDashboard(businessId);
  useDemoDateRange(filters, setFilters, dashboard?.metadata);
  const range = resolveDateRange(filters);
  const { lines, loading, err } = useLedgerLines(businessId, range.start, range.end);
  const [selected, setSelected] = useState<LedgerLine | null>(null);
  const [page, setPage] = useState(1);

  const accounts = useMemo(
    () => uniqueOptions(lines.map((line) => line.account_name)),
    [lines]
  );
  const categories = useMemo(
    () => uniqueOptions(lines.map((line) => line.category_name)),
    [lines]
  );

  const filtered = useMemo(() => {
    const query = (filters.q ?? "").toLowerCase();
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

  const pageSize = 50;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const paged = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const columns: Array<TableColumn<LedgerLine>> = [
    {
      key: "occurred_at",
      header: "Date/Time",
      render: (row) => formatDateTime(row.occurred_at),
    },
    {
      key: "description",
      header: "Description",
      render: (row) => (
        <div className={styles.descriptionCell}>
          <div className={styles.descriptionTitle}>{row.description}</div>
          <div className={styles.descriptionMeta}>
            {row.counterparty_hint ?? "Counterparty unknown"}
          </div>
        </div>
      ),
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
  ];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Ledger"
        subtitle="Source-of-truth timeline with filters, search, and transaction drilldowns."
        actions={
          <div className={styles.summary}>
            <span>
              {range.start} → {range.end}
            </span>
            <span>{filtered.length} results</span>
          </div>
        }
      />

      <FilterBar
        filters={filters}
        onChange={(updates) => {
          setPage(1);
          setFilters(updates);
        }}
        accounts={accounts}
        categories={categories}
        showDirection
      />

      {loading && <LoadingState label="Loading ledger lines…" />}
      {err && <ErrorState label={`Failed to load ledger: ${err}`} />}

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

      <Drawer
        open={Boolean(selected)}
        title="Transaction detail"
        onClose={() => setSelected(null)}
      >
        {selected && (
          <>
            <div className={styles.drawerBlock}>
              <div className={styles.drawerLabel}>Occurred at</div>
              <div>{formatDateTime(selected.occurred_at)}</div>
            </div>
            <div className={styles.drawerBlock}>
              <div className={styles.drawerLabel}>Description</div>
              <div>{selected.description}</div>
              <div className={styles.drawerMeta}>
                Source ID: {selected.source_event_id}
              </div>
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
                {selected.payload
                  ? JSON.stringify(selected.payload, null, 2)
                  : "Payload not available."}
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
    </div>
  );
}
