import './LoadingSpinner.css';

export function LoadingSpinner({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="loading-spinner-container">
      <div className="loading-spinner" />
      <p className="loading-message">{message}</p>
    </div>
  );
}
