import math
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from db import check_connection, get_db, get_mentions_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

def clean_doc(doc: Optional[dict]) -> Optional[dict]:
    """Convert MongoDB _id field to string for JSON serialization."""
    if not doc:
        return None
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    return d

@router.get("/health", response_model=Dict[str, Any])
def get_health():
    """System health check & MongoDB connection status."""
    connected, version, err = check_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    if not connected:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {err}"
        )
    return {
        "status": "ok",
        "database": "connected",
        "mongodb_version": version,
        "timestamp": now_iso
    }

@router.get("/summary", response_model=Dict[str, Any])
def get_summary():
    """High-level system overview stats."""
    db = get_db()
    mentions_coll = db["mentions"]
    events_coll = db["events"]
    anom_coll = db["anomalies"]
    scorecards_coll = db["risk_scorecards"]

    total_mentions = mentions_coll.count_documents({})
    total_events = events_coll.count_documents({})
    active_anomalies = anom_coll.count_documents({})
    scorecard = scorecards_coll.find_one({"scorecard_id": "scorecard_latest"}) or {}

    return {
        "total_mentions": total_mentions,
        "total_events": total_events,
        "active_anomalies_count": active_anomalies,
        "global_brand_indicator": scorecard.get("global_brand_indicator", 100.0),
        "global_threat_level": scorecard.get("global_threat_level", "NORMAL"),
        "risk_level_breakdown": scorecard.get("risk_level_breakdown", {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0})
    }

@router.get("/scorecard", response_model=Dict[str, Any])
def get_scorecard():
    """Latest Global Brand Health Indicator scorecard snapshot."""
    db = get_db()
    sc = db["risk_scorecards"].find_one({"scorecard_id": "scorecard_latest"})
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard snapshot not found.")
    return clean_doc(sc)

@router.get("/mentions", response_model=Dict[str, Any])
def get_mentions(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    topic: Optional[str] = Query(None, description="Filter by topic selected_label"),
    sentiment: Optional[str] = Query(None, description="Filter by sentiment selected_label"),
    risk_level: Optional[str] = Query(None, description="Filter by risk_level (LOW, MEDIUM, HIGH, CRITICAL)"),
    is_official: Optional[bool] = Query(None, description="Filter by official brand status"),
    source_type: Optional[str] = Query(None, description="Filter by source_type (NEWS, REDDIT, YOUTUBE, OFFICIAL)"),
    q: Optional[str] = Query(None, description="Text search query in title or snippet"),
    sort_by: str = Query("discovered_at", description="Sort field (risk_score, discovered_at, publication_date)"),
    order: str = Query("desc", description="Sort order (asc, desc)")
):
    """Paginated, filtered, searchable, and sortable mentions list."""
    db = get_db()
    query_filter: Dict[str, Any] = {}

    if topic:
        query_filter["topic.selected_label"] = topic
    if sentiment:
        query_filter["sentiment.selected_label"] = sentiment
    if risk_level:
        query_filter["risk_level"] = risk_level.upper()
    if is_official is not None:
        query_filter["is_official"] = is_official
    if source_type:
        query_filter["source_type"] = source_type.upper()
    if q:
        query_filter["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"snippet": {"$regex": q, "$options": "i"}}
        ]

    # Validate sort field
    allowed_sort_fields = {"risk_score", "discovered_at", "publication_date"}
    if sort_by not in allowed_sort_fields:
        sort_by = "discovered_at"

    sort_direction = -1 if order.lower() == "desc" else 1

    coll = db["mentions"]
    total = coll.count_documents(query_filter)
    pages = max(1, math.ceil(total / limit))
    skip = (page - 1) * limit

    cursor = coll.find(query_filter).sort([(sort_by, sort_direction)]).skip(skip).limit(limit)
    items = [clean_doc(m) for m in cursor]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "data": items
    }

