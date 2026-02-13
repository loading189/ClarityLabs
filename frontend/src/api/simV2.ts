import { apiGet, apiPost } from "./client";

export type SimCatalog = {
  scenarios: { id: string; name: string; description: string; tags: string[]; parameters: Record<string, unknown> }[];
};

export type SimSeedRequest = {
  business_id: string;
  scenario_id: string;
  params?: Record<string, unknown>;
};

export type SimSeedResponse = {
  business_id: string;
  scenario_id: string;
  seed_key: number;
  summary: {
    txns_created: number;
    ledger_rows: number;
    signals_open_count: number;
    actions_open_count?: number | null;
  };
};

export function getSimV2Catalog() {
  return apiGet<SimCatalog>("/api/scenarios/catalog");
}

export function seedSimV2(payload: SimSeedRequest) {
  return apiPost<SimSeedResponse>("/api/scenarios/seed", payload);
}

export function resetSimV2(business_id: string) {
  return apiPost<{ business_id: string; deleted_raw_events: number }>("/api/scenarios/reset", { business_id });
}
