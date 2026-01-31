import { Component, type ErrorInfo, type ReactNode } from "react";
import styles from "./ErrorBoundary.module.css";

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  message: string;
};

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error.message ?? "Unexpected error" };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] render error", error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className={styles.wrapper}>
          <h1>Something went wrong</h1>
          <p>
            We hit an unexpected error while rendering this page. Reload to try again.
          </p>
          {this.state.message && (
            <pre className={styles.message}>{this.state.message}</pre>
          )}
          <button type="button" onClick={this.handleReload} className={styles.button}>
            Reload
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
