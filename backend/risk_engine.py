import os
import math
import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Any

logger = logging.getLogger(__name__)

PARAMETER_STATUS = "UNCALIBRATED_ENGINEERING_HEURISTICS"

TOPIC_MULTIPLIERS = {
    "legal_regulatory_dispute": 1.5,
    "product_quality_issue": 1.4,
    "customer_service_complaint": 1.3,
    "executive_controversy": 1.2,
    "financial_corporate": 1.1,
    "general_discussion": 0.6,
    "routine_marketing_launch": 0.4
}

SENTIMENT_FACTORS = {
    "negative": 1.0,
    "neutral": 0.3,
    "positive": 0.0
}

def get_source_weight(source_type: str, is_official: bool) -> float:
    """Get source impact weight based on channel credibility and reach."""
    if is_official:
        return 1.0
    st_upper = (source_type or "").upper()
    if st_upper == "NEWS":
        return 1.2
    if st_upper in ("REDDIT", "YOUTUBE", "TWITTER", "SOCIAL"):
        return 1.1
    return 1.0

def calculate_mention_risk_score(mention: dict) -> Tuple[float, str]:
    """
    Calculate composite mention risk score S_mention in [0.0, 100.0]
    while preserving the raw model P(risk) probability untouched.
    """
    risk_threshold_med = float(os.getenv("RISK_THRESHOLD_MEDIUM", "30.0"))
    risk_threshold_high = float(os.getenv("RISK_THRESHOLD_HIGH", "55.0"))
    risk_threshold_crit = float(os.getenv("RISK_THRESHOLD_CRITICAL", "75.0"))

    # Raw Laya outputs preserved untouched
    p_risk = float(mention.get("reputation_risk", {}).get("risk_probability", 0.0))
    urgency = float(mention.get("urgency", {}).get("expected_score", 0.0))
    sentiment = mention.get("sentiment", {}).get("selected_label", "neutral")
    topic = mention.get("topic", {}).get("selected_label", "routine_marketing_launch")
    source_type = mention.get("source_type", "")
    is_official = bool(mention.get("is_official", False))

    s_factor = SENTIMENT_FACTORS.get(sentiment, 0.3)
    m_topic = TOPIC_MULTIPLIERS.get(topic, 0.6)
    w_source = get_source_weight(source_type, is_official)

    base_score = 40.0 * p_risk + 25.0 * (urgency / 2.0) + 20.0 * s_factor + 15.0 * m_topic
    final_score = min(100.0, max(0.0, base_score * w_source))
    final_score = round(final_score, 2)

    if final_score >= risk_threshold_crit:
        risk_level = "CRITICAL"
    elif final_score >= risk_threshold_high:
        risk_level = "HIGH"
    elif final_score >= risk_threshold_med:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return final_score, risk_level

def calculate_event_risk_score(
    event: dict,
    member_mentions: List[dict],
    active_anomalies: List[dict]
) -> Tuple[float, str]:
    """
    Calculate composite event cluster risk score S_event in [0.0, 100.0].
    Amplified by member count k and configurable EVENT_ANOMALY_BOOST.
    """
    anomaly_boost = float(os.getenv("EVENT_ANOMALY_BOOST", "15.0"))
    risk_threshold_med = float(os.getenv("RISK_THRESHOLD_MEDIUM", "30.0"))
    risk_threshold_high = float(os.getenv("RISK_THRESHOLD_HIGH", "55.0"))
    risk_threshold_crit = float(os.getenv("RISK_THRESHOLD_CRITICAL", "75.0"))

    if not member_mentions:
        return 0.0, "LOW"

    m_scores = [m.get("risk_score", 0.0) for m in member_mentions]
    mean_m_score = sum(m_scores) / len(m_scores)
    k = len(member_mentions)

    evt_id = event.get("event_id")
    has_anomaly = False
    for anom in active_anomalies:
        if evt_id in anom.get("affected_event_ids", []):
            has_anomaly = True
            break

    boost = anomaly_boost if has_anomaly else 0.0
    raw_score = (mean_m_score * math.log2(k + 1)) + boost
    final_score = min(100.0, max(0.0, raw_score))
    final_score = round(final_score, 2)

    if final_score >= risk_threshold_crit:
        threat_level = "CRITICAL"
    elif final_score >= risk_threshold_high:
        threat_level = "HIGH"
    elif final_score >= risk_threshold_med:
        threat_level = "ELEVATED"
    else:
        threat_level = "LOW"

    return final_score, threat_level

def generate_global_scorecard(
    mentions: List[dict],
    events: List[dict],
    anomalies: List[dict]
) -> dict:
    """
    Generate Global Brand Health Indicator Snapshot.
    Documented strictly as an UNCALIBRATED ENGINEERING INDICATOR.
    """
    score_crit = float(os.getenv("GLOBAL_BRAND_SCORE_CRITICAL", "50.0"))
    score_high = float(os.getenv("GLOBAL_BRAND_SCORE_HIGH", "70.0"))
    score_elev = float(os.getenv("GLOBAL_BRAND_SCORE_ELEVATED", "85.0"))

    now_iso = datetime.now(timezone.utc).isoformat()
    n_mentions = len(mentions)

    if n_mentions == 0:
        return {
            "_id": "scorecard_latest",
            "scorecard_id": "scorecard_latest",
            "global_brand_indicator": 100.0,
            "global_threat_level": "NORMAL",
            "parameter_status": PARAMETER_STATUS,
            "total_mentions_analyzed": 0,
            "total_events_analyzed": 0,
            "risk_level_breakdown": {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0},
            "active_anomalies_count": 0,
            "top_threat_events": [],
            "generated_at": now_iso
        }

    m_scores = [m.get("risk_score", 0.0) for m in mentions]
    avg_mention_risk = sum(m_scores) / n_mentions
    global_score = max(0.0, min(100.0, round(100.0 - avg_mention_risk, 2)))

    # Risk level breakdown
    breakdown = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for m in mentions:
        lvl = m.get("risk_level", "LOW")
        breakdown[lvl] = breakdown.get(lvl, 0) + 1

    # Global threat level derived purely from global_score thresholds (no anomaly override)
    if global_score < score_crit:
        global_threat = "CRITICAL"
    elif global_score < score_high:
        global_threat = "HIGH"
    elif global_score < score_elev:
        global_threat = "ELEVATED"
    else:
        global_threat = "NORMAL"

    # Sort top threat events by event risk_score
    sorted_events = sorted(events, key=lambda e: e.get("risk_score", 0.0), reverse=True)
    top_threat_events = [
        {
            "event_id": e.get("event_id"),
            "canonical_title": e.get("canonical_title", "")[:60],
            "risk_score": e.get("risk_score", 0.0),
            "threat_level": e.get("threat_level", "LOW")
        }
        for e in sorted_events[:3]
    ]

    return {
        "_id": "scorecard_latest",
        "scorecard_id": "scorecard_latest",
        "global_brand_indicator": global_score,
        "global_threat_level": global_threat,
        "parameter_status": PARAMETER_STATUS,
        "total_mentions_analyzed": n_mentions,
        "total_events_analyzed": len(events),
        "risk_level_breakdown": breakdown,
        "active_anomalies_count": len(anomalies),
        "top_threat_events": top_threat_events,
        "generated_at": now_iso
    }
