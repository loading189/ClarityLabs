const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isBusinessIdValid(businessId: string | null | undefined): boolean {
  if (!businessId) return false;
  return UUID_REGEX.test(businessId);
}

export function assertBusinessId(
  businessId: string | null | undefined,
  context: string
): string {
  if (!businessId) {
    console.error(`[businessId] Missing businessId in ${context}.`);
    return "";
  }
  if (!isBusinessIdValid(businessId)) {
    console.error(
      `[businessId] Invalid businessId "${businessId}" in ${context}. Expected UUID.`
    );
    return "";
  }
  return businessId;
}
