import { apiGet, apiPut } from "./client";

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
