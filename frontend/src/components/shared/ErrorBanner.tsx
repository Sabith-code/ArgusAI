import './ErrorBanner.css';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="error-banner">
      <span className="error-icon">⚠</span>
      <span className="error-text">{message}</span>
      {onRetry && (
        <button className="error-retry-btn" onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}
