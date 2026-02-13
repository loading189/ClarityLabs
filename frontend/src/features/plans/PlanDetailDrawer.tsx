import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Drawer from "../../components/common/Drawer";
import { fetchBusinessMembers, type BusinessMember } from "../../api/businesses";
import {
  activatePlan,
  addPlanNote,
  assignPlan,
  closePlan,
  getPlanDetail,
  refreshPlan,
  type PlanCloseOutcome,
  type PlanDetail,
  type PlanObservation,
} from "../../api/plansV2";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth/AuthContext";
import { Button, Card, Chip, EmptyState, InlineAlert, LoadingState, Section } from "../../components/ui";
import {
  formatObservationSummary,
  formatObservationWindow,
  formatPlanStatus,
  formatVerdict,
  planStatusTone,
  verdictTone,
} from "./planSummary";
import styles from "./PlanDetailDrawer.module.css";

type LoadError = { message: string; status?: number };

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
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
  const { logout } = useAuth();
  const [detail, setDetail] = useState<PlanDetail | null>(null);
  const [members, setMembers] = useState<BusinessMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<LoadError | null>(null);
  const [latestObservationOverride, setLatestObservationOverride] = useState<PlanObservation | null>(null);
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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to load plan", status: err?.status });
    } finally {
      setLoading(false);
    }
  }, [businessId, logout, planId]);

  const loadMembers = useCallback(async () => {
    if (!businessId) return;
    try {
      const response = await fetchBusinessMembers(businessId);
      setMembers(response ?? []);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to load members", status: err?.status });
    }
  }, [businessId, logout]);

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
    setLatestObservationOverride(null);
  }, [open, planId]);

  const plan = detail?.plan;
  const latestObservation: PlanObservation | null =
    latestObservationOverride ?? detail?.latest_observation ?? null;

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

  const assignedMember = members.find((member) => member.id === plan?.assigned_to_user_id);
  const assignedLabel = assignedMember?.name ?? assignedMember?.email ?? "Unassigned";

  const orderedObservations = useMemo(() => {
    if (!detail?.observations) return [];
    return [...detail.observations].sort((a, b) => {
      const aTime = a.observed_at ? new Date(a.observed_at).getTime() : 0;
      const bTime = b.observed_at ? new Date(b.observed_at).getTime() : 0;
      return aTime - bTime;
    });
  }, [detail?.observations]);

  const handleActivate = async () => {
    if (!planId || !businessId) return;
    setError(null);
    try {
      await activatePlan(businessId, planId);
      await loadPlan();
      onUpdated?.();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to activate plan", status: err?.status });
    }
  };

  const handleRefresh = async () => {
    if (!planId || !businessId) return;
    setError(null);
    try {
      const response = await refreshPlan(businessId, planId);
      setLatestObservationOverride(response.observation);
      setDetail((current) => {
        if (!current) return current;
        const nextObservation = response.observation;
        const existing = current.observations.filter((obs) => obs.id !== nextObservation.id);
        return {
          ...current,
          latest_observation: nextObservation,
          observations: [nextObservation, ...existing],
        };
      });
      onUpdated?.();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to refresh plan", status: err?.status });
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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to update assignment", status: err?.status });
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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to add note", status: err?.status });
    }
  };

  const handleClose = async () => {
    if (!planId || !businessId) return;
    setError(null);
    try {
      const response = await closePlan(businessId, planId, { outcome: closeOutcome, note: closeNote || undefined });
      setDetail(response);
      onUpdated?.();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to close plan", status: err?.status });
    }
  };

  return (
    <Drawer open={open} title={plan?.title ?? "Plan detail"} onClose={onClose}>
      <div className={styles.content}>
        {error?.status === 403 && (
          <EmptyState title="You don’t have access" description="Ask an admin to grant plan access." />
        )}
        {error && error.status !== 403 && (
          <InlineAlert tone="error" title="Plan update failed" description={error.message} />
        )}
        {loading && <LoadingState label="Loading plan details…" rows={3} />}

        {plan && (
          <>
            <div className={styles.header}>
              <div>
                <div className={styles.title}>{plan.title}</div>
                <div className={styles.subtitle}>Assigned to {assignedLabel}</div>
                <div className={styles.subtitle}>
                  Attached to Action:{" "}
                  {plan.source_action_id && businessId ? (
                    <Link to={`/app/${businessId}/inbox?action_id=${encodeURIComponent(plan.source_action_id)}`}>
                      {plan.source_action_id}
                    </Link>
                  ) : (
                    "—"
                  )}
                </div>
                <div className={styles.subtitle}>
                  Created from Signal:{" "}
                  {plan.primary_signal_id && businessId ? (
                    <Link to={`/app/${businessId}/signals?signal_id=${encodeURIComponent(plan.primary_signal_id)}`}>
                      {plan.primary_signal_id}
                    </Link>
                  ) : (
                    "—"
                  )}
                </div>
              </div>
              <Chip tone={planStatusTone(plan.status)}>{formatPlanStatus(plan.status)}</Chip>
            </div>

            <Section title="Latest outcome" subtitle="Most recent observation summary and verdict.">
              <Card className={styles.outcomeCard}>
                <div className={styles.outcomeSummary}>
                  {formatObservationSummary(latestObservation, detail.conditions)}
                </div>
                <div className={styles.outcomeMeta}>
                  <Chip tone={verdictTone(latestObservation?.verdict)}>{formatVerdict(latestObservation?.verdict)}</Chip>
                  <span>Last checked {formatTimestamp(latestObservation?.observed_at)}</span>
                  <span>Window {formatObservationWindow(latestObservation)}</span>
                </div>
              </Card>
            </Section>

            <Section title="Primary actions">
              <div className={styles.actions}>
                {plan.status === "draft" && (
                  <Button variant="primary" onClick={handleActivate}>
                    Activate plan
                  </Button>
                )}
                {plan.status === "active" && (
                  <Button variant="secondary" onClick={handleRefresh}>
                    Refresh
                  </Button>
                )}
                <Button variant="secondary" onClick={handleAddNote}>
                  Add note
                </Button>
                {plan.status !== "succeeded" && plan.status !== "failed" && plan.status !== "canceled" && (
                  <Button variant="ghost" onClick={handleClose}>
                    Close plan
                  </Button>
                )}
              </div>
            </Section>

            <Section title="Intent">
              <Card className={styles.textCard}>{plan.intent}</Card>
            </Section>

            <Section title="Conditions">
              <Card className={styles.textCard}>{conditionSummary}</Card>
            </Section>

            <Section title="Assignment">
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
            </Section>

            <Section title="Add note">
              <textarea
                className={styles.input}
                rows={3}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Add advisor note"
              />
            </Section>

            {plan.status !== "succeeded" && plan.status !== "failed" && plan.status !== "canceled" && (
              <Section title="Close plan">
                <div className={styles.closeRow}>
                  <select
                    className={styles.select}
                    value={closeOutcome}
                    onChange={(event) => setCloseOutcome(event.target.value as PlanCloseOutcome)}
                  >
                    <option value="succeeded">Succeeded</option>
                    <option value="failed">Failed</option>
                    <option value="canceled">Canceled</option>
                  </select>
                  <textarea
                    className={styles.input}
                    rows={2}
                    value={closeNote}
                    onChange={(event) => setCloseNote(event.target.value)}
                    placeholder="Optional close note"
                  />
                </div>
              </Section>
            )}

            <Section title="Observation history" subtitle="Chronological tracking of plan checks.">
              <div className={styles.historyHeader}>
                Last checked {formatTimestamp(latestObservation?.observed_at)}
              </div>
              {detail.observations.length === 0 && (
                <EmptyState
                  title="No observations yet"
                  description="Run a refresh to capture the first observation." 
                />
              )}
              <div className={styles.historyList}>
                {orderedObservations.map((observation) => (
                  <Card key={observation.id} className={styles.historyItem}>
                    <div className={styles.historySummary}>
                      {formatObservationSummary(observation, detail.conditions)}
                    </div>
                    <div className={styles.historyMeta}>
                      <Chip tone={verdictTone(observation.verdict)}>{formatVerdict(observation.verdict)}</Chip>
                      <span>{formatTimestamp(observation.observed_at)}</span>
                      <span>Window {formatObservationWindow(observation)}</span>
                    </div>
                  </Card>
                ))}
              </div>
            </Section>

            <Section title="Plan events" subtitle="Audit trail for the plan lifecycle.">
              {detail.state_events.length === 0 && (
                <EmptyState title="No events logged yet" description="Plan activity will appear here." />
              )}
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
            </Section>
          </>
        )}
      </div>
    </Drawer>
  );
}
