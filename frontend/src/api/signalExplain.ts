import { apiGet } from "./client";

export type SignalExplainCaseFile = {
  signal_id: string;
  business_id: string;
  title: string;
  status: string;
  severity: string | null;
  detector: { domain: string; rule_id: string; version: string };
  linked_action_id: string | null;
  narrative: {
    headline: string;
    why_it_matters: string[];
    what_changed: string[];
  };
  case_evidence: {
    window: { start: string | null; end: string | null };
    stats: { baseline_total: number | null; current_total: number | null; pct_change: number | null };
    top_transactions: Array<{
      occurred_at: string | null;
      source_event_id: string;
      amount: number | null;
      vendor?: string | null;
      name?: string | null;
      memo?: string | null;
    }>;
    ledger_anchors: Array<{ anchor_id: string; occurred_at: string | null; source_event_id: string | null }>;
  };
};

export function fetchSignalExplain(businessId: string, signalId: string, signal?: AbortSignal) {
  return apiGet<SignalExplainCaseFile>(`/api/signals/${businessId}/${signalId}/explain`, { signal });
}
