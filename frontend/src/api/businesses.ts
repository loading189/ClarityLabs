import { apiDelete, apiPost } from "./client";

export type BusinessOut = {
  id: string;
  name: string;
  org_id: string;
  created_at: string;
  is_demo?: boolean;
};

export function createBusiness(payload: { name: string; is_demo?: boolean }) {
  return apiPost<BusinessOut>("/api/businesses", payload);
}

export function deleteBusiness(businessId: string) {
  return apiDelete<{ deleted: boolean; business_id: string }>(`/api/businesses/${businessId}?confirm=true`);
}
