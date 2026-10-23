export function EmptyState({ message = 'No data available' }: { message?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '4rem 2rem', gap: '0.75rem' }}>
      <span style={{ fontSize: '2.5rem', opacity: 0.4 }}>📭</span>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>{message}</p>
    </div>
  );
}
