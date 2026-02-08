// frontend/src/app/routes/AppIndexRedirect.tsx
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchBusinessesMine } from "../../api/businesses";
import { assertBusinessId } from "../../utils/businessId";

export default function AppIndexRedirect() {
  const navigate = useNavigate();

  useEffect(() => {
    const run = async () => {
      try {
        const list = await fetchBusinessesMine();
        const candidate = assertBusinessId(list?.[0]?.business_id, "AppIndexRedirect list");
        if (!candidate) {
          navigate("/businesses", { replace: true });
          return;
        }

        navigate(`/app/${candidate}/assistant`, { replace: true });
      } catch (e: any) {
        console.error("[AppIndexRedirect] failed", e);
        navigate("/businesses", { replace: true });
      }
    };

    run();
  }, [navigate]);

  return null;
}
