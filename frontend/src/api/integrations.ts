import { apiGet, apiPost, apiPut } from "./client";

export type IntegrationProfile = {
  business_id: string;
  bank: boolean;
  payroll: boolean;
  card_processor: boolean;
  ecommerce: boolean;
  invoicing: boolean;
  simulation_params: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type IntegrationProfileUpsert = Partial<
  Pick<
    IntegrationProfile,
    "bank" | "payroll" | "card_processor" | "ecommerce" | "invoicing" | "simulation_params"
  >
>;

// Ensures we never send `simulation_params: null`
function sanitizeUpsertPayload(payload: IntegrationProfileUpsert): IntegrationProfileUpsert {
  const out: IntegrationProfileUpsert = { ...payload };
  if ((out as any).simulation_params === null) {
    delete (out as any).simulation_params; // treat null like "not provided"
  }
  return out;
}

export function getIntegrationProfile(businessId: string) {
  return apiGet<IntegrationProfile>(`/integrations/business/${businessId}`);
}

export function putIntegrationProfile(businessId: string, payload: IntegrationProfileUpsert) {
  return apiPut<IntegrationProfile>(`/integrations/business/${businessId}`, sanitizeUpsertPayload(payload));
}

export type IntegrationConnection = {
  id: string;
  business_id: string;
  provider: string;
  is_enabled: boolean;
  status: "connected" | "disabled" | "error" | "disconnected";
  disconnected_at?: string | null;
  last_sync_at?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error?: Record<string, any> | null;
  provider_cursor?: string | null;
  last_ingested_source_event_id?: string | null;
  last_processed_source_event_id?: string | null;
};

export type ReplayRequest = {
  since?: string | null;
  last_n?: number | null;
};

export function getIntegrationConnections(businessId: string) {
  return apiGet<IntegrationConnection[]>(`/integrations/${businessId}/connections`);
}

export function syncIntegration(businessId: string, provider: string) {
  return apiPost<any>(`/integrations/${businessId}/${provider}/sync`, {});
}

export function replayIntegration(businessId: string, provider: string, payload: ReplayRequest = {}) {
  return apiPost<any>(`/integrations/${businessId}/${provider}/replay`, payload);
}

export function toggleIntegration(businessId: string, provider: string, isEnabled: boolean) {
  return apiPost<IntegrationConnection>(`/integrations/${businessId}/${provider}/toggle`, {
    is_enabled: isEnabled,
  });
}

export function disconnectIntegration(businessId: string, provider: string) {
  return apiPost<IntegrationConnection>(`/integrations/${businessId}/${provider}/disconnect`, {});
}
