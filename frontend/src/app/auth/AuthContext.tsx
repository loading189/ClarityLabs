import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError } from "../../api/client";
import { fetchMe, type CurrentUser, type MembershipSummary } from "../../api/users";
import { getDevUserEmail, setDevUserEmail } from "../../utils/devAuth";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  status: AuthStatus;
  user: CurrentUser | null;
  memberships: MembershipSummary[];
  error: string | null;
  login: (email: string) => void;
  logout: () => void;
  reload: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [memberships, setMemberships] = useState<MembershipSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(() => getDevUserEmail());

  const load = useCallback(async () => {
    const currentEmail = getDevUserEmail();
    if (!currentEmail) {
      setUser(null);
      setMemberships([]);
      setStatus("unauthenticated");
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const me = await fetchMe();
      setUser(me);
      setMemberships(me.memberships ?? []);
      setStatus("authenticated");
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        setDevUserEmail(null);
        setEmail(null);
        setUser(null);
        setMemberships([]);
        setStatus("unauthenticated");
        return;
      }
      setError(err?.message ?? "Failed to load user");
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, email]);

  const login = useCallback((nextEmail: string) => {
    const trimmed = nextEmail.trim().toLowerCase();
    if (!trimmed) return;
    setDevUserEmail(trimmed);
    setEmail(trimmed);
  }, []);

  const logout = useCallback(() => {
    setDevUserEmail(null);
    setEmail(null);
    setUser(null);
    setMemberships([]);
    setStatus("unauthenticated");
  }, []);

  const value = useMemo(
    () => ({
      status,
      user,
      memberships,
      error,
      login,
      logout,
      reload: load,
    }),
    [error, load, login, logout, memberships, status, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
