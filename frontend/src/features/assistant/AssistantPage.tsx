import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { listChanges, type ChangeEvent } from "../../api/changes";
import { fetchHealthScore, type HealthScoreOut } from "../../api/healthScore";
import {
  getSignalExplain,
  listSignalStates,
  updateSignalStatus,
  type SignalExplainOut,
  type SignalState,
} from "../../api/signals";
import { useAppState } from "../../app/state/appState";
import styles from "./AssistantPage.module.css";

type ThreadMessage = {
  id: string;
  type: "system" | "summary" | "explain" | "action_result";
  created_at: string;
  payload: Record<string, unknown>;
};

const THREAD_CAP = 200;

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

function threadKey(businessId: string) {
  return `clarity.assistant.thread.${businessId}`;
}

export default function AssistantPage() {
  const { businessId: businessIdParam } = useParams();
  const [searchParams] = useSearchParams();
  const businessId = businessIdParam?.trim() || searchParams.get("businessId")?.trim() || "";
  const initialSignalId = searchParams.get("signalId")?.trim() || null;
  const { setActiveBusinessId } = useAppState();

  const [signals, setSignals] = useState<SignalState[]>([]);
  const [changes, setChanges] = useState<ChangeEvent[]>([]);
  const [healthScore, setHealthScore] = useState<HealthScoreOut | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(initialSignalId);
  const [explain, setExplain] = useState<SignalExplainOut | null>(null);
  const [thread, setThread] = useState<ThreadMessage[]>([]);
  const [actor, setActor] = useState("analyst");
  const [reason, setReason] = useState("");

  useEffect(() => setActiveBusinessId(businessId || null), [businessId, setActiveBusinessId]);

  useEffect(() => {
    if (!businessId) return;
    const raw = localStorage.getItem(threadKey(businessId));
    if (!raw) {
      setThread([
        {
          id: "system-initial",
          type: "system",
          created_at: new Date().toISOString(),
          payload: { text: "Here’s what matters right now." },
        },
      ]);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as ThreadMessage[];
      setThread(parsed.slice(-THREAD_CAP));
    } catch {
      setThread([]);
    }
  }, [businessId]);

  useEffect(() => {
    if (!businessId) return;
    localStorage.setItem(threadKey(businessId), JSON.stringify(thread.slice(-THREAD_CAP)));
  }, [businessId, thread]);

  const appendMessage = useCallback((message: Omit<ThreadMessage, "id" | "created_at">) => {
    setThread((prev) => {
      const next = [
        ...prev,
        {
          ...message,
          id: `${message.type}-${Date.now()}-${prev.length}`,
          created_at: new Date().toISOString(),
        },
      ];
      return next.slice(-THREAD_CAP);
    });
  }, []);

  const loadAll = useCallback(async () => {
    if (!businessId) return;
    const [signalsData, scoreData, changesData] = await Promise.all([
      listSignalStates(businessId),
      fetchHealthScore(businessId),
      listChanges(businessId, 10),
    ]);
    setSignals(signalsData.signals ?? []);
    setHealthScore(scoreData);
    setChanges(changesData ?? []);
  }, [businessId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const loadExplain = useCallback(
    async (signalId: string, source: "priority" | "change") => {
      if (!businessId) return;
      const data = await getSignalExplain(businessId, signalId);
      setExplain(data);
      setSelectedSignalId(signalId);
      appendMessage({ type: "explain", payload: { signal_id: signalId, source, explain: data } });
    },
    [appendMessage, businessId]
  );

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
        if ((b.severity ?? "").localeCompare(a.severity ?? "") !== 0) {
          return (b.severity ?? "").localeCompare(a.severity ?? "");
        }
        return a.id.localeCompare(b.id);
      })
      .slice(0, 5);
  }, [healthScore?.contributors, signals]);

  const handleAction = async (action: SignalExplainOut["next_actions"][number]) => {
    if (!businessId || !selectedSignalId || !actor.trim() || !reason.trim()) return;
    const result = await updateSignalStatus(businessId, selectedSignalId, {
      status: actionToStatus(action.action),
      actor,
      reason,
    });
    appendMessage({
      type: "action_result",
      payload: {
        signal_id: selectedSignalId,
        audit_id: result.audit_id,
        status: result.status,
        reason,
      },
    });
    setReason("");
    await loadAll();
    await loadExplain(selectedSignalId, "priority");
  };

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
            <button key={signal.id} className={styles.alertRow} onClick={() => loadExplain(signal.id, "priority")}>
              {index + 1}. {signal.title ?? signal.id}
            </button>
          ))}
        </div>

        <div className={styles.card}>
          <div className={styles.cardTitle}>Recent changes</div>
          {changes.slice(0, 10).map((change) => (
            <button key={change.id} className={styles.alertRow} onClick={() => loadExplain(change.signal_id, "change")}>
              <div>{change.type.replace(/_/g, " ")} · {change.title ?? change.signal_id}</div>
              <div className={styles.muted}>{formatDate(change.occurred_at)} {change.actor ? `· ${change.actor}` : ""}</div>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.mainPanel}>
        {thread.map((message) => (
          <div key={message.id} className={styles.card}>
            <div className={styles.cardTitle}>{message.type.replace("_", " ")}</div>
            {message.type === "system" && <p>{String(message.payload.text ?? "")}</p>}
            {message.type === "explain" && (
              <div>
                <div>{(message.payload.explain as SignalExplainOut)?.detector?.title}</div>
                <div className={styles.muted}>Signal {(message.payload.signal_id as string) ?? ""}</div>
              </div>
            )}
            {message.type === "action_result" && (
              <div>Updated to {String(message.payload.status)} (audit {String(message.payload.audit_id)}).</div>
            )}
          </div>
        ))}

        {explain && (
          <div className={styles.card}>
            <div className={styles.cardTitle}>Next actions</div>
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
