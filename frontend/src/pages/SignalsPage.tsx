import { useState, useEffect } from 'react';
import { api } from '../api';
import type { AnomalySignal, HistoricalAggregate } from '../types';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import { Badge, riskVariant } from '../components/shared/Badge';
import { UncalibratedDisclaimer } from '../components/shared/UncalibratedDisclaimer';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar, Legend } from 'recharts';
import '../components/signals/Signals.css';

export function SignalsPage() {
  const [anomalies, setAnomalies] = useState<AnomalySignal[]>([]);
  const [aggregates, setAggregates] = useState<HistoricalAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateBasis, setDateBasis] = useState<'publication_date' | 'discovered_at'>('publication_date');

  const fetchData = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.getAnomalies(),
      api.getAggregates({ date_basis: dateBasis, bucket_type: 'yearly' }),
    ])
      .then(([an, ag]) => { setAnomalies(an); setAggregates(ag); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [dateBasis]);

  if (loading) return <LoadingSpinner message="Loading signals..." />;
  if (error) return <ErrorBanner message={error} onRetry={fetchData} />;

  const chartData = aggregates.map(a => ({
    bucket: a.bucket_key,
    mentions: a.total_mentions,
    avg_risk: +(a.avg_reputation_risk * 100).toFixed(2),
    positive: a.sentiment_distribution.positive || 0,
    neutral: a.sentiment_distribution.neutral || 0,
    negative: a.sentiment_distribution.negative || 0,
  }));

  return (
    <div className="signals-page animate-fade-in">
      <div className="dashboard__header">
        <h1 className="page-title">Signals & History</h1>
        <button className="refresh-btn" onClick={fetchData}>↻ Refresh</button>
      </div>

      <UncalibratedDisclaimer />

      {/* Anomaly Cards */}
      <h2 className="section-title">Engineering Signals ({anomalies.length})</h2>
      <div className="anomaly-card-grid">
        {anomalies.map(a => (
          <div key={a.anomaly_id} className="anomaly-card">
            <div className="anomaly-card__header">
              <Badge label={a.anomaly_type.replace(/_/g, ' ')} variant="info" />
              <Badge label={a.severity} variant={riskVariant(a.severity)} />
            </div>
            <p className="anomaly-card__description">{a.description}</p>
            <div className="anomaly-card__stats">
              <div className="anomaly-stat">
                <span className="anomaly-stat__label">z-score</span>
                <span className="anomaly-stat__value">{a.z_score.toFixed(2)}</span>
              </div>
              <div className="anomaly-stat">
                <span className="anomaly-stat__label">Metric</span>
                <span className="anomaly-stat__value">{a.metric_value}</span>
              </div>
              <div className="anomaly-stat">
                <span className="anomaly-stat__label">Baseline</span>
                <span className="anomaly-stat__value">{a.baseline_mean.toFixed(1)}</span>
              </div>
              <div className="anomaly-stat">
                <span className="anomaly-stat__label">Threshold</span>
                <span className="anomaly-stat__value">{a.triggered_threshold}</span>
              </div>
            </div>
            <div className="anomaly-card__footer">
              <span>{a.affected_mention_keys.length} mentions · {a.affected_event_ids.length} events</span>
              <Badge label={a.signal_status.replace(/_/g, ' ')} variant="warning" />
            </div>
            {a.data_sufficiency_warning && (
              <p className="anomaly-card__warning">⚠ {a.data_sufficiency_warning}</p>
            )}
          </div>
        ))}
      </div>

      {/* Historical Charts */}
      <div className="history-header">
        <h2 className="section-title">Historical Aggregates</h2>
        <div className="date-basis-toggle">
          <button className={`toggle-btn ${dateBasis === 'publication_date' ? 'toggle-btn--active' : ''}`} onClick={() => setDateBasis('publication_date')}>Publication Date</button>
          <button className={`toggle-btn ${dateBasis === 'discovered_at' ? 'toggle-btn--active' : ''}`} onClick={() => setDateBasis('discovered_at')}>Discovered At</button>
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="charts-row">
          <div className="chart-card">
            <h3 className="chart-card__title">Mention Volume Over Time</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="bucket" stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} />
                <Bar dataKey="mentions" fill="var(--accent-primary)" radius={[4, 4, 0, 0]} name="Mentions" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card">
            <h3 className="chart-card__title">Avg Risk Probability (%) Over Time</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="bucket" stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} />
                <Line type="monotone" dataKey="avg_risk" stroke="var(--color-high)" strokeWidth={2} dot={{ fill: 'var(--color-high)', r: 3 }} name="Avg Risk %" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {chartData.length > 0 && (
        <div className="chart-card" style={{ maxWidth: 700 }}>
          <h3 className="chart-card__title">Sentiment Distribution Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="bucket" stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
              <YAxis stroke="var(--text-muted)" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: 'var(--bg-surface)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-secondary)' }} />
              <Bar dataKey="positive" stackId="s" fill="var(--color-positive)" name="Positive" />
              <Bar dataKey="neutral" stackId="s" fill="var(--color-neutral)" name="Neutral" />
              <Bar dataKey="negative" stackId="s" fill="var(--color-negative)" name="Negative" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
