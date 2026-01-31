export type AnalyticsLine = {
  occurred_at: string;
  source_event_id: string;
  signed_amount: number;
  category_name?: string | null;
  counterparty_hint?: string | null;
};

export type TraceBundle = {
  supporting_event_ids: string[];
  supporting_line_count: number;
  computation_version: string;
  features_snapshot: Record<string, unknown>;
};

export type TracedMetric = {
  value: number;
  trace: TraceBundle;
};

const COMPUTATION_VERSION = "analytics_core_v1";

function traceBundle(supportingEventIds: string[], featuresSnapshot: Record<string, unknown>) {
  return {
    supporting_event_ids: supportingEventIds,
    supporting_line_count: supportingEventIds.length,
    computation_version: COMPUTATION_VERSION,
    features_snapshot: featuresSnapshot,
  } satisfies TraceBundle;
}

function tracedMetric(value: number, supportingEventIds: string[], metric: string): TracedMetric {
  return {
    value,
    trace: traceBundle(supportingEventIds, { metric }),
  };
}

function sortLines(lines: AnalyticsLine[]) {
  return [...lines].sort((a, b) => {
    const timeDiff = new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime();
    if (timeDiff !== 0) return timeDiff;
    return a.source_event_id.localeCompare(b.source_event_id);
  });
}

export function computeLedgerSummary(lines: AnalyticsLine[]) {
  const ordered = sortLines(lines);
  const inflowIds: string[] = [];
  const outflowIds: string[] = [];
  const netIds: string[] = [];

  let inflow = 0;
  let outflow = 0;
  let net = 0;

  for (const line of ordered) {
    netIds.push(line.source_event_id);
    if (line.signed_amount >= 0) {
      inflow += line.signed_amount;
      inflowIds.push(line.source_event_id);
    } else {
      outflow += Math.abs(line.signed_amount);
      outflowIds.push(line.source_event_id);
    }
    net += line.signed_amount;
  }

  return {
    inflow: tracedMetric(inflow, inflowIds, "inflow"),
    outflow: tracedMetric(outflow, outflowIds, "outflow"),
    net: tracedMetric(net, netIds, "net"),
    count: ordered.length,
  };
}

export function computeRunningBalance(lines: AnalyticsLine[]) {
  const ordered = sortLines(lines);
  const map = new Map<string, number>();
  let balance = 0;
  for (const line of ordered) {
    balance += line.signed_amount;
    map.set(line.source_event_id, balance);
  }
  return map;
}
