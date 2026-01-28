export type Risk = "green" | "yellow" | "red";
export type Severity = "green" | "yellow" | "red";
export type Dimension = "liquidity" | "stability" | "discipline" | "spend" | "revenue" | "ops";

export type DashboardCard = {
  business_id: string;
  name: string;
  risk: Risk;
  health_score: number;
  highlights: string[];
};

export type Signal = {
  key: string;
  title: string;
  severity: Severity;
  dimension: Dimension;
  priority: number;
  value: any;
  message: string;
  inputs?: string[] | null;
  conditions?: Record<string, any> | null;
  evidence?: Record<string, any> | null;
  why?: string | null;
  how_to_fix?: string | null;
  evidence_refs?: Array<Record<string, any>> | null;
  version?: number;
};

export type HealthSignalStatus = "open" | "monitoring" | "resolved";
export type HealthSignalDrilldownTarget = "transactions" | "categorize" | "ledger" | "trends";

export type HealthSignalEvidence = {
  date_range: { start: string; end: string; label?: string };
  metrics: Record<string, any>;
  examples: Array<Record<string, any>>;
};

export type HealthSignalDrilldown = {
  target: HealthSignalDrilldownTarget;
  payload?: Record<string, any> | null;
  label?: string | null;
};

export type HealthSignal = {
  id: string;
  title: string;
  severity: Severity;
  status: HealthSignalStatus;
  updated_at?: string | null;
  short_summary: string;
  why_it_matters: string;
  evidence: HealthSignalEvidence[];
  drilldowns: HealthSignalDrilldown[];
};

export type BusinessDetail = {
  business_id: string;
  name: string;
  as_of: string;
  risk: Risk;
  health_score: number;
  highlights: string[];
  signals: Signal[];
  health_signals?: HealthSignal[];
  pillars?: { liquidity: number; stability: number; discipline: number };
  ledger_preview?: Array<Record<string, any>>;
  facts?: Record<string, any>;
};

export type ReviewExample = {
  date: string;
  description: string;
  amount: number;
};

export type ReviewGroup = {
  merchant_key: string;
  canonical_guess?: string; 
  count: number;
  total_abs_amount: number;
  suggested_category?: string;
  suggested_confidence?: number;
  examples: ReviewExample[];
};

export type ReviewQueue = {
  business_id: string;
  groups: ReviewGroup[];
};

export type LabelScope = "business" | "global";

export type BrainLabelRequest = {
  description: string;
  canonical_name: string;
  category: string;
  confidence?: number;
};



