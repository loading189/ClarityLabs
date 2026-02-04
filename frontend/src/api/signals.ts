import { apiGet, apiPost } from "./client";

export type SignalSeverity = "green" | "yellow" | "red";

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
  return apiGet<SignalsResponse>(`/api/signals?${query.toString()}`, { signal });
}

export type SignalStatus = "open" | "in_progress" | "resolved" | "ignored";

export type SignalState = {
  id: string;
  type: string | null;
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

export function updateSignalStatus(
  businessId: string,
  signalId: string,
  payload: SignalStatusUpdateInput
) {
  return apiPost<SignalStatusUpdateResponse>(
    `/api/signals/${businessId}/${signalId}/status`,
    payload
  );
}
