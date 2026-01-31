import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";

export type ScenarioCatalog = {
  version?: number;
  scenarios?: Array<{
    id: string;
    name?: string;
    summary?: string;
    defaults?: Record<string, any>;
  }>;
};

export type SimPlanOut = {
  business_id: string;
  scenario_id: string;
  story_version: number;
  plan: Record<string, any>;
  story_text?: string;
};

export type SimPlanUpsert = {
  scenario_id: string;
  story_version: number;
  plan: Record<string, any>;
};

export type InterventionOut = {
  id: string;
  business_id: string;
  kind: string;
  name: string;
  start_date: string;
  duration_days: number | null;
  params: Record<string, any>;
  enabled: boolean;
  updated_at?: string | null;
};

export type InterventionCreate = {
  kind: string;
  name: string;
  start_date: string;
  duration_days?: number | null;
  params?: Record<string, any>;
  enabled?: boolean;
};

export type InterventionPatch = Partial<{
  kind: string;
  name: string;
  start_date: string;
  duration_days: number | null;
  params: Record<string, any>;
  enabled: boolean;
}>;

export type InterventionTemplateField = {
  key: string;
  label: string;
  type: "number" | "percent" | "text" | "days";
  default?: any;
  min?: number;
  max?: number;
  step?: number;
};

export type InterventionTemplate = {
  kind: string;
  label: string;
  description: string;
  defaults: Record<string, any>;
  fields: InterventionTemplateField[];
};

export type GenerateIn = {
  start_date: string;
  days: number;
  seed?: number;
  events_per_day?: number;
  enable_shocks?: boolean;
  shock_days?: number;
  revenue_drop_pct?: number;
  expense_spike_pct?: number;
  mode: "append" | "replace_from_start";
};

export type GenerateOut = {
  status: string;
  business_id: string;
  start_date: string;
  days: number;
  inserted: number;
  deleted: number;
  shock_window?: { start: string; end: string } | null;
};

export type TruthOut = {
  business_id: string;
  scenario_id: string;
  story_version: number;
  truth_events: Array<Record<string, any>>;
};

export function getScenarioCatalog(options?: { signal?: AbortSignal }) {
  return apiGet<ScenarioCatalog>("/simulator/catalog", options);
}

export function getSimPlan(businessId: string, options?: { signal?: AbortSignal }) {
  return apiGet<SimPlanOut>(`/simulator/plan/${businessId}`, options);
}

export function putSimPlan(businessId: string, payload: SimPlanUpsert) {
  return apiPut<SimPlanOut>(`/simulator/plan/${businessId}`, payload);
}

export function getSimTruth(businessId: string, options?: { signal?: AbortSignal }) {
  return apiGet<TruthOut>(`/simulator/truth/${businessId}`, options);
}

export function getInterventionLibrary(options?: { signal?: AbortSignal }) {
  return apiGet<InterventionTemplate[]>("/simulator/intervention-library", options);
}

export function listSimInterventions(businessId: string, options?: { signal?: AbortSignal }) {
  return apiGet<InterventionOut[]>(`/simulator/interventions/${businessId}`, options);
}

export function createSimIntervention(businessId: string, payload: InterventionCreate) {
  return apiPost<InterventionOut>(`/simulator/interventions/${businessId}`, payload);
}

export function patchSimIntervention(
  businessId: string,
  interventionId: string,
  patch: InterventionPatch
) {
  return apiPatch<InterventionOut>(
    `/simulator/interventions/${businessId}/${interventionId}`,
    patch
  );
}

export function deleteSimIntervention(businessId: string, interventionId: string) {
  return apiDelete<{ status: string; deleted: number }>(
    `/simulator/interventions/${businessId}/${interventionId}`
  );
}

export function generateSimHistory(businessId: string, payload: GenerateIn) {
  return apiPost<GenerateOut>(`/simulator/generate/${businessId}`, payload);
}
