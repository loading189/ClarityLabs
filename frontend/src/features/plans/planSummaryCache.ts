import { getPlanSummaries, type PlanSummary } from "../../api/plansV2";

const planSummaryCache = new Map<string, PlanSummary>();

function uniqueIds(planIds: string[]) {
  return Array.from(new Set(planIds.filter(Boolean)));
}

function chunk<T>(items: T[], size: number) {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks;
}

export function readPlanSummary(planId: string | null | undefined) {
  if (!planId) return null;
  return planSummaryCache.get(planId) ?? null;
}

export async function ensurePlanSummaries(planIds: string[]) {
  const unique = uniqueIds(planIds);
  const missing = unique.filter((id) => !planSummaryCache.has(id));
  if (!missing.length) {
    return new Map(planSummaryCache);
  }
  const batches = chunk(missing, 50);
  const responses = await Promise.all(batches.map((batch) => getPlanSummaries(batch)));
  responses.flat().forEach((summary) => {
    planSummaryCache.set(summary.id, summary);
  });
  return new Map(planSummaryCache);
}
