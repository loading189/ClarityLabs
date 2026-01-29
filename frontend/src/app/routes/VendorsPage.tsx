import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import FilterBar from "../../components/common/FilterBar";
import Table, { type TableColumn } from "../../components/common/Table";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { useFilters } from "../filters/useFilters";
import { resolveDateRange } from "../filters/filters";
import { ledgerPath } from "./routeUtils";
import { useLedgerLines } from "../../features/ledger/useLedgerLines";
import styles from "./VendorsPage.module.css";

type VendorSummary = {
  name: string;
  total: number;
  count: number;
  lastSeen: string;
};

function formatMoney(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function VendorsPage() {
  const { businessId = "" } = useParams();
  const navigate = useNavigate();
  const [filters, setFilters] = useFilters();
  const range = resolveDateRange(filters);
  const { lines, loading, err } = useLedgerLines(businessId, range.start, range.end);

  const vendorRows = useMemo(() => {
    const map = new Map<string, VendorSummary>();
    lines.forEach((line) => {
      const name = line.counterparty_hint || line.description || "Unknown vendor";
      const existing = map.get(name) ?? {
        name,
        total: 0,
        count: 0,
        lastSeen: line.occurred_at,
      };
      const outflowAmount = line.direction === "outflow" ? Math.abs(line.signed_amount) : 0;
      existing.total += outflowAmount;
      existing.count += 1;
      if (line.occurred_at > existing.lastSeen) {
        existing.lastSeen = line.occurred_at;
      }
      map.set(name, existing);
    });
    return Array.from(map.values()).sort((a, b) => b.total - a.total);
  }, [lines]);

  const columns: Array<TableColumn<VendorSummary>> = [
    {
      key: "name",
      header: "Vendor",
      render: (row) => row.name,
    },
    {
      key: "total",
      header: "Total spend",
      align: "right",
      render: (row) => formatMoney(row.total),
    },
    {
      key: "count",
      header: "Txn count",
      align: "right",
      render: (row) => row.count,
    },
    {
      key: "lastSeen",
      header: "Last seen",
      render: (row) => new Date(row.lastSeen).toLocaleDateString(),
    },
  ];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Vendors"
        subtitle="Spend by counterparty. Click a vendor to drill into the ledger."
      />

      <FilterBar filters={filters} onChange={setFilters} />

      {loading && <LoadingState label="Loading vendor rollups…" />}
      {err && <ErrorState label={`Failed to load vendors: ${err}`} />}

      {!loading && !err && (
        <Table
          columns={columns}
          rows={vendorRows}
          getRowId={(row) => row.name}
          emptyMessage="No vendors found for this window."
          onRowClick={(row) => {
            navigate(
              ledgerPath(businessId, {
                ...filters,
                q: row.name,
              })
            );
          }}
        />
      )}
    </div>
  );
}
