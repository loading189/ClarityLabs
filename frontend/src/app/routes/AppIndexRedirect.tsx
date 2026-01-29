import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useDashboardCards } from "../../hooks/useDashboardCards";
import { DEFAULT_BUSINESS_ID } from "./defaults";

export default function AppIndexRedirect() {
  const navigate = useNavigate();
  const { cards, loading } = useDashboardCards();

  useEffect(() => {
    if (loading) return;
    const businessId = cards[0]?.business_id ?? DEFAULT_BUSINESS_ID;
    navigate(`/app/${businessId}/home`, { replace: true });
  }, [cards, loading, navigate]);

  return null;
}
