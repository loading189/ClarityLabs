import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchAssistantSummary, postAssistantAction, type AssistantSummary } from "../../api/assistantTools";
import { useAppState } from "../../app/state/appState";
import styles from "./AssistantPage.module.css";

type ChatMessage = {
  id: string;
  author: "assistant" | "user";
  content: string;
  created_at: string;
};

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

function buildSummaryText(summary: AssistantSummary) {
  return [
    `Monitoring: ${summary.monitor_status?.stale ? "stale" : "fresh"}`,
    `Open signals: ${summary.open_signals}`,
    `Uncategorized: ${summary.uncategorized_count}`,
    `Integrations: ${summary.integrations.length}`,
  ].join(" • ");
}

export default function AssistantPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = businessIdParam?.trim() || "";
  const navigate = useNavigate();
  const { setActiveBusinessId } = useAppState();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [summary, setSummary] = useState<AssistantSummary | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setActiveBusinessId(businessId || null), [businessId, setActiveBusinessId]);

  const loadSummary = useCallback(
    async (signal?: AbortSignal) => {
      if (!businessId) return;
      setError(null);
      try {
        const data = await fetchAssistantSummary(businessId, signal);
        if (signal?.aborted) return;
        setSummary(data);
        return data;
      } catch (err: any) {
        if (signal?.aborted) return;
        setError(err?.message ?? "Failed to load assistant summary.");
      }
    },
    [businessId]
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadSummary(controller.signal);
    return () => controller.abort();
  }, [loadSummary]);

  const suggestedActions = useMemo(() => {
    if (!summary) return [];
    const items: string[] = [];
    if (summary.monitor_status?.stale) items.push("Run monitoring pulse");
    if (summary.open_signals > 0) items.push("Open top signal");
    if (summary.uncategorized_count > 0) items.push("Review uncategorized");
    if (summary.integrations.length > 0) items.push("Sync integrations");
    return items;
  }, [summary]);

  const appendMessage = useCallback((author: ChatMessage["author"], content: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `${author}-${Date.now()}-${prev.length}`,
        author,
        content,
        created_at: new Date().toISOString(),
      },
    ]);
  }, []);

  const handleSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || !businessId) return;
      appendMessage("user", trimmed);
      setInput("");
      const data = await loadSummary();
      if (data) {
        appendMessage("assistant", buildSummaryText(data));
      }
    },
    [appendMessage, businessId, input, loadSummary, summary]
  );

  const runAction = useCallback(
    async (actionType: string) => {
      if (!businessId) return;
      setLoading(true);
      setError(null);
      try {
        const response = await postAssistantAction(businessId, actionType);
        if (response.navigation_hint?.path) {
          navigate(response.navigation_hint.path);
        }
        if (response.result) {
          appendMessage("assistant", `Action "${actionType}" completed.`);
        }
        await loadSummary();
      } catch (err: any) {
        setError(err?.message ?? "Action failed.");
      } finally {
        setLoading(false);
      }
    },
    [appendMessage, businessId, loadSummary, navigate]
  );

  return (
    <div className={styles.layout}>
      <section className={styles.chatPane}>
        <header className={styles.chatHeader}>
          <h2>Assistant</h2>
          <span className={styles.subtleText}>Control plane</span>
        </header>

        <div className={styles.chatBody}>
          {messages.length === 0 && (
            <div className={styles.emptyState}>
              Ask for a status update or run an action to get started.
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={msg.author === "assistant" ? styles.messageAssistant : styles.messageUser}
            >
              <div className={styles.messageMeta}>
                <strong>{msg.author === "assistant" ? "Assistant" : "You"}</strong>
                <span>{formatDate(msg.created_at)}</span>
              </div>
              <div className={styles.messageContent}>{msg.content}</div>
            </div>
          ))}
        </div>

        <form className={styles.chatInput} onSubmit={handleSubmit}>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask for the current status..."
          />
          <button type="submit" disabled={!input.trim()}>
            Send
          </button>
        </form>
        {error && <div className={styles.error}>{error}</div>}
      </section>

      <aside className={styles.actionsPane}>
        <div className={styles.panelCard}>
          <h3>Actions</h3>
          <div className={styles.buttonGroup}>
            <button type="button" onClick={() => runAction("run_pulse")} disabled={loading}>
              Run monitoring pulse
            </button>
            <button type="button" onClick={() => runAction("sync_integrations")} disabled={loading}>
              Sync integrations
            </button>
            <button type="button" onClick={() => runAction("open_uncategorized")} disabled={loading}>
              Review uncategorized
            </button>
            <button type="button" onClick={() => runAction("open_signal")} disabled={loading}>
              Open top signal
            </button>
          </div>
        </div>

        <div className={styles.panelCard}>
          <h3>Status</h3>
          <div className={styles.statusGrid}>
            <div>
              <span className={styles.statusLabel}>Monitoring</span>
              <span className={styles.statusValue}>{summary?.monitor_status?.stale ? "Stale" : "Fresh"}</span>
            </div>
            <div>
              <span className={styles.statusLabel}>Open signals</span>
              <span className={styles.statusValue}>{summary?.open_signals ?? "—"}</span>
            </div>
            <div>
              <span className={styles.statusLabel}>Uncategorized</span>
              <span className={styles.statusValue}>{summary?.uncategorized_count ?? "—"}</span>
            </div>
            <div>
              <span className={styles.statusLabel}>Integrations</span>
              <span className={styles.statusValue}>{summary?.integrations.length ?? "—"}</span>
            </div>
          </div>
        </div>

        <div className={styles.panelCard}>
          <h3>Integrations</h3>
          {summary?.integrations?.length ? (
            <ul className={styles.list}>
              {summary.integrations.map((row) => (
                <li key={row.provider}>
                  <strong>{row.provider}</strong> · {row.status}
                </li>
              ))}
            </ul>
          ) : (
            <div className={styles.subtleText}>No integrations connected.</div>
          )}
        </div>

        <div className={styles.panelCard}>
          <h3>Suggested next actions</h3>
          {suggestedActions.length ? (
            <ul className={styles.list}>
              {suggestedActions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <div className={styles.subtleText}>All clear.</div>
          )}
        </div>
      </aside>
    </div>
  );
}
