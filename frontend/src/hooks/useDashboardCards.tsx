import { useEffect, useState } from "react";
import { fetchDashboard } from "../api/demo";
import type { DashboardCard } from "../types";

export function useDashboardCards() {
  const [cards, setCards] = useState<DashboardCard[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();

    fetchDashboard(controller.signal)
      .then((data) => setCards(data.cards))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        if (e instanceof Error) {
          setErr(e.message);
          return;
        }
        setErr("Failed to load dashboard cards");
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, []);

  return { cards, err, loading };
}
