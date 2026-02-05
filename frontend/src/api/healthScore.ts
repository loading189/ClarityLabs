import { apiGet } from "./client";
import type { ChangeEvent } from "./changes";

export type HealthScoreContributor = {
  signal_id: string;
  domain: string;
  status: string;
  severity: string;
  penalty: number;
  rationale: string;
};

export type HealthScoreDomain = {
  domain:
    | "liquidity"
    | "revenue"
    | "expense"
    | "timing"
    | "concentration"
    | "hygiene"
    | "unknown";
  score: number;
  penalty: number;
  contributors: HealthScoreContributor[];
};

export type HealthScoreOut = {
  business_id: string;
  score: number;
  risk_score?: number | null;
  attention_score?: number | null;
  generated_at: string;
  domains: HealthScoreDomain[];
  contributors: HealthScoreContributor[];
  meta: {
    model_version: string;
    weights: Record<string, unknown>;
  };
};

export type HealthScoreImpact = {
  signal_id: string;
  domain: string | null;
  severity: string | null;
  change_type: "signal_detected" | "signal_resolved" | "signal_status_updated";
  estimated_penalty_delta: number;
  rationale: string;
};

export type HealthScoreExplainChangeOut = {
  business_id: string;
  computed_at: string;
  window: { since_hours: number };
  changes: ChangeEvent[];
  impacts: HealthScoreImpact[];
  summary: {
    headline: string;
    net_estimated_delta: number;
    top_drivers: string[];
  };
};

export function fetchHealthScore(businessId: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ business_id: businessId });
  return apiGet<HealthScoreOut>(`/api/health_score?${params.toString()}`, { signal });
}

export function fetchHealthScoreExplainChange(businessId: string, sinceHours = 72, limit = 20, signal?: AbortSignal) {
  const params = new URLSearchParams({
    business_id: businessId,
    since_hours: String(sinceHours),
    limit: String(limit),
  });
  return apiGet<HealthScoreExplainChangeOut>(`/api/health_score/explain_change?${params.toString()}`, { signal });
}
