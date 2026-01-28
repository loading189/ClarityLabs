const REFRESH_LOG_ENABLED = import.meta.env.VITE_REFRESH_LOG === "true";

export function logRefresh(tab: string, event: string) {
  if (!REFRESH_LOG_ENABLED) return;
  const timestamp = new Date().toISOString();
  // eslint-disable-next-line no-console
  console.info(`[refresh] ${tab} · ${event} · ${timestamp}`);
}
