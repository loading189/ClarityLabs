import { apiGet } from "./client";

export type MembershipSummary = {
  business_id: string;
  business_name: string;
  role: string;
};

export type CurrentUser = {
  id: string;
  email: string;
  name?: string | null;
  memberships: MembershipSummary[];
};

export function fetchMe() {
  return apiGet<CurrentUser>("/api/me");
}
