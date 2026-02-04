import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Drawer from "../../components/common/Drawer";
import { ErrorState, LoadingState } from "../../components/common/DataState";
import { getAuditLog, type AuditLogOut } from "../../api/audit";
import {
  fetchSignals,
  getSignalDetail,
  listSignalStates,
  updateSignalStatus,
  type Signal,
  type SignalState,
  type SignalStateDetail,
  type SignalStatus,
} from "../../api/signals";
import styles from "./SignalsCenter.module.css";

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Resolved",
  ignored: "Ignored",
};

const SIGNAL_AUDIT_TYPES = new Set([
  "signal_detected",
  "signal_updated",
  "signal_resolved",
  "signal_status_changed",
]);

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function severityClass(severity: string | null) {
  if (severity === "red") return styles.severityRed;
  if (severity === "yellow") return styles.severityYellow;
  if (severity === "green") return styles.severityGreen;
  return styles.severityNeutral;
}

function formatDomainLabel(domain?: string | null) {
  if (!domain) return "—";
  return domain.charAt(0).toUpperCase() + domain.slice(1);
}

function toIsoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function buildLegacyDateRange() {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 30);
  return { start: toIsoDate(start), end: toIsoDate(end) };
}

function mapLegacySignal(signal: Signal): SignalState {
  const title = signal.type.replace(/_/g, " ");
  return {
    id: signal.id,
    type: signal.type,
    severity: signal.severity,
    status: "open",
    title,
    summary: signal.window ? `Window ${signal.window}` : "—",
    updated_at: null,
  };
}

type StatusModalState = {
  open: boolean;
  nextStatus: SignalStatus | null;
};

