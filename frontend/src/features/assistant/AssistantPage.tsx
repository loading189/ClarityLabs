import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchAssistantThread, postAssistantMessage, type AssistantThreadMessage } from "../../api/assistantThread";
import { publishDailyBrief, type DailyBriefOut, type DailyBriefPlaybook } from "../../api/dailyBrief";
import { listChanges, type ChangeEvent } from "../../api/changes";
import {
  fetchHealthScore,
  fetchHealthScoreExplainChange,
  type HealthScoreExplainChangeOut,
  type HealthScoreOut,
} from "../../api/healthScore";
import {
  getSignalExplain,
  listSignalStates,
  updateSignalStatus,
  type SignalExplainOut,
  type SignalState,
} from "../../api/signals";
import { useAppState } from "../../app/state/appState";
import { addPlanNote, createPlan, listPlans, markPlanStepDone, updatePlanStatus, verifyPlan, type ResolutionPlan, type ResolutionPlanVerify } from "../../api/plans";
import { fetchAssistantProgress, type AssistantProgress } from "../../api/progress";
import { fetchWorkQueue, type WorkQueueItem } from "../../api/workQueue";
import styles from "./AssistantPage.module.css";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function severityScore(severity?: string | null) {
  if (severity === "critical") return 3;
  if (severity === "warning") return 2;
  return 1;
}

function actionToStatus(action: SignalExplainOut["next_actions"][number]["action"]) {
  if (action === "acknowledge") return "in_progress" as const;
  if (action === "snooze") return "ignored" as const;
  if (action === "resolve") return "resolved" as const;
  return "in_progress" as const;
}

function verificationLabel(status: "met" | "not_met" | "unknown") {
  if (status === "met") return "Met";
  if (status === "not_met") return "Not met";
  return "Unknown";
}

function playbookIcon(kind: "inspect" | "adjust" | "decide") {
  if (kind === "inspect") return "🔎";
  if (kind === "adjust") return "🛠️";
  return "✅";
}

