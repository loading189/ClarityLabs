import { useCallback, useEffect, useMemo, useState } from "react";
import Drawer from "../../components/common/Drawer";
import { fetchBusinessMembers, type BusinessMember } from "../../api/businesses";
import {
  activatePlan,
  addPlanNote,
  assignPlan,
  closePlan,
  getPlanDetail,
  refreshPlan,
  type PlanDetail,
  type PlanCloseOutcome,
  type PlanObservation,
} from "../../api/plansV2";
import styles from "./PlanDetailDrawer.module.css";

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

export default function PlanDetailDrawer({
  open,
  planId,
  businessId,
  onClose,
  onUpdated,
}: {
  open: boolean;
  planId: string | null;
  businessId: string | null | undefined;
  onClose: () => void;
  onUpdated?: () => void;
}) {
  const [detail, setDetail] = useState<PlanDetail | null>(null);
  const [members, setMembers] = useState<BusinessMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [closeOutcome, setCloseOutcome] = useState<PlanCloseOutcome>("succeeded");
  const [closeNote, setCloseNote] = useState("");

  const loadPlan = useCallback(async () => {
    if (!planId || !businessId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await getPlanDetail(businessId, planId);
      setDetail(response);
    } catch (err: any) {
      setError(err?.message ?? "Failed to load plan");
    } finally {
      setLoading(false);
    }
  }, [businessId, planId]);

  const loadMembers = useCallback(async () => {
    if (!businessId) return;
    try {
      const response = await fetchBusinessMembers(businessId);
      setMembers(response ?? []);
    } catch (err: any) {
      setError(err?.message ?? "Failed to load members");
    }
  }, [businessId]);

  useEffect(() => {
    if (!open) return;
    void loadPlan();
    void loadMembers();
  }, [loadMembers, loadPlan, open]);

  useEffect(() => {
    if (!open) return;
    setNote("");
    setCloseNote("");
    setError(null);
  }, [open, planId]);

  const plan = detail?.plan;
  const latestObservation: PlanObservation | null = detail?.latest_observation ?? null;

  const conditionSummary = useMemo(() => {
    if (!detail?.conditions?.length) return "No conditions configured.";
    return detail.conditions
      .map((condition) => {
        if (condition.type === "signal_resolved") {
          return `Signal ${condition.signal_id ?? "(none)"} resolved over ${condition.evaluation_window_days}d.`;
        }
        return `Metric ${condition.metric_key ?? "(none)"} ${condition.direction} over ${condition.evaluation_window_days}d.`;
      })
      .join(" ");
  }, [detail?.conditions]);

  const handleActivate = async () => {
    if (!planId || !businessId) return;
    setError(null);
    try {
      await activatePlan(businessId, planId);
      await loadPlan();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to activate plan");
    }
  };

  const handleRefresh = async () => {
    if (!planId || !businessId) return;
    setError(null);
    try {
      await refreshPlan(businessId, planId);
      await loadPlan();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to refresh plan");
    }
  };

  const handleAssign = async (assignedToUserId: string) => {
    if (!planId || !businessId) return;
    setError(null);
    try {
      await assignPlan(businessId, planId, {
        assigned_to_user_id: assignedToUserId || null,
      });
      await loadPlan();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to update assignment");
    }
  };

  const handleAddNote = async () => {
    if (!planId || !businessId || !note.trim()) return;
    setError(null);
    try {
      await addPlanNote(businessId, planId, { note: note.trim() });
      setNote("");
      await loadPlan();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to add note");
    }
  };

  const handleClose = async () => {
    if (!planId || !businessId) return;
    setError(null);
    try {
      await closePlan(businessId, planId, { outcome: closeOutcome, note: closeNote || undefined });
      await loadPlan();
      onUpdated?.();
    } catch (err: any) {
      setError(err?.message ?? "Failed to close plan");
    }
  };

  return (
    <Drawer open={open} title={plan?.title ?? "Plan detail"} onClose={onClose}>
      <div className={styles.content}>
        {error && <div className={styles.error}>{error}</div>}
        {loading && <div className={styles.muted}>Loading plan details…</div>}

        {plan && (
          <>
            <div className={styles.section}>
              <div className={styles.label}>Intent</div>
              <div className={styles.text}>{plan.intent}</div>
            </div>

            <div className={styles.section}>
              <div className={styles.label}>Assignment</div>
              <div className={styles.row}>
                <select
                  className={styles.select}
                  value={plan.assigned_to_user_id ?? ""}
                  onChange={(event) => handleAssign(event.target.value)}
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
              <div className={styles.label}>Status</div>
              <div className={styles.text}>
                {plan.status} · Created {formatTimestamp(plan.created_at)}
              </div>
              {plan.activated_at && <div className={styles.muted}>Activated {formatTimestamp(plan.activated_at)}</div>}
              {plan.closed_at && <div className={styles.muted}>Closed {formatTimestamp(plan.closed_at)}</div>}
            </div>

            <div className={styles.section}>
              <div className={styles.label}>Conditions</div>
              <div className={styles.text}>{conditionSummary}</div>
            </div>

            <div className={styles.section}>
              <div className={styles.label}>Latest observation</div>
              {latestObservation ? (
                <div className={styles.text}>
                  Verdict: {latestObservation.verdict} · Baseline {formatNumber(latestObservation.metric_baseline)} →
                  {" "}
                  {formatNumber(latestObservation.metric_value)} (Δ {formatNumber(latestObservation.metric_delta)})
                </div>
              ) : (
                <div className={styles.muted}>No observations recorded yet.</div>
              )}
            </div>

            <div className={styles.actions}>
              {plan.status === "draft" && (
                <button type="button" className={styles.primaryButton} onClick={handleActivate}>
                  Activate plan
                </button>
              )}
              {plan.status === "active" && (
                <button type="button" className={styles.secondaryButton} onClick={handleRefresh}>
                  Refresh observation
                </button>
              )}
            </div>

            <div className={styles.section}>
              <div className={styles.label}>Add note</div>
              <textarea
                className={styles.input}
                rows={3}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Add advisor note"
              />
              <button type="button" className={styles.secondaryButton} onClick={handleAddNote}>
                Add note
              </button>
            </div>

            {plan.status !== "succeeded" && plan.status !== "failed" && plan.status !== "canceled" && (
              <div className={styles.section}>
                <div className={styles.label}>Close plan</div>
                <div className={styles.row}>
                  <select
                    className={styles.select}
                    value={closeOutcome}
                    onChange={(event) => setCloseOutcome(event.target.value as PlanCloseOutcome)}
                  >
                    <option value="succeeded">Succeeded</option>
                    <option value="failed">Failed</option>
                    <option value="canceled">Canceled</option>
                  </select>
                  <button type="button" className={styles.secondaryButton} onClick={handleClose}>
                    Close plan
                  </button>
                </div>
                <textarea
                  className={styles.input}
                  rows={2}
                  value={closeNote}
                  onChange={(event) => setCloseNote(event.target.value)}
                  placeholder="Optional close note"
                />
              </div>
            )}

            <div className={styles.section}>
              <div className={styles.label}>Audit trail</div>
              {detail.state_events.length === 0 && <div className={styles.muted}>No events logged yet.</div>}
              <div className={styles.auditList}>
                {detail.state_events.map((event) => (
                  <div key={event.id} className={styles.auditItem}>
                    <div>
                      {event.event_type}
                      {event.from_status ? ` · ${event.from_status} → ${event.to_status}` : ""}
                    </div>
                    <div className={styles.muted}>{formatTimestamp(event.created_at)}</div>
                    {event.note && <div>Note: {event.note}</div>}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </Drawer>
  );
}