@router.get("/mentions/{dedup_key:path}", response_model=Dict[str, Any])
def get_mention_by_key(dedup_key: str):
    """Get single mention document by its unique dedup_key."""
    db = get_db()
    doc = db["mentions"].find_one({"dedup_key": dedup_key})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Mention with dedup_key '{dedup_key}' not found.")
    return clean_doc(doc)

@router.get("/events", response_model=Dict[str, Any])
def get_events(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    topic: Optional[str] = Query(None, description="Filter by dominant_topic"),
    threat_level: Optional[str] = Query(None, description="Filter by threat_level (LOW, ELEVATED, HIGH, CRITICAL)"),
    sort_by: str = Query("risk_score", description="Sort field (risk_score, mention_count, first_seen_at)"),
    order: str = Query("desc", description="Sort order (asc, desc)")
):
    """Paginated, filtered list of event entities."""
    db = get_db()
    query_filter: Dict[str, Any] = {}

    if topic:
        query_filter["metadata.dominant_topic"] = topic
    if threat_level:
        query_filter["threat_level"] = threat_level.upper()

    allowed_sort_fields = {"risk_score", "mention_count", "first_seen_at"}
    if sort_by not in allowed_sort_fields:
        sort_by = "risk_score"

    sort_direction = -1 if order.lower() == "desc" else 1

    coll = db["events"]
    total = coll.count_documents(query_filter)
    pages = max(1, math.ceil(total / limit))
    skip = (page - 1) * limit

    cursor = coll.find(query_filter).sort([(sort_by, sort_direction)]).skip(skip).limit(limit)
    items = [clean_doc(e) for e in cursor]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
        "data": items
    }

@router.get("/events/{event_id}", response_model=Dict[str, Any])
def get_event_by_id(event_id: str):
    """Get single event entity detail with member mention summaries."""
    db = get_db()
    evt = db["events"].find_one({"event_id": event_id})
    if not evt:
        raise HTTPException(status_code=404, detail=f"Event entity with event_id '{event_id}' not found.")
    
    evt_doc = clean_doc(evt)
    member_keys = evt_doc.get("mention_ids", [])
    
    # Fetch member mention details
    member_mentions = list(db["mentions"].find(
        {"dedup_key": {"$in": member_keys}},
        {"dedup_key": 1, "title": 1, "canonical_url": 1, "publication_date": 1, "risk_score": 1, "risk_level": 1, "source_type": 1, "is_official": 1}
    ))
    evt_doc["member_mentions"] = [clean_doc(m) for m in member_mentions]
    return evt_doc

@router.get("/aggregates", response_model=List[Dict[str, Any]])
def get_historical_aggregates(
    date_basis: Optional[str] = Query(None, description="Filter by date_basis (publication_date, discovered_at)"),
    bucket_type: Optional[str] = Query(None, description="Filter by bucket_type (monthly, yearly, snapshot_batch, missing_date)")
):
    """Queryable time-series aggregate metric buckets."""
    db = get_db()
    query_filter: Dict[str, Any] = {}
    if date_basis:
        query_filter["date_basis"] = date_basis
    if bucket_type:
        query_filter["bucket_type"] = bucket_type

    cursor = db["historical_aggregates"].find(query_filter).sort([("bucket_key", 1)])
    return [clean_doc(a) for a in cursor]

@router.get("/anomalies", response_model=List[Dict[str, Any]])
def get_anomalies(
    severity: Optional[str] = Query(None, description="Filter by severity (MEDIUM, HIGH, CRITICAL)"),
    anomaly_type: Optional[str] = Query(None, description="Filter by anomaly_type"),
    date_basis: Optional[str] = Query(None, description="Filter by date_basis")
):
    """Queryable early-warning engineering signals and anomaly alerts."""
    db = get_db()
    query_filter: Dict[str, Any] = {}
    if severity:
        query_filter["severity"] = severity.upper()
    if anomaly_type:
        query_filter["anomaly_type"] = anomaly_type.upper()
    if date_basis:
        query_filter["date_basis"] = date_basis

    cursor = db["anomalies"].find(query_filter).sort([("detected_at", -1)])
    return [clean_doc(an) for an in cursor]
