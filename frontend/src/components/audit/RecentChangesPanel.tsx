import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getAuditLog, type AuditLogOut } from "../../api/audit";
import styles from "./RecentChangesPanel.module.css";

const EVENT_LABELS: Record<string, string> = {
  categorization_change: "Categorization updated",
  rule_create: "Rule created",
  rule_update: "Rule updated",
  rule_delete: "Rule deleted",
  vendor_default_set: "Vendor default set",
  vendor_default_remove: "Vendor default removed",
};

function summarizeEvent(event: AuditLogOut): string {
  return EVENT_LABELS[event.event_type] ?? event.event_type.replace(/_/g, " ");
}

function detailLine(event: AuditLogOut): string | null {
  const after = event.after_state ?? {};
  if (after.category_name) {
    return `Category: ${after.category_name}`;
  }
  if (after.system_key) {
    return `System key: ${after.system_key}`;
  }
  if (event.rule_id) {
    return `Rule: ${event.rule_id}`;
  }
  return null;
}

const EVENT_OPTIONS = [
  { value: "", label: "All events" },
  { value: "categorization_change", label: "Categorization updated" },
  { value: "rule_create", label: "Rule created" },
  { value: "rule_update", label: "Rule updated" },
  { value: "rule_delete", label: "Rule deleted" },
  { value: "vendor_default_set", label: "Vendor default set" },
  { value: "vendor_default_remove", label: "Vendor default removed" },
];

function formatJson(value: Record<string, any> | null | undefined) {
  return JSON.stringify(value ?? {}, null, 2);
}

function diffKeys(
  before: Record<string, any> | null | undefined,
  after: Record<string, any> | null | undefined
) {
  const keys = new Set<string>();
  const beforeObj = before ?? {};
  const afterObj = after ?? {};
  for (const key of new Set([...Object.keys(beforeObj), ...Object.keys(afterObj)])) {
    if (JSON.stringify(beforeObj[key]) !== JSON.stringify(afterObj[key])) {
      keys.add(key);
    }
  }
  return keys;
}

function formatJsonLines(value: Record<string, any> | null | undefined, changedKeys: Set<string>) {
  const lines = formatJson(value).split("\n");
  return lines.map((line) => {
    const match = line.match(/\"([^"]+)\":/);
    const key = match?.[1];
    return {
      line,
      highlight: key ? changedKeys.has(key) : false,
    };
  });
}