export default function AssistantPage() {
  const { businessId: businessIdParam } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const businessId = businessIdParam?.trim() || searchParams.get("businessId")?.trim() || "";
  const initialSignalId = searchParams.get("signalId")?.trim() || null;
  const createPlanSignalId = searchParams.get("createPlanSignalId")?.trim() || null;
  const initialPlanId = searchParams.get("planId")?.trim() || null;
  const { setActiveBusinessId } = useAppState();

  const [signals, setSignals] = useState<SignalState[]>([]);
  const [changes, setChanges] = useState<ChangeEvent[]>([]);
  const [healthScore, setHealthScore] = useState<HealthScoreOut | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(initialSignalId);
  const [explain, setExplain] = useState<SignalExplainOut | null>(null);
  const [thread, setThread] = useState<AssistantThreadMessage[]>([]);
  const [scoreExplain, setScoreExplain] = useState<HealthScoreExplainChangeOut | null>(null);
  const [changesError, setChangesError] = useState<string | null>(null);
  const [scoreExplainError, setScoreExplainError] = useState<string | null>(null);
  const [dailyBrief, setDailyBrief] = useState<DailyBriefOut | null>(null);
  const [actor, setActor] = useState("analyst");
  const [reason, setReason] = useState("");
  const [showCompletionPrompt, setShowCompletionPrompt] = useState(false);
  const [plans, setPlans] = useState<ResolutionPlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(initialPlanId);
  const [planNoteText, setPlanNoteText] = useState("");
  const [progress, setProgress] = useState<AssistantProgress | null>(null);
  const [workQueue, setWorkQueue] = useState<WorkQueueItem[]>([]);
  const [planVerification, setPlanVerification] = useState<ResolutionPlanVerify | null>(null);
  const resumedRef = useRef(false);
  const planStepRefs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => setActiveBusinessId(businessId || null), [businessId, setActiveBusinessId]);

  useEffect(() => {
    resumedRef.current = false;
  }, [businessId]);

  const loadAll = useCallback(async (signal?: AbortSignal) => {
    if (!businessId) return;
    setChangesError(null);
    setScoreExplainError(null);
    const [signalsResult, scoreResult, changesResult, scoreChangeResult] = await Promise.allSettled([
      listSignalStates(businessId, signal),
      fetchHealthScore(businessId, signal),
      listChanges(businessId, 10, signal),
      fetchHealthScoreExplainChange(businessId, 72, 20, signal),
    ]);
    if (signal?.aborted) return;
    if (signalsResult.status === "fulfilled") {
      setSignals(signalsResult.value.signals ?? []);
    } else {
      setSignals([]);
    }
    if (scoreResult.status === "fulfilled") {
      setHealthScore(scoreResult.value);
    } else {
      setHealthScore(null);
    }
    if (changesResult.status === "fulfilled") {
      setChanges(changesResult.value ?? []);
    } else {
      setChanges([]);
      setChangesError("Couldn't load changes.");
    }
    if (scoreChangeResult.status === "fulfilled") {
      setScoreExplain(scoreChangeResult.value);
    } else {
      setScoreExplain(null);
      setScoreExplainError("Couldn't load explanation.");
    }
  }, [businessId]);

  const loadThread = useCallback(async (signal?: AbortSignal) => {
    if (!businessId) return;
    try {
      const rows = await fetchAssistantThread(businessId, 200, signal);
      if (signal?.aborted) return;
      setThread(rows);
    } catch {
      if (signal?.aborted) return;
      setThread([]);
    }
  }, [businessId]);


  const loadPlans = useCallback(async (signal?: AbortSignal) => {
    if (!businessId) return;
    try {
      const rows = await listPlans(businessId, signal);
      if (signal?.aborted) return;
      setPlans(rows);
      setSelectedPlanId((prev) => prev ?? initialPlanId ?? rows[0]?.plan_id ?? null);
    } catch {
      if (signal?.aborted) return;
      setPlans([]);
    }
  }, [businessId, initialPlanId]);

  const loadWorkQueue = useCallback(async (signal?: AbortSignal) => {
    if (!businessId) return;
    try {
      const queue = await fetchWorkQueue(businessId, 50, signal);
      if (signal?.aborted) return;
      setWorkQueue(queue.items ?? []);
    } catch {
      if (signal?.aborted) return;
      setWorkQueue([]);
    }
  }, [businessId]);

