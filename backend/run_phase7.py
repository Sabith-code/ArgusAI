import sys
import time
import logging
from db import check_connection, get_db, get_mentions_collection
from aggregations import generate_historical_aggregates
from anomaly_detector import detect_anomalies

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HISTORICAL_AGGREGATES_COLL = "historical_aggregates"
ANOMALIES_COLL = "anomalies"

def get_aggregates_collection():
    db = get_db()
    return db[HISTORICAL_AGGREGATES_COLL]

def get_anomalies_collection():
    db = get_db()
    return db[ANOMALIES_COLL]

def ensure_phase7_indexes(agg_coll, anom_coll):
    """Create required Phase 7 indexes on historical_aggregates and anomalies collections."""
    idx1 = agg_coll.create_index(
        [("date_basis", 1), ("bucket_type", 1), ("bucket_key", 1)],
        unique=True,
        name="idx_agg_composite"
    )
    idx2 = agg_coll.create_index([("computed_at", -1)], name="idx_agg_computed")

    idx3 = anom_coll.create_index([("anomaly_id", 1)], unique=True, name="idx_anom_id")
    idx4 = anom_coll.create_index([("severity", 1)], name="idx_anom_severity")
    idx5 = anom_coll.create_index([("anomaly_type", 1)], name="idx_anom_type")
    idx6 = anom_coll.create_index([("date_basis", 1)], name="idx_anom_date_basis")
    idx7 = anom_coll.create_index([("detected_at", -1)], name="idx_anom_detected")

    return [idx1, idx2, idx3, idx4, idx5, idx6, idx7]

def run_phase7_pipeline() -> dict:
    """Execute Phase 7 Historical Aggregation & Anomaly Detection Pipeline."""
    t0 = time.time()
    logger.info("================ STARTING PHASE 7 PIPELINE ================")

    # 1. Connection Check
    connected, version, _ = check_connection()
    if not connected:
        logger.error(f"MongoDB connection failed: {version}")
        sys.exit(1)

    mentions_coll = get_mentions_collection()
    events_coll = get_db()["events"]
    agg_coll = get_aggregates_collection()
    anom_coll = get_anomalies_collection()

    raw_mentions = list(mentions_coll.find({}))
    raw_events = list(events_coll.find({}))
    logger.info(f"Loaded {len(raw_mentions)} mentions and {len(raw_events)} events from MongoDB.")

    if len(raw_mentions) != 77:
        logger.error(f"Expected 77 mentions in MongoDB, found {len(raw_mentions)}.")
        sys.exit(1)

    # 2. Historical Aggregation
    logger.info("\n--- Step 1: Computing Historical Aggregates (Dual Date Basis) ---")
    aggregates = generate_historical_aggregates(raw_mentions)

    for agg in aggregates:
        agg_coll.replace_one({"aggregate_id": agg["aggregate_id"]}, agg, upsert=True)

    # 3. Anomaly & Early-Warning Signal Detection
    logger.info("\n--- Step 2: Executing Anomaly & Early-Warning Signal Detection ---")
    anomalies = detect_anomalies(raw_mentions, raw_events)

    for anom in anomalies:
        anom_coll.replace_one({"anomaly_id": anom["anomaly_id"]}, anom, upsert=True)

    # 4. Indexes
    index_names = ensure_phase7_indexes(agg_coll, anom_coll)
    logger.info(f"Verified/created {len(index_names)} Phase 7 indexes.")

    stats = {
        "total_mentions": len(raw_mentions),
        "total_events": len(raw_events),
        "historical_aggregates_count": len(aggregates),
        "anomalies_detected_count": len(anomalies),
        "indexes_active": len(index_names),
        "execution_time_sec": round(time.time() - t0, 2)
    }

    logger.info(f"\n================ PHASE 7 FIRST RUN METRICS ================")
    logger.info(f"Total Mentions Analyzed:      {stats['total_mentions']}")
    logger.info(f"Total Event Entities:         {stats['total_events']}")
    logger.info(f"Historical Bucket Aggregates: {stats['historical_aggregates_count']}")
    logger.info(f"Anomalies / Signals Detected: {stats['anomalies_detected_count']}")
    logger.info(f"Execution Time:               {stats['execution_time_sec']} seconds")
    logger.info("==========================================================")

    return stats

def run_idempotency_test(stats_run1: dict):
    """Execute second run to verify zero duplicate documents created."""
    logger.info("\n--- Performing SECOND Ingestion Run (Idempotency Test) ---")
    t0 = time.time()
    
    mentions_coll = get_mentions_collection()
    events_coll = get_db()["events"]
    agg_coll = get_aggregates_collection()
    anom_coll = get_anomalies_collection()

    raw_mentions = list(mentions_coll.find({}))
    raw_events = list(events_coll.find({}))

    aggregates = generate_historical_aggregates(raw_mentions)
    for agg in aggregates:
        agg_coll.replace_one({"aggregate_id": agg["aggregate_id"]}, agg, upsert=True)

    anomalies = detect_anomalies(raw_mentions, raw_events)
    for anom in anomalies:
        anom_coll.replace_one({"anomaly_id": anom["anomaly_id"]}, anom, upsert=True)

    count_agg_run2 = agg_coll.count_documents({})
    count_anom_run2 = anom_coll.count_documents({})

    logger.info(f"Second Run Document Counts - historical_aggregates: {count_agg_run2}, anomalies: {count_anom_run2}")
    logger.info(f"Second Run Execution Time: {time.time() - t0:.2f} seconds")

    idempotent_passed = (
        count_agg_run2 == stats_run1["historical_aggregates_count"] and
        count_anom_run2 == stats_run1["anomalies_detected_count"]
    )
    return idempotent_passed

if __name__ == "__main__":
    stats = run_phase7_pipeline()
    idempotent = run_idempotency_test(stats)

    if idempotent:
        print("\n================ PHASE 7 IDEMPOTENCY TEST PASSED 100% ================")
        print("Historical aggregate and anomaly collection document counts remain identical.")
        print("======================================================================")
    else:
        print("\nCRITICAL: Phase 7 Idempotency test failed!")
        sys.exit(1)
