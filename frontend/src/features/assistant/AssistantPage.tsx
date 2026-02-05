import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchAssistantThread, postAssistantMessage, type AssistantThreadMessage } from "../../api/assistantThread";
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

function playbookIcon(kind: "inspect" | "adjust" | "decide") {
  if (kind === "inspect") return "🔎";
  if (kind === "adjust") return "🛠️";
  return "✅";
}

export default function AssistantPage() {
  const { businessId: businessIdParam } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const businessId = businessIdParam?.trim() || searchParams.get("businessId")?.trim() || "";
  const initialSignalId = searchParams.get("signalId")?.trim() || null;
  const { setActiveBusinessId } = useAppState();

  const [signals, setSignals] = useState<SignalState[]>([]);
  const [changes, setChanges] = useState<ChangeEvent[]>([]);
  const [healthScore, setHealthScore] = useState<HealthScoreOut | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(initialSignalId);
  const [explain, setExplain] = useState<SignalExplainOut | null>(null);
  const [thread, setThread] = useState<AssistantThreadMessage[]>([]);
  const [scoreExplain, setScoreExplain] = useState<HealthScoreExplainChangeOut | null>(null);
  const [actor, setActor] = useState("analyst");
  const [reason, setReason] = useState("");
  const [showCompletionPrompt, setShowCompletionPrompt] = useState(false);

  useEffect(() => setActiveBusinessId(businessId || null), [businessId, setActiveBusinessId]);

  const loadAll = useCallback(async () => {
    if (!businessId) return;
    const [signalsData, scoreData, changesData, scoreChangeData] = await Promise.all([
      listSignalStates(businessId),
      fetchHealthScore(businessId),
      listChanges(businessId, 10),
      fetchHealthScoreExplainChange(businessId, 72, 20),
    ]);
    setSignals(signalsData.signals ?? []);
    setHealthScore(scoreData);
    setChanges(changesData ?? []);
    setScoreExplain(scoreChangeData);
  }, [businessId]);

  const loadThread = useCallback(async () => {
    if (!businessId) return;
    const rows = await fetchAssistantThread(businessId, 200);
    setThread(rows);
  }, [businessId]);

  useEffect(() => {
    loadAll();
    loadThread();
  }, [loadAll, loadThread]);

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
    const result = await updateSignalStatus(businessId, selectedSignalId, {
      status: actionToStatus(action.action),
      actor,
      reason,
    });
    await postAssistantMessage(businessId, {
      author: "assistant",
      kind: "action_result",
      signal_id: selectedSignalId,
      audit_id: result.audit_id,
      content_json: {
        signal_id: selectedSignalId,
        audit_id: result.audit_id,
        status: result.status,
        reason,
      },
    });
    setReason("");
    setShowCompletionPrompt(false);
    await Promise.all([loadAll(), loadThread(), appendExplainMessage(selectedSignalId, "priority")]);
  };

  const handleStartPlaybook = useCallback(async (playbook: NonNullable<SignalExplainOut["playbooks"]>[number]) => {
    if (!businessId || !selectedSignalId) return;
    await postAssistantMessage(businessId, {
      author: "system",
      kind: "playbook_started",
      signal_id: selectedSignalId,
      content_json: { playbook_id: playbook.id, title: playbook.title },
    });
    await loadThread();
    setShowCompletionPrompt(true);
    const deepLink = playbook.deep_link?.replace("{businessId}", businessId);
    if (deepLink) {
      navigate(deepLink);
      return;
    }
  }, [businessId, loadThread, navigate, selectedSignalId]);

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
          <div className={styles.cardTitle}>Top priorities</div>
          {topPriorities.map((signal, index) => (
            <button key={signal.id} className={styles.alertRow} onClick={() => appendExplainMessage(signal.id, "priority")}>
              {index + 1}. {signal.title ?? signal.id}
            </button>
          ))}
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Recent changes</div>
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
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Score changed because…</div>
          <button className={styles.alertRow} onClick={appendScoreChangeSummary}>
            {scoreExplain?.summary.headline ?? "No recent score-impacting changes."}
          </button>
        </div>
      </div>

      <div className={styles.mainPanel}>
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
            {message.kind === "playbook_started" && (
              <div>Started playbook: {String(message.content_json.title ?? "")}</div>
            )}
            {message.kind === "action_result" && (
              <div>Updated to {String(message.content_json.status)} (audit {String(message.audit_id)}).</div>
            )}
          </div>
        ))}

        {explain && (
          <div className={styles.card}>
            <div className={styles.cardTitle}>What resolves this</div>
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
