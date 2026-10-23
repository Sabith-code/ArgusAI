from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    status: str = Field(..., example="ok")
    database: str = Field(..., example="connected")
    mongodb_version: str = Field(..., example="8.0.5")
    timestamp: str

class SummaryResponse(BaseModel):
    total_mentions: int
    total_events: int
    active_anomalies_count: int
    global_brand_indicator: float
    global_threat_level: str
    risk_level_breakdown: Dict[str, int]

class TopThreatEvent(BaseModel):
    event_id: str
    canonical_title: str
    risk_score: float
    threat_level: str

class ScorecardResponse(BaseModel):
    scorecard_id: str
    global_brand_indicator: float
    global_threat_level: str
    parameter_status: str
    total_mentions_analyzed: int
    total_events_analyzed: int
    risk_level_breakdown: Dict[str, int]
    active_anomalies_count: int
    top_threat_events: List[TopThreatEvent]
    generated_at: str

class PaginatedMentionsResponse(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    data: List[Dict[str, Any]]

class PaginatedEventsResponse(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    data: List[Dict[str, Any]]
