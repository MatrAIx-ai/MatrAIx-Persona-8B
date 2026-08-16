/**
 * ErrorBoundary: a top-level React error boundary so an uncaught render error
 * shows a recoverable fallback instead of a white screen.
 *
 * Wraps `<App/>` in `main.tsx`. A render-time exception is caught, the message
 * is surfaced, and the operator can "Try again" (re-mount the subtree) or
 * "Reload" (hard refresh). Data-fetch errors are handled in-pane by React Query;
 * this is the last-resort net for component crashes.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { I18nProvider, useI18n } from "@/i18n/I18nProvider";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

function ErrorFallback({
  error,
  onReset,
  onReload,
}: {
  error: Error;
  onReset: () => void;
  onReload: () => void;
}) {
  const { t } = useI18n();

  return (
    <div className="grid min-h-screen place-items-center bg-surface-dim p-6 text-text-main">
      <div className="panel rise-in w-full max-w-md rounded-md border border-outline bg-surface p-6 shadow-2xl">
        <div className="flex items-center gap-2.5">
          <Sym
            name="error"
            fill={1}
            size={22}
            className="flex-none text-danger"
          />
          <h1 className="font-display text-lg font-bold tracking-tight text-text-main">
            {t("errorBoundary.title")}
          </h1>
        </div>
        <p className="mt-2 text-[15px] leading-relaxed text-text-variant">
          {t("errorBoundary.description")}
        </p>
        {error.message && (
          <pre className="mt-3 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-md border border-outline bg-field px-3 py-2 font-mono text-[13px] leading-relaxed text-text-variant">
            {error.message}
          </pre>
        )}
        <div className="mt-4 flex items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            className={`inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-xs font-medium text-on-primary transition hover:bg-primary-dim active:scale-[0.98] ${FOCUS_RING}`}
          >
            <Sym name="refresh" size={16} />
            {t("errorBoundary.tryAgain")}
          </button>
          <button
            type="button"
            onClick={onReload}
            className={`inline-flex items-center gap-1.5 rounded-md border border-outline px-4 py-2 text-xs font-medium text-text-variant transition hover:bg-surface-low hover:text-text-main active:scale-[0.98] ${FOCUS_RING}`}
          >
            {t("errorBoundary.reload")}
          </button>
        </div>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface the crash for local debugging; in a research tool the console is
    // the operator's primary log.
    // eslint-disable-next-line no-console
    console.error("Playground crashed:", error, info.componentStack);
  }

  private handleReset = (): void => {
    this.setState({ error: null });
  };

  private handleReload = (): void => {
    if (typeof window !== "undefined") window.location.reload();
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    // This boundary is deliberately above the app's primary I18nProvider. A
    // fallback provider keeps the recovery screen localized even if that
    // primary provider is part of the failed subtree.
    return (
      <I18nProvider>
        <ErrorFallback
          error={error}
          onReset={this.handleReset}
          onReload={this.handleReload}
        />
      </I18nProvider>
    );
  }
}

export default ErrorBoundary;
