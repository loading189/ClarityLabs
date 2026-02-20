// frontend/src/app/layout/AppLayout.tsx
import { useEffect, useMemo } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";
import styles from "./AppLayout.module.css";
import { assertBusinessId } from "../../utils/businessId";
import { useAppState } from "../state/appState";
import ErrorBoundary from "../../components/common/ErrorBoundary";
import { useFilters } from "../filters/useFilters";
import { buildSearchParams, resolveDateRange } from "../filters/filters";
import BusinessSwitcher from "../../components/business/BusinessSwitcher";
import { useAuth } from "../auth/AuthContext";

type NavItem = { label: string; path: string };
type NavSectionItem = { title: string; items: NavItem[] };

const navSections: NavSectionItem[] = [
  { title: "Work", items: [{ label: "Inbox", path: "advisor" }, { label: "Case Center", path: "cases" }] },
  { title: "Observe", items: [{ label: "Signals", path: "signals" }] },
  { title: "Verify", items: [{ label: "Ledger", path: "ledger" }] },
  { title: "Organize", items: [{ label: "Categorize", path: "categorize" }, { label: "Rules", path: "rules" }] },
  { title: "Explain", items: [{ label: "Summary", path: "summary" }] },
];


function NavSection({
  title,
  items,
  businessId,
  search,
}: {
  title?: string;
  items: NavItem[];
  businessId: string;
  search: string;
}) {
  return (
    <div className={styles.navSection}>
      {title && <div className={styles.navSectionTitle}>{title}</div>}
      <div className={styles.navItems}>
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={`/app/${businessId}/${item.path}${search}`}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.navItemActive : ""}`
            }
          >
            <span className={styles.navLabel}>{item.label}</span>
          </NavLink>
        ))}
      </div>
    </div>
  );
}

export default function AppLayout() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "AppLayout");
  const { setActiveBusinessId, setDateRange } = useAppState();
  const { user, logout } = useAuth();
  const [filters] = useFilters();
  const resolvedRange = useMemo(() => resolveDateRange(filters), [filters]);
  const navSearch = useMemo(() => {
    const params = buildSearchParams({
      start: resolvedRange.start,
      end: resolvedRange.end,
      window: resolvedRange.window,
    });
    const query = params.toString();
    return query ? `?${query}` : "";
  }, [resolvedRange.end, resolvedRange.start, resolvedRange.window]);

  useEffect(() => {
    setActiveBusinessId(businessId || null);
  }, [businessId, setActiveBusinessId]);

  useEffect(() => {
    setDateRange({ start: resolvedRange.start, end: resolvedRange.end });
  }, [resolvedRange.end, resolvedRange.start, setDateRange]);

  if (!businessId) {
    return (
      <div className={styles.shell}>
        <div className={styles.emptyState}>
          <h2 className={styles.emptyTitle}>No business selected</h2>
          <p className={styles.emptyText}>
            Your URL is missing a valid business id. Go pick a business workspace.
          </p>
          <a href="/businesses" className={styles.switchLink}>Go to Business Picker</a>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <img src="/logo.svg" alt="Clarity Labs" className={styles.logo} />
          <div>
            <div className={styles.brandName}>Clarity Labs</div>
            <div className={styles.brandMeta}>Workspace</div>
          </div>
        </div>
        {navSections.map((section) => (
          <NavSection
            key={section.title}
            title={section.title}
            items={section.items}
            businessId={businessId}
            search={navSearch}
          />
        ))}
      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <div>
            <div className={styles.topbarTitle}>Financial intelligence workspace</div>
            <div className={styles.topbarSubtitle}>Observe → Investigate → Correct → Operate</div>
          </div>
          <div className={styles.topbarActions}>
            <BusinessSwitcher />
            <a className={styles.manageLink} href="/businesses">Manage businesses</a>
            <button type="button" className={styles.userChip} onClick={logout}>
              {user?.name ?? user?.email ?? "Signed in"}
            </button>
          </div>
        </header>
        <main className={styles.content}>
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
