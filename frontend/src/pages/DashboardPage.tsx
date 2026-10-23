import { useState, useEffect } from 'react';
import { api } from '../api';
import type { SummaryResponse, ScorecardResponse, AnomalySignal } from '../types';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import { Badge, riskVariant } from '../components/shared/Badge';
import { UncalibratedDisclaimer } from '../components/shared/UncalibratedDisclaimer';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import '../components/dashboard/Dashboard.css';

const RISK_COLORS: Record<string, string> = {
  LOW: '#22c55e', MEDIUM: '#f59e0b', HIGH: '#f97316', CRITICAL: '#ef4444',
};

const TOPIC_LABELS: Record<string, string> = {
  routine_marketing_launch: 'Marketing',
  general_discussion: 'General',
  customer_service_complaint: 'Service',
  product_quality_issue: 'Quality',
  legal_regulatory_dispute: 'Legal',
  financial_corporate: 'Financial',
  executive_controversy: 'Executive',
};

export function DashboardPage() {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [scorecard, setScorecard] = useState<ScorecardResponse | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalySignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = () => {
    setLoading(true);
    setError(null);
    Promise.all([api.getSummary(), api.getScorecard(), api.getAnomalies()])
      .then(([sum, sc, an]) => { setSummary(sum); setScorecard(sc); setAnomalies(an); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, []);

  if (loading) return <LoadingSpinner message="Loading dashboard..." />;
  if (error) return <ErrorBanner message={error} onRetry={fetchData} />;
  if (!summary || !scorecard) return null;

  const riskData = Object.entries(summary.risk_level_breakdown).map(([name, value]) => ({ name, value }));

  // Build topic distribution from mentions API
  const topicDistData = anomalies.length > 0
    ? Object.entries(
        anomalies.reduce<Record<string, number>>((acc, a) => {
          if (a.anomaly_type === 'VOLUME_SPIKE') {
            acc[a.target_key] = a.metric_value;
          }
          return acc;
        }, {})
      ).map(([key, val]) => ({ name: TOPIC_LABELS[key] || key, count: val }))
    : [];

  const threatColor = (tl: string) => {
    if (tl === 'CRITICAL') return 'var(--color-critical)';
    if (tl === 'HIGH') return 'var(--color-high)';
    if (tl === 'ELEVATED') return 'var(--color-medium)';
    return 'var(--color-low)';
  };

  return (
    <div className="dashboard animate-fade-in">
      <div className="dashboard__header">
        <h1 className="page-title">Dashboard Overview</h1>
        <button className="refresh-btn" onClick={fetchData}>↻ Refresh</button>
      </div>

      <UncalibratedDisclaimer />

      {/* Hero Metrics Row */}
      <div className="hero-metrics">
        <div className="metric-card">
          <span className="metric-card__label">Total Mentions</span>
          <span className="metric-card__value">{summary.total_mentions}</span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Event Clusters</span>
          <span className="metric-card__value">{summary.total_events}</span>
        </div>
        <div className="metric-card">
          <span className="metric-card__label">Active Signals</span>
          <span className="metric-card__value" style={{ color: 'var(--color-medium)' }}>{summary.active_anomalies_count}</span>
        </div>
        <div className="metric-card metric-card--accent">
          <span className="metric-card__label">Brand Indicator</span>
          <span className="metric-card__value" style={{ color: threatColor(summary.global_threat_level) }}>
            {summary.global_brand_indicator}
            <span className="metric-card__unit"> / 100</span>
          </span>
          <Badge label={summary.global_threat_level} variant={riskVariant(summary.global_threat_level)} />
        </div>
      </div>

      {/* Charts Row */}
      <div className="charts-row">
        {/* Risk Donut */}
        <div className="chart-card">
          <h3 className="chart-card__title">Risk Level Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={riskData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                {riskData.map(entry => (
                  <Cell key={entry.name} fill={RISK_COLORS[entry.name] || '#64748b'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Top Threat Events */}
        <div className="chart-card">
          <h3 className="chart-card__title">Top Threat Events</h3>
          <div className="threat-events-list">
            {scorecard.top_threat_events.map((evt, i) => (
              <div key={evt.event_id} className="threat-event-item">
                <span className="threat-rank">#{i + 1}</span>
                <div className="threat-info">
                  <span className="threat-title">{evt.canonical_title}</span>
                  <div className="threat-meta">
                    <Badge label={evt.threat_level} variant={riskVariant(evt.threat_level)} />
                    <span className="threat-score">Score: {evt.risk_score.toFixed(1)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Anomalies & Topic Distribution */}
      <div className="charts-row">
        {topicDistData.length > 0 && (
          <div className="chart-card">
            <h3 className="chart-card__title">Volume Spike Topics</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={topicDistData} layout="vertical" margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                <XAxis type="number" stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={70} stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} />
                <Bar dataKey="count" fill="var(--accent-primary)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="chart-card">
          <h3 className="chart-card__title">Recent Engineering Signals</h3>
          <div className="anomaly-preview-list">
            {anomalies.slice(0, 3).map(a => (
              <div key={a.anomaly_id} className="anomaly-preview-item">
                <div className="anomaly-preview-header">
                  <Badge label={a.anomaly_type.replace(/_/g, ' ')} variant="info" />
                  <Badge label={a.severity} variant={riskVariant(a.severity)} />
                </div>
                <p className="anomaly-preview-desc">{a.description}</p>
                <span className="anomaly-preview-meta">z={a.z_score.toFixed(2)} · {a.affected_mention_keys.length} mentions</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
