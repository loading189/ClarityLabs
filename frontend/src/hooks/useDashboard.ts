import { useEffect, useState } from "react";
import { fetchDashboard } from "../api/demo";
import type { DashboardCard } from "../types";

export function useDashboard() {
  const [cards, setCards] = useState<DashboardCard[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboard()
      .then((data) => setCards(data.cards))
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, []);

  return { cards, err, loading };
}
