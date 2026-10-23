export function UncalibratedDisclaimer() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '0.5rem',
      padding: '0.5rem 0.875rem',
      background: 'rgba(245,158,11,0.08)',
      border: '1px solid rgba(245,158,11,0.2)',
      borderRadius: 'var(--radius-sm)',
      fontSize: '0.75rem',
      color: 'var(--color-medium)',
    }}>
      <span>⚙</span>
      <span>Scores are <strong>uncalibrated engineering heuristics</strong> — not validated brand health measurements.</span>
    </div>
  );
}
