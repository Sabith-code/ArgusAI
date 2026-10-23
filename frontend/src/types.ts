// ============================================================
// Brand Reputation Monitoring System — TypeScript Interfaces
// All types mirror the actual Phase 9 FastAPI response schemas.
// ============================================================

export interface HealthResponse {
  status: string;
  database: string;
  mongodb_version: string;
  timestamp: string;
}

export interface SummaryResponse {
  total_mentions: number;
  total_events: number;
  active_anomalies_count: number;
  global_brand_indicator: number;
  global_threat_level: string;
  risk_level_breakdown: Record<string, number>;
}

export interface TopThreatEvent {
  event_id: string;
  canonical_title: string;
  risk_score: number;
  threat_level: string;
}

export interface ScorecardResponse {
  scorecard_id: string;
  global_brand_indicator: number;
  global_threat_level: string;
  parameter_status: string;
  total_mentions_analyzed: number;
  total_events_analyzed: number;
  risk_level_breakdown: Record<string, number>;
  active_anomalies_count: number;
  top_threat_events: TopThreatEvent[];
  generated_at: string;
}

export interface SentimentData {
  selected_label: string;
  confidence: number;
  answer_confidence: number;
  probabilities: Record<string, number>;
}

export interface TopicData {
  selected_label: string;
  confidence: number;
  answer_confidence: number;
  probabilities: Record<string, number>;
}

export interface UrgencyData {
  expected_score: number;
  confidence: number;
  answer_confidence: number;
  probabilities: Record<string, number>;
}

export interface ReputationRiskData {
  risk_probability: number;
  confidence: number;
  answer_confidence: number;
}

export interface Mention {
  _id: string;
  dedup_key: string;
  canonical_url: string;
  original_url: string;
  domain: string;
  title: string;
  snippet: string;
  text: string;
  source_type: string;
  is_official: boolean;
  publication_date: string | null;
  discovered_at: string;
  extraction_status: string;
  extraction_method: string;
  sentiment: SentimentData;
  topic: TopicData;
  urgency: UrgencyData;
  reputation_risk: ReputationRiskData;
  risk_score: number;
  risk_level: string;
  event_id: string | null;
  classification_model: string;
  classification_version: string;
  classification_scope: string;
  classification_runtime_ms: number;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  limit: number;
  pages: number;
  data: T[];
}

export interface EventMetadata {
  dominant_topic: string;
  avg_reputation_risk: number;
  topic_distribution: Record<string, number>;
  sentiment_distribution: Record<string, number>;
  source_type_counts: Record<string, number>;
}

export interface MemberMentionSummary {
  _id: string;
  dedup_key: string;
  title: string;
  canonical_url: string;
  publication_date: string | null;
  risk_score: number;
  risk_level: string;
  source_type: string;
  is_official: boolean;
}

export interface EventCluster {
  _id: string;
  event_id: string;
  canonical_title: string;
  mention_count: number;
  mention_ids: string[];
  first_seen_at: string;
  last_seen_at: string;
  metadata: EventMetadata;
  risk_score: number;
  threat_level: string;
  member_mentions?: MemberMentionSummary[];
}

export interface HistoricalAggregate {
  aggregate_id: string;
  date_basis: string;
  bucket_type: string;
  bucket_key: string;
  start_date: string;
  end_date: string;
  total_mentions: number;
  avg_reputation_risk: number;
  max_reputation_risk: number;
  sentiment_distribution: Record<string, number>;
  topic_distribution: Record<string, number>;
  official_vs_third_party: Record<string, number>;
  data_sufficiency_warning: string;
}

export interface AnomalySignal {
  anomaly_id: string;
  anomaly_type: string;
  severity: string;
  signal_status: string;
  description: string;
  metric_name: string;
  metric_value: number;
  baseline_mean: number;
  z_score: number;
  triggered_threshold: number;
  date_basis: string;
  target_type: string;
  target_key: string;
  affected_mention_keys: string[];
  affected_event_ids: string[];
  data_sufficiency_warning: string;
  detected_at: string;
}

export interface MentionQueryParams {
  page?: number;
  limit?: number;
  topic?: string;
  sentiment?: string;
  risk_level?: string;
  is_official?: boolean;
  source_type?: string;
  q?: string;
  sort_by?: string;
  order?: string;
}

export interface EventQueryParams {
  page?: number;
  limit?: number;
  topic?: string;
  threat_level?: string;
  sort_by?: string;
  order?: string;
}
