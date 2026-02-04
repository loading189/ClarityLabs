import { apiGet } from "./client";

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

export function fetchHealthScore(businessId: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ business_id: businessId });
  return apiGet<HealthScoreOut>(`/api/health_score?${params.toString()}`, { signal });
}
