import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Drawer from "../../components/common/Drawer";
import { refreshActions, resolveAction, snoozeAction } from "../../api/actions";
import type {ActionItem} from "../../api/actions"
import type { FilterState } from "../../app/filters/filters";
import { ledgerPath } from "../../app/routes/routeUtils";
import styles from "./NextActionsPanel.module.css";

const SNOOZE_DAYS = 7;

function joinListParam(values?: string[] | null) {
  if (!values || values.length === 0) return undefined;
  return values.slice().sort((a, b) => a.localeCompare(b)).join(",");
}

function anchorToLedgerFilters(anchor: { query?: Record<string, any> } | null): FilterState | null {
  if (!anchor || !anchor.query) return null;
  const query = anchor.query;
  const filters: FilterState = {};
  if (query.start_date && query.end_date) {
    filters.start = query.start_date;
    filters.end = query.end_date;
    filters.window = undefined;
  }
  const accountParam = joinListParam(query.accounts ?? undefined);
  if (accountParam) filters.account = accountParam;
  const vendorParam = joinListParam(query.vendors ?? undefined);
  if (vendorParam) filters.vendor = vendorParam;
  const categoryParam = joinListParam(query.categories ?? undefined);
  if (categoryParam) filters.category = categoryParam;
  if (query.search) filters.q = query.search;
  if (query.direction) filters.direction = query.direction;
  const highlightParam = joinListParam(query.source_event_ids ?? undefined);
  if (highlightParam) {
    filters.highlight_source_event_ids = highlightParam;
    if (query.source_event_ids && query.source_event_ids.length === 1) {
      filters.anchor_source_event_id = query.source_event_ids[0] ?? undefined;
    }
  }
  return filters;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  return value.split("T")[0];
}

function formatPriority(value: number) {
  if (value >= 5) return "Critical";
  if (value >= 4) return "High";
  if (value >= 3) return "Medium";
  return "Low";
}

function formatJson(value: unknown) {
  if (!value) return "—";
  return JSON.stringify(value, null, 2);
}

export default function NextActionsPanel({ businessId }: { businessId: string }) {
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ActionItem | null>(null);

  const loadActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await refreshActions(businessId);
      setActions(response.actions ?? []);
      setSummary(response.summary ?? {});
    } catch (err: any) {
      setError(err?.message ?? "Failed to load actions");
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    void loadActions();
  }, [loadActions]);

  const openCount = summary.open ?? actions.length;

  const sortedActions = useMemo(() => {
    return [...actions].sort((a, b) => {
      if (a.priority !== b.priority) return b.priority - a.priority;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [actions]);

  const topActions = sortedActions.slice(0, 5);

  const handleResolve = async (actionId: string, status: "done" | "ignored") => {
    try {
      await resolveAction(businessId, actionId, { status });
      await loadActions();
    } catch (err: any) {
      setError(err?.message ?? "Failed to update action");
    }
  };

  const handleSnooze = async (actionId: string) => {
    const until = new Date();
    until.setDate(until.getDate() + SNOOZE_DAYS);
    try {
      await snoozeAction(businessId, actionId, { until: until.toISOString(), reason: "Snoozed" });
      await loadActions();
    } catch (err: any) {
      setError(err?.message ?? "Failed to snooze action");
    }
  };

  const ledgerLink = useMemo(() => {
    if (!selected?.evidence_json) return null;
    const anchors = Array.isArray(selected.evidence_json.ledger_anchors)
      ? selected.evidence_json.ledger_anchors
      : [];
    const firstAnchor = anchors[0] ?? null;
    const filters = anchorToLedgerFilters(firstAnchor);
    if (!filters) return null;
    return ledgerPath(businessId, filters);
  }, [businessId, selected]);

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <h2>Next Actions</h2>
          <p className={styles.subtitle}>Deterministic next steps from signals and ledger facts.</p>
        </div>
        <div className={styles.count}>
          <span className={styles.countValue}>{openCount}</span>
          <span className={styles.countLabel}>Open</span>
        </div>
      </div>

      {loading && <div className={styles.state}>Loading action plan…</div>}
      {error && <div className={styles.error}>{error}</div>}

      {!loading && topActions.length === 0 && <div className={styles.empty}>No open actions right now.</div>}

      <div className={styles.list}>
        {topActions.map((action) => (
          <div key={action.id} className={styles.row}>
            <div className={styles.rowMain}>
              <div className={styles.titleRow}>
                <div className={styles.title}>{action.title}</div>
                <span className={styles.priority}>{formatPriority(action.priority)}</span>
              </div>
              <div className={styles.summary}>{action.summary}</div>
              <div className={styles.meta}>
                <span>Type: {action.action_type}</span>
                <span>Created: {formatDate(action.created_at)}</span>
              </div>
            </div>
            <div className={styles.actions}>
              <button type="button" onClick={() => setSelected(action)} className={styles.linkButton}>
                View details
              </button>
              <button type="button" onClick={() => handleResolve(action.id, "done")} className={styles.primaryButton}>
                Mark done
              </button>
              <button type="button" onClick={() => handleResolve(action.id, "ignored")} className={styles.secondaryButton}>
                Ignore
              </button>
              <button type="button" onClick={() => handleSnooze(action.id)} className={styles.secondaryButton}>
                Snooze
              </button>
            </div>
          </div>
        ))}
      </div>

      <Drawer
        open={Boolean(selected)}
        title={selected?.title ?? "Action detail"}
        onClose={() => setSelected(null)}
      >
        {selected && (
          <div className={styles.drawerContent}>
            <div className={styles.drawerSection}>
              <div className={styles.drawerLabel}>Summary</div>
              <div className={styles.drawerText}>{selected.summary}</div>
            </div>
            <div className={styles.drawerSection}>
              <div className={styles.drawerLabel}>Rationale</div>
              <pre className={styles.drawerPre}>{formatJson(selected.rationale_json)}</pre>
            </div>
            <div className={styles.drawerSection}>
              <div className={styles.drawerLabel}>Evidence</div>
              <pre className={styles.drawerPre}>{formatJson(selected.evidence_json)}</pre>
            </div>
            <div className={styles.drawerLinks}>
              {ledgerLink && (
                <Link className={styles.drawerLink} to={ledgerLink}>
                  View in Ledger →
                </Link>
              )}
              {selected.source_signal_id && (
                <Link
                  className={styles.drawerLink}
                  to={`/app/${businessId}/signals?signal_id=${selected.source_signal_id}`}
                >
                  Open Signal →
                </Link>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </section>
  );
}
