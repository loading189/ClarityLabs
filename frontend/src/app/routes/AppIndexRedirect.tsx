// frontend/src/app/routes/AppIndexRedirect.tsx
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchDashboard, fetchBusinessDashboard } from "../../api/demo";
import { assertBusinessId } from "../../utils/businessId";

export default function AppIndexRedirect() {
  const navigate = useNavigate();

  useEffect(() => {
    const controller = new AbortController();

    const run = async () => {
      try {
        const list = await fetchDashboard(controller.signal);
        const candidate = assertBusinessId(list?.cards?.[0]?.business_id, "AppIndexRedirect list");
        if (!candidate) {
          navigate("/app/select", { replace: true });
          return;
        }

        const detail = await fetchBusinessDashboard(candidate, controller.signal);
        const resolved = assertBusinessId(
          detail?.metadata?.business_id ?? candidate,
          "AppIndexRedirect dashboard metadata"
        );

        if (!resolved) {
          navigate("/app/select", { replace: true });
          return;
        }

        navigate(`/app/${resolved}/assistant`, { replace: true });
      } catch (e: any) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        console.error("[AppIndexRedirect] failed", e);
        navigate("/app/select", { replace: true });
      }
    };

    run();
    return () => controller.abort();
  }, [navigate]);

  return null;
}
