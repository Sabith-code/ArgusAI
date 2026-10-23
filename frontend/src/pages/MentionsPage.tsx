import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import type { Mention, PaginatedResponse } from '../types';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import { EmptyState } from '../components/shared/EmptyState';
import { Badge, riskVariant, sentimentVariant } from '../components/shared/Badge';
import { UncalibratedDisclaimer } from '../components/shared/UncalibratedDisclaimer';
import '../components/mentions/Mentions.css';

const TOPICS = ['', 'routine_marketing_launch', 'general_discussion', 'customer_service_complaint', 'product_quality_issue', 'legal_regulatory_dispute', 'financial_corporate', 'executive_controversy'];
const SENTIMENTS = ['', 'positive', 'neutral', 'negative'];
const RISK_LEVELS = ['', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

export function MentionsPage() {
  const [data, setData] = useState<PaginatedResponse<Mention> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMention, setSelectedMention] = useState<Mention | null>(null);

  const [page, setPage] = useState(1);
  const [topic, setTopic] = useState('');
  const [sentiment, setSentiment] = useState('');
  const [riskLevel, setRiskLevel] = useState('');
  const [searchQ, setSearchQ] = useState('');
  const [sortBy, setSortBy] = useState('risk_score');
  const [order, setOrder] = useState('desc');

  const fetchMentions = useCallback(() => {
    setLoading(true);
    setError(null);
    api.getMentions({
      page, limit: 15, topic: topic || undefined, sentiment: sentiment || undefined,
      risk_level: riskLevel || undefined, q: searchQ || undefined, sort_by: sortBy, order,
    })
      .then(d => setData(d))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [page, topic, sentiment, riskLevel, searchQ, sortBy, order]);

  useEffect(() => { fetchMentions(); }, [fetchMentions]);

  useEffect(() => { setPage(1); }, [topic, sentiment, riskLevel, searchQ]);

  const handleSort = (field: string) => {
    if (sortBy === field) { setOrder(o => o === 'desc' ? 'asc' : 'desc'); }
    else { setSortBy(field); setOrder('desc'); }
  };

  const loadDetail = (m: Mention) => {
    api.getMentionDetail(m.dedup_key).then(setSelectedMention).catch(() => setSelectedMention(m));
  };

  return (
    <div className="mentions-page animate-fade-in">
      <div className="dashboard__header">
        <h1 className="page-title">Mention Explorer</h1>
        <button className="refresh-btn" onClick={fetchMentions}>↻ Refresh</button>
      </div>

      <UncalibratedDisclaimer />

      {/* Filters */}
      <div className="mention-filters">
        <input className="filter-search" type="text" placeholder="Search title or snippet..." value={searchQ} onChange={e => setSearchQ(e.target.value)} />
        <select className="filter-select" value={topic} onChange={e => setTopic(e.target.value)}>
          <option value="">All Topics</option>
          {TOPICS.filter(Boolean).map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
        </select>
        <select className="filter-select" value={sentiment} onChange={e => setSentiment(e.target.value)}>
          <option value="">All Sentiments</option>
          {SENTIMENTS.filter(Boolean).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="filter-select" value={riskLevel} onChange={e => setRiskLevel(e.target.value)}>
          <option value="">All Risk Levels</option>
          {RISK_LEVELS.filter(Boolean).map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>

      {error && <ErrorBanner message={error} onRetry={fetchMentions} />}

      {loading ? <LoadingSpinner /> : !data || data.data.length === 0 ? <EmptyState message="No mentions match your filters" /> : (
        <>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th onClick={() => handleSort('title')} style={{ cursor: 'pointer' }}>Title</th>
                  <th>Domain</th>
                  <th onClick={() => handleSort('risk_score')} style={{ cursor: 'pointer' }}>
                    Risk Score {sortBy === 'risk_score' ? (order === 'desc' ? '▾' : '▴') : ''}
                  </th>
                  <th>Risk Level</th>
                  <th>Sentiment</th>
                  <th>Topic</th>
                  <th onClick={() => handleSort('publication_date')} style={{ cursor: 'pointer' }}>
                    Date {sortBy === 'publication_date' ? (order === 'desc' ? '▾' : '▴') : ''}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.data.map(m => (
                  <tr key={m.dedup_key} className="data-table__row" onClick={() => loadDetail(m)}>
                    <td className="cell-title">{m.title?.slice(0, 50) || '—'}</td>
                    <td className="cell-domain">{m.domain}</td>
                    <td>{m.risk_score.toFixed(1)}</td>
                    <td><Badge label={m.risk_level} variant={riskVariant(m.risk_level)} /></td>
                    <td><Badge label={m.sentiment.selected_label} variant={sentimentVariant(m.sentiment.selected_label)} /></td>
                    <td className="cell-topic">{m.topic.selected_label.replace(/_/g, ' ')}</td>
                    <td className="cell-date">{m.publication_date || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="pagination">
            <button className="pagination-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span className="pagination-info">Page {data.page} of {data.pages} · {data.total} total</span>
            <button className="pagination-btn" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        </>
      )}

      {/* Detail Drawer */}
      {selectedMention && (
        <div className="drawer-overlay" onClick={() => setSelectedMention(null)}>
          <div className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer__header">
              <h2 className="drawer__title">{selectedMention.title}</h2>
              <button className="drawer__close" onClick={() => setSelectedMention(null)}>✕</button>
            </div>
            <div className="drawer__body">
              <div className="drawer-section">
                <span className="drawer-label">URL</span>
                <a href={selectedMention.canonical_url} target="_blank" rel="noreferrer" className="drawer-link">{selectedMention.canonical_url}</a>
              </div>
              <div className="drawer-row">
                <div className="drawer-section">
                  <span className="drawer-label">Domain</span><span>{selectedMention.domain}</span>
                </div>
                <div className="drawer-section">
                  <span className="drawer-label">Source</span><span>{selectedMention.source_type} {selectedMention.is_official ? '(Official)' : ''}</span>
                </div>
              </div>
              <div className="drawer-row">
                <div className="drawer-section">
                  <span className="drawer-label">Raw Model P(Risk)</span>
                  <span className="drawer-value">{selectedMention.reputation_risk.risk_probability.toFixed(4)}</span>
                  <span className="drawer-sublabel">Laya model output — not transformed</span>
                </div>
                <div className="drawer-section">
                  <span className="drawer-label">Composite Risk Score</span>
                  <span className="drawer-value">{selectedMention.risk_score.toFixed(2)} / 100</span>
                  <Badge label="UNCALIBRATED" variant="warning" />
                </div>
              </div>
              <div className="drawer-row">
                <div className="drawer-section">
                  <span className="drawer-label">Sentiment</span>
                  <Badge label={selectedMention.sentiment.selected_label} variant={sentimentVariant(selectedMention.sentiment.selected_label)} />
                  <span className="drawer-sublabel">Confidence: {(selectedMention.sentiment.answer_confidence * 100).toFixed(1)}%</span>
                </div>
                <div className="drawer-section">
                  <span className="drawer-label">Topic</span>
                  <span>{selectedMention.topic.selected_label.replace(/_/g, ' ')}</span>
                  <span className="drawer-sublabel">Confidence: {(selectedMention.topic.answer_confidence * 100).toFixed(1)}%</span>
                </div>
              </div>
              <div className="drawer-section">
                <span className="drawer-label">Urgency</span>
                <span>Expected Score: {selectedMention.urgency.expected_score.toFixed(4)} / 2.0</span>
              </div>
              <div className="drawer-section">
                <span className="drawer-label">Event Cluster</span>
                <span>{selectedMention.event_id || 'Unclustered'}</span>
              </div>
              <div className="drawer-section">
                <span className="drawer-label">Classification</span>
                <span className="drawer-sublabel">{selectedMention.classification_model} v{selectedMention.classification_version} · {selectedMention.classification_scope} · {selectedMention.classification_runtime_ms.toFixed(0)}ms</span>
              </div>
              <div className="drawer-section">
                <span className="drawer-label">Snippet</span>
                <p className="drawer-text">{selectedMention.snippet}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
