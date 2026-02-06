import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Drawer from "../common/Drawer";
import { fetchTransactionDetail, type TransactionDetail } from "../../api/transactions";
import { updateSignalStatus, type SignalStatus } from "../../api/signals";
import styles from "./TransactionDetailDrawer.module.css";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function formatMoney(amount?: number | null, direction?: string | null) {
  if (amount == null || !Number.isFinite(amount)) return "—";
  const sign = direction === "outflow" ? "-" : direction === "inflow" ? "+" : "";
  return `${sign}$${Math.abs(amount).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function prettyJson(value: any) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? "");
  }
}

export default function TransactionDetailDrawer({
  open,
  businessId,
  sourceEventId,
  onClose,
}: {
  open: boolean;
  businessId: string;
  sourceEventId: string | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<TransactionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [statusSelections, setStatusSelections] = useState<Record<string, SignalStatus>>({});
  const [statusSaving, setStatusSaving] = useState<Record<string, boolean>>({});
  const [statusErrors, setStatusErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    if (!open || !businessId || !sourceEventId) return;
    setLoading(true);
    setErr(null);
    fetchTransactionDetail(businessId, sourceEventId)
      .then((data) => {
        if (!active) return;
        setDetail(data);
      })
      .catch((error: Error) => {
        if (!active) return;
        setErr(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, open, sourceEventId]);

  useEffect(() => {
    if (!detail) return;
    setStatusSelections({});
    setStatusErrors({});
    setStatusSaving({});
  }, [detail?.source_event_id]);

  const assumptions = useMemo(() => detail?.processing_assumptions ?? [], [detail]);
  const auditRows = useMemo(() => detail?.audit_history ?? [], [detail]);
  const relatedSignals = useMemo(() => detail?.related_signals ?? [], [detail]);

  const handleStatusSelect = (signalId: string, status: SignalStatus) => {
    setStatusSelections((prev) => ({ ...prev, [signalId]: status }));
  };

  const handleStatusSave = async (signalId: string) => {
    if (!businessId) return;
    const current = relatedSignals.find((signal) => signal.signal_id === signalId);
    const nextStatus = statusSelections[signalId] ?? (current?.status as SignalStatus) ?? "open";
    setStatusSaving((prev) => ({ ...prev, [signalId]: true }));
    setStatusErrors((prev) => ({ ...prev, [signalId]: "" }));
    try {
      await updateSignalStatus(businessId, signalId, { status: nextStatus });
      setDetail((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          related_signals: prev.related_signals.map((signal) =>
            signal.signal_id === signalId ? { ...signal, status: nextStatus } : signal
          ),
        };
      });
    } catch (error: any) {
      setStatusErrors((prev) => ({
        ...prev,
        [signalId]: error?.message ?? "Failed to update status",
      }));
    } finally {
      setStatusSaving((prev) => ({ ...prev, [signalId]: false }));
    }
  };

  return (
    <Drawer open={open} title="Transaction detail" onClose={onClose}>
      {!sourceEventId && <div className={styles.muted}>Select a transaction to inspect.</div>}
      {loading && <div className={styles.muted}>Loading transaction detail…</div>}
      {err && <div className={styles.error}>{err}</div>}
      {!loading && !err && detail && (
        <div className={styles.body}>
          <section className={styles.section}>
            <h3>Raw Event</h3>
            <div className={styles.grid}>
              <div>
                <div className={styles.label}>Source</div>
                <div>{detail.raw_event.source}</div>
              </div>
              <div>
                <div className={styles.label}>Source event id</div>
                <div className={styles.code}>{detail.raw_event.source_event_id}</div>
              </div>
              <div>
                <div className={styles.label}>Occurred at</div>
                <div>{formatDate(detail.raw_event.occurred_at)}</div>
              </div>
              <div>
                <div className={styles.label}>Ingested at</div>
                <div>{formatDate(detail.raw_event.created_at)}</div>
              </div>
              <div>
                <div className={styles.label}>Processed at</div>
                <div>{formatDate(detail.raw_event.processed_at)}</div>
              </div>
            </div>
            <div className={styles.payloadBlock}>
              <div className={styles.label}>Raw payload</div>
              <pre className={styles.payload}>{prettyJson(detail.raw_event.payload)}</pre>
            </div>
          </section>

          <section className={styles.section}>
            <h3>Normalized</h3>
            <div className={styles.grid}>
              <div>
                <div className={styles.label}>Date</div>
                <div>{detail.normalized_txn.date}</div>
              </div>
              <div>
                <div className={styles.label}>Description</div>
                <div>{detail.normalized_txn.description}</div>
              </div>
              <div>
                <div className={styles.label}>Amount</div>
                <div>{formatMoney(detail.normalized_txn.amount, detail.normalized_txn.direction)}</div>
              </div>
              <div>
                <div className={styles.label}>Direction</div>
                <div>{detail.normalized_txn.direction}</div>
              </div>
              <div>
                <div className={styles.label}>Counterparty hint</div>
                <div>{detail.normalized_txn.counterparty_hint ?? "—"}</div>
              </div>
              <div>
                <div className={styles.label}>Vendor normalization</div>
                <div>
                  {detail.vendor_normalization.canonical_name} · {detail.vendor_normalization.source}
                </div>
              </div>
              <div>
                <div className={styles.label}>Category hint</div>
                <div>{detail.normalized_txn.category_hint}</div>
              </div>
              <div>
                <div className={styles.label}>Merchant key</div>
                <div className={styles.code}>{detail.normalized_txn.merchant_key ?? "—"}</div>
              </div>
            </div>

            <div className={styles.subSection}>
              <div className={styles.label}>Processing assumptions</div>
              {assumptions.length === 0 ? (
                <div className={styles.muted}>No assumptions recorded.</div>
              ) : (
                <ul className={styles.list}>
                  {assumptions.map((item) => (
                    <li key={`${item.field}-${item.detail}`}>
                      <strong>{item.field}:</strong> {item.detail}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className={styles.subSection}>
              <div className={styles.label}>Ledger snapshot</div>
              {detail.ledger_context ? (
                <div className={styles.grid}>
                  <div>
                    <div className={styles.label}>Balance at row</div>
                    <div>${detail.ledger_context.balance.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className={styles.label}>Running inflows</div>
                    <div>${detail.ledger_context.running_total_in.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className={styles.label}>Running outflows</div>
                    <div>${detail.ledger_context.running_total_out.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className={styles.label}>Ledger row</div>
                    <div>
                      {detail.ledger_context.row.description} · {detail.ledger_context.row.category}
                    </div>
                  </div>
                </div>
              ) : (
                <div className={styles.muted}>No ledger row available (not yet categorized).</div>
              )}
              <div className={styles.linkRow}>
                <Link
                  to={`/app/${businessId}/ledger?anchor_source_event_id=${encodeURIComponent(
                    detail.source_event_id
                  )}`}
                  className={styles.linkButton}
                >
                  View in Ledger
                </Link>
              </div>
            </div>
          </section>

          <section className={styles.section}>
            <h3>Categorization</h3>
            {detail.categorization ? (
              <div className={styles.grid}>
                <div>
                  <div className={styles.label}>Category</div>
                  <div>{detail.categorization.category_name}</div>
                </div>
                <div>
                  <div className={styles.label}>Account</div>
                  <div>{detail.categorization.account_name}</div>
                </div>
                <div>
                  <div className={styles.label}>Source</div>
                  <div>{detail.categorization.source}</div>
                </div>
                <div>
                  <div className={styles.label}>Confidence</div>
                  <div>{Math.round(detail.categorization.confidence * 100)}%</div>
                </div>
                <div>
                  <div className={styles.label}>Rule ID</div>
                  <div className={styles.code}>{detail.categorization.rule_id ?? "—"}</div>
                </div>
                <div>
                  <div className={styles.label}>Note</div>
                  <div>{detail.categorization.note ?? "—"}</div>
                </div>
              </div>
            ) : (
              <div className={styles.muted}>No categorization applied yet.</div>
            )}
          </section>

          <section className={styles.section}>
            <h3>Related Signals</h3>
            {relatedSignals.length === 0 ? (
              <div className={styles.muted}>No related signals found.</div>
            ) : (
              <div className={styles.stack}>
                {relatedSignals.map((signal) => {
                  const selectedStatus =
                    statusSelections[signal.signal_id] ??
                    (signal.status as SignalStatus) ??
                    "open";
                  return (
                    <div key={signal.signal_id} className={styles.card}>
                      <div className={styles.cardTitle}>{signal.title ?? signal.signal_id}</div>
                      <div className={styles.cardMeta}>
                        {signal.domain ?? "signal"} · {signal.severity ?? "—"} ·{" "}
                        {signal.status ?? "—"}
                      </div>
                      {signal.matched_on && (
                        <div className={styles.cardMeta}>Matched on: {signal.matched_on}</div>
                      )}
                      {signal.window && (
                        <div className={styles.cardMeta}>
                          Window: {signal.window.start ?? "—"} → {signal.window.end ?? "—"}
                        </div>
                      )}
                      {signal.facts && (
                        <pre className={styles.payload}>{prettyJson(signal.facts)}</pre>
                      )}
                      <div className={styles.statusRow}>
                        <select
                          className={styles.statusSelect}
                          value={selectedStatus}
                          onChange={(event) =>
                            handleStatusSelect(
                              signal.signal_id,
                              event.target.value as SignalStatus
                            )
                          }
                        >
                          <option value="open">Open</option>
                          <option value="in_progress">In progress</option>
                          <option value="resolved">Resolved</option>
                          <option value="ignored">Ignored</option>
                        </select>
                        <button
                          className={styles.statusButton}
                          type="button"
                          onClick={() => handleStatusSave(signal.signal_id)}
                          disabled={statusSaving[signal.signal_id]}
                        >
                          {statusSaving[signal.signal_id] ? "Saving…" : "Update status"}
                        </button>
                      </div>
                      {statusErrors[signal.signal_id] && (
                        <div className={styles.error}>{statusErrors[signal.signal_id]}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className={styles.section}>
            <h3>Audit History</h3>
            {auditRows.length === 0 ? (
              <div className={styles.muted}>No audit history recorded.</div>
            ) : (
              <div className={styles.stack}>
                {auditRows.map((row) => (
                  <div key={row.id} className={styles.card}>
                    <div className={styles.cardTitle}>{row.event_type}</div>
                    <div className={styles.cardMeta}>
                      {row.actor} · {formatDate(row.created_at)} · {row.reason ?? "—"}
                    </div>
                    {(row.before_state || row.after_state) && (
                      <pre className={styles.payload}>
                        {prettyJson({ before: row.before_state, after: row.after_state })}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
}
