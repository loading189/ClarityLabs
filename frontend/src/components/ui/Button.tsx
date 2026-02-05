import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost";

export default function Button({
  children,
  variant = "secondary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={`${styles.button} ${styles[variant]} ${className ?? ""}`}
    >
      {children}
    </button>
  );
}
