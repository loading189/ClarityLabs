import { apiGet } from "./client";

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
