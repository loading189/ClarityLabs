import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import FilterBar from "../../components/common/FilterBar";
import Table, { type TableColumn } from "../../components/common/Table";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import Drawer from "../../components/common/Drawer";
import { useFilters } from "../filters/useFilters";
import { resolveDateRange } from "../filters/filters";
import { useDemoDateRange } from "../filters/useDemoDateRange";
import { ledgerPath } from "./routeUtils";
import { useLedgerLines } from "../../features/ledger/useLedgerLines";
import { useDemoDashboard } from "../../hooks/useDemoDashboard";
import { assertBusinessId } from "../../utils/businessId";
import { useAppState } from "../state/appState";
import styles from "./VendorsPage.module.css";
import {
  getBrainVendors,
  getCategories,
  setBrainVendor,
  type BrainVendor,
  type CategoryOut,
} from "../../api/categorize";
import { normalizeVendorDisplay, normalizeVendorKey } from "../../utils/vendors";
import { hasValidCategoryMapping } from "../../utils/categories";

type VendorSummary = {
  name: string;
  total: number;
  count: number;
  lastSeen: string;
  keys: string[];
  topCategories: Array<{ name: string; total: number }>;
};

function formatMoney(value: number) {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function VendorsPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "VendorsPage");
  const navigate = useNavigate();

  if (!businessId) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Vendors"
          subtitle="Spend by counterparty. Click a vendor to drill into the ledger."
        />
        <ErrorState label="Invalid business id in URL. Go back to /app to re-select a business." />
      </div>
    );
  }
  const [filters, setFilters] = useFilters();
  const { data: dashboard } = useDemoDashboard();
  const { setDateRange, dataVersion, bumpDataVersion } = useAppState();
  useDemoDateRange(filters, setFilters, dashboard?.metadata);
  const range = resolveDateRange(filters);
  useEffect(() => {
    setDateRange(range);
  }, [range.end, range.start, setDateRange]);
  const { lines, loading, err } = useLedgerLines();
  const [brainVendors, setBrainVendors] = useState<BrainVendor[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [vendorErr, setVendorErr] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedVendor, setSelectedVendor] = useState<VendorSummary | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [canonicalName, setCanonicalName] = useState("");
  const [categoryId, setCategoryId] = useState("");

  const vendorsByAlias = useMemo(() => {
    const map = new Map<string, BrainVendor>();
    brainVendors.forEach((vendor) => {
      vendor.alias_keys?.forEach((alias) => {
        map.set(alias, vendor);
      });
    });
    return map;
  }, [brainVendors]);

  const categoriesBySystemKey = useMemo(() => {
    const map = new Map<string, CategoryOut>();
    categories.forEach((cat) => {
      if (cat.system_key) {
        map.set(cat.system_key.toLowerCase(), cat);
      }
    });
    return map;
  }, [categories]);

  const vendorRows = useMemo(() => {
    const map = new Map<string, VendorSummary>();
    lines.forEach((line) => {
      const keySource = line.counterparty_hint || line.description || "";
      const key = normalizeVendorKey(keySource);
      const vendor = vendorsByAlias.get(key);
      const displayName = normalizeVendorDisplay(
        line.counterparty_hint || line.description || "",
        vendor?.canonical_name
      );
      const existing = map.get(displayName) ?? {
        name: displayName,
        total: 0,
        count: 0,
        lastSeen: line.occurred_at,
        keys: key ? [key] : [],
        topCategories: [],
      };
      const outflowAmount = line.direction === "outflow" ? Math.abs(line.signed_amount) : 0;
      existing.total += outflowAmount;
      existing.count += 1;
      if (line.occurred_at > existing.lastSeen) {
        existing.lastSeen = line.occurred_at;
      }
      if (key && !existing.keys.includes(key)) {
        existing.keys.push(key);
      }
      const categoryName = line.category_name || "Uncategorized";
      const categoryEntry = existing.topCategories.find((cat) => cat.name === categoryName);
      if (categoryEntry) {
        categoryEntry.total += outflowAmount;
      } else {
        existing.topCategories.push({ name: categoryName, total: outflowAmount });
      }
      map.set(displayName, existing);
    });
    return Array.from(map.values())
      .map((row) => ({
        ...row,
        topCategories: row.topCategories.sort((a, b) => b.total - a.total).slice(0, 3),
      }))
      .sort((a, b) => b.total - a.total);
  }, [lines, vendorsByAlias]);

  useEffect(() => {
    if (!businessId) return;
    setVendorErr(null);
    Promise.all([getBrainVendors(businessId), getCategories(businessId)])
      .then(([vendors, cats]) => {
        setBrainVendors(vendors);
        setCategories(cats);
      })
      .catch((e: any) => {
        console.error("[vendors] fetch failed", {
          businessId,
          dateRange: range,
          url: `/categorize/business/${businessId}/brain/vendors`,
          error: e?.message ?? e,
        });
        setVendorErr(e?.message ?? "Failed to load vendor mappings");
      });
  }, [businessId, range, dataVersion]);

  useEffect(() => {
    if (!selectedVendor) return;
    const vendor = selectedVendor.keys
      .map((key) => vendorsByAlias.get(key))
      .find(Boolean);
    setCanonicalName(vendor?.canonical_name ?? selectedVendor.name);
    const mappedCategory = vendor?.system_key
      ? categoriesBySystemKey.get(vendor.system_key.toLowerCase())
      : null;
    setCategoryId(mappedCategory?.id ?? "");
  }, [categoriesBySystemKey, selectedVendor, vendorsByAlias]);

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

  const selectedVendorLines = useMemo(() => {
    if (!selectedVendor) return [];
    const vendorKeys = new Set(selectedVendor.keys);
    return lines.filter((line) => {
      const keySource = line.counterparty_hint || line.description || "";
      const key = normalizeVendorKey(keySource);
      return vendorKeys.has(key);
    });
  }, [lines, selectedVendor]);

  const handleSaveVendor = async () => {
    if (!selectedVendor) return;
    const key = selectedVendor.keys[0];
    if (!key) {
      setSaveErr("No merchant key available for this vendor.");
      return;
    }
    const category = categories.find((cat) => cat.id === categoryId);
    if (!hasValidCategoryMapping(category)) {
      setSaveErr("Select a category with a valid COA mapping.");
      return;
    }
    setSaveLoading(true);
    setSaveErr(null);
    try {
      await setBrainVendor(businessId, {
        merchant_key: key,
        category_id: categoryId,
        canonical_name: canonicalName.trim() || undefined,
      });
      bumpDataVersion();
    } catch (e: any) {
      setSaveErr(e?.message ?? "Failed to update vendor");
    } finally {
      setSaveLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="Vendors"
        subtitle="Spend by counterparty. Click a vendor to drill into the ledger."
      />

      <FilterBar filters={filters} onChange={setFilters} />

      {loading && <LoadingState label="Loading vendor rollups…" />}
      {err && <ErrorState label={`Failed to load vendors: ${err}`} />}
      {vendorErr && <ErrorState label={`Failed to load vendor mappings: ${vendorErr}`} />}

      {!loading && !err && (
        <Table
          columns={columns}
          rows={vendorRows}
          getRowId={(row) => row.name}
          emptyMessage="No vendors found for this window."
          onRowClick={(row) => {
            setSelectedVendor(row);
            setDetailOpen(true);
          }}
        />
      )}

      <Drawer
        title={selectedVendor?.name ?? "Vendor details"}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      >
        {!selectedVendor ? (
          <div className={styles.drawerEmpty}>Select a vendor to see details.</div>
        ) : (
          <div className={styles.drawerContent}>
            <div className={styles.drawerSection}>
              <div className={styles.drawerLabel}>Totals</div>
              <div className={styles.drawerValue}>
                {formatMoney(selectedVendor.total)} • {selectedVendor.count} transactions
              </div>
              <div className={styles.drawerSub}>
                Last seen {new Date(selectedVendor.lastSeen).toLocaleDateString()}
              </div>
            </div>

            <div className={styles.drawerSection}>
              <div className={styles.drawerLabel}>Top categories</div>
              {selectedVendor.topCategories.length === 0 ? (
                <div className={styles.drawerValue}>No category data.</div>
              ) : (
                <ul className={styles.drawerList}>
                  {selectedVendor.topCategories.map((cat) => (
                    <li key={cat.name}>
                      {cat.name} • {formatMoney(cat.total)}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className={styles.drawerSection}>
              <div className={styles.drawerLabel}>Vendor identity</div>
              <label className={styles.drawerField}>
                Canonical name
                <input
                  type="text"
                  value={canonicalName}
                  onChange={(event) => setCanonicalName(event.target.value)}
                />
              </label>
              <label className={styles.drawerField}>
                Default category
                <select
                  value={categoryId}
                  onChange={(event) => setCategoryId(event.target.value)}
                >
                  <option value="">Select category</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.name}
                    </option>
                  ))}
                </select>
              </label>
              {saveErr && <div className={styles.drawerError}>{saveErr}</div>}
              <button
                className={styles.drawerButton}
                onClick={handleSaveVendor}
                disabled={saveLoading}
                type="button"
              >
                {saveLoading ? "Saving…" : "Save vendor"}
              </button>
            </div>

            <div className={styles.drawerSection}>
              <div className={styles.drawerLabel}>Recent transactions</div>
              {selectedVendorLines.length === 0 ? (
                <div className={styles.drawerValue}>No transactions found.</div>
              ) : (
                <ul className={styles.drawerList}>
                  {selectedVendorLines.slice(0, 6).map((line) => (
                    <li key={line.source_event_id}>
                      {new Date(line.occurred_at).toLocaleDateString()} •{" "}
                      {formatMoney(line.signed_amount)} • {line.description}
                    </li>
                  ))}
                </ul>
              )}
              <button
                className={styles.drawerLink}
                onClick={() =>
                  navigate(
                    ledgerPath(businessId, {
                      ...filters,
                      q: selectedVendor.name,
                    })
                  )
                }
                type="button"
              >
                View in ledger
              </button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
