import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchAssistantSummary, type AssistantSummary } from "../../api/assistantTools";
import { fetchActionTriage, getActions, type ActionItem } from "../../api/actions";
import { getAuditLog, type AuditLogOut } from "../../api/audit";
import { ApiError } from "../../api/client";
import { useAuth } from "../../app/auth/AuthContext";
import { EmptyState, InlineAlert, KeyValueList, LoadingState, Panel, Section } from "../../components/ui";
import styles from "./AssistantPage.module.css";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString();
}

const HIGHLIGHT_TYPES = new Set([
  "signal_detected",
  "signal_resolved",
  "signal_status_changed",
  "action_created",
  "action_resolved",
  "action_status_changed",
]);

export default function AssistantPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = businessIdParam?.trim() || "";
  const { logout } = useAuth();

  const [summary, setSummary] = useState<AssistantSummary | null>(null);
  const [openActionCount, setOpenActionCount] = useState<number | null>(null);
  const [recentResolutions, setRecentResolutions] = useState<ActionItem[]>([]);
  const [highlights, setHighlights] = useState<AuditLogOut[]>([]);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingActions, setLoadingActions] = useState(false);
  const [loadingHighlights, setLoadingHighlights] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!businessId) return;
    let active = true;
    const controller = new AbortController();

    async function loadSummary() {
      setLoadingSummary(true);
      setError(null);
      try {
        const data = await fetchAssistantSummary(businessId, controller.signal);
        if (!active) return;
        setSummary(data);
      } catch (err: any) {
        if (!active || controller.signal.aborted) return;
        setError(err?.message ?? "Failed to load summary.");
      } finally {
        if (active) setLoadingSummary(false);
      }
    }

    async function loadActions() {
      setLoadingActions(true);
      try {
        const response = await fetchActionTriage(businessId, { status: "open", assigned: "any" });
        if (!active) return;
        setOpenActionCount(response.actions?.length ?? 0);
        const resolutions = await getActions(businessId, { status: "done", limit: 3 });
        if (!active) return;
        setRecentResolutions(resolutions.actions ?? []);
      } catch (err: any) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        if (active) setError(err?.message ?? "Failed to load action summary.");
      } finally {
        if (active) setLoadingActions(false);
      }
    }

    async function loadHighlights() {
      setLoadingHighlights(true);
      try {
        const response = await getAuditLog(businessId, { limit: 12 });
        if (!active) return;
        const filtered = response.items.filter((item) => HIGHLIGHT_TYPES.has(item.event_type));
        setHighlights(filtered.slice(0, 6));
      } catch (err: any) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        if (active) setError(err?.message ?? "Failed to load recent highlights.");
      } finally {
        if (active) setLoadingHighlights(false);
      }
    }

    void loadSummary();
    void loadActions();
    void loadHighlights();

    return () => {
      active = false;
      controller.abort();
    };
  }, [businessId, logout]);

  const inboxLink = useMemo(() => (businessId ? `/app/${businessId}/advisor` : "#"), [businessId]);
  const signalsLink = useMemo(() => (businessId ? `/app/${businessId}/signals` : "#"), [businessId]);
  const ledgerLink = useMemo(() => (businessId ? `/app/${businessId}/ledger` : "#"), [businessId]);

  return (
    <div className={styles.layout}>
      <div className={styles.primaryColumn}>
        {error && <InlineAlert tone="error" title="Summary unavailable" description={error} />}
        <Section
          title="What changed"
          subtitle="Highlights from the latest signal and action activity."
        >
          {loadingHighlights && <LoadingState label="Loading highlights…" rows={2} />}
          {!loadingHighlights && highlights.length === 0 && (
            <EmptyState
              title="No recent highlights"
              description="New signal detections and action updates will appear here."
            />
          )}
          {!loadingHighlights && highlights.length > 0 && (
            <ul className={styles.highlightList}>
              {highlights.map((event) => (
                <li key={event.id} className={styles.highlightItem}>
                  <div className={styles.highlightTitle}>{event.event_type.replace(/_/g, " ")}</div>
                  <div className={styles.highlightMeta}>{formatDate(event.created_at)}</div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          title="Open actions"
          subtitle="Work that is currently queued for your firm."
        >
          {loadingActions && <LoadingState label="Loading open actions…" rows={1} />}
          {!loadingActions && (
            <Panel className={styles.cardPanel}>
              <KeyValueList
                items={[
                  { label: "Open actions", value: openActionCount ?? "—" },
                  { label: "Open signals", value: summary?.open_signals ?? "—" },
                ]}
              />
              <div className={styles.linkRow}>
                <Link className={styles.linkButton} to={`${inboxLink}?status=open`}>
                  View inbox
                </Link>
                <Link className={styles.linkButton} to={signalsLink}>
                  View signals
                </Link>
              </div>
            </Panel>
          )}
        </Section>

        <Section
          title="Recent resolutions"
          subtitle="Recently closed actions and their outcomes."
        >
          {loadingActions && <LoadingState label="Loading resolutions…" rows={2} />}
          {!loadingActions && recentResolutions.length === 0 && (
            <EmptyState
              title="No recent resolutions"
              description="Resolved actions will show up here with quick links back to the inbox."
            />
          )}
          {!loadingActions && recentResolutions.length > 0 && (
            <ul className={styles.resolutionList}>
              {recentResolutions.map((action) => (
                <li key={action.id} className={styles.resolutionItem}>
                  <div>
                    <div className={styles.resolutionTitle}>{action.title}</div>
                    <div className={styles.resolutionMeta}>Resolved {formatDate(action.resolved_at)}</div>
                  </div>
                  <Link className={styles.linkButton} to={`${inboxLink}?status=resolved`}>
                    View in inbox
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <aside className={styles.secondaryColumn}>
        <Section title="Summary snapshot" subtitle="Signals are evidence. Actions are work.">
          {loadingSummary && <LoadingState label="Loading summary…" rows={2} />}
          {!loadingSummary && summary && (
            <Panel className={styles.cardPanel}>
              <KeyValueList
                items={[
                  {
                    label: "Monitoring",
                    value: summary.monitor_status?.stale ? "Stale" : "Fresh",
                  },
                  { label: "Integrations", value: summary.integrations.length },
                  { label: "Uncategorized", value: summary.uncategorized_count },
                ]}
              />
              <div className={styles.linkRow}>
                <Link className={styles.linkButton} to={`${signalsLink}?status=open`}>
                  Review evidence
                </Link>
                <Link className={styles.linkButton} to={ledgerLink}>
                  Verify in ledger
                </Link>
              </div>
            </Panel>
          )}
          {!loadingSummary && !summary && (
            <EmptyState
              title="Summary unavailable"
              description="Connect data sources to populate the summary snapshot."
            />
          )}
        </Section>
      </aside>
    </div>
  );
}
