import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type DateRange = {
  start: string;
  end: string;
};

type AppState = {
  activeBusinessId: string | null;
  dateRange: DateRange;
  dataVersion: number;
  setActiveBusinessId: (id: string | null) => void;
  setDateRange: (range: DateRange) => void;
  bumpDataVersion: () => void;
};

const AppStateContext = createContext<AppState | undefined>(undefined);

function todayISO() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function daysAgoISO(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

const defaultRange = (): DateRange => ({
  start: daysAgoISO(30),
  end: todayISO(),
});

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [activeBusinessId, setActiveBusinessId] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<DateRange>(() => defaultRange());
  const [dataVersion, setDataVersion] = useState(0);

  const bumpDataVersion = useCallback(() => {
    setDataVersion((prev) => prev + 1);
  }, []);

  const value = useMemo(
    () => ({
      activeBusinessId,
      dateRange,
      dataVersion,
      setActiveBusinessId,
      setDateRange,
      bumpDataVersion,
    }),
    [activeBusinessId, dateRange, dataVersion, bumpDataVersion]
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const context = useContext(AppStateContext);
  if (!context) {
    throw new Error("useAppState must be used within AppStateProvider");
  }
  return context;
}

export type { DateRange };
