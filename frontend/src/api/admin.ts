// frontend/src/api/admin.ts

const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export async function deleteBusiness(businessId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/business/${businessId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Failed to delete business (${res.status})`);
  }
}
