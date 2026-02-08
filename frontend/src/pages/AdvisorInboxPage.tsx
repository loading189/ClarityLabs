import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchActionTriage, refreshActions, type ActionTriageItem } from "../api/actions";
import { ApiError } from "../api/client";
import { useAuth } from "../app/auth/AuthContext";
import PageHeader from "../components/common/PageHeader";
import { Button, Chip, EmptyState, InlineAlert, LoadingState, Panel } from "../components/ui";
import ActionDetailDrawer from "../features/actions/ActionDetailDrawer";
import {
  formatObservationSummary,
  formatPlanStatus,
  formatVerdict,
  planStatusTone,
  verdictTone,
} from "../features/plans/planSummary";
import { ensurePlanSummaries, readPlanSummary } from "../features/plans/planSummaryCache";
import { useBusinessesMine } from "../hooks/useBusinessesMine";
import type { PlanSummary } from "../api/plansV2";
import { ledgerPath } from "../app/routes/routeUtils";
import styles from "./AdvisorInboxPage.module.css";

type AssignedFilter = "me" | "unassigned" | "any";
type StatusFilter = "open" | "snoozed" | "done" | "ignored";

type LoadError = { message: string; status?: number };

function formatDate(value: string) {
  return value.split("T")[0];
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatPriority(priority: number) {
  if (priority >= 5) return "Critical";
  if (priority >= 4) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
}

function priorityTone(priority: number) {
  if (priority >= 5) return "danger" as const;
  if (priority >= 4) return "warning" as const;
  if (priority >= 3) return "info" as const;
  return "neutral" as const;
}

function statusTone(status: StatusFilter) {
  if (status === "done") return "success" as const;
  if (status === "snoozed") return "warning" as const;
  if (status === "ignored") return "neutral" as const;
  return "info" as const;
}

export default function AdvisorInboxPage() {
  const { businesses } = useBusinessesMine();
  const { user, logout } = useAuth();
  const [status, setStatus] = useState<StatusFilter>("open");
  const [assigned, setAssigned] = useState<AssignedFilter>("any");
  const [businessId, setBusinessId] = useState<string>("all");
  const [actions, setActions] = useState<ActionTriageItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<LoadError | null>(null);
  const [refreshError, setRefreshError] = useState<LoadError | null>(null);
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [selected, setSelected] = useState<ActionTriageItem | null>(null);
  const [planSummaries, setPlanSummaries] = useState<Map<string, PlanSummary>>(new Map());
  const [planSummaryError, setPlanSummaryError] = useState<LoadError | null>(null);
  const [planSummaryLoading, setPlanSummaryLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchActionTriage(businessId, { status, assigned });
      setActions(response.actions ?? []);
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      if (import.meta.env.DEV) {
        console.error("Failed to load advisor inbox", err);
      }
      setError({ message: err?.message ?? "Failed to load advisor inbox", status: err?.status });
    } finally {
      setLoading(false);
    }
  }, [assigned, businessId, logout, status]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (businessId !== "all" || businesses.length === 0) return;
    setBusinessId(businesses[0]?.business_id ?? "all");
  }, [businessId, businesses]);

  useEffect(() => {
    const planIds = actions.map((action) => action.plan_id).filter(Boolean) as string[];
    if (!planIds.length) {
      setPlanSummaries(new Map());
      return;
    }
    let active = true;
    setPlanSummaryLoading(true);
    setPlanSummaryError(null);
    ensurePlanSummaries(planIds)
      .then((map) => {
        if (active) setPlanSummaries(map);
      })
      .catch((err: any) => {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        if (import.meta.env.DEV) {
          console.error("Failed to load plan summaries", err);
        }
        setPlanSummaryError({ message: err?.message ?? "Failed to load plan summaries", status: err?.status });
      })
      .finally(() => {
        if (active) setPlanSummaryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [actions, logout]);

  const businessOptions = useMemo(() => {
    return [
      { business_id: "all", business_name: "All businesses" },
      ...businesses,
    ];
  }, [businesses]);

  const canRefreshActions = businessId !== "all";

  const handleRefreshActions = useCallback(async () => {
    if (!canRefreshActions) {
      const message = "Select a specific business to refresh actions.";
      setRefreshError({ message, status: 400 });
      if (import.meta.env.DEV) {
        console.warn("Refresh actions requires a specific business_id.");
      }
      return;
    }
    setRefreshLoading(true);
    setRefreshError(null);
    try {
      await refreshActions(businessId);
      await load();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      if (import.meta.env.DEV) {
        console.error("Failed to refresh actions", err);
      }
      setRefreshError({ message: err?.message ?? "Failed to refresh actions", status: err?.status });
    } finally {
      setRefreshLoading(false);
    }
  }, [businessId, canRefreshActions, load, logout]);

  const ledgerLink = useMemo(() => {
    if (!canRefreshActions) return null;
    return ledgerPath(businessId, {});
  }, [businessId, canRefreshActions]);

  const renderPlanSummary = (action: ActionTriageItem) => {
    if (!action.plan_id) {
      return (
        <div className={styles.planMeta}>
          <Chip tone="neutral">No plan</Chip>
          <span className={styles.metaText}>No outcome yet</span>
        </div>
      );
    }
    const summary = planSummaries.get(action.plan_id) ?? readPlanSummary(action.plan_id);
    if (!summary) {
      return (
        <div className={styles.planMeta}>
          <Chip tone="neutral">Plan linked</Chip>
          <span className={styles.metaText}>{planSummaryLoading ? "Loading outcome…" : "Outcome pending"}</span>
        </div>
      );
    }
    const latest = summary.latest_observation;
    return (
      <div className={styles.planMeta}>
        <Chip tone={planStatusTone(summary.status)}>{formatPlanStatus(summary.status)}</Chip>
        <Chip tone={verdictTone(latest?.verdict)}>{formatVerdict(latest?.verdict)}</Chip>
        <span className={styles.metaText}>
          {latest ? `Last checked ${formatTimestamp(latest.observed_at)}` : "No check yet"}
        </span>
      </div>
    );
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="Advisor Inbox"
        subtitle="Triage actions across assigned clients and track plan outcomes."
        actions={
          <div className={styles.filters}>
            <select
              className={styles.select}
              value={status}
              onChange={(event) => setStatus(event.target.value as StatusFilter)}
            >
              <option value="open">Open</option>
              <option value="snoozed">Snoozed</option>
              <option value="done">Done</option>
              <option value="ignored">Ignored</option>
            </select>
            <select
              className={styles.select}
              value={assigned}
              onChange={(event) => setAssigned(event.target.value as AssignedFilter)}
            >
              <option value="any">Any assignment</option>
              <option value="me">Assigned to me</option>
              <option value="unassigned">Unassigned</option>
            </select>
            <select
              className={styles.select}
              value={businessId}
              onChange={(event) => setBusinessId(event.target.value)}
            >
              {businessOptions.map((biz) => (
                <option key={biz.business_id} value={biz.business_id}>
                  {biz.business_name}
                </option>
              ))}
            </select>
            <Button type="button" onClick={() => void load()}>
              Refresh
            </Button>
          </div>
        }
      />

      {loading && <LoadingState label="Loading actions…" rows={4} />}

      {error?.status === 403 && (
        <EmptyState
          title="You don’t have access"
          description="Ask an admin to grant access to this business." 
        />
      )}

      {error && error.status !== 403 && (
        <InlineAlert
          tone="error"
          title="Unable to load inbox"
          description={error.message}
          action={<Button onClick={() => void load()}>Retry</Button>}
        />
      )}

      {refreshError && (
        <InlineAlert
          tone="error"
          title="Unable to refresh actions"
          description={refreshError.message}
          action={<Button onClick={() => void handleRefreshActions()}>Retry refresh</Button>}
        />
      )}

      {planSummaryError && (
        <InlineAlert
          tone="error"
          title="Plan summaries unavailable"
          description={planSummaryError.message}
        />
      )}

      {!loading && !error && actions.length === 0 && (
        <EmptyState
          title="No open actions yet for this business."
          description="Actions appear after signals are evaluated."
          action={
            <div className={styles.emptyActions}>
              <Button
                variant="primary"
                onClick={() => void handleRefreshActions()}
                disabled={!canRefreshActions || refreshLoading}
              >
                {refreshLoading ? "Refreshing Actions…" : "Refresh Actions"}
              </Button>
              {ledgerLink && (
                <a className={styles.secondaryLink} href={ledgerLink}>
                  Go to Ledger
                </a>
              )}
            </div>
          }
        />
      )}

      {!loading && actions.length > 0 && (
        <Panel className={styles.list}>
          {actions.map((action) => {
            const assignedLabel =
              action.assigned_to_user?.id && action.assigned_to_user?.id === user?.id
                ? "Me"
                : action.assigned_to_user?.name ??
                  action.assigned_to_user?.email ??
                  (action.assigned_to_user_id ? "Assigned" : "Unassigned");
            const planSummary = action.plan_id
              ? planSummaries.get(action.plan_id) ?? readPlanSummary(action.plan_id)
              : null;
            const latestSummary = action.plan_id
              ? formatObservationSummary(planSummary?.latest_observation)
              : null;

            return (
              <button
                type="button"
                key={action.id}
                className={styles.row}
                onClick={() => setSelected(action)}
              >
                <div className={styles.rowHeader}>
                  <div>
                    <div className={styles.business}>{action.business_name}</div>
                    <div className={styles.title}>{action.title}</div>
                    <div className={styles.summary}>{action.summary}</div>
                  </div>
                  <div className={styles.created}>Created {formatDate(action.created_at)}</div>
                </div>
                <div className={styles.rowChips}>
                  <Chip tone={statusTone(action.status as StatusFilter)}>{action.status}</Chip>
                  <Chip tone={priorityTone(action.priority)}>{formatPriority(action.priority)}</Chip>
                  <Chip tone={assignedLabel === "Unassigned" ? "neutral" : "info"}>{assignedLabel}</Chip>
                  {renderPlanSummary(action)}
                </div>
                {latestSummary && <div className={styles.outcome}>{latestSummary}</div>}
              </button>
            );
          })}
        </Panel>
      )}

      <ActionDetailDrawer
        open={Boolean(selected)}
        action={selected}
        onClose={() => setSelected(null)}
        onUpdated={load}
      />
    </div>
  );
}
