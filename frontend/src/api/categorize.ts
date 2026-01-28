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

export type BrainVendor = {
  merchant_id: string;
  canonical_name: string;
  system_key: string;
  confidence: number;
  evidence_count: number;
  updated_at: string;
  alias_keys?: string[] | null;
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

export type CategorizeMetricsOut = {
  total_events: number;
  posted: number;
  uncategorized: number;
  suggestion_coverage: number;
  brain_coverage: number;
};

export type BulkApplyByMerchantKeyIn = {
  merchant_key: string;
  category_id: string;
  source?: string;
  confidence?: number;
  note?: string | null;
};

export type BulkApplyByMerchantKeyOut = {
  status: string;
  matched_events: number;
  created: number;
  updated: number;
};

export function labelVendor(
  businessId: string,
  payload: { source_event_id: string; system_key: string; canonical_name?: string; confidence?: number }
) {
  return apiPost<any>(`/categorize/business/${businessId}/label_vendor`, payload);
}

export function getBrainVendors(businessId: string) {
  return apiGet<BrainVendor[]>(`/categorize/business/${businessId}/brain/vendors`);
}

export function getBrainVendor(businessId: string, merchantKey: string) {
  const params = new URLSearchParams({ merchant_key: merchantKey });
  return apiGet<BrainVendor>(`/categorize/business/${businessId}/brain/vendor?${params.toString()}`);
}

export function setBrainVendor(
  businessId: string,
  payload: { merchant_key: string; category_id: string; canonical_name?: string; confidence?: number }
) {
  return apiPost<BrainVendor>(`/categorize/business/${businessId}/brain/vendor/set`, payload);
}

export function forgetBrainVendor(businessId: string, payload: { merchant_key: string }) {
  return apiPost<{ status: string; deleted: boolean }>(
    `/categorize/business/${businessId}/brain/vendor/forget`,
    payload
  );
}

export function getTxnsToCategorize(businessId: string, limit = 50) {
  return apiGet<NormalizedTxn[]>(`/categorize/business/${businessId}/txns?limit=${limit}&only_uncategorized=true`);
}

export function getCategories(businessId: string) {
  return apiGet<CategoryOut[]>(`/categorize/business/${businessId}/categories`);
}

export function getCategorizeMetrics(businessId: string) {
  return apiGet<CategorizeMetricsOut>(`/categorize/business/${businessId}/categorize/metrics`);
}

export function bulkApplyByMerchantKey(businessId: string, payload: BulkApplyByMerchantKeyIn) {
  return apiPost<BulkApplyByMerchantKeyOut>(`/categorize/business/${businessId}/categorize/bulk_apply`, payload);
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
