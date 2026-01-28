// src/api/sim.ts
import { apiGet, apiPut, apiPost, apiDelete, apiPatch } from "./client";

/**
 * Existing SimConfig endpoints (keep as-is)
 */
export type SimConfig = {
  business_id: string;
  enabled: boolean;
  profile: string;
  avg_events_per_day: number;
  typical_ticket_cents: number;
  payroll_every_n_days: number;
  updated_at: string;
};

export type SimConfigUpsert = Partial<{
  enabled: boolean;
  profile: string;
  avg_events_per_day: number;
  typical_ticket_cents: number;
  payroll_every_n_days: number;
}>;

export function getSimConfig(businessId: string) {
  return apiGet<SimConfig>(`/sim/config/${businessId}`);
}

export function putSimConfig(businessId: string, patch: SimConfigUpsert) {
  return apiPut<SimConfig>(`/sim/config/${businessId}`, patch);
}

export function pulseSim(businessId: string, n = 25) {
  return apiPost<{ status: string; business_id: string; inserted: number }>(
    `/sim/pulse/${businessId}?n=${n}`,
    undefined
  );
}

/**
 * ---------------------------------------------------------------------------
 * Simulator v2 (Story + Levers + Interventions)
 * Backend routes assumed:
 *   GET    /simulator/catalog
 *   GET    /simulator/plan/{businessId}
 *   PUT    /simulator/plan/{businessId}
 *   GET    /simulator/interventions/{businessId}
 *   POST   /simulator/interventions/{businessId}
 *   PUT    /simulator/interventions/{businessId}/{id}
 *   DELETE /simulator/interventions/{businessId}/{id}
 *   POST   /simulator/generate/{businessId}
 * ---------------------------------------------------------------------------
 */

export type ScenarioCatalog = {
  version: number;
  scenarios: Array<{
    id: string;
    name: string;
    summary?: string;
    defaults?: Record<string, any>;
  }>;
};

export type SimPlanOut = {
  business_id: string;
  scenario_id: string;
  story_version: number;
  plan: Record<string, any>;
  story_text: string;
};

export type SimPlanUpsert = {
  scenario_id?: string;
  story_version?: number;
  plan: Record<string, any>;
};

export type SimIntervention = {
  id: string;
  business_id: string;
  kind: string; // "revenue_drop" | "expense_spike" | ...
  name: string;
  start_date: string; // YYYY-MM-DD
  duration_days: number | null;
  params: Record<string, any>;
  enabled: boolean;
  updated_at?: string;
};

export type SimInterventionCreate = {
  kind: string;
  name?: string;
  start_date: string;
  duration_days?: number | null;
  params?: Record<string, any>;
  enabled?: boolean;
};

export type SimInterventionPatch = Partial<{
  kind: string;
  name: string;
  start_date: string;
  duration_days: number | null;
  params: Record<string, any>;
  enabled: boolean;
}>;

export type GenerateRequest = {
  start_date: string;
  days: number;
  mode: "replace_from_start" | "append";

  seed?: number;
  events_per_day?: number;

  business_hours_only?: boolean;
  open_hour?: number;
  close_hour?: number;

  enable_shocks?: boolean;
  shock_days?: number;
  revenue_drop_pct?: number;   // 0..1
  expense_spike_pct?: number;  // 0..5
};



export type GenerateResponse = {
  status: string;
  business_id: string;
  start_date: string;
  days: number;
  inserted: number;
  deleted: number;
  shock_window?: { start: string; end: string } | null;
};

export type InterventionTemplate = {
  kind: string;
  label: string;
  description: string;
  defaults: Record<string, any>;
  fields: Array<{
    key: string;
    label: string;
    type: "number" | "percent" | "text" | "days";
    default?: any;
    min?: number;
    max?: number;
    step?: number;
  }>;
};

export type TruthOut = {
  business_id: string;
  scenario_id: string;
  story_version: number;
  truth_events: Array<Record<string, any>>;
};

export function getSimTruth(businessId: string) {
  return apiGet<TruthOut>(`/simulator/truth/${businessId}`);
}


export function getInterventionLibrary() {
  return apiGet<InterventionTemplate[]>(`/simulator/intervention-library`);
}


export function getScenarioCatalog() {
  return apiGet<ScenarioCatalog>(`/simulator/catalog`);
}

export function getSimPlan(businessId: string) {
  return apiGet<SimPlanOut>(`/simulator/plan/${businessId}`);
}

export function putSimPlan(businessId: string, payload: SimPlanUpsert) {
  return apiPut<SimPlanOut>(`/simulator/plan/${businessId}`, payload);
}

export function listSimInterventions(businessId: string) {
  return apiGet<SimIntervention[]>(`/simulator/interventions/${businessId}`);
}

export function createSimIntervention(businessId: string, payload: SimInterventionCreate) {
  // IMPORTANT: backend requires name (non-optional)
  return apiPost<SimIntervention>(`/simulator/interventions/${businessId}`, {
    ...payload,
    name: payload.name ?? payload.kind,
  });
}


export function updateSimIntervention(
  businessId: string,
  interventionId: string,
  patch: SimInterventionPatch
) {
  return apiPatch<SimIntervention>(`/simulator/interventions/${businessId}/${interventionId}`, patch);
}


export function deleteSimIntervention(businessId: string, interventionId: string) {
  return apiDelete<{ status: string; deleted: number }>(
    `/simulator/interventions/${businessId}/${interventionId}`
  );
}

export function generateSimEvents(businessId: string, payload: GenerateRequest) {
  return apiPost<GenerateResponse>(`/simulator/generate/${businessId}`, payload);
}

