import { apiGet, apiPost } from "./client";

export type SimCatalog = {
  presets: { id: string; title: string; scenarios: { id: string; intensity: number }[] }[];
  scenarios: { id: string; title: string; description: string; expected_signals: string[] }[];
};

export type SimSeedRequest = {
  business_id: string;
  preset_id?: string;
  scenarios?: { id: string; intensity?: number }[];
  anchor_date?: string;
  lookback_days?: number;
  forward_days?: number;
  mode?: "replace" | "append";
  seed?: number;
};

export type SimSeedResponse = {
  business_id: string;
  window: {
    anchor_date: string;
    start_date: string;
    end_date: string;
    lookback_days: number;
    forward_days: number;
  };
  preset_id?: string;
  scenarios_applied: { id: string; intensity: number }[];
  stats: { raw_events_inserted: number; raw_events_deleted?: number; pulse_ran: boolean };
  signals: {
    total: number;
    by_severity: Record<string, number>;
    by_domain: Record<string, number>;
    top: { signal_id: string; status: string; severity: string; domain: string; title: string }[];
  };
};

export function getSimV2Catalog() {
  return apiGet<SimCatalog>("/api/sim_v2/catalog");
}

export function seedSimV2(payload: SimSeedRequest) {
  return apiPost<SimSeedResponse>("/api/sim_v2/seed", payload);
}

export function resetSimV2(business_id: string) {
  return apiPost<{ business_id: string; deleted_raw_events: number; pulse_ran: boolean }>(
    "/api/sim_v2/reset",
    { business_id }
  );
}
