// src/api/demo.ts
import type {
  BusinessDetail,
  BrainLabelRequest,
  DashboardCard,
  DashboardDetail,
  DrilldownResponse,
} from "../types";
import { apiGet, apiPost } from "./client";

export function postBrainLabel(payload: BrainLabelRequest) {
  return apiPost<any>("/brain/label", payload);
}

export function fetchDashboard() {
  return apiGet<{ cards: DashboardCard[] }>("/demo/dashboard");
}

export function fetchBusinessHealth(businessId: string) {
  return apiGet<BusinessDetail>(`/demo/health/${businessId}`);
}

export function fetchBusinessDashboard(businessId: string) {
  return apiGet<DashboardDetail>(`/demo/dashboard/${businessId}`);
}

export function fetchCategoryDrilldown(
  businessId: string,
  category: string,
  windowDays = 30,
  limit = 50,
  offset = 0
) {
  const params = new URLSearchParams({
    business_id: businessId,
    category,
    window_days: String(windowDays),
    limit: String(limit),
    offset: String(offset),
  });
  return apiGet<DrilldownResponse>(`/demo/drilldown/category?${params.toString()}`);
}

export function fetchVendorDrilldown(
  businessId: string,
  vendor: string,
  windowDays = 30,
  limit = 50,
  offset = 0
) {
  const params = new URLSearchParams({
    business_id: businessId,
    vendor,
    window_days: String(windowDays),
    limit: String(limit),
    offset: String(offset),
  });
  return apiGet<DrilldownResponse>(`/demo/drilldown/vendor?${params.toString()}`);
}

export function updateHealthSignalStatus(
  businessId: string,
  signalId: string,
  payload: { status: string; resolution_note?: string | null }
) {
  return apiPost<{ status: string; resolved_at?: string | null; resolution_note?: string | null }>(
    `/demo/health/${businessId}/signals/${signalId}/status`,
    payload
  );
}

export function fetchReviewQueue(businessId: string, minConf = 0.75) {
  return apiGet<any>(`/demo/review_queue?business_id=${businessId}&min_conf=${minConf}`);
}

// ✅ FIX: use apiGet so API_BASE is respected
export function fetchMonthlyTrends(businessId: string, lookbackMonths = 12, k = 2.0) {
  const qs = new URLSearchParams({
    lookback_months: String(lookbackMonths),
    k: String(k),
  });
  return apiGet<any>(`/demo/analytics/monthly-trends/${businessId}?${qs.toString()}`);
}