function RelatedChanges({
  businessId,
  onSelect,
}: {
  businessId: string;
  onSelect: (auditId: string) => void;
}) {
  const [items, setItems] = useState<AuditLogOut[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      const data = await getAuditLog(businessId, { limit: 20 });
      const filtered = data.items.filter((item) => SIGNAL_AUDIT_TYPES.has(item.event_type));
      setItems(filtered.slice(0, 10));
      setNextCursor(data.next_cursor ?? null);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load audit history");
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  const loadMore = useCallback(async () => {
    if (!businessId || !nextCursor || loadingMore) return;
    setLoadingMore(true);
    setErr(null);
    try {
      const data = await getAuditLog(businessId, { limit: 20, cursor: nextCursor });
      const filtered = data.items.filter((item) => SIGNAL_AUDIT_TYPES.has(item.event_type));
      setItems((prev) => [...prev, ...filtered]);
      setNextCursor(data.next_cursor ?? null);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load more audit history");
    } finally {
      setLoadingMore(false);
    }
  }, [businessId, loadingMore, nextCursor]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className={styles.auditSection}>
      <div className={styles.auditHeader}>
        <div>
          <div className={styles.auditTitle}>Related changes</div>
          <div className={styles.auditSubtitle}>Latest signal detections and updates.</div>
        </div>
        <button className={styles.secondaryButton} type="button" onClick={load}>
          Refresh
        </button>
      </div>

      {loading && <LoadingState label="Loading related changes…" />}
      {err && <ErrorState label={err} />}

      {!loading && !err && (
        <div className={styles.auditList}>
          {items.length === 0 && <div className={styles.empty}>No related changes yet.</div>}
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={styles.auditRow}
              onClick={() => onSelect(item.id)}
            >
              <div>
                <div className={styles.auditEvent}>{item.event_type.replace(/_/g, " ")}</div>
                <div className={styles.auditMeta}>
                  {item.actor} · {formatDate(item.created_at)}
                </div>
              </div>
              <span className={styles.auditLink}>View</span>
            </button>
          ))}
        </div>
      )}

      {nextCursor && (
        <button
          className={styles.loadMore}
          type="button"
          onClick={loadMore}
          disabled={loadingMore}
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}

export default function SignalsCenter({ businessId }: { businessId: string }) {
  const navigate = useNavigate();
  const [signals, setSignals] = useState<SignalState[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [useLegacyV1, setUseLegacyV1] = useState(false);
  const [selected, setSelected] = useState<SignalState | null>(null);
  const [detail, setDetail] = useState<SignalStateDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailErr, setDetailErr] = useState<string | null>(null);
  const [statusModal, setStatusModal] = useState<StatusModalState>({
    open: false,
    nextStatus: null,
  });
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [savingStatus, setSavingStatus] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [toastAuditId, setToastAuditId] = useState<string | null>(null);
  const legacyDateRange = useMemo(() => buildLegacyDateRange(), []);

  const loadSignals = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      if (useLegacyV1) {
        const data = await fetchSignals(businessId, {
          start_date: legacyDateRange.start,
          end_date: legacyDateRange.end,
        });
        setSignals((data.signals ?? []).map(mapLegacySignal));
      } else {
        const data = await listSignalStates(businessId);
        setSignals(data.signals ?? []);
      }
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load signals");
    } finally {
      setLoading(false);
    }
  }, [businessId, legacyDateRange.end, legacyDateRange.start, useLegacyV1]);

  useEffect(() => {
    loadSignals();
  }, [loadSignals]);

  useEffect(() => {
    if (useLegacyV1) {
      setSelected(null);
      setDetail(null);
      setStatusModal({ open: false, nextStatus: null });
      setActor("");
      setReason("");
      setStatusFilter("");
      return;
    }
    if (!selected?.id) {
      setDetail(null);
      return;
    }
    let active = true;
    async function loadDetail() {
      setDetailLoading(true);
      setDetailErr(null);
      try {
        const data = await getSignalDetail(businessId, selected.id);
        if (!active) return;
        setDetail(data);
      } catch (e: any) {
        if (!active) return;
        setDetailErr(e?.message ?? "Failed to load signal details");
      } finally {
        if (active) setDetailLoading(false);
      }
    }
    loadDetail();
    return () => {
      active = false;
    };
  }, [businessId, selected, useLegacyV1]);

  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const filterOptions = useMemo(() => {
    const types = Array.from(new Set(signals.map((signal) => signal.type).filter(Boolean)));
    const severities = Array.from(
      new Set(signals.map((signal) => signal.severity).filter(Boolean))
    );
    return { types, severities };
  }, [signals]);

  const filteredSignals = useMemo(() => {
    return signals.filter((signal) => {
      if (statusFilter && signal.status !== statusFilter) return false;
      if (severityFilter && signal.severity !== severityFilter) return false;
      if (typeFilter && signal.type !== typeFilter) return false;
      return true;
    });
  }, [signals, severityFilter, statusFilter, typeFilter]);

  const openStatusModal = (nextStatus: SignalStatus) => {
    setStatusModal({ open: true, nextStatus });
  };

  const closeStatusModal = () => {
    setStatusModal({ open: false, nextStatus: null });
    setActor("");
    setReason("");
  };

  const handleStatusSubmit = async () => {
    if (useLegacyV1) return;
    if (!selected || !statusModal.nextStatus) return;
    if (!actor.trim() || !reason.trim()) return;
    setSavingStatus(true);
    setToastMsg(null);
    setToastAuditId(null);
    try {
      const result = await updateSignalStatus(businessId, selected.id, {
        status: statusModal.nextStatus,
        actor: actor.trim(),
        reason: reason.trim(),
      });
      setToastAuditId(result.audit_id ?? null);
      setToastMsg(`Status updated to ${STATUS_LABELS[result.status] ?? result.status}.`);
      closeStatusModal();
      await loadSignals();
      const detailData = await getSignalDetail(businessId, selected.id);
      setDetail(detailData);
      setSelected((prev) => (prev ? { ...prev, status: result.status } : prev));
    } catch (e: any) {
      setDetailErr(e?.message ?? "Failed to update status");
    } finally {
      setSavingStatus(false);
    }
  };

  const handleAuditSelect = (auditId: string) => {
    navigate(`/app/${businessId}/categorize?auditId=${auditId}#recent-changes`);
  };

  const statusButtons = useMemo(() => {
    if (!detail) return [] as Array<{ label: string; status: SignalStatus }>;
    if (detail.status === "resolved" || detail.status === "ignored") {
      return [{ label: "Reopen", status: "open" }];
    }
    return [
      { label: "Resolve", status: "resolved" },
      { label: "Ignore", status: "ignored" },
    ];
  }, [detail]);

  return (
    <div className={styles.container}>
      <div className={styles.filters}>
        <label className={styles.filterField}>
          Status
          <select
            className={styles.select}
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            disabled={useLegacyV1}
          >
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="resolved">Resolved</option>
            <option value="ignored">Ignored</option>
          </select>
        </label>
        <label className={styles.filterField}>
          Severity
          <select
            className={styles.select}
            value={severityFilter}
            onChange={(event) => setSeverityFilter(event.target.value)}
          >
            <option value="">All</option>
            {filterOptions.severities.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.filterField}>
          Type
          <select
            className={styles.select}
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
          >
            <option value="">All</option>
            {filterOptions.types.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.legacyToggle}>
          <span>V1 (legacy)</span>
          <input
            type="checkbox"
            checked={useLegacyV1}
            onChange={(event) => setUseLegacyV1(event.target.checked)}
          />
        </label>
      </div>
      {useLegacyV1 && (
        <div className={styles.legacyNote}>
          Legacy signals are read-only. Switch off to manage statuses and view details.
        </div>
      )}

      {loading && <LoadingState label="Loading signals…" />}
      {err && <ErrorState label={err} />}

      {!loading && !err && (
        <div className={styles.list}>
          {filteredSignals.length === 0 && (
            <div className={styles.empty}>No signals match the selected filters.</div>
          )}
          {filteredSignals.map((signal) => (
            <button
              key={signal.id}
              type="button"
              className={`${styles.row} ${selected?.id === signal.id ? styles.rowActive : ""} ${
                useLegacyV1 ? styles.rowDisabled : ""
              }`}
              onClick={() => {
                if (useLegacyV1) return;
                setSelected(signal);
              }}
              disabled={useLegacyV1}
            >
              <span className={`${styles.severityBadge} ${severityClass(signal.severity)}`}>
                {signal.severity ?? "—"}
              </span>
              <div className={styles.rowMain}>
                <div className={styles.rowTitle}>{signal.title ?? signal.type ?? "Signal"}</div>
                <div className={styles.rowDomain}>{formatDomainLabel(signal.domain)}</div>
                <div className={styles.rowSummary}>{signal.summary ?? "—"}</div>
              </div>
              <div className={styles.rowMeta}>
                <div>{formatDate(signal.updated_at)}</div>
                <div className={styles.statusPill}>{STATUS_LABELS[signal.status] ?? signal.status}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      {toastMsg && (
        <div className={styles.toast}>
          <span>{toastMsg}</span>
          {toastAuditId && (
            <button
              type="button"
              className={styles.toastLink}
              onClick={() => handleAuditSelect(toastAuditId)}
            >
              View in Recent Changes
            </button>
          )}
        </div>
      )}

      <Drawer
        open={Boolean(selected)}
        title="Signal details"
        onClose={() => setSelected(null)}
      >
        {detailLoading && <LoadingState label="Loading signal details…" />}
        {detailErr && <ErrorState label={detailErr} />}

        {!detailLoading && !detailErr && detail && (
          <div className={styles.detailContent}>
            <div>
              <div className={styles.detailTitle}>{detail.title ?? detail.type ?? "Signal"}</div>
              <div className={styles.detailSummary}>{detail.summary ?? "—"}</div>
              <div className={styles.detailMeta}>
                <span>Status: {STATUS_LABELS[detail.status] ?? detail.status}</span>
                <span>Domain: {formatDomainLabel(detail.domain)}</span>
                <span>Last updated: {formatDate(detail.updated_at)}</span>
              </div>
            </div>

            <div className={styles.statusActions}>
              {statusButtons.map((btn) => (
                <button
                  key={btn.status}
                  className={styles.primaryButton}
                  type="button"
                  onClick={() => openStatusModal(btn.status)}
                >
                  {btn.label}
                </button>
              ))}
              {detail && (
                <Link
                  className={styles.secondaryButton}
                  to={`/assistant?businessId=${businessId}&signalId=${detail.id}`}
                >
                  Send to Assistant
                </Link>
              )}
            </div>

            <div>
              <div className={styles.sectionTitle}>Payload</div>
              <pre className={styles.payload}>
                {JSON.stringify(detail.payload_json ?? {}, null, 2)}
              </pre>
            </div>

            <RelatedChanges businessId={businessId} onSelect={handleAuditSelect} />
          </div>
        )}
      </Drawer>

      {statusModal.open && (
        <div className={styles.modalOverlay} role="dialog" aria-modal="true">
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <div>
                <div className={styles.modalTitle}>Update status</div>
                <div className={styles.modalSubtitle}>
                  Provide who is making this change and why.
                </div>
              </div>
              <button type="button" className={styles.modalClose} onClick={closeStatusModal}>
                Close
              </button>
            </div>
            <div className={styles.modalBody}>
              <label className={styles.modalField}>
                Actor
                <input
                  className={styles.input}
                  type="text"
                  value={actor}
                  onChange={(event) => setActor(event.target.value)}
                  placeholder="Name"
                />
              </label>
              <label className={styles.modalField}>
                Reason
                <textarea
                  className={styles.textarea}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Why are you updating this signal?"
                />
              </label>
              <div className={styles.modalActions}>
                <button
                  className={styles.secondaryButton}
                  type="button"
                  onClick={closeStatusModal}
                  disabled={savingStatus}
                >
                  Cancel
                </button>
                <button
                  className={styles.primaryButton}
                  type="button"
                  onClick={handleStatusSubmit}
                  disabled={savingStatus || !actor.trim() || !reason.trim()}
                >
                  {savingStatus ? "Saving…" : "Confirm update"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