export default function RecentChangesPanel({
  businessId,
  dataVersion,
  limit = 8,
}: {
  businessId: string;
  dataVersion: number;
  limit?: number;
}) {
  const [items, setItems] = useState<AuditLogOut[]>([]);
  const [selected, setSelected] = useState<AuditLogOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [sinceFilter, setSinceFilter] = useState("");
  const [untilFilter, setUntilFilter] = useState("");
  const [searchParams] = useSearchParams();
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const autoLoadCount = useRef(0);

  const targetAuditId = searchParams.get("auditId");

  const load = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    setErr(null);
    try {
      const data = await getAuditLog(businessId, {
        limit,
        event_type: eventFilter || undefined,
        actor: actorFilter || undefined,
        since: sinceFilter || undefined,
        until: untilFilter || undefined,
      });
      setItems(data.items);
      setNextCursor(data.next_cursor ?? null);
      setSelected(data.items[0] ?? null);
      autoLoadCount.current = 0;
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  }, [actorFilter, businessId, eventFilter, limit, sinceFilter, untilFilter]);

  const loadMore = useCallback(async () => {
    if (!businessId || !nextCursor || loadingMore) return;
    setLoadingMore(true);
    setErr(null);
    try {
      const data = await getAuditLog(businessId, {
        limit,
        cursor: nextCursor,
        event_type: eventFilter || undefined,
        actor: actorFilter || undefined,
        since: sinceFilter || undefined,
        until: untilFilter || undefined,
      });
      setItems((prev) => [...prev, ...data.items]);
      setNextCursor(data.next_cursor ?? null);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load more audit log items");
    } finally {
      setLoadingMore(false);
    }
  }, [actorFilter, businessId, eventFilter, limit, loadingMore, nextCursor, sinceFilter, untilFilter]);

  useEffect(() => {
    load();
  }, [load, dataVersion]);

  useEffect(() => {
    if (!targetAuditId) return;
    const matched = items.find((item) => item.id === targetAuditId);
    if (matched) {
      setSelected(matched);
      setHighlightId(targetAuditId);
      const element = document.getElementById(`audit-${targetAuditId}`);
      element?.scrollIntoView({ behavior: "smooth", block: "center" });
      const timer = window.setTimeout(() => setHighlightId(null), 4000);
      return () => window.clearTimeout(timer);
    }
    if (nextCursor && !loading && autoLoadCount.current < 3) {
      autoLoadCount.current += 1;
      loadMore();
    }
  }, [items, loadMore, loading, nextCursor, targetAuditId]);

  const list = useMemo(() => items, [items]);
  const diffSet = useMemo(
    () => diffKeys(selected?.before_state, selected?.after_state),
    [selected]
  );
  const beforeLines = useMemo(
    () => formatJsonLines(selected?.before_state ?? null, diffSet),
    [diffSet, selected]
  );
  const afterLines = useMemo(
    () => formatJsonLines(selected?.after_state ?? null, diffSet),
    [diffSet, selected]
  );
  const highlightDetail = selected ? detailLine(selected) : null;

  const relatedLinks = useMemo(() => {
    if (!selected) return [];
    const links: { label: string; href: string }[] = [];
    if (selected.rule_id) {
      links.push({
        label: "Rule",
        href: `/app/${businessId}/rules?ruleId=${selected.rule_id}`,
      });
    }
    if (selected.source_event_id) {
      links.push({
        label: "Transaction",
        href: `/app/${businessId}/ledger?source_event_id=${selected.source_event_id}`,
      });
    }
    if (selected.event_type?.includes("vendor")) {
      links.push({ label: "Vendors", href: `/app/${businessId}/vendors` });
    }
    return links;
  }, [businessId, selected]);

  return (
    <div className={styles.panel} id="recent-changes">
      <div className={styles.headerRow}>
        <div>
          <h3 className={styles.title}>Recent changes</h3>
          <div className={styles.subtitle}>Append-only audit trail for categorization actions.</div>
        </div>
        <div className={styles.headerActions}>
          <button className={styles.button} onClick={load} type="button">
            Refresh
          </button>
        </div>
      </div>

      <div className={styles.filters}>
        <label className={styles.filterField}>
          Event type
          <select
            className={styles.select}
            value={eventFilter}
            onChange={(event) => setEventFilter(event.target.value)}
          >
            {EVENT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.filterField}>
          Actor
          <input
            className={styles.input}
            placeholder="system, manual…"
            value={actorFilter}
            onChange={(event) => setActorFilter(event.target.value)}
          />
        </label>
        <label className={styles.filterField}>
          Since
          <input
            className={styles.input}
            type="date"
            value={sinceFilter}
            onChange={(event) => setSinceFilter(event.target.value)}
          />
        </label>
        <label className={styles.filterField}>
          Until
          <input
            className={styles.input}
            type="date"
            value={untilFilter}
            onChange={(event) => setUntilFilter(event.target.value)}
          />
        </label>
        <button className={styles.buttonSecondary} onClick={load} type="button">
          Apply filters
        </button>
      </div>

      {err && <div className={styles.error}>Error: {err}</div>}
      {loading ? (
        <div className={styles.loading}>Loading audit log…</div>
      ) : list.length === 0 ? (
        <div className={styles.empty}>No recent changes yet.</div>
      ) : (
        <div className={styles.contentGrid}>
          <ul className={styles.list}>
            {list.map((event) => {
              const detail = detailLine(event);
              const isActive = selected?.id === event.id;
              return (
                <li key={event.id} className={styles.itemWrapper}>
                  <button
                    id={`audit-${event.id}`}
                    className={`${styles.item} ${isActive ? styles.itemActive : ""} ${
                      highlightId === event.id ? styles.itemHighlight : ""
                    }`}
                    onClick={() => setSelected(event)}
                    type="button"
                  >
                    <div className={styles.itemHeader}>
                      <span className={styles.itemTitle}>{summarizeEvent(event)}</span>
                      <span className={styles.itemTime}>
                        {new Date(event.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className={styles.itemMeta}>
                      Actor: {event.actor}
                      {event.reason ? ` • ${event.reason}` : ""}
                    </div>
                    {detail && <div className={styles.itemDetail}>{detail}</div>}
                  </button>
                </li>
              );
            })}
            {nextCursor && (
              <li>
                <button
                  className={styles.buttonSecondary}
                  onClick={loadMore}
                  type="button"
                  disabled={loadingMore}
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </li>
            )}
          </ul>
          <aside className={styles.detailPanel}>
            {selected ? (
              <>
                <div className={styles.detailHeader}>
                  <div>
                    <div className={styles.detailTitle}>{summarizeEvent(selected)}</div>
                    <div className={styles.detailMeta}>
                      {new Date(selected.created_at).toLocaleString()} • {selected.actor}
                    </div>
                  </div>
                  {highlightDetail && <div className={styles.detailSummary}>{highlightDetail}</div>}
                </div>
                <div className={styles.detailLinks}>
                  {relatedLinks.map((link) => (
                    <a key={link.href} className={styles.link} href={link.href}>
                      View {link.label}
                    </a>
                  ))}
                </div>
                <div className={styles.detailDiff}>
                  <div>
                    <div className={styles.diffHeader}>Before</div>
                    <pre className={styles.jsonBlock}>
                      {beforeLines.map((line, idx) => (
                        <span
                          key={`before-${idx}`}
                          className={line.highlight ? styles.diffHighlight : ""}
                        >
                          {line.line}
                          {"\n"}
                        </span>
                      ))}
                    </pre>
                  </div>
                  <div>
                    <div className={styles.diffHeader}>After</div>
                    <pre className={styles.jsonBlock}>
                      {afterLines.map((line, idx) => (
                        <span
                          key={`after-${idx}`}
                          className={line.highlight ? styles.diffHighlight : ""}
                        >
                          {line.line}
                          {"\n"}
                        </span>
                      ))}
                    </pre>
                  </div>
                </div>
              </>
            ) : (
              <div className={styles.emptyDetail}>Select an event to view details.</div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
