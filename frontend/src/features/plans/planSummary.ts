import type { PlanCondition, PlanObservation, PlanObservationVerdict, PlanStatus } from "../../api/plansV2";

export function formatPlanStatus(status: PlanStatus) {
  switch (status) {
    case "draft":
      return "Draft";
    case "active":
      return "Active";
    case "succeeded":
      return "Succeeded";
    case "failed":
      return "Failed";
    case "canceled":
      return "Canceled";
    default:
      return status;
  }
}

export function planStatusTone(status: PlanStatus) {
  switch (status) {
    case "succeeded":
      return "success" as const;
    case "failed":
      return "danger" as const;
    case "canceled":
      return "warning" as const;
    case "active":
      return "info" as const;
    case "draft":
    default:
      return "neutral" as const;
  }
}

export function formatVerdict(verdict?: PlanObservationVerdict | null) {
  if (!verdict) return "No verdict";
  switch (verdict) {
    case "no_change":
      return "No change";
    case "improving":
      return "Improving";
    case "worsening":
      return "Worsening";
    case "success":
      return "Success";
    case "failure":
      return "Failure";
    default:
      return verdict;
  }
}

export function verdictTone(verdict?: PlanObservationVerdict | null) {
  if (!verdict) return "neutral" as const;
  switch (verdict) {
    case "success":
      return "success" as const;
    case "failure":
      return "danger" as const;
    case "worsening":
      return "warning" as const;
    case "improving":
      return "info" as const;
    case "no_change":
    default:
      return "neutral" as const;
  }
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

export function formatObservationWindow(observation?: PlanObservation | null) {
  if (!observation) return "—";
  return `${observation.evaluation_start} → ${observation.evaluation_end}`;
}

export function formatObservationSummary(
  observation?: PlanObservation | null,
  conditions?: PlanCondition[] | null
) {
  if (!observation) return "No observations recorded yet.";
  const usesSignal = conditions?.some((condition) => condition.type === "signal_resolved");
  if (usesSignal) {
    const state = observation.signal_state ?? "unknown";
    return `Signal state ${state} over ${observation.evaluation_start} → ${observation.evaluation_end}.`;
  }
  return `Metric baseline ${formatNumber(observation.metric_baseline)} → ${formatNumber(
    observation.metric_value
  )} (Δ ${formatNumber(observation.metric_delta)}) over ${observation.evaluation_start} → ${
    observation.evaluation_end
  }.`;
}
