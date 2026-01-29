import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchBusinessDashboard, fetchDashboard } from "../../api/demo";
import { assertBusinessId } from "../../utils/businessId";

export default function AppIndexRedirect() {
  const navigate = useNavigate();

  useEffect(() => {
    const controller = new AbortController();

    const redirect = async () => {
      try {
        const list = await fetchDashboard(controller.signal);
        const candidateId = assertBusinessId(list.cards[0]?.business_id, "AppIndexRedirect");
        if (!candidateId) return;
        const detail = await fetchBusinessDashboard(candidateId, controller.signal);
        const resolvedId = assertBusinessId(
          detail.metadata?.business_id,
          "AppIndexRedirect dashboard metadata"
        );
        if (!resolvedId) return;
        navigate(`/app/${resolvedId}/dashboard`, { replace: true });
      } catch (e: unknown) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        console.error("[AppIndexRedirect] Failed to resolve business.", e);
      }
    };

    redirect();

    return () => controller.abort();
  }, [navigate]);

  return null;
}
