import { apiGet } from "./client";

export type AppConfig = {
  pilot_mode_enabled: boolean;
  allow_business_delete: boolean;
};

export function fetchConfig() {
  return apiGet<AppConfig>("/api/config");
}
