import { useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useBusinessesMine } from "../../hooks/useBusinessesMine";
import styles from "./BusinessSwitcher.module.css";

export default function BusinessSwitcher() {
  const { businessId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { businesses, loading, error } = useBusinessesMine();

  const current = useMemo(
    () => businesses.find((biz) => biz.business_id === businessId) ?? null,
    [businessId, businesses]
  );

  const handleChange = (nextId: string) => {
    if (!businessId) return;
    const prefix = `/app/${businessId}`;
    const nextPath = location.pathname.startsWith(prefix)
      ? location.pathname.replace(prefix, `/app/${nextId}`)
      : `/app/${nextId}/assistant`;
    navigate(`${nextPath}${location.search}`);
  };

  return (
    <div className={styles.switcher}>
      <div className={styles.label}>Business</div>
      <select
        className={styles.select}
        value={businessId ?? ""}
        onChange={(event) => handleChange(event.target.value)}
        disabled={loading || businesses.length === 0}
      >
        {businesses.map((biz) => (
          <option key={biz.business_id} value={biz.business_id}>
            {biz.business_name} · {biz.role}
          </option>
        ))}
      </select>
      {error && <div className={styles.error}>{error}</div>}
      {!error && current && <div className={styles.meta}>Role: {current.role}</div>}
    </div>
  );
}
