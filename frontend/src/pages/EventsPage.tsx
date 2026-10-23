import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import type { EventCluster, PaginatedResponse } from '../types';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import { EmptyState } from '../components/shared/EmptyState';
import { Badge, riskVariant } from '../components/shared/Badge';
import { UncalibratedDisclaimer } from '../components/shared/UncalibratedDisclaimer';
import '../components/events/Events.css';

const THREAT_LEVELS = ['', 'LOW', 'ELEVATED', 'HIGH', 'CRITICAL'];

export function EventsPage() {
  const [data, setData] = useState<PaginatedResponse<EventCluster> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventCluster | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [threatLevel, setThreatLevel] = useState('');
  const [sortBy, setSortBy] = useState('risk_score');
  const [order, setOrder] = useState('desc');

  const fetchEvents = useCallback(() => {
    setLoading(true);
    setError(null);
    api.getEvents({
      page: 1, limit: 50,
      threat_level: threatLevel || undefined,
      sort_by: sortBy, order,
    })
      .then(d => setData(d))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [threatLevel, sortBy, order]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const loadDetail = (evt: EventCluster) => {
    setDetailLoading(true);
    api.getEventDetail(evt.event_id)
      .then(d => setSelectedEvent(d))
      .catch(() => setSelectedEvent(evt))
      .finally(() => setDetailLoading(false));
  };

  return (
    <div className="events-page animate-fade-in">
      <div className="dashboard__header">
        <h1 className="page-title">Event Explorer</h1>
        <button className="refresh-btn" onClick={fetchEvents}>↻ Refresh</button>
      </div>

      <UncalibratedDisclaimer />

      <div className="mention-filters">
        <select className="filter-select" value={threatLevel} onChange={e => setThreatLevel(e.target.value)}>
          <option value="">All Threat Levels</option>
          {THREAT_LEVELS.filter(Boolean).map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select className="filter-select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="risk_score">Sort: Risk Score</option>
          <option value="mention_count">Sort: Mention Count</option>
        </select>
        <select className="filter-select" value={order} onChange={e => setOrder(e.target.value)}>
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </div>

      {error && <ErrorBanner message={error} onRetry={fetchEvents} />}

      {loading ? <LoadingSpinner /> : !data || data.data.length === 0 ? <EmptyState message="No events match your filters" /> : (
        <div className="event-card-grid">
          {data.data.map(evt => (
            <div key={evt.event_id} className="event-card" onClick={() => loadDetail(evt)}>
              <div className="event-card__header">
                <Badge label={evt.threat_level} variant={riskVariant(evt.threat_level)} />
                <span className="event-card__score">{evt.risk_score.toFixed(1)}</span>
              </div>
              <h3 className="event-card__title">{evt.canonical_title}</h3>
              <div className="event-card__meta">
                <span>{evt.mention_count} mentions</span>
                <span>·</span>
                <span>{evt.metadata.dominant_topic.replace(/_/g, ' ')}</span>
              </div>
              <div className="event-card__dates">
                {evt.first_seen_at?.slice(0, 10)} → {evt.last_seen_at?.slice(0, 10)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Event Detail Panel */}
      {selectedEvent && (
        <div className="drawer-overlay" onClick={() => setSelectedEvent(null)}>
          <div className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer__header">
              <h2 className="drawer__title">{selectedEvent.canonical_title}</h2>
              <button className="drawer__close" onClick={() => setSelectedEvent(null)}>✕</button>
            </div>
            <div className="drawer__body">
              {detailLoading ? <LoadingSpinner /> : (
                <>
                  <div className="drawer-row">
                    <div className="drawer-section">
                      <span className="drawer-label">Threat Level</span>
                      <Badge label={selectedEvent.threat_level} variant={riskVariant(selectedEvent.threat_level)} />
                      <Badge label="UNCALIBRATED" variant="warning" />
                    </div>
                    <div className="drawer-section">
                      <span className="drawer-label">Risk Score</span>
                      <span className="drawer-value">{selectedEvent.risk_score.toFixed(2)} / 100</span>
                    </div>
                  </div>
                  <div className="drawer-row">
                    <div className="drawer-section">
                      <span className="drawer-label">Dominant Topic</span>
                      <span>{selectedEvent.metadata.dominant_topic.replace(/_/g, ' ')}</span>
                    </div>
                    <div className="drawer-section">
                      <span className="drawer-label">Avg Model P(Risk)</span>
                      <span>{selectedEvent.metadata.avg_reputation_risk.toFixed(4)}</span>
                    </div>
                  </div>
                  <div className="drawer-section">
                    <span className="drawer-label">Sentiment Distribution</span>
                    <div className="dist-row">
                      {Object.entries(selectedEvent.metadata.sentiment_distribution).map(([k, v]) => (
                        <span key={k} className="dist-chip"><Badge label={k} variant={k === 'positive' ? 'positive' : k === 'negative' ? 'negative' : 'neutral'} /> {v}</span>
                      ))}
                    </div>
                  </div>
                  <div className="drawer-section">
                    <span className="drawer-label">Member Mentions ({selectedEvent.member_mentions?.length || selectedEvent.mention_count})</span>
                    {selectedEvent.member_mentions && selectedEvent.member_mentions.length > 0 ? (
                      <div className="member-mentions-list">
                        {selectedEvent.member_mentions.map(mm => (
                          <div key={mm.dedup_key} className="member-mention-item">
                            <div className="member-mention-title">{mm.title?.slice(0, 60) || mm.dedup_key}</div>
                            <div className="member-mention-meta">
                              <Badge label={mm.risk_level} variant={riskVariant(mm.risk_level)} />
                              <span>{mm.risk_score.toFixed(1)}</span>
                              <span>{mm.source_type}</span>
                              {mm.is_official && <Badge label="Official" variant="info" />}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : <span className="drawer-sublabel">Detail not available</span>}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
