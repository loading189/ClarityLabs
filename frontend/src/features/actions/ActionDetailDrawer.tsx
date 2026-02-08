import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Drawer from "../../components/common/Drawer";
import {
  assignAction,
  fetchActionEvents,
  resolveAction,
  snoozeAction,
  type ActionItem,
  type ActionStateEvent,
  type ActionTriageItem,
} from "../../api/actions";
import { fetchBusinessMembers, type BusinessMember } from "../../api/businesses";
import type { FilterState } from "../../app/filters/filters";
import { ledgerPath } from "../../app/routes/routeUtils";
import styles from "./ActionDetailDrawer.module.css";

const SNOOZE_DAYS = 7;

type ActionDetail = (ActionItem | ActionTriageItem) & {
  business_name?: string;
};

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

function formatJson(value: unknown) {
  if (!value) return "—";
  return JSON.stringify(value, null, 2);
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export default function ActionDetailDrawer({
  open,
  action,
  onClose,
  onUpdated,
}: {
  open: boolean;
  action: ActionDetail | null;
  onClose: () => void;
  onUpdated?: () => void;
}) {
  const [note, setNote] = useState("");
  const [members, setMembers] = useState<BusinessMember[]>([]);
  const [events, setEvents] = useState<ActionStateEvent[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const actionId = action?.id;
  const businessId = action?.business_id;

  const loadMembers = useCallback(async () => {
    if (!businessId) return;
    setLoadingMembers(true);
    try {
      const response = await fetchBusinessMembers(businessId);
      setMembers(response ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Failed to load members");
    } finally {
      setLoadingMembers(false);
    }
  }, [businessId]);

  const loadEvents = useCallback(async () => {
    if (!businessId || !actionId) return;
    setLoadingEvents(true);
    try {
      const response = await fetchActionEvents(businessId, actionId);
      setEvents(response ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Failed to load audit trail");
    } finally {
      setLoadingEvents(false);
    }
  }, [actionId, businessId]);

  useEffect(() => {
    if (!open || !businessId) return;
    void loadMembers();
  }, [loadMembers, open, businessId]);

  useEffect(() => {
    if (!open || !businessId || !actionId) return;
    void loadEvents();
  }, [actionId, businessId, loadEvents, open]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setNote(action?.resolution_note ?? "");
  }, [action?.resolution_note, open]);

  const ledgerLink = useMemo(() => {
    if (!action?.evidence_json) return null;
    const anchors = Array.isArray(action.evidence_json.ledger_anchors)
      ? action.evidence_json.ledger_anchors
      : [];
    const firstAnchor = anchors[0] ?? null;
    const filters = anchorToLedgerFilters(firstAnchor);
    if (!filters || !businessId) return null;
    return ledgerPath(businessId, filters);
  }, [action?.evidence_json, businessId]);

  const assignedTo = action?.assigned_to_user_id ?? "";

  const handleAssign = async (nextUserId: string) => {
    if (!businessId || !actionId) return;
    setError(null);
    try {
      await assignAction(businessId, actionId, {
        assigned_to_user_id: nextUserId || null,
      });
      await loadEvents();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to update assignment");
    }
  };

  const handleResolve = async (status: "done" | "ignored") => {
    if (!businessId || !actionId) return;
    setError(null);
    try {
      await resolveAction(businessId, actionId, {
        status,
        resolution_reason: status === "done" ? "Completed" : "Ignored",
        resolution_note: note || undefined,
      });
      await loadEvents();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to update action");
    }
  };

  const handleSnooze = async () => {
    if (!businessId || !actionId) return;
    const until = new Date();
    until.setDate(until.getDate() + SNOOZE_DAYS);
    setError(null);
    try {
      await snoozeAction(businessId, actionId, {
        until: until.toISOString(),
        reason: "Snoozed",
        note: note || undefined,
      });
      await loadEvents();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to snooze action");
    }
  };

  return (
    <Drawer open={open} title={action?.title ?? "Action detail"} onClose={onClose}>
      {action && (
        <div className={styles.content}>
          {error && <div className={styles.error}>{error}</div>}

          <div className={styles.section}>
            <div className={styles.label}>Assignment</div>
            <div className={styles.row}>
              <select
                className={styles.select}
                value={assignedTo}
                onChange={(event) => handleAssign(event.target.value)}
                disabled={loadingMembers}
              >
                <option value="">Unassigned</option>
                {members.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name ?? member.email} · {member.role}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.label}>Resolution note</div>
            <textarea
              className={styles.input}
              rows={3}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Add context for the audit trail"
            />
          </div>

          <div className={styles.actions}>
            <button type="button" className={styles.primaryButton} onClick={() => handleResolve("done")}>
              Mark done
            </button>
            <button type="button" className={styles.secondaryButton} onClick={() => handleResolve("ignored")}>
              Ignore
            </button>
            <button type="button" className={styles.secondaryButton} onClick={handleSnooze}>
              Snooze 7d
            </button>
          </div>

          <div className={styles.section}>
            <div className={styles.label}>Summary</div>
            <div className={styles.text}>{action.summary}</div>
          </div>

          <div className={styles.section}>
            <div className={styles.label}>Rationale</div>
            <pre className={styles.pre}>{formatJson(action.rationale_json)}</pre>
          </div>

          <div className={styles.section}>
            <div className={styles.label}>Evidence</div>
            <pre className={styles.pre}>{formatJson(action.evidence_json)}</pre>
          </div>

          <div className={styles.row}>
            {ledgerLink && (
              <Link className={styles.linkButton} to={ledgerLink}>
                View in Ledger →
              </Link>
            )}
            {action.source_signal_id && businessId && (
              <Link
                className={styles.linkButton}
                to={`/app/${businessId}/signals?signal_id=${action.source_signal_id}`}
              >
                Open Signal →
              </Link>
            )}
          </div>

          <div className={styles.section}>
            <div className={styles.label}>Audit Trail</div>
            {loadingEvents && <div className={styles.muted}>Loading audit events…</div>}
            {!loadingEvents && events.length === 0 && (
              <div className={styles.muted}>No transitions recorded yet.</div>
            )}
            <div className={styles.auditList}>
              {events.map((event) => (
                <div key={event.id} className={styles.auditItem}>
                  <div>
                    {event.from_status} → {event.to_status}
                  </div>
                  <div className={styles.muted}>
                    {formatTimestamp(event.created_at)} · {event.actor_name ?? event.actor_email ?? "Unknown"}
                  </div>
                  {event.reason && <div>Reason: {event.reason}</div>}
                  {event.note && <div>Note: {event.note}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}
