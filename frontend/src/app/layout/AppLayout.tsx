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

type NavItem = { label: string; path: string };

const primaryNav: NavItem[] = [
  { label: "Assistant", path: "assistant" },
  { label: "Advisor Inbox", path: "advisor" },
  { label: "Signals", path: "signals" },
  { label: "Ledger", path: "ledger" },
];

const toolsNav: NavItem[] = [
  { label: "Categorize", path: "categorize" },
  { label: "Rules", path: "rules" },
  { label: "Vendors", path: "vendors" },
  { label: "Integrations", path: "integrations" },
  { label: "Trends", path: "trends" },
  { label: "Settings", path: "settings" },
  { label: "Simulator", path: "admin/simulator" },
  { label: "Dashboard", path: "dashboard" },
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
          <a href="/app/select" className={styles.switchLink}>Go to Business Picker</a>
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
        <BusinessSwitcher />

        <NavSection title="Workspace" items={primaryNav} businessId={businessId} search={navSearch} />
        <details className={styles.toolsDropdown} open>
          <summary className={styles.toolsSummary}>Tools</summary>
          <div className={styles.navItems}>
            {toolsNav.map((item) => (
              <NavLink
                key={item.path}
                to={`/app/${businessId}/${item.path}${navSearch}`}
                className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
              >
                <span className={styles.navLabel}>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </details>
      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <div>
            <div className={styles.topbarTitle}>Financial intelligence workspace</div>
            <div className={styles.topbarSubtitle}>Observe → Investigate → Correct → Operate</div>
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
