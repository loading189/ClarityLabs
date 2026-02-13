import { apiGet } from "./client";

export type RiskBand = "stable" | "watch" | "elevated" | "at_risk";

export interface FirmOverviewBusiness {
  business_id: string;
  business_name: string;
  risk_score: number;
  risk_band: RiskBand;
  open_signals: number;
  signals_by_severity: {
    critical: number;
    warning: number;
    info: number;
  };
  open_actions: number;
  stale_actions: number;
  uncategorized_txn_count: number;
  latest_signal_at?: string | null;
  latest_action_at?: string | null;
}

export interface FirmOverviewResponse {
  businesses: FirmOverviewBusiness[];
  generated_at: string;
}

export async function fetchFirmOverview(): Promise<FirmOverviewResponse> {
  return apiGet("/api/firm/overview");
}