const loadDailyBrief = useCallback(async (signal?: AbortSignal) => {
  if (!businessId) return;

  // Daily brief should not block progress
  try {
    const result = await publishDailyBrief(businessId);
    if (signal?.aborted) return;
    setDailyBrief(result.brief);
  } catch {
    if (signal?.aborted) return;
    setDailyBrief(null);
  }

  // Progress should load even if daily brief fails
  try {
    const progressData = await fetchAssistantProgress(businessId, 7, signal);
    if (signal?.aborted) return;
    setProgress(progressData);
  } catch {
    if (signal?.aborted) return;
    // keep whatever progress we already had instead of wiping it
    // OR: setProgress(null) if you want explicit empty-state
  }
}, [businessId]);


  useEffect(() => {
    const controller = new AbortController();
    void loadDailyBrief(controller.signal);
    void loadAll(controller.signal);
    void loadThread(controller.signal);
    void loadPlans(controller.signal);
    void loadWorkQueue(controller.signal);
    return () => controller.abort();
  }, [loadAll, loadThread, loadDailyBrief, loadPlans, loadWorkQueue]);

  const topPriorities = useMemo(() => {
    const penalties = new Map((healthScore?.contributors ?? []).map((row) => [row.signal_id, row.penalty]));
    return [...signals]
      .filter((signal) => signal.status !== "resolved")
      .map((signal) => ({
        ...signal,
        priority: (penalties.get(signal.id) ?? 0) + severityScore(signal.severity),
      }))
      .sort((a, b) => {
        if (b.priority !== a.priority) return b.priority - a.priority;
        if ((b.severity ?? "").localeCompare(a.severity ?? "") !== 0) return (b.severity ?? "").localeCompare(a.severity ?? "");
        return a.id.localeCompare(b.id);
      })
      .slice(0, 5);
  }, [healthScore?.contributors, signals]);

  const seedThreadIfEmpty = useCallback(async () => {
    if (!businessId || thread.length !== 0 || !healthScore) return;
    await postAssistantMessage(businessId, {
      author: "system",
      kind: "summary",
      content_json: { text: "Here’s what matters right now.", score: healthScore.score },
    });
    await postAssistantMessage(businessId, {
      author: "assistant",
      kind: "priority",
      content_json: { top_signal_ids: topPriorities.map((row) => row.id) },
    });
    await loadThread();
  }, [businessId, healthScore, loadThread, thread.length, topPriorities]);

  useEffect(() => {
    seedThreadIfEmpty();
  }, [seedThreadIfEmpty]);

  const appendExplainMessage = useCallback(
    async (signalId: string, source: "priority" | "change" | "score_change") => {
      if (!businessId) return;
      const data = await getSignalExplain(businessId, signalId);
      setExplain(data);
      setSelectedSignalId(signalId);
      setShowCompletionPrompt(false);
      await postAssistantMessage(businessId, {
        author: "assistant",
        kind: "explain",
        signal_id: signalId,
        content_json: { signal_id: signalId, source },
      });
      await loadThread();
    },
    [businessId, loadThread]
  );

  const appendScoreChangeSummary = useCallback(async () => {
    if (!businessId || !scoreExplain) return;
    await postAssistantMessage(businessId, {
      author: "assistant",
      kind: "changes",
      content_json: {
        headline: scoreExplain.summary.headline,
        top_drivers: scoreExplain.summary.top_drivers,
        impacts: scoreExplain.impacts,
      },
    });
    await loadThread();
  }, [businessId, scoreExplain, loadThread]);

  const handleAction = async (action: SignalExplainOut["next_actions"][number]) => {
    if (!businessId || !selectedSignalId || !actor.trim() || !reason.trim()) return;
    await updateSignalStatus(businessId, selectedSignalId, {
      status: actionToStatus(action.action),
      actor,
      reason,
    });
    setReason("");
    setShowCompletionPrompt(false);
    await Promise.all([loadAll(), loadThread(), appendExplainMessage(selectedSignalId, "priority")]);
  };

  const handleStartPlaybook = useCallback(async (playbook: NonNullable<SignalExplainOut["playbooks"]>[number]) => {
    if (!businessId || !selectedSignalId) return;
    await postAssistantMessage(businessId, {
      author: "system",
      kind: "receipt_playbook_started",
      signal_id: selectedSignalId,
      content_json: { action: "playbook_started", playbook_id: playbook.id, title: playbook.title, signal_id: selectedSignalId, created_at: new Date().toISOString(), links: { signal: `/app/${businessId}/assistant?signalId=${selectedSignalId}`, plan: null, audit: null } },
    });
    await loadThread();
    setShowCompletionPrompt(true);
    const deepLink = playbook.deep_link?.replace("{businessId}", businessId);
    if (deepLink) {
      navigate(deepLink);
      return;
    }
  }, [businessId, loadThread, navigate, selectedSignalId]);

  const handleWorkQueueAction = useCallback(async (item: WorkQueueItem, options?: { allowNavigation?: boolean }) => {
    if (!businessId) return;
    const allowNavigation = options?.allowNavigation ?? true;
    const payload = item.primary_action.payload || {};
    if (item.primary_action.type === "open_plan") {
      const planId = String(payload.plan_id ?? item.id);
      setSelectedPlanId(planId);
      return;
    }
    if (item.primary_action.type === "open_explain") {
      const signalId = String(payload.signal_id ?? item.id);
      await appendExplainMessage(signalId, "priority");
      return;
    }
    const signalId = String(payload.signal_id ?? item.id);
    const playbookId = String(payload.playbook_id ?? "");
    const title = String(payload.title ?? item.title);
    const deepLinkRaw = payload.deep_link;
    const deepLink = typeof deepLinkRaw === "string" ? deepLinkRaw.replace("{businessId}", businessId) : null;
    await postAssistantMessage(businessId, {
      author: "assistant",
      kind: "receipt_playbook_started",
      signal_id: signalId,
      content_json: { action: "playbook_started", playbook_id: playbookId, title, source: "work_queue", signal_id: signalId, created_at: new Date().toISOString(), links: { signal: `/app/${businessId}/assistant?signalId=${signalId}` } },
    });
    await loadThread();
    if (deepLink && allowNavigation) {
      navigate(deepLink);
      return;
    }
    await appendExplainMessage(signalId, "priority");
  }, [appendExplainMessage, businessId, loadThread, navigate]);

  const handleBriefStartPlaybook = useCallback(async (signalId: string, playbook: DailyBriefPlaybook) => {
    if (!businessId) return;
    await postAssistantMessage(businessId, {
      author: "assistant",
      kind: "receipt_playbook_started",
      signal_id: signalId,
      content_json: {
        action: "playbook_started",
        playbook_id: playbook.id,
        title: playbook.title,
        source: "daily_brief",
        signal_id: signalId,
        created_at: new Date().toISOString(),
        links: { signal: `/app/${businessId}/assistant?signalId=${signalId}` },
      },
    });
    await loadThread();
    const deepLink = playbook.deep_link?.replace("{businessId}", businessId);
    if (deepLink) {
      navigate(deepLink);
    }
  }, [businessId, loadThread, navigate]);

  const handleCompletionResponse = useCallback(async (decision: "yes" | "not_yet") => {
    if (!businessId || !selectedSignalId || !explain) return;
    if (decision === "yes") {
      const resolveAction = explain.next_actions.find((action) => action.action === "resolve");
      if (resolveAction) {
        setReason((prev) => prev || "Resolved through guided playbook.");
      }
      return;
    }
    const snoozeAction = explain.next_actions.find((action) => action.action === "snooze");
    if (snoozeAction) {
      setReason((prev) => prev || "Playbook attempted; follow-up required.");
    }
  }, [businessId, explain, selectedSignalId]);



  const doNextItems = useMemo(() => workQueue.slice(0, 3), [workQueue]);
  const backlogItems = useMemo(() => workQueue.slice(3), [workQueue]);
  const selectedPlan = useMemo(() => plans.find((plan) => plan.plan_id === selectedPlanId) ?? null, [plans, selectedPlanId]);
  useEffect(() => {
    if (!selectedPlan) return;
    const firstUnfinished = selectedPlan.steps.find((step) => step.status !== "done");
    if (!firstUnfinished) return;
    const node = planStepRefs.current[firstUnfinished.step_id];
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [selectedPlan]);

  useEffect(() => {
    if (!businessId || resumedRef.current) return;
    if (plans.length === 0 && workQueue.length === 0) return;

    const activePlan = plans.find((plan) => plan.status === "open" || plan.status === "in_progress");
    if (activePlan) {
      setSelectedPlanId(activePlan.plan_id);
      resumedRef.current = true;
      return;
    }

    const topSignal = workQueue.find((item) => item.kind === "signal");
    if (topSignal) {
      resumedRef.current = true;
      void handleWorkQueueAction(topSignal, { allowNavigation: false });
      return;
    }
    resumedRef.current = true;
  }, [businessId, handleWorkQueueAction, plans, workQueue]);

  const planActivity = useMemo(() => {
    if (!selectedPlanId) return [];
    return thread.filter((message) => String(message.content_json.plan_id ?? "") === selectedPlanId);
  }, [selectedPlanId, thread]);

  const handleCreatePlan = useCallback(async (signalIds: string[], title?: string) => {
    if (!businessId || signalIds.length === 0) return;
    const plan = await createPlan({ business_id: businessId, title, signal_ids: signalIds });
    await Promise.all([loadPlans(), loadThread()]);
    setSelectedPlanId(plan.plan_id);
    return plan;
  }, [businessId, loadPlans, loadThread]);

  const handlePlanStepDone = useCallback(async (stepId: string) => {
    if (!businessId || !selectedPlanId) return;
    await markPlanStepDone(businessId, selectedPlanId, { step_id: stepId, actor });
    await Promise.all([loadPlans(), loadThread()]);
  }, [actor, businessId, selectedPlanId, loadPlans, loadThread]);

  const handlePlanStatusDone = useCallback(async () => {
    if (!businessId || !selectedPlanId) return;
    await updatePlanStatus(businessId, selectedPlanId, { actor, status: "done" });
    setPlanVerification(null);
    await Promise.all([loadPlans(), loadThread()]);
  }, [actor, businessId, selectedPlanId, loadPlans, loadThread]);

  const handleVerifyPlan = useCallback(async () => {
    if (!businessId || !selectedPlanId) return;
    const verification = await verifyPlan(businessId, selectedPlanId);
    setPlanVerification(verification);
  }, [businessId, selectedPlanId]);

  const handlePlanNoteSubmit = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (!businessId || !selectedPlanId || !planNoteText.trim()) return;
    await addPlanNote(businessId, selectedPlanId, { actor, text: planNoteText.trim() });
    setPlanNoteText("");
    await Promise.all([loadPlans(), loadThread()]);
  }, [actor, businessId, selectedPlanId, planNoteText, loadPlans, loadThread]);


  useEffect(() => {
    if (!createPlanSignalId || !businessId) return;
    let active = true;
    const run = async () => {
      const plan = await handleCreatePlan([createPlanSignalId], `Plan · ${createPlanSignalId}`);
      if (!active || !plan) return;
      const next = new URLSearchParams(searchParams);
      next.delete("createPlanSignalId");
      next.set("planId", plan.plan_id);
      setSearchParams(next, { replace: true });
    };
    void run();
    return () => {
      active = false;
    };
  }, [businessId, createPlanSignalId, handleCreatePlan, searchParams, setSearchParams]);

  if (!businessId) {
    return (
      <div className={styles.emptyState}>
        <h2>Assistant</h2>
        <p>Select a business to start the assistant experience.</p>
        <Link to="/app/select">Go to business picker</Link>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.contextPanel}>
        <div className={styles.card}>
          <div className={styles.cardTitle}>Health score</div>
          <div>{healthScore ? Math.round(healthScore.score) : "—"}</div>
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Plans</div>
          {plans.map((plan) => (
            <button key={plan.plan_id} className={styles.alertRow} onClick={() => setSelectedPlanId(plan.plan_id)}>
              {plan.title} · {plan.status}
            </button>
          ))}
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Top priorities</div>
          {topPriorities.map((signal, index) => (
            <button key={signal.id} className={styles.alertRow} onClick={() => appendExplainMessage(signal.id, "priority")}>
              {index + 1}. {signal.title ?? signal.id}
            </button>
          ))}
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Recent changes</div>
          {changesError ? (
            <div className={styles.muted}>{changesError}</div>
          ) : (
            <>
              {changes.length === 0 && (
                <div className={styles.muted}>No changes yet.</div>
              )}
              {changes.slice(0, 10).map((change) => (
                <button key={change.id} className={styles.alertRow} onClick={() => appendExplainMessage(change.signal_id, "change")}>
                  <div>
                    {change.type.replace(/_/g, " ")} · {change.title ?? change.signal_id}
                  </div>
                  <div className={styles.muted}>
                    {formatDate(change.occurred_at)} {change.actor ? `· ${change.actor}` : ""}
                  </div>
                </button>
              ))}
            </>
          )}
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Score changed because…</div>
          {scoreExplainError ? (
            <div className={styles.muted}>{scoreExplainError}</div>
          ) : (
            <button className={styles.alertRow} onClick={appendScoreChangeSummary} disabled={!scoreExplain}>
              {scoreExplain?.summary.headline ?? "No recent score-impacting changes."}
            </button>
          )}
        </div>
      </div>

      <div className={styles.mainPanel}>
        {progress && (
          <div className={styles.card}>
            <div className={styles.cardTitle}>Progress</div>
            <div>Health score {progress.health_score.current} ({progress.health_score.delta_window >= 0 ? "+" : ""}{progress.health_score.delta_window})</div>
            <div>Open signals {progress.open_signals.current} ({progress.open_signals.delta_window >= 0 ? "+" : ""}{progress.open_signals.delta_window})</div>
            <div>Plans this week {progress.plans.completed_count_window} · Active {progress.plans.active_count}</div>
            <div>Streak {progress.streak_days} day{progress.streak_days === 1 ? "" : "s"}</div>
            <div className={styles.actionChips} style={{ marginTop: 8 }}>
              {progress.top_domains_open.map((row) => (
                <span key={row.domain} className={styles.actionChip}>{row.domain} ({row.count})</span>
              ))}
            </div>
          </div>
        )}

        <div className={styles.card}>
          <div className={styles.cardTitle}>Today's Work Queue</div>
          <div className={styles.cardTitle} style={{ marginTop: 8 }}>Do next</div>
          {doNextItems.map((item) => (
            <div key={`${item.kind}-${item.id}`} className={styles.card}>
              <div><strong>{item.title}</strong></div>
              <div className={styles.actionChips}>
                {item.domain ? <span className={styles.actionChip}>{item.domain}</span> : null}
                {item.severity ? <span className={styles.actionChip}>{item.severity}</span> : null}
                <span className={styles.actionChip}>{item.status}</span>
              </div>
              <div className={styles.muted}>{item.why_now}</div>
              <div className={styles.actionChips}>
                <button className={styles.actionChip} onClick={() => handleWorkQueueAction(item)}>{item.primary_action.label}</button>
              </div>
            </div>
          ))}
          {backlogItems.length > 0 ? <div className={styles.cardTitle} style={{ marginTop: 8 }}>Backlog</div> : null}
          {backlogItems.map((item) => (
            <button key={`${item.kind}-${item.id}`} className={styles.alertRow} onClick={() => handleWorkQueueAction(item)}>
              <div>{item.title}</div>
              <div className={styles.muted}>{item.why_now}</div>
            </button>
          ))}
        </div>

        {dailyBrief && (
          <div className={styles.card}>
            <div className={styles.cardTitle}>Daily brief</div>
            <div>{dailyBrief.headline}</div>
            <ul>
              {dailyBrief.summary_bullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
            <div className={styles.muted}>
              Score {dailyBrief.metrics.health_score} · Open signals {dailyBrief.metrics.open_signals_count} · New changes {dailyBrief.metrics.new_changes_count}
            </div>
            <div className={styles.cardTitle} style={{ marginTop: 12 }}>Daily priorities</div>
            {dailyBrief.priorities.map((priority) => (
              <div key={priority.signal_id} className={styles.card}>
                <div><strong>{priority.title}</strong> · {priority.severity} · {priority.status.replace(/_/g, " ")}</div>
                <div className={styles.muted}>{priority.why_now}</div>
                <div className={styles.muted}>{priority.clear_condition_summary}</div>
                <div className={styles.actionChips}>
                  <button className={styles.actionChip} onClick={() => appendExplainMessage(priority.signal_id, "priority")}>Open Explain</button>
                  <button className={styles.actionChip} onClick={() => handleCreatePlan([priority.signal_id], `Plan · ${priority.title}`)}>Create plan</button>
                  {priority.recommended_playbooks.map((playbook) => (
                    <button key={playbook.id} className={styles.actionChip} onClick={() => handleBriefStartPlaybook(priority.signal_id, playbook)}>
                      Start Playbook: {playbook.title}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {thread.map((message) => (
          <div key={message.id} className={styles.card}>
            <div className={styles.cardTitle}>{message.kind.replace("_", " ")}</div>
            {message.kind === "summary" && <p>{String(message.content_json.text ?? "")}</p>}
            {message.kind === "priority" && <p>Current priorities are loaded from deterministic signal ranking.</p>}
            {message.kind === "changes" && (
              <div>
                <div>{String(message.content_json.headline ?? "")}</div>
                <ul>
                  {((message.content_json.top_drivers as string[] | undefined) ?? []).map((driver) => (
                    <li key={driver}>{driver}</li>
                  ))}
                </ul>
                <ul>
                  {((message.content_json.impacts as HealthScoreExplainChangeOut["impacts"] | undefined) ?? []).map((impact) => (
                    <li key={`${impact.signal_id}-${impact.change_type}`}>
                      <button className={styles.alertRow} onClick={() => appendExplainMessage(impact.signal_id, "score_change")}>
                        {impact.signal_id} · {impact.change_type.replace(/_/g, " ")} · {impact.estimated_penalty_delta}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {message.kind === "explain" && (
              <div>
                <div>{message.signal_id ? `Signal ${message.signal_id}` : "Signal"}</div>
                <div className={styles.muted}>Open explain card for deterministic evidence and actions.</div>
              </div>
            )}
            {(message.kind === "receipt" || message.kind === "receipt_signal_status_updated" || message.kind === "receipt_playbook_started" || message.kind === "receipt_plan_done") && (
              <div>
                <div>Receipt: {String(message.content_json.action ?? message.kind)}</div>
                {message.audit_id && <div><a href={String((message.content_json.links as Record<string, string> | undefined)?.audit ?? "#")}>Audit {String(message.audit_id)}</a></div>}
                {(message.content_json.signal_id || message.signal_id) && <div><a href={String((message.content_json.links as Record<string, string> | undefined)?.signal ?? "#")}>Signal link</a></div>}
                {message.content_json.plan_id != null && <div><a href={String((message.content_json.links as Record<string, string> | undefined)?.plan ?? "#")}>Plan link</a></div>}
              </div>
            )}
          </div>
        ))}



        {selectedPlan && (
          <div className={styles.card}>
            <div className={styles.cardTitle}>Plan</div>
            <div><strong>{selectedPlan.title}</strong> · {selectedPlan.status}</div>
            <div className={styles.muted}>Signals: {selectedPlan.signal_ids.join(", ")}</div>
            <div className={styles.actionChips} style={{ marginTop: 8 }}>
              {selectedPlan.signal_ids.map((signalId) => (
                <button key={signalId} className={styles.actionChip} onClick={() => appendExplainMessage(signalId, "priority")}>
                  Open {signalId}
                </button>
              ))}
            </div>
            <div className={styles.actionChips} style={{ marginTop: 8 }}><button className={styles.actionChip} onClick={handlePlanStatusDone}>Mark done</button><button className={styles.actionChip} onClick={handleVerifyPlan}>Verify plan</button></div>
            <div className={styles.cardTitle} style={{ marginTop: 12 }}>Steps</div>
            {selectedPlan.steps.map((step) => (
              <label key={step.step_id} className={styles.field}>
                <span>
                  <input ref={(node) => { planStepRefs.current[step.step_id] = node; }} type="checkbox" checked={step.status === "done"} onChange={() => handlePlanStepDone(step.step_id)} /> {step.title}
                </span>
              </label>
            ))}
            <div className={styles.cardTitle} style={{ marginTop: 12 }}>Notes</div>
            <ul>
              {selectedPlan.notes.map((note) => (
                <li key={note.id}>{note.text}</li>
              ))}
            </ul>
            <form onSubmit={handlePlanNoteSubmit}>
              <textarea className={styles.textarea} value={planNoteText} onChange={(event) => setPlanNoteText(event.target.value)} />
              <button className={styles.actionChip} type="submit">Add note</button>
            </form>
            {selectedPlan.status === "done" && selectedPlan.outcome && (
              <>
                <div className={styles.cardTitle} style={{ marginTop: 12 }}>Outcome</div>
                <div className={styles.muted}>Health {selectedPlan.outcome.health_score_at_start} → {selectedPlan.outcome.health_score_at_done} ({selectedPlan.outcome.health_score_delta})</div>
                <div className={styles.muted}>Signals resolved {selectedPlan.outcome.signals_resolved_count}/{selectedPlan.outcome.signals_total}; still open {selectedPlan.outcome.signals_still_open_count}</div>
                <ul>
                  {selectedPlan.outcome.summary_bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              </>
            )}
            {planVerification && (<>
              <div className={styles.cardTitle} style={{ marginTop: 12 }}>Verification</div>
              <div className={styles.muted}>Met {planVerification.totals.met} · Not met {planVerification.totals.not_met} · Unknown {planVerification.totals.unknown}</div>
              <ul>
                {planVerification.signals.map((row) => (
                  <li key={row.signal_id}>{row.signal_id} · {verificationLabel(row.verification_status)} · {row.title} · {row.domain}</li>
                ))}
              </ul>
            </>)}
            <div className={styles.cardTitle} style={{ marginTop: 12 }}>Activity</div>
            <ul>
              {planActivity.map((message) => (
                <li key={message.id}>{message.kind} · {formatDate(message.created_at)}</li>
              ))}
            </ul>
          </div>
        )}

        {explain && (
          <div className={styles.card}>
            <div className={styles.cardTitle}>What resolves this</div>
            <div className={styles.muted}>Verification: {verificationLabel((explain.verification?.status ?? "unknown") as "met" | "not_met" | "unknown")}</div>
            <div>{explain.clear_condition?.summary ?? "Resolution criteria are not explicitly defined."}</div>
            <div className={styles.actionChips} style={{ marginTop: 8 }}>
              {(explain.clear_condition?.fields ?? []).map((field) => (
                <span key={field} className={styles.actionChip}>{field}</span>
              ))}
              {explain.clear_condition?.window_days ? (
                <span className={styles.actionChip}>window: {explain.clear_condition.window_days}d</span>
              ) : null}
            </div>

            <div className={styles.cardTitle} style={{ marginTop: 14 }}>Playbooks</div>
            <div className={styles.actionChips}><button className={styles.actionChip} onClick={() => explain && handleCreatePlan([explain.signal_id], `Plan · ${explain.detector.title}`)}>Create plan from this signal</button></div>
            <div className={styles.actionChips}>
              {explain.playbooks.map((playbook) => (
                <button key={playbook.id} className={styles.actionChip} onClick={() => handleStartPlaybook(playbook)}>
                  {playbookIcon(playbook.kind)} {playbook.title}
                </button>
              ))}
            </div>

            {showCompletionPrompt && (
              <div style={{ marginTop: 12 }}>
                <div className={styles.muted}>Did this help resolve the issue?</div>
                <div className={styles.actionChips}>
                  <button className={styles.actionChip} onClick={() => handleCompletionResponse("yes")}>Yes</button>
                  <button className={styles.actionChip} onClick={() => handleCompletionResponse("not_yet")}>Not yet</button>
                </div>
              </div>
            )}

            <div className={styles.cardTitle} style={{ marginTop: 14 }}>Next actions</div>
            <div className={styles.actionChips}>
              {explain.next_actions.map((action) => (
                <button key={action.key} className={styles.actionChip} onClick={() => handleAction(action)}>
                  {action.label}
                  {action.suggested_snooze_minutes ? ` (${action.suggested_snooze_minutes}m)` : ""}
                </button>
              ))}
            </div>
            <label className={styles.field}>
              Actor
              <input className={styles.input} value={actor} onChange={(event) => setActor(event.target.value)} />
            </label>
            <label className={styles.field}>
              Reason
              <textarea className={styles.textarea} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
          </div>
        )}
      </div>
    </div>
  );
}
