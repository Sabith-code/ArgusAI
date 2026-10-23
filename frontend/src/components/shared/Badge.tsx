import './Badge.css';

interface BadgeProps {
  label: string;
  variant?: 'low' | 'medium' | 'high' | 'critical' | 'elevated' | 'normal' | 'positive' | 'neutral' | 'negative' | 'info' | 'warning';
}

const variantMap: Record<string, string> = {
  low: 'badge--low',
  medium: 'badge--medium',
  high: 'badge--high',
  critical: 'badge--critical',
  elevated: 'badge--medium',
  normal: 'badge--low',
  positive: 'badge--positive',
  neutral: 'badge--neutral',
  negative: 'badge--negative',
  info: 'badge--info',
  warning: 'badge--warning',
};

export function Badge({ label, variant = 'info' }: BadgeProps) {
  const cls = variantMap[variant] || 'badge--info';
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function riskVariant(level: string): BadgeProps['variant'] {
  const l = level.toLowerCase();
  if (l === 'critical') return 'critical';
  if (l === 'high') return 'high';
  if (l === 'medium' || l === 'elevated') return 'medium';
  return 'low';
}

export function sentimentVariant(label: string): BadgeProps['variant'] {
  const l = label.toLowerCase();
  if (l === 'positive') return 'positive';
  if (l === 'negative') return 'negative';
  return 'neutral';
}
