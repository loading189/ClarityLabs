// src/api/demo.ts
import type { DashboardCard, BusinessDetail, BrainLabelRequest } from "../types";
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
