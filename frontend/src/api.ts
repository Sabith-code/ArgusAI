import type {
  HealthResponse,
  SummaryResponse,
  ScorecardResponse,
  Mention,
  PaginatedResponse,
  EventCluster,
  HistoricalAggregate,
  AnomalySignal,
  MentionQueryParams,
  EventQueryParams,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJSON<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") {
        url.searchParams.set(k, String(v));
      }
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const detail = await res.text();
    throw new ApiError(res.status, `HTTP ${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  getHealth: () => fetchJSON<HealthResponse>("/health"),
  getSummary: () => fetchJSON<SummaryResponse>("/summary"),
  getScorecard: () => fetchJSON<ScorecardResponse>("/scorecard"),
  getMentions: (params?: MentionQueryParams) =>
    fetchJSON<PaginatedResponse<Mention>>("/mentions", params as Record<string, string | number | boolean | undefined>),
  getMentionDetail: (dedupKey: string) =>
    fetchJSON<Mention>(`/mentions/${dedupKey}`),
  getEvents: (params?: EventQueryParams) =>
    fetchJSON<PaginatedResponse<EventCluster>>("/events", params as Record<string, string | number | boolean | undefined>),
  getEventDetail: (eventId: string) =>
    fetchJSON<EventCluster>(`/events/${eventId}`),
  getAggregates: (params?: { date_basis?: string; bucket_type?: string }) =>
    fetchJSON<HistoricalAggregate[]>("/aggregates", params as Record<string, string | number | boolean | undefined>),
  getAnomalies: (params?: { severity?: string; anomaly_type?: string; date_basis?: string }) =>
    fetchJSON<AnomalySignal[]>("/anomalies", params as Record<string, string | number | boolean | undefined>),
};

export { ApiError };
