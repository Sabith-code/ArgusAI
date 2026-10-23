import os
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO date string or YYYY-MM-DD into a UTC datetime object."""
    if not date_str:
        return None
    try:
        # ISO-8601 UTC
        if "T" in date_str:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # YYYY-MM-DD
        return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def cluster_mentions(mentions: List[dict]) -> Tuple[List[dict], List[dict]]:
    """
    Cluster mentions into real-world event entities using Agglomerative Clustering
    with Cosine Distance Thresholding and Temporal Window Constraints.
    
    Returns:
      - updated_mentions: list of mentions with assigned `event_id` (or None if unclustered)
      - events: list of cluster event objects for the `events` collection
    """
    sim_threshold = float(os.getenv("EVENT_SIMILARITY_THRESHOLD", "0.82"))
    max_window_days = int(os.getenv("MAX_EVENT_WINDOW_DAYS", "30"))
    dist_threshold = round(1.0 - sim_threshold, 4)
    
    n_items = len(mentions)
    if n_items == 0:
        return [], []
        
    logger.info(f"Running Agglomerative Event Clustering on {n_items} mentions...")
    logger.info(f"Configured Similarity Threshold: {sim_threshold} (Max Distance: {dist_threshold})")
    logger.info(f"Configured Max Event Window: {max_window_days} days (Uncalibrated Engineering Constraint)")

    # 1. Extract Vectors
    vecs = np.array([m["embedding"] for m in mentions], dtype=np.float32)
    
    # 2. Pairwise Cosine Distance Matrix
    sim_matrix = cosine_similarity(vecs, vecs)
    dist_matrix = np.clip(1.0 - sim_matrix, 0.0, 1.0)
    
    # 3. Apply Temporal Constraint
    dates = []
    for m in mentions:
        pub_dt = parse_date(m.get("publication_date"))
        disc_dt = parse_date(m.get("discovered_at"))
        dates.append(pub_dt or disc_dt)
        
    for i in range(n_items):
        for j in range(i + 1, n_items):
            dt_i = dates[i]
            dt_j = dates[j]
            if dt_i and dt_j:
                delta_days = abs((dt_i - dt_j).days)
                if delta_days > max_window_days:
                    # Bar merging by forcing maximum distance
                    dist_matrix[i, j] = 1.0
                    dist_matrix[j, i] = 1.0

    # 4. Agglomerative Clustering
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=dist_threshold,
        metric="precomputed",
        linkage="average"
    )
    clustering.fit(dist_matrix)
    labels = clustering.labels_
    
    # Group indices by cluster label
    clusters_map: Dict[int, List[int]] = {}
    for idx, lbl in enumerate(labels):
        clusters_map.setdefault(lbl, []).append(idx)

    updated_mentions = [dict(m) for m in mentions]
    events_list = []
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 5. Process Clusters & Isolate Unclustered Singletons
    for cluster_label, member_indices in clusters_map.items():
        # Singletons remain unclustered outliers
        if len(member_indices) == 1:
            idx = member_indices[0]
            updated_mentions[idx]["event_id"] = None
            continue
            
        # Deterministic Event ID generation
        member_keys = sorted([mentions[idx]["dedup_key"] for idx in member_indices])
        hash_src = "|".join(member_keys)
        event_id = f"evt_{hashlib.md5(hash_src.encode('utf-8')).hexdigest()[:12]}"
        
        # Assign event_id to member mentions
        for idx in member_indices:
            updated_mentions[idx]["event_id"] = event_id
            
        # Compute Normalized Event Centroid
        member_vecs = vecs[member_indices]
        c_raw = np.mean(member_vecs, axis=0)
        c_norm = np.linalg.norm(c_raw)
        event_embedding = (c_raw / c_norm if c_norm > 0 else c_raw).astype(float).tolist()
        
        # Determine canonical title (prefer official or earliest)
        canonical_title = mentions[member_indices[0]].get("title", "")
        for idx in member_indices:
            if mentions[idx].get("is_official"):
                canonical_title = mentions[idx].get("title", "")
                break

        # Calculate time span
        member_dates = [dates[idx] for idx in member_indices if dates[idx]]
        first_seen = min(member_dates).isoformat() if member_dates else now_iso
        last_seen = max(member_dates).isoformat() if member_dates else now_iso
        
        # Post-hoc Metadata Aggregations (Phase 4 signals NOT used for clustering)
        topic_counts = {}
        sent_counts = {}
        source_counts = {}
        risk_probs = []
        
        for idx in member_indices:
            item = mentions[idx]
            top = item.get("topic", {}).get("selected_label", "unknown")
            topic_counts[top] = topic_counts.get(top, 0) + 1
            
            sent = item.get("sentiment", {}).get("selected_label", "unknown")
            sent_counts[sent] = sent_counts.get(sent, 0) + 1
            
            st = item.get("source_type", "unknown")
            source_counts[st] = source_counts.get(st, 0) + 1
            
            r_p = item.get("reputation_risk", {}).get("risk_probability")
            if r_p is not None:
                risk_probs.append(r_p)
                
        dominant_topic = max(topic_counts, key=topic_counts.get) if topic_counts else "general_discussion"
        avg_risk = round(sum(risk_probs) / len(risk_probs), 4) if risk_probs else 0.0
        
        event_doc = {
            "_id": event_id,
            "event_id": event_id,
            "canonical_title": canonical_title,
            "mention_count": len(member_indices),
            "mention_ids": member_keys,
            "event_embedding": event_embedding,
            "first_seen_at": first_seen,
            "last_seen_at": last_seen,
            "metadata": {
                "dominant_topic": dominant_topic,
                "avg_reputation_risk": avg_risk,
                "topic_distribution": topic_counts,
                "sentiment_distribution": sent_counts,
                "source_type_counts": source_counts
            },
            "created_at": now_iso,
            "updated_at": now_iso
        }
        events_list.append(event_doc)

    return updated_mentions, events_list
