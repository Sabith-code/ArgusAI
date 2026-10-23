import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

DATA_SUFFICIENCY_WARNING = "Uncalibrated baseline due to sparse historical depth"

def compute_bucket_metrics(
    mentions: List[dict],
    date_basis: str,
    bucket_type: str,
    bucket_key: str,
    start_date: str,
    end_date: str
) -> dict:
    """Compute metric aggregates for a specific list of mentions in a time bucket."""
    n_total = len(mentions)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if n_total == 0:
        return {
            "_id": f"agg_{date_basis}_{bucket_type}_{bucket_key}",
            "aggregate_id": f"agg_{date_basis}_{bucket_type}_{bucket_key}",
            "date_basis": date_basis,
            "bucket_type": bucket_type,
            "bucket_key": bucket_key,
            "start_date": start_date,
            "end_date": end_date,
            "total_mentions": 0,
            "avg_reputation_risk": 0.0,
            "max_reputation_risk": 0.0,
            "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "topic_distribution": {},
            "official_vs_third_party": {"official": 0, "third_party": 0},
            "data_sufficiency_warning": DATA_SUFFICIENCY_WARNING,
            "computed_at": now_iso
        }
        
    risk_probs = []
    sent_counts = {"positive": 0, "neutral": 0, "negative": 0}
    topic_counts = {}
    official_count = 0
    third_party_count = 0
    
    for m in mentions:
        # Reputation risk
        r_p = m.get("reputation_risk", {}).get("risk_probability")
        if r_p is not None:
            risk_probs.append(r_p)
            
        # Sentiment
        sent = m.get("sentiment", {}).get("selected_label", "neutral")
        sent_counts[sent] = sent_counts.get(sent, 0) + 1
        
        # Topic
        top = m.get("topic", {}).get("selected_label", "general_discussion")
        topic_counts[top] = topic_counts.get(top, 0) + 1
        
        # Official status
        if m.get("is_official"):
            official_count += 1
        else:
            third_party_count += 1
            
    avg_risk = round(sum(risk_probs) / len(risk_probs), 4) if risk_probs else 0.0
    max_risk = round(max(risk_probs), 4) if risk_probs else 0.0
    
    return {
        "_id": f"agg_{date_basis}_{bucket_type}_{bucket_key}",
        "aggregate_id": f"agg_{date_basis}_{bucket_type}_{bucket_key}",
        "date_basis": date_basis,
        "bucket_type": bucket_type,
        "bucket_key": bucket_key,
        "start_date": start_date,
        "end_date": end_date,
        "total_mentions": n_total,
        "avg_reputation_risk": avg_risk,
        "max_reputation_risk": max_risk,
        "sentiment_distribution": sent_counts,
        "topic_distribution": topic_counts,
        "official_vs_third_party": {
            "official": official_count,
            "third_party": third_party_count
        },
        "data_sufficiency_warning": DATA_SUFFICIENCY_WARNING,
        "computed_at": now_iso
    }

def generate_historical_aggregates(mentions: List[dict]) -> List[dict]:
    """
    Generate historical aggregate documents across both date_basis dimensions:
    1. date_basis = 'publication_date' (Monthly, Yearly, Missing)
    2. date_basis = 'discovered_at' (Snapshot Batch)
    """
    logger.info(f"Generating historical aggregates for {len(mentions)} mentions...")
    aggregates = []
    
    # ----------------------------------------------------
    # 1. Publication-Time Analysis (date_basis = 'publication_date')
    # ----------------------------------------------------
    pub_monthly_groups: Dict[str, List[dict]] = {}
    pub_yearly_groups: Dict[str, List[dict]] = {}
    pub_missing_group: List[dict] = []
    
    for m in mentions:
        p_date = m.get("publication_date")
        if p_date and len(str(p_date)) >= 7:
            p_str = str(p_date)[:10]
            month_key = p_str[:7]  # YYYY-MM
            year_key = p_str[:4]   # YYYY
            
            pub_monthly_groups.setdefault(month_key, []).append(m)
            pub_yearly_groups.setdefault(year_key, []).append(m)
        else:
            pub_missing_group.append(m)
            
    # Monthly publication aggregates
    for m_key in sorted(pub_monthly_groups.keys()):
        group = pub_monthly_groups[m_key]
        agg_doc = compute_bucket_metrics(
            mentions=group,
            date_basis="publication_date",
            bucket_type="monthly",
            bucket_key=m_key,
            start_date=f"{m_key}-01",
            end_date=f"{m_key}-31"
        )
        aggregates.append(agg_doc)
        
    # Yearly publication aggregates
    for y_key in sorted(pub_yearly_groups.keys()):
        group = pub_yearly_groups[y_key]
        agg_doc = compute_bucket_metrics(
            mentions=group,
            date_basis="publication_date",
            bucket_type="yearly",
            bucket_key=y_key,
            start_date=f"{y_key}-01-01",
            end_date=f"{y_key}-12-31"
        )
        aggregates.append(agg_doc)

    # Missing publication date aggregate
    if pub_missing_group:
        agg_missing = compute_bucket_metrics(
            mentions=pub_missing_group,
            date_basis="publication_date",
            bucket_type="missing_date",
            bucket_key="publication_date_missing",
            start_date="null",
            end_date="null"
        )
        aggregates.append(agg_missing)

    # ----------------------------------------------------
    # 2. Observation-Time Analysis (date_basis = 'discovered_at')
    # ----------------------------------------------------
    # Group all mentions under the 2026-09-25 snapshot discovery batch
    agg_snapshot = compute_bucket_metrics(
        mentions=mentions,
        date_basis="discovered_at",
        bucket_type="snapshot_batch",
        bucket_key="2026-09-25_batch",
        start_date="2026-09-25T10:15:52Z",
        end_date="2026-09-25T10:16:01Z"
    )
    aggregates.append(agg_snapshot)

    logger.info(f"Generated {len(aggregates)} historical aggregate bucket documents.")
    return aggregates
