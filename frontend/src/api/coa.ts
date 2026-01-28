import { apiGet, apiPost, apiPut, apiDelete } from "./client";

export type AccountType = "asset" | "liability" | "equity" | "revenue" | "expense";

export type Account = {
  id: string;
  business_id: string;
  code?: string | null;
  name: string;
  type: AccountType;
  subtype?: string | null;
  active: boolean;
  created_at: string;
};

export type AccountCreate = {
  code?: string;
  name: string;
  type: AccountType;
  subtype?: string;
  active?: boolean;
};

export type AccountUpdate = Partial<AccountCreate> & { active?: boolean };

export function listAccounts(businessId: string, includeInactive = false) {
  return apiGet<Account[]>(`/coa/business/${businessId}/accounts?include_inactive=${includeInactive}`);
}

export function createAccount(businessId: string, payload: AccountCreate) {
  return apiPost<Account>(`/coa/business/${businessId}/accounts`, payload);
}

export function updateAccount(businessId: string, accountId: string, payload: AccountUpdate) {
  return apiPut<Account>(`/coa/business/${businessId}/accounts/${accountId}`, payload);
}

export function deactivateAccount(businessId: string, accountId: string) {
  return apiDelete<any>(`/coa/business/${businessId}/accounts/${accountId}`);
}
