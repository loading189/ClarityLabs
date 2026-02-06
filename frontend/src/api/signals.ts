import { apiGet, apiPost } from "./client";

export type SignalSeverity =
  | "green"
  | "yellow"
  | "red"
  | "info"
  | "warning"
  | "critical"
  | "low"
  | "medium"
  | "high";

export interface Signal {
  id: string;
  type: string;
  severity: SignalSeverity;
  window: string;
  baseline_value: number | null;
  current_value: number | null;
  delta: number | null;
  explanation_seed: Record<string, unknown>;
  confidence: number;
}

export interface SignalsResponse {
  signals: Signal[];
  meta: Record<string, unknown>;
}

export async function fetchSignals(
  businessId: string,
  params: { start_date: string; end_date: string },
  signal?: AbortSignal
): Promise<SignalsResponse> {
  const query = new URLSearchParams({
    business_id: businessId,
    start_date: params.start_date,
    end_date: params.end_date,
  });
  return apiGet<SignalsResponse>(`/api/signals/v1?${query.toString()}`, { signal });
}

export type SignalStatus = "open" | "in_progress" | "resolved" | "ignored";

export type SignalState = {
  id: string;
  type: string | null;
  domain?: string | null;
  severity: SignalSeverity | null;
  status: SignalStatus;
  title: string | null;
  summary: string | null;
  updated_at: string | null;
};

export type SignalStateDetail = SignalState & {
  payload_json: Record<string, unknown> | null;
  fingerprint: string | null;
  detected_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
};

export type SignalStateResponse = {
  signals: SignalState[];
  meta: Record<string, unknown>;
};

export type SignalStatusUpdateInput = {
  status: SignalStatus;
  reason?: string | null;
  actor?: string | null;
};

export type SignalStatusUpdateResponse = {
  business_id: string;
  signal_id: string;
  status: SignalStatus;
  last_seen_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  reason: string | null;
  audit_id: string;
};

export function listSignalStates(businessId: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ business_id: businessId });
  return apiGet<SignalStateResponse>(`/api/signals?${query.toString()}`, { signal });
}

export function getSignalDetail(
  businessId: string,
  signalId: string,
  signal?: AbortSignal
) {
  return apiGet<SignalStateDetail>(`/api/signals/${businessId}/${signalId}`, { signal });
}

export type SignalExplainEvidence = {
  key: string;
  label: string;
  value: string | number | boolean | null;
  unit?: string | null;
  as_of?: string | null;
  source: "ledger" | "state" | "derived" | "detector";
  anchors?: {
    txn_ids?: string[] | null;
    date_start?: string | null;
    date_end?: string | null;
    account_id?: string | null;
    vendor?: string | null;
    category?: string | null;
  } | null;
};


export type SignalExplainNextAction = {
  key: string;
  label: string;
  action: "acknowledge" | "snooze" | "resolve" | null;
  suggested_snooze_minutes?: number | null;
  requires_reason: boolean;
  rationale: string;
  guardrails?: string[] | null;
};


export type SignalExplainClearCondition = {
  summary: string;
  type: "threshold" | "trend" | "categorical";
  fields?: string[] | null;
  window_days?: number | null;
  comparator?: ">=" | "<=" | "==" | null;
  target?: number | string | null;
};

export type SignalExplainPlaybook = {
  id: string;
  title: string;
  description: string;
  kind: "inspect" | "adjust" | "decide";
  ui_target: "ledger" | "vendors" | "rules" | "categorize" | "assistant";
  deep_link?: string | null;
  requires_confirmation?: boolean | null;
};

export type SignalVerificationStatus = "met" | "not_met" | "unknown";

export type SignalExplainVerification = {
  status: SignalVerificationStatus;
  checked_at: string;
  facts: Array<{ key: string; label: string; value: string | number | boolean | null; source: "ledger" | "state" | "derived" | "detector" }>;
};

export type SignalExplainAudit = {
  id: string;
  event_type: string;
  actor: string | null;
  reason: string | null;
  status: string | null;
  created_at: string | null;
};

export type SignalExplainOut = {
  business_id: string;
  signal_id: string;
  state: {
    status: SignalStatus;
    severity: SignalSeverity | null;
    created_at: string | null;
    updated_at: string | null;
    last_seen_at: string | null;
    resolved_at: string | null;
    metadata: Record<string, unknown> | null;
    resolved_condition_met: boolean;
  };
  detector: {
    type: string;
    title: string;
    description: string;
    domain: string;
    default_severity: string | null;
    recommended_actions: Array<{
      action_id: string;
      label: string;
      rationale: string;
      parameters?: Record<string, unknown> | null;
    }>;
    evidence_schema: string[];
    scoring_profile: Record<string, unknown>;
  };
  evidence: SignalExplainEvidence[];
  related_audits: SignalExplainAudit[];
  next_actions: SignalExplainNextAction[];
  clear_condition: SignalExplainClearCondition | null;
  verification: SignalExplainVerification;
  playbooks: SignalExplainPlaybook[];
  links: string[];
};

export function getSignalExplain(
  businessId: string,
  signalId: string,
  signal?: AbortSignal
) {
  return apiGet<SignalExplainOut>(`/api/signals/${businessId}/${signalId}/explain`, { signal });
}

export function updateSignalStatus(
  businessId: string,
  signalId: string,
  payload: SignalStatusUpdateInput
): Promise<SignalStatusUpdateResponse>;
export function updateSignalStatus(
  businessId: string,
  signalId: string,
  payload: SignalStatusUpdateInput,
  options: { mode: "demo" }
): Promise<LegacySignalStatusUpdateResponse>;
export function updateSignalStatus(
  businessId: string,
  signalId: string,
  payload: SignalStatusUpdateInput,
  options?: { mode?: "demo" }
) {
  if (options?.mode === "demo") {
    return apiPost<LegacySignalStatusUpdateResponse>(
      `/demo/health/${businessId}/signals/${signalId}/status`,
      {
        status: payload.status,
        resolution_note: payload.reason ?? null,
      }
    );
  }
  return apiPost<SignalStatusUpdateResponse>(
    `/api/signals/${businessId}/${signalId}/status`,
    payload
  );
}

export type LegacySignalStatusUpdateResponse = {
  status: SignalStatus;
  resolved_at?: string | null;
  resolution_note?: string | null;
};
