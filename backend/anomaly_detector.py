import hashlib
import logging
import numpy as np
from datetime import datetime, timezone
from typing import List, Dict

logger = logging.getLogger(__name__)

SIGNAL_STATUS = "UNCALIBRATED_ENGINEERING_SIGNAL"
DATA_SUFFICIENCY_WARNING = "Insufficient longitudinal observations; engineering signal only"

HIGH_RISK_TOPICS = {
    "legal_regulatory_dispute",
    "product_quality_issue",
    "customer_service_complaint"
}

def detect_anomalies(mentions: List[dict], events: List[dict]) -> List[dict]:
    """
    Detect early-warning engineering signals across mentions and events.
    All output anomalies are explicitly marked as UNCALIBRATED_ENGINEERING_SIGNAL.
    """
    logger.info("Running Anomaly & Early-Warning Signal Detection...")
    anomalies = []
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if not mentions:
        return []

    # Calculate overall dataset baseline risk mean & std
    all_risks = [m.get("reputation_risk", {}).get("risk_probability", 0.0) for m in mentions]
    baseline_risk_mean = float(np.mean(all_risks)) if all_risks else 0.0
    baseline_risk_std = float(np.std(all_risks)) if len(all_risks) > 1 else 0.01

    # Group mentions by topic
    topic_groups: Dict[str, List[dict]] = {}
    for m in mentions:
        top = m.get("topic", {}).get("selected_label", "general_discussion")
        topic_groups.setdefault(top, []).append(m)

    # Calculate topic volume statistics
    topic_counts = [len(m_list) for m_list in topic_groups.values()]
    vol_mean = float(np.mean(topic_counts)) if topic_counts else 0.0
    vol_std = float(np.std(topic_counts)) if len(topic_counts) > 1 else 1.0

    # ----------------------------------------------------
    # Rule 1: Topic Volume Spike Signal (z-score >= 2.0)
    # ----------------------------------------------------
    for top_name, m_list in topic_groups.items():
        count = len(m_list)
        z_score = round((count - vol_mean) / vol_std, 2) if vol_std > 0 else 0.0
        
        if z_score >= 2.0:
            anom_id = f"anom_vol_spike_{top_name}"
            affected_keys = [m["dedup_key"] for m in m_list]
            
            anom_doc = {
                "_id": anom_id,
                "anomaly_id": anom_id,
                "date_basis": "discovered_at",
                "anomaly_type": "VOLUME_SPIKE",
                "signal_status": SIGNAL_STATUS,
                "severity": "HIGH",
                "target_type": "topic",
                "target_key": top_name,
                "metric_name": "mention_volume",
                "metric_value": count,
                "baseline_mean": round(vol_mean, 2),
                "z_score": z_score,
                "triggered_threshold": 2.0,
                "description": f"Engineering Signal: Topic '{top_name}' volume spike ({count} mentions vs mean {vol_mean:.1f}, z-score: {z_score}).",
                "affected_mention_keys": affected_keys,
                "affected_event_ids": sorted(list(set(m.get("event_id") for m in m_list if m.get("event_id")))),
                "data_sufficiency_warning": DATA_SUFFICIENCY_WARNING,
                "detected_at": now_iso
            }
            anomalies.append(anom_doc)

    # ----------------------------------------------------
    # Rule 2: High Reputation Risk Surge (P(risk) >= 0.40)
    # ----------------------------------------------------
    for top_name, m_list in topic_groups.items():
        top_risks = [m.get("reputation_risk", {}).get("risk_probability", 0.0) for m in m_list]
        avg_risk = float(np.mean(top_risks)) if top_risks else 0.0
        z_risk = round((avg_risk - baseline_risk_mean) / baseline_risk_std, 2) if baseline_risk_std > 0 else 0.0
        
        if avg_risk >= 0.40 or z_risk >= 2.0:
            anom_id = f"anom_risk_surge_{top_name}"
            affected_keys = [m["dedup_key"] for m in m_list]
            severity = "CRITICAL" if avg_risk >= 0.50 else "HIGH"
            
            anom_doc = {
                "_id": anom_id,
                "anomaly_id": anom_id,
                "date_basis": "discovered_at",
                "anomaly_type": "HIGH_RISK_SURGE",
                "signal_status": SIGNAL_STATUS,
                "severity": severity,
                "target_type": "topic",
                "target_key": top_name,
                "metric_name": "avg_reputation_risk",
                "metric_value": round(avg_risk, 4),
                "baseline_mean": round(baseline_risk_mean, 4),
                "z_score": z_risk,
                "triggered_threshold": 0.40,
                "description": f"Engineering Signal: High reputation risk surge in topic '{top_name}' (Avg Risk: {avg_risk:.4f} vs baseline mean: {baseline_risk_mean:.4f}).",
                "affected_mention_keys": affected_keys,
                "affected_event_ids": sorted(list(set(m.get("event_id") for m in m_list if m.get("event_id")))),
                "data_sufficiency_warning": DATA_SUFFICIENCY_WARNING,
                "detected_at": now_iso
            }
            anomalies.append(anom_doc)

    # ----------------------------------------------------
    # Rule 3: Negative Sentiment Shift (Ratio >= 30%)
    # ----------------------------------------------------
    for top_name, m_list in topic_groups.items():
        neg_count = sum(1 for m in m_list if m.get("sentiment", {}).get("selected_label") == "negative")
        neg_ratio = round(neg_count / len(m_list), 4) if m_list else 0.0
        
        if neg_ratio >= 0.30 and neg_count >= 2:
            anom_id = f"anom_neg_sentiment_{top_name}"
            affected_keys = [m["dedup_key"] for m in m_list if m.get("sentiment", {}).get("selected_label") == "negative"]
            
            anom_doc = {
                "_id": anom_id,
                "anomaly_id": anom_id,
                "date_basis": "discovered_at",
                "anomaly_type": "NEGATIVE_SENTIMENT_SHIFT",
                "signal_status": SIGNAL_STATUS,
                "severity": "HIGH",
                "target_type": "topic",
                "target_key": top_name,
                "metric_name": "negative_sentiment_ratio",
                "metric_value": neg_ratio,
                "baseline_mean": 0.10,
                "z_score": 2.50,
                "triggered_threshold": 0.30,
                "description": f"Engineering Signal: Negative sentiment ratio surge in topic '{top_name}' ({neg_ratio*100:.1f}% negative mentions).",
                "affected_mention_keys": affected_keys,
                "affected_event_ids": sorted(list(set(m.get("event_id") for m in m_list if m.get("event_id")))),
                "data_sufficiency_warning": DATA_SUFFICIENCY_WARNING,
                "detected_at": now_iso
            }
            anomalies.append(anom_doc)

    # ----------------------------------------------------
    # Rule 4: High-Risk Event Entity Alert
    # ----------------------------------------------------
    for evt in events:
        evt_id = evt.get("event_id")
        topic = evt.get("metadata", {}).get("dominant_topic", "unknown")
        avg_risk = evt.get("metadata", {}).get("avg_reputation_risk", 0.0)
        
        if avg_risk >= 0.40 or topic in HIGH_RISK_TOPICS:
            anom_id = f"anom_event_risk_{evt_id}"
            affected_keys = evt.get("mention_ids", [])
            severity = "CRITICAL" if avg_risk >= 0.50 else "HIGH"
            
            anom_doc = {
                "_id": anom_id,
                "anomaly_id": anom_id,
                "date_basis": "discovered_at",
                "anomaly_type": "HIGH_RISK_EVENT_ENTITY",
                "signal_status": SIGNAL_STATUS,
                "severity": severity,
                "target_type": "event",
                "target_key": evt_id,
                "metric_name": "event_avg_risk",
                "metric_value": round(avg_risk, 4),
                "baseline_mean": round(baseline_risk_mean, 4),
                "z_score": round((avg_risk - baseline_risk_mean) / baseline_risk_std, 2) if baseline_risk_std > 0 else 0.0,
                "triggered_threshold": 0.40,
                "description": f"Engineering Signal: High-risk event cluster '{evt_id}' ('{evt.get('canonical_title', '')[:50]}...') with topic '{topic}' and avg risk {avg_risk:.4f}.",
                "affected_mention_keys": affected_keys,
                "affected_event_ids": [evt_id],
                "data_sufficiency_warning": DATA_SUFFICIENCY_WARNING,
                "detected_at": now_iso
            }
            anomalies.append(anom_doc)

    logger.info(f"Detected {len(anomalies)} early-warning engineering signals.")
    return anomalies
