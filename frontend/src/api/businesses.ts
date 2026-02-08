import { apiDelete, apiGet, apiPost } from "./client";

export type BusinessOut = {
  id: string;
  name: string;
  org_id: string;
  created_at: string;
  is_demo?: boolean;
};

export type BusinessMembershipSummary = {
  business_id: string;
  business_name: string;
  role: string;
};

export type BusinessMember = {
  id: string;
  email: string;
  name?: string | null;
  role: string;
};

export function createBusiness(payload: { name: string; is_demo?: boolean }) {
  return apiPost<BusinessOut>("/api/businesses", payload);
}

export function deleteBusiness(businessId: string) {
  return apiDelete<{ deleted: boolean; business_id: string }>(`/api/businesses/${businessId}?confirm=true`);
}

export function fetchBusinessesMine() {
  return apiGet<BusinessMembershipSummary[]>("/api/businesses/mine");
}

export function fetchBusinessMembers(businessId: string) {
  return apiGet<BusinessMember[]>(`/api/businesses/${businessId}/members`);
}
