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

export type DashboardKpis = {
  current_cash: TracedMetric;
  last_30d_inflow: TracedMetric;
  last_30d_outflow: TracedMetric;
  last_30d_net: TracedMetric;
  prev_30d_inflow: TracedMetric;
  prev_30d_outflow: TracedMetric;
  prev_30d_net: TracedMetric;
};

export type DashboardSignalDrilldown = {
  kind: "category" | "vendor";
  value: string;
  window_days: number;
  label?: string | null;
};

export type DashboardSignal = {
  key: string;
  title: string;
  severity: Severity;
  dimension: Dimension;
  priority: number;
  value: any;
  message: string;
  drilldown?: DashboardSignalDrilldown | null;
};

export type DashboardTrends = {
  experiment: Record<string, any>;
  metrics: Record<string, any>;
  cash: Record<string, any>;
  series: Array<Record<string, any>>;
  band?: Record<string, any> | null;
  status: string;
  current?: Record<string, any> | null;
};

export type DashboardDetail = {
  metadata: {
    business_id: string;
    name: string;
    as_of: string;
    last_event_occurred_at?: string | null;
    start_at?: string | null;
    end_at?: string | null;
  };
  kpis: DashboardKpis;
  signals: DashboardSignal[];
  trends: DashboardTrends;
  analytics: AnalyticsPayload;
};

export type TraceBundle = {
  supporting_event_ids: string[];
  supporting_line_count: number;
  computation_version: string;
  features_snapshot: Record<string, any>;
};

export type TracedMetric = {
  value: number;
  trace: TraceBundle;
};

export type AnalyticsSeriesRow = {
  month: string;
  inflow: TracedMetric;
  outflow: TracedMetric;
  net: TracedMetric;
  cash_end: TracedMetric;
};

export type AnalyticsPayload = {
  computation_version: string;
  kpis: DashboardKpis;
  series: AnalyticsSeriesRow[];
  category_breakdown: Array<Record<string, any>>;
  vendor_concentration: Array<Record<string, any>>;
  anomalies: Array<Record<string, any>>;
  change_explanations: Record<string, any>;
};

export type DrilldownRow = {
  source_event_id: string;
  occurred_at: string;
  date: string;
  description: string;
  amount: number;
  direction: string;
  account: string;
  category: string;
  counterparty_hint?: string | null;
  merchant_key: string;
};

export type DrilldownResponse = {
  business_id: string;
  name: string;
  window_days: number;
  limit: number;
  offset: number;
  total: number;
  rows: DrilldownRow[];
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

export type HealthSignalStatus = "open" | "in_progress" | "resolved" | "ignored";
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
  last_seen_at?: string | null;
  resolved_at?: string | null;
  resolution_note?: string | null;
  short_summary: string;
  why_it_matters: string;
  evidence: HealthSignalEvidence[];
  drilldowns: HealthSignalDrilldown[];
  fix_suggestions?: Array<{
    merchant_key: string;
    suggested_category_id: string;
    suggested_category_name: string;
    contains_text?: string | null;
    direction?: string | null;
    account?: string | null;
    sample_description?: string | null;
    sample_source_event_id?: string | null;
    sample_amount?: number | null;
    sample_occurred_at?: string | null;
    count?: number | null;
    total_abs_amount?: number | null;
  }>;
};

export type BusinessDetail = {
  business_id: string;
  name: string;
  as_of: string;
  start_at?: string | null;
  end_at?: string | null;
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
