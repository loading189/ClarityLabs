import { useState, type ReactNode } from "react";
import { useAuth } from "./AuthContext";
import styles from "./DevAuthGate.module.css";

export default function DevAuthGate({ children }: { children: ReactNode }) {
  const { status, error, login, logout, user } = useAuth();
  const [email, setEmail] = useState("");

  if (status === "loading") {
    return (
      <div className={styles.shell}>
        <div className={styles.card}>
          <h2 className={styles.title}>Loading workspace…</h2>
          <p className={styles.subtitle}>Checking dev login headers.</p>
        </div>
      </div>
    );
  }

  if (status === "authenticated") {
    return (
      <>
        {children}
        <div style={{ position: "fixed", bottom: 16, right: 16, opacity: 0.6 }}>
          <button type="button" className={styles.linkButton} onClick={logout}>
            Sign out {user?.email}
          </button>
        </div>
      </>
    );
  }

  return (
    <div className={styles.shell}>
      <div className={styles.card}>
        <h2 className={styles.title}>Dev Login</h2>
        <p className={styles.subtitle}>Enter an email to send in X-User-Email headers.</p>
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            login(email);
          }}
        >
          <input
            className={styles.input}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@firm.com"
            type="email"
            required
          />
          {error && <div className={styles.error}>{error}</div>}
          <div className={styles.buttonRow}>
            <button className={styles.primaryButton} type="submit">
              Continue
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
