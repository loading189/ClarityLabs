const DEV_EMAIL_KEY = "claritylabs.devUserEmail";

export function getDevUserEmail(): string | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(DEV_EMAIL_KEY);
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

export function setDevUserEmail(email: string | null) {
  if (typeof window === "undefined") return;
  if (!email) {
    window.localStorage.removeItem(DEV_EMAIL_KEY);
    return;
  }
  window.localStorage.setItem(DEV_EMAIL_KEY, email.trim());
}
