import sys
import time
import logging
from db import check_connection, get_db, get_mentions_collection
from risk_engine import (
    calculate_mention_risk_score,
    calculate_event_risk_score,
    generate_global_scorecard
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SCORECARDS_COLL = "risk_scorecards"

def get_scorecards_collection():
    db = get_db()
    return db[SCORECARDS_COLL]

def ensure_phase8_indexes(mentions_coll, events_coll, scorecards_coll):
    """Create required Phase 8 indexes."""
    idx1 = mentions_coll.create_index([("risk_score", -1)], name="idx_risk_score")
    idx2 = mentions_coll.create_index([("risk_level", 1)], name="idx_risk_level")

    idx3 = events_coll.create_index([("risk_score", -1)], name="idx_events_risk_score")
    idx4 = events_coll.create_index([("threat_level", 1)], name="idx_events_threat_level")

    idx5 = scorecards_coll.create_index([("scorecard_id", 1)], unique=True, name="idx_scorecard_id")
    idx6 = scorecards_coll.create_index([("generated_at", -1)], name="idx_scorecard_gen")

    return [idx1, idx2, idx3, idx4, idx5, idx6]

def run_phase8_pipeline() -> dict:
    """Execute Phase 8 Risk Engine Pipeline."""
    t0 = time.time()
    logger.info("================ STARTING PHASE 8 PIPELINE ================")

    connected, version, _ = check_connection()
    if not connected:
        logger.error(f"MongoDB connection failed: {version}")
        sys.exit(1)

    mentions_coll = get_mentions_collection()
    events_coll = get_db()["events"]
    anom_coll = get_db()["anomalies"]
    scorecards_coll = get_scorecards_collection()

    raw_mentions = list(mentions_coll.find({}))
    raw_events = list(events_coll.find({}))
    raw_anomalies = list(anom_coll.find({}))

    n_mentions = len(raw_mentions)
    n_events = len(raw_events)
    n_anomalies = len(raw_anomalies)

    logger.info(f"Loaded {n_mentions} mentions, {n_events} events, and {n_anomalies} anomalies from MongoDB.")

    if n_mentions != 77:
        logger.error(f"Expected 77 mentions in MongoDB, found {n_mentions}.")
        sys.exit(1)

    # 1. Mention Composite Risk Scoring
    logger.info("\n--- Step 1: Computing Mention Composite Risk Scores ---")
    updated_mentions = []
    for m in raw_mentions:
        doc = dict(m)
        score, level = calculate_mention_risk_score(doc)
        doc["risk_score"] = score
        doc["risk_level"] = level
        mentions_coll.replace_one({"dedup_key": doc["dedup_key"]}, doc, upsert=True)
        updated_mentions.append(doc)

    # 2. Event Cluster Composite Risk Scoring
    logger.info("\n--- Step 2: Computing Event Cluster Risk Scores ---")
    mentions_by_key = {m["dedup_key"]: m for m in updated_mentions}
    updated_events = []
    
    for evt in raw_events:
        evt_doc = dict(evt)
        member_keys = evt_doc.get("mention_ids", [])
        member_m = [mentions_by_key[k] for k in member_keys if k in mentions_by_key]
        
        e_score, t_level = calculate_event_risk_score(evt_doc, member_m, raw_anomalies)
        evt_doc["risk_score"] = e_score
        evt_doc["threat_level"] = t_level
        events_coll.replace_one({"event_id": evt_doc["event_id"]}, evt_doc, upsert=True)
        updated_events.append(evt_doc)

    # 3. Global Scorecard Generation
    logger.info("\n--- Step 3: Generating Global Brand Indicator Scorecard ---")
    scorecard = generate_global_scorecard(updated_mentions, updated_events, raw_anomalies)
    scorecards_coll.replace_one({"scorecard_id": scorecard["scorecard_id"]}, scorecard, upsert=True)

    index_names = ensure_phase8_indexes(mentions_coll, events_coll, scorecards_coll)

    stats = {
        "total_mentions": n_mentions,
        "total_events": n_events,
        "total_anomalies": n_anomalies,
        "global_brand_indicator": scorecard["global_brand_indicator"],
        "global_threat_level": scorecard["global_threat_level"],
        "risk_breakdown": scorecard["risk_level_breakdown"],
        "indexes_active": len(index_names),
        "execution_time_sec": round(time.time() - t0, 2)
    }

    logger.info(f"\n================ PHASE 8 FIRST RUN METRICS ================")
    logger.info(f"Total Mentions Analyzed:    {stats['total_mentions']}")
    logger.info(f"Total Event Entities:       {stats['total_events']}")
    logger.info(f"Global Brand Indicator:     {stats['global_brand_indicator']} / 100")
    logger.info(f"Global Threat Level:        {stats['global_threat_level']}")
    logger.info(f"Risk Breakdown:             {stats['risk_breakdown']}")
    logger.info(f"Execution Time:             {stats['execution_time_sec']} seconds")
    logger.info("==========================================================")

    return stats

def run_idempotency_test(stats_run1: dict):
    """Execute second run to verify 100% score stability and zero duplicate creation."""
    logger.info("\n--- Performing SECOND Run (Idempotency & Score Stability Test) ---")
    t0 = time.time()

    mentions_coll = get_mentions_collection()
    events_coll = get_db()["events"]
    anom_coll = get_db()["anomalies"]
    scorecards_coll = get_scorecards_collection()

    raw_mentions = list(mentions_coll.find({}))
    raw_events = list(events_coll.find({}))
    raw_anomalies = list(anom_coll.find({}))

    updated_mentions = []
    for m in raw_mentions:
        doc = dict(m)
        score, level = calculate_mention_risk_score(doc)
        doc["risk_score"] = score
        doc["risk_level"] = level
        mentions_coll.replace_one({"dedup_key": doc["dedup_key"]}, doc, upsert=True)
        updated_mentions.append(doc)

    mentions_by_key = {m["dedup_key"]: m for m in updated_mentions}
    updated_events = []
    for evt in raw_events:
        evt_doc = dict(evt)
        member_keys = evt_doc.get("mention_ids", [])
        member_m = [mentions_by_key[k] for k in member_keys if k in mentions_by_key]
        e_score, t_level = calculate_event_risk_score(evt_doc, member_m, raw_anomalies)
        evt_doc["risk_score"] = e_score
        evt_doc["threat_level"] = t_level
        events_coll.replace_one({"event_id": evt_doc["event_id"]}, evt_doc, upsert=True)
        updated_events.append(evt_doc)

    scorecard = generate_global_scorecard(updated_mentions, updated_events, raw_anomalies)
    scorecards_coll.replace_one({"scorecard_id": scorecard["scorecard_id"]}, scorecard, upsert=True)

    final_mentions_count = mentions_coll.count_documents({})
    final_events_count = events_coll.count_documents({})
    final_scorecards_count = scorecards_coll.count_documents({})

    logger.info(f"Second Run Counts - mentions: {final_mentions_count}, events: {final_events_count}, scorecards: {final_scorecards_count}")
    logger.info(f"Second Run Execution Time: {time.time() - t0:.2f} seconds")

    idempotent_passed = (
        final_mentions_count == 77 and
        final_events_count == stats_run1["total_events"] and
        final_scorecards_count == 1 and
        scorecard["global_brand_indicator"] == stats_run1["global_brand_indicator"]
    )
    return idempotent_passed

if __name__ == "__main__":
    stats = run_phase8_pipeline()
    idempotent = run_idempotency_test(stats)

    if idempotent:
        print("\n================ PHASE 8 IDEMPOTENCY TEST PASSED 100% ================")
        print("Score stability and single scorecard persistence verified.")
        print("======================================================================")
    else:
        print("\nCRITICAL: Phase 8 Idempotency test failed!")
        sys.exit(1)
