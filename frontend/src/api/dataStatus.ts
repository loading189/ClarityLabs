import { apiGet } from "./client";

export type DataStatus = {
  latest_event: {
    source?: string | null;
    occurred_at?: string | null;
  };
  open_signals: number;
  open_actions: number;
  ledger_rows: number;
  uncategorized_txns: number;
  last_sync_at?: string | null;
};

export function fetchDataStatus(businessId: string) {
  return apiGet<DataStatus>(`/api/diagnostics/status/${businessId}`);
}
