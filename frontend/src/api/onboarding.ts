import { apiGet, apiPost } from "./client";

export type CreateOrgIn = {
  name: string;
};

export type OrgOut = {
  id: string;
  name: string;
  created_at: string;
};

export type BootstrapBusinessIn = {
  org_id: string;
  name: string;
  industry?: string | null;
  bank?: boolean;
  payroll?: boolean;
  card_processor?: boolean;
  ecommerce?: boolean;
  invoicing?: boolean;
  scenario_id?: string | null;
  sim_enabled?: boolean;
  avg_events_per_day?: number;
  typical_ticket_cents?: number;
  payroll_every_n_days?: number;
};

export type BusinessOut = {
  id: string;
  org_id: string;
  name: string;
  industry?: string | null;
  created_at: string;
};

export type SimulatorConfigOut = {
  business_id: string;
  enabled: boolean;
  profile: string;
  avg_events_per_day: number;
  typical_ticket_cents: number;
  payroll_every_n_days: number;
  updated_at: string;
};

export type IntegrationProfileOut = {
  business_id: string;
  bank: boolean;
  payroll: boolean;
  card_processor: boolean;
  ecommerce: boolean;
  invoicing: boolean;
  scenario_id: string;
  story_version: number;
  simulation_params: Record<string, any>;
  updated_at: string;
};

export type BootstrapBusinessOut = {
  business: BusinessOut;
  sim_config: SimulatorConfigOut;
  integration_profile: IntegrationProfileOut;
};

export type BusinessStatusOut = {
  business_id: string;
  has_accounts: boolean;
  accounts_count: number;
  has_events: boolean;
  events_count: number;
  sim_enabled: boolean;
  ready: boolean;
};

export function createOrg(payload: CreateOrgIn) {
  return apiPost<OrgOut>("/onboarding/orgs", payload);
}

export function bootstrapBusiness(payload: BootstrapBusinessIn) {
  return apiPost<BootstrapBusinessOut>("/onboarding/businesses/bootstrap", payload);
}

export function getBusinessStatus(businessId: string, options?: { signal?: AbortSignal }) {
  return apiGet<BusinessStatusOut>(`/onboarding/businesses/${businessId}/status`, options);
}
