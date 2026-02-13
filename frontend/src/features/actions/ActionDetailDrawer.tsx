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
import {
  closePlan,
  createPlan,
  getPlanDetail,
  refreshPlan,
  type PlanCloseOutcome,
  type PlanDetail,
  type PlanObservation,
} from "../../api/plansV2";
import type { FilterState } from "../../app/filters/filters";
import { ledgerPath } from "../../app/routes/routeUtils";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth/AuthContext";
import { Button, Card, Chip, EmptyState, InlineAlert, KeyValueList, LoadingState, Section } from "../../components/ui";
import {
  formatObservationSummary,
  formatPlanStatus,
  formatVerdict,
  planStatusTone,
  verdictTone,
} from "../plans/planSummary";
import PlanDetailDrawer from "../plans/PlanDetailDrawer";
import styles from "./ActionDetailDrawer.module.css";

const SNOOZE_DAYS = 7;

type ActionDetail = (ActionItem | ActionTriageItem) & {
  business_name?: string;
};

type LoadError = { message: string; status?: number };

type ActivityItem = {
  id: string;
  title: string;
  detail: string;
  timestamp: string;
  note?: string | null;
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

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatPriority(priority?: number | null) {
  if (!priority) return "—";
  if (priority >= 5) return "Critical";
  if (priority >= 4) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
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
  const { logout } = useAuth();
  const [note, setNote] = useState("");
  const [members, setMembers] = useState<BusinessMember[]>([]);
  const [events, setEvents] = useState<ActionStateEvent[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [error, setError] = useState<LoadError | null>(null);
  const [planIntent, setPlanIntent] = useState("");
  const [planError, setPlanError] = useState<LoadError | null>(null);
  const [planCreateLoading, setPlanCreateLoading] = useState(false);
  const [planRefreshLoading, setPlanRefreshLoading] = useState(false);
  const [planIdOverride, setPlanIdOverride] = useState<string | null>(null);
  const [planOpen, setPlanOpen] = useState(false);
  const [planDetail, setPlanDetail] = useState<PlanDetail | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [latestObservationOverride, setLatestObservationOverride] = useState<PlanObservation | null>(null);
  const [planCloseOutcome, setPlanCloseOutcome] = useState<PlanCloseOutcome>("succeeded");
  const [planCloseNote, setPlanCloseNote] = useState("");
  const [showPlanClose, setShowPlanClose] = useState(false);

  const actionId = action?.id;
  const businessId = action?.business_id;
  const planId = planIdOverride ?? action?.plan_id ?? null;

  const loadMembers = useCallback(async () => {
    if (!businessId) return;
    setLoadingMembers(true);
    try {
      const response = await fetchBusinessMembers(businessId);
      setMembers(response ?? []);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to load members", status: err?.status });
    } finally {
      setLoadingMembers(false);
    }
  }, [businessId, logout]);

  const loadEvents = useCallback(async () => {
    if (!businessId || !actionId) return;
    setLoadingEvents(true);
    try {
      const response = await fetchActionEvents(businessId, actionId);
      setEvents(response ?? []);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to load audit trail", status: err?.status });
    } finally {
      setLoadingEvents(false);
    }
  }, [actionId, businessId, logout]);

  const loadPlan = useCallback(async () => {
    if (!businessId || !planId) return;
    setLoadingPlan(true);
    try {
      const response = await getPlanDetail(businessId, planId);
      setPlanDetail(response);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setPlanError({ message: err?.message ?? "Failed to load plan", status: err?.status });
    } finally {
      setLoadingPlan(false);
    }
  }, [businessId, logout, planId]);

  useEffect(() => {
    if (!open || !businessId) return;
    void loadMembers();
  }, [loadMembers, open, businessId]);

  useEffect(() => {
    if (!open || !businessId || !actionId) return;
    void loadEvents();
  }, [actionId, businessId, loadEvents, open]);

  useEffect(() => {
    if (!open || !planId) return;
    void loadPlan();
  }, [loadPlan, open, planId]);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setNote(action?.resolution_note ?? "");
    setPlanIntent("");
    setPlanError(null);
    setPlanCreateLoading(false);
    setPlanRefreshLoading(false);
    setPlanIdOverride(null);
    setPlanDetail(null);
    setLatestObservationOverride(null);
    setShowPlanClose(false);
  }, [action?.resolution_note, open]);

  useEffect(() => {
    if (!open) return;
    if (!businessId || !actionId) {
      console.warn("ActionDetailDrawer missing business_id or action_id; disabling plan actions.");
    }
    if (!planId && action?.plan_id == null) {
      return;
    }
    if (planId && !businessId) {
      console.warn("ActionDetailDrawer missing business_id for plan actions.");
    }
  }, [action?.plan_id, actionId, businessId, open, planId]);

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

  const assignedLabel = useMemo(() => {
    if (!assignedTo) return "Unassigned";
    const member = members.find((candidate) => candidate.id === assignedTo);
    return member?.name ?? member?.email ?? "Assigned";
  }, [assignedTo, members]);

  const planAssignedLabel = useMemo(() => {
    const planAssigned = planDetail?.plan.assigned_to_user_id;
    if (!planAssigned) return "Unassigned";
    const member = members.find((candidate) => candidate.id === planAssigned);
    return member?.name ?? member?.email ?? "Assigned";
  }, [members, planDetail?.plan.assigned_to_user_id]);

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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to update assignment", status: err?.status });
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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to update action", status: err?.status });
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
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError({ message: err?.message ?? "Failed to snooze action", status: err?.status });
    }
  };

  const handleCreatePlan = async () => {
    if (!businessId || !actionId || !action) return;
    if (!planIntent.trim()) {
      setPlanError({ message: "Add a plan intent before creating.", status: 400 });
      return;
    }
    setPlanError(null);
    const conditions = [
      {
        type: "signal_resolved" as const,
        signal_id: action.source_signal_id ?? null,
        baseline_window_days: 0,
        evaluation_window_days: 14,
        direction: "resolve" as const,
      },
    ];
    setPlanCreateLoading(true);
    try {
      const response = await createPlan({
        business_id: businessId,
        title: action.title,
        intent: planIntent.trim(),
        source_action_id: actionId,
        primary_signal_id: action.source_signal_id ?? undefined,
        assigned_to_user_id: action.assigned_to_user_id ?? undefined,
        conditions,
      });
      setPlanIdOverride(response.plan.id);
      setPlanDetail(response);
      setPlanOpen(true);
      onUpdated?.();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setPlanError({ message: err?.message ?? "Failed to create plan", status: err?.status });
    } finally {
      setPlanCreateLoading(false);
    }
  };

  const handlePlanRefresh = async () => {
    if (!businessId || !planId) return;
    setPlanError(null);
    setPlanRefreshLoading(true);
    try {
      const response = await refreshPlan(businessId, planId);
      setLatestObservationOverride(response.observation);
      setPlanDetail((current) => {
        if (!current) return current;
        const nextObservation: PlanObservation = response.observation;
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
      setPlanError({ message: err?.message ?? "Failed to refresh plan", status: err?.status });
    } finally {
      setPlanRefreshLoading(false);
    }
  };

  const handlePlanClose = async () => {
    if (!businessId || !planId) return;
    setPlanError(null);
    try {
      const response = await closePlan(businessId, planId, {
        outcome: planCloseOutcome,
        note: planCloseNote || undefined,
      });
      setPlanDetail(response);
      setShowPlanClose(false);
      setPlanCloseNote("");
      onUpdated?.();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setPlanError({ message: err?.message ?? "Failed to close plan", status: err?.status });
    }
  };

  const activityItems = useMemo(() => {
    const combined: ActivityItem[] = [];
    events.forEach((event) => {
      combined.push({
        id: `action-${event.id}`,
        title: "Action status updated",
        detail: `${event.from_status} → ${event.to_status}`,
        timestamp: event.created_at,
        note: event.note ?? null,
      });
    });
    planDetail?.state_events.forEach((event) => {
      combined.push({
        id: `plan-${event.id}`,
        title: "Plan event",
        detail: event.event_type + (event.from_status ? ` · ${event.from_status} → ${event.to_status}` : ""),
        timestamp: event.created_at,
        note: event.note ?? null,
      });
    });
    return combined.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [events, planDetail?.state_events]);

  const evidenceAnchors = Array.isArray(action?.evidence_json?.ledger_anchors)
    ? action?.evidence_json?.ledger_anchors
    : [];
  const evidenceSummary = action?.evidence_json?.summary ?? action?.evidence_json?.reason ?? "—";
  const canCreatePlan = Boolean(businessId && actionId);
  const canViewPlan = Boolean(planId && businessId);
  const canRefreshPlan = Boolean(planId && businessId && planDetail?.plan.status === "active");
  const planHelpText = !canCreatePlan
    ? "Plan actions need a business and action id."
    : !planIntent.trim() && !planId
      ? "Add a plan intent to enable plan creation."
      : null;
  const handleOpenPlan = async () => {
    if (!canViewPlan) return;
    if (!planDetail) {
      await loadPlan();
    }
    setPlanOpen(true);
  };

  return (
    <Drawer open={open} title={action?.title ?? "Action detail"} onClose={onClose}>
      {action && (
        <div className={styles.content}>
          {error?.status === 403 && (
            <EmptyState title="You don’t have access" description="Ask an admin to grant access to this action." />
          )}
          {error && error.status !== 403 && (
            <InlineAlert
              tone="error"
              title="Unable to load action details"
              description={error.message}
            />
          )}

          <Section title="Summary" subtitle="Case summary and current status.">
            <Card className={styles.card}>
              <div className={styles.summaryText}>{action.summary}</div>
              <div className={styles.summaryMeta}>Created {formatTimestamp(action.created_at)}</div>
            </Card>
            <KeyValueList
              items={[
                { label: "Status", value: action.status },
                { label: "Priority", value: formatPriority(action.priority) },
                { label: "Assigned to", value: assignedLabel },
                { label: "Due", value: formatTimestamp(action.due_at) },
              ]}
            />

          </Section>

          <Section title="Evidence" subtitle="Signals and ledger anchors that informed this action.">
            <KeyValueList
              items={[
                { label: "Signal", value: action.source_signal_id ?? "—" },
                { label: "Ledger anchors", value: evidenceAnchors.length || "—" },
                { label: "Evidence summary", value: evidenceSummary },
              ]}
            />
            <div className={styles.linkRow}>
              {ledgerLink && (
                <Link className={styles.linkButton} to={ledgerLink}>
                  View in Ledger →
                </Link>
              )}
              {action.source_signal_id && businessId && (
                <Link className={styles.linkButton} to={`/app/${businessId}/signals?signal_id=${action.source_signal_id}`}>
                  Open Signal →
                </Link>
              )}
            </div>
          </Section>

          <Section title="Plan timeline & history" subtitle="Remediation progress, checks, and case history.">
            {planError && (
              <InlineAlert tone="error" title="Plan update failed" description={planError.message} />
            )}
            {planHelpText && <div className={styles.planHelp}>{planHelpText}</div>}
            {planId && !canViewPlan && (
              <InlineAlert
                tone="info"
                title="Plan actions unavailable"
                description="Select a business to view and refresh the linked plan."
              />
            )}
            {!planId && (
              <Card className={styles.planCard}>
                <div className={styles.planTitle}>Create a remediation plan</div>
                <div className={styles.planMeta}>
                  Plans track the remediation outcome for this action and surface observations after refresh.
                </div>
                <textarea
                  className={styles.input}
                  rows={3}
                  value={planIntent}
                  onChange={(event) => setPlanIntent(event.target.value)}
                  placeholder="Document the plan intent and why it matters"
                />
                <Button variant="primary" onClick={handleCreatePlan} disabled={!canCreatePlan || planCreateLoading}>
                  {planCreateLoading ? "Creating Plan…" : "Create Plan"}
                </Button>
              </Card>
            )}
            {planId && loadingPlan && <LoadingState label="Loading plan summary…" rows={2} />}
            {planId && !loadingPlan && planDetail && (
              <Card className={styles.planCard}>
                <div className={styles.planHeader}>
                  <div>
                    <div className={styles.planTitle}>{planDetail.plan.title}</div>
                    <div className={styles.planMeta}>Assigned to {planAssignedLabel}</div>
                  </div>
                  <Chip tone={planStatusTone(planDetail.plan.status)}>
                    {formatPlanStatus(planDetail.plan.status)}
                  </Chip>
                </div>
                <div className={styles.planObservation}>
                  <div className={styles.planObservationSummary} data-testid="plan-observation-summary">
                    {formatObservationSummary(
                      latestObservationOverride ?? planDetail.latest_observation,
                      planDetail.conditions
                    )}
                  </div>
                  <div className={styles.planObservationMeta}>
                    <Chip tone={verdictTone((latestObservationOverride ?? planDetail.latest_observation)?.verdict)}>
                      {formatVerdict((latestObservationOverride ?? planDetail.latest_observation)?.verdict)}
                    </Chip>
                    <span>
                      Last checked {formatTimestamp((latestObservationOverride ?? planDetail.latest_observation)?.observed_at)}
                    </span>
                  </div>
                </div>
                <div className={styles.planActions}>
                  <Button variant="secondary" onClick={handleOpenPlan} disabled={!canViewPlan}>
                    View Plan
                  </Button>
                  {planDetail.plan.status === "active" && (
                    <Button variant="secondary" onClick={handlePlanRefresh} disabled={!canRefreshPlan || planRefreshLoading}>
                      {planRefreshLoading ? "Refreshing…" : "Refresh"}
                    </Button>
                  )}
                  {planDetail.plan.status !== "succeeded" &&
                    planDetail.plan.status !== "failed" &&
                    planDetail.plan.status !== "canceled" && (
                      <Button variant="ghost" onClick={() => setShowPlanClose((prev) => !prev)}>
                        Close
                      </Button>
                    )}
                </div>
                {showPlanClose && (
                  <div className={styles.planClose}>
                    <select
                      className={styles.select}
                      value={planCloseOutcome}
                      onChange={(event) => setPlanCloseOutcome(event.target.value as PlanCloseOutcome)}
                    >
                      <option value="succeeded">Succeeded</option>
                      <option value="failed">Failed</option>
                      <option value="canceled">Canceled</option>
                    </select>
                    <textarea
                      className={styles.input}
                      rows={2}
                      value={planCloseNote}
                      onChange={(event) => setPlanCloseNote(event.target.value)}
                      placeholder="Optional close note"
                    />
                    <Button variant="secondary" onClick={handlePlanClose}>
                      Confirm close
                    </Button>
                  </div>
                )}
              </Card>
            )}
          </Section>

          <Section title="Controls" subtitle="Assign, snooze, and resolve this case.">
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
              <Chip tone={assignedTo ? "info" : "neutral"}>{assignedLabel}</Chip>
            </div>
            <div className={styles.actions}>
              <Button variant="primary" onClick={() => handleResolve("done")}>
                Mark done
              </Button>
              <Button variant="secondary" onClick={() => handleResolve("ignored")}>
                Ignore
              </Button>
              <Button variant="secondary" onClick={handleSnooze}>
                Snooze 7d
              </Button>
            </div>
            <textarea
              className={styles.input}
              rows={3}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Add control note for the audit trail"
            />
            {loadingEvents && <LoadingState label="Loading activity…" rows={2} />}
            {!loadingEvents && activityItems.length === 0 && (
              <EmptyState title="No activity yet" description="Action updates will appear here as the case progresses." />
            )}
            <div className={styles.auditList}>
              {activityItems.map((event) => (
                <div key={event.id} className={styles.auditItem}>
                  <div className={styles.auditTitle}>{event.title}</div>
                  <div>{event.detail}</div>
                  <div className={styles.muted}>{formatTimestamp(event.timestamp)}</div>
                  {event.note && <div>Note: {event.note}</div>}
                </div>
              ))}
            </div>
          </Section>
        </div>
      )}

      <PlanDetailDrawer
        open={planOpen}
        planId={planId}
        businessId={businessId}
        onClose={() => setPlanOpen(false)}
        onUpdated={onUpdated}
      />
    </Drawer>
  );
}
