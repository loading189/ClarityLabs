import { NavLink, Outlet, useParams } from "react-router-dom";
import styles from "./AppLayout.module.css";

type NavItem = {
  label: string;
  path: string;
};

const primaryNav: NavItem[] = [
  { label: "Home", path: "home" },
  { label: "Health", path: "health" },
  { label: "Dashboard", path: "dashboard" },
  { label: "Ledger", path: "ledger" },
  { label: "Trends", path: "trends" },
  { label: "Vendors", path: "vendors" },
  { label: "Categorize", path: "categorize" },
  { label: "Rules", path: "rules" },
  { label: "Integrations", path: "integrations" },
  { label: "Settings", path: "settings" },
];

const adminNav: NavItem[] = [{ label: "Simulator", path: "admin/simulator" }];

function NavSection({ title, items }: { title?: string; items: NavItem[] }) {
  const { businessId = "" } = useParams();
  return (
    <div className={styles.navSection}>
      {title && <div className={styles.navSectionTitle}>{title}</div>}
      <div className={styles.navItems}>
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={`/app/${businessId}/${item.path}`}
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
  const { businessId = "" } = useParams();

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <img src="/logo.svg" alt="Clarity Labs" className={styles.logo} />
          <div>
            <div className={styles.brandName}>Clarity Labs</div>
            <div className={styles.brandMeta}>Business {businessId}</div>
          </div>
        </div>

        <NavSection items={primaryNav} />
        <NavSection title="Admin" items={adminNav} />
      </aside>

      <div className={styles.main}>
        <header className={styles.topbar}>
          <div>
            <div className={styles.topbarTitle}>Financial intelligence workspace</div>
            <div className={styles.topbarSubtitle}>
              Observe → Investigate → Correct → Operate
            </div>
          </div>
        </header>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
