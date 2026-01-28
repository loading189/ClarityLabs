import { apiGet, apiPost } from "./client";

export type NormalizedTxn = {
  source_event_id: string;
  occurred_at: string;
  description: string;
  amount: number;
  direction: string;
  account: string;
  category_hint: string;

  suggested_system_key?: string | null;
  suggested_category_id?: string | null;
  suggested_category_name?: string | null;
  suggestion_source?: string | null;
  confidence?: number | null;
  reason?: string | null;
  merchant_key?: string | null;
};



export type CategoryOut = {
  id: string;
  name: string;
  system_key?: string | null;
  account_id: string;
  account_code?: string | null;
  account_name: string;
};


export function labelVendor(
  businessId: string,
  payload: { source_event_id: string; system_key: string; canonical_name?: string; confidence?: number }
) {
  return apiPost<any>(`/categorize/business/${businessId}/label_vendor`, payload);
}


export function getTxnsToCategorize(businessId: string, limit = 50) {
  return apiGet<NormalizedTxn[]>(`/categorize/business/${businessId}/txns?limit=${limit}&only_uncategorized=true`);
}

export function getCategories(businessId: string) {
  return apiGet<CategoryOut[]>(`/categorize/business/${businessId}/categories`);
}

export function saveCategorization(
  businessId: string,
  payload: {
    source_event_id: string;
    category_id: string;
    source?: string;
    confidence?: number;
    note?: string | null;
  }
) {
  return apiPost<{ status: string; updated: boolean; learned?: boolean; learned_system_key?: string | null }>(
    `/categorize/business/${businessId}/categorize`,
    payload
  );
}

