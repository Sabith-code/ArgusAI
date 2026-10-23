import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple

from db import check_connection, get_mentions_collection, MONGODB_DATABASE, MONGODB_COLLECTION

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

APPROVED_TOPICS = {
    "product_quality_issue",
    "customer_service_complaint",
    "legal_regulatory_dispute",
    "financial_corporate",
    "executive_controversy",
    "routine_marketing_launch",
    "general_discussion"
}

APPROVED_SENTIMENTS = {"positive", "neutral", "negative"}

def validate_phase4_data(phase4_data: dict) -> Tuple[bool, List[str]]:
    """
    Programmatically validate phase4_output.json content before database insertion.
    """
    errors = []
    mentions = phase4_data.get("mentions", [])
    
    if len(mentions) != 77:
        errors.append(f"Expected 77 records in phase4_output.json, found {len(mentions)}.")

    dedup_keys = [m.get("dedup_key") for m in mentions if m.get("dedup_key")]
    canonical_urls = [m.get("canonical_url") for m in mentions if m.get("canonical_url")]

    if len(dedup_keys) != len(set(dedup_keys)):
        errors.append("Duplicate dedup_key values found in phase4_output.json!")

    if len(canonical_urls) != len(set(canonical_urls)):
        errors.append("Duplicate canonical_url values found in phase4_output.json!")

    for idx, m in enumerate(mentions, start=1):
        if not m.get("dedup_key"):
            errors.append(f"Record #{idx} missing required identity field 'dedup_key'")
        if not m.get("canonical_url"):
            errors.append(f"Record #{idx} missing required identity field 'canonical_url'")

        # Classification fields
        for q in ["sentiment", "urgency", "reputation_risk", "topic"]:
            if q not in m:
                errors.append(f"Record #{idx} ({m.get('dedup_key')}) missing classification output '{q}'")

        # Sentiment check
        sent = m.get("sentiment", {}).get("selected_label")
        if sent not in APPROVED_SENTIMENTS:
            errors.append(f"Record #{idx} unapproved sentiment label: '{sent}'")

        # Topic check
        top = m.get("topic", {}).get("selected_label")
        if top not in APPROVED_TOPICS:
            errors.append(f"Record #{idx} unapproved topic label: '{top}'")

        # Reputation Risk check
        risk_p = m.get("reputation_risk", {}).get("risk_probability")
        if risk_p is None or not (0.0 <= risk_p <= 1.0):
            errors.append(f"Record #{idx} invalid reputation risk probability: {risk_p}")

        # Failure & Fallback state checks
        ext_status = m.get("extraction_status")
        scope = m.get("classification_scope")

        if ext_status == "failed" and m.get("text") != "":
            errors.append(f"Record #{idx} extraction_status='failed' but non-empty text")

        if ext_status == "failed" and scope != "snippet_fallback":
            errors.append(f"Record #{idx} extraction_status='failed' but scope='{scope}' (expected 'snippet_fallback')")

        if not m.get("raw_laya_response"):
            errors.append(f"Record #{idx} missing raw_laya_response")

    return len(errors) == 0, errors

def ensure_indexes(collection) -> List[str]:
    """
    Create required MongoDB indexes on the mentions collection.
    - dedup_key: UNIQUE index for identity
    - canonical_url: Standard index for lookup
    - discovered_at, source_type, domain, topic.selected_label, sentiment.selected_label, is_official
    """
    index_names = []
    
    # 1. Unique index on dedup_key
    name1 = collection.create_index([("dedup_key", 1)], unique=True, name="idx_dedup_key_unique")
    index_names.append(name1)

    # 2. Standard lookup index on canonical_url
    name2 = collection.create_index([("canonical_url", 1)], name="idx_canonical_url")
    index_names.append(name2)

    # 3. Discovered timestamp index (time-range filtering)
    name3 = collection.create_index([("discovered_at", -1)], name="idx_discovered_at")
    index_names.append(name3)

    # 4. Source type index
    name4 = collection.create_index([("source_type", 1)], name="idx_source_type")
    index_names.append(name4)

    # 5. Domain index
    name5 = collection.create_index([("domain", 1)], name="idx_domain")
    index_names.append(name5)

    # 6. Topic selected label index
    name6 = collection.create_index([("topic.selected_label", 1)], name="idx_topic_selected_label")
    index_names.append(name6)

    # 7. Sentiment selected label index
    name7 = collection.create_index([("sentiment.selected_label", 1)], name="idx_sentiment_selected_label")
    index_names.append(name7)

    # 8. Is official flag index
    name8 = collection.create_index([("is_official", 1)], name="idx_is_official")
    index_names.append(name8)

    return index_names

def ingest_records(collection, mentions: List[dict]) -> dict:
    """
    Idempotently ingest/upsert mentions into MongoDB using dedup_key as the unique identity.
    Preserves all original fields from phase4_output.json without discarding or flattening.
    """
    inserted_count = 0
    updated_count = 0
    matched_count = 0

    now_iso = datetime.now(timezone.utc).isoformat()

    for item in mentions:
        doc = dict(item)  # Preserve complete structure programmatically
        doc["ingested_at"] = now_iso

        key = doc["dedup_key"]
        res = collection.replace_one({"dedup_key": key}, doc, upsert=True)

        if res.upserted_id is not None:
            inserted_count += 1
        elif res.modified_count > 0:
            updated_count += 1
        else:
            matched_count += 1

    return {
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "matched_count": matched_count,
        "total_processed": len(mentions)
    }

def run_phase5_pipeline(phase4_path: str = "phase4_output.json"):
    logger.info("Starting Phase 5 MongoDB Persistence Pipeline...")

    # 1. Connection check
    connected, db_version, server_info = check_connection()
    if not connected:
        logger.error(f"MongoDB connection failed: {db_version}")
        sys.exit(1)

    logger.info(f"Connected to MongoDB Server v{db_version} at database '{MONGODB_DATABASE}', collection '{MONGODB_COLLECTION}'.")

    # 2. Load and validate Phase 4 data
    if not os.path.exists(phase4_path):
        logger.error(f"File not found: {phase4_path}")
        sys.exit(1)

    with open(phase4_path, "r", encoding="utf-8") as f:
        phase4_data = json.load(f)

    mentions = phase4_data.get("mentions", [])
    logger.info(f"Loaded {len(mentions)} records from '{phase4_path}'.")

    valid, val_errors = validate_phase4_data(phase4_data)
    if not valid:
        logger.error(f"Phase 4 data validation failed with {len(val_errors)} errors:")
        for err in val_errors:
            logger.error(f"  - {err}")
        sys.exit(1)

    logger.info("Pre-ingestion schema validation PASSED 100%.")

    # 3. Collection setup & Index creation
    coll = get_mentions_collection()
    index_names = ensure_indexes(coll)
    logger.info(f"Successfully verified/created {len(index_names)} indexes on collection '{MONGODB_COLLECTION}'.")

    # 4. First Ingestion Run
    logger.info("\n--- Performing FIRST Ingestion Run ---")
    stats_run1 = ingest_records(coll, mentions)
    count_after_run1 = coll.count_documents({})

    logger.info(f"Run 1 Ingested: {stats_run1['inserted_count']} new, {stats_run1['updated_count']} updated, {stats_run1['matched_count']} unchanged.")
    logger.info(f"Collection Document Count after Run 1: {count_after_run1}")

    # 5. Second Ingestion Run (Idempotency Test)
    logger.info("\n--- Performing SECOND Ingestion Run (Idempotency Test) ---")
    stats_run2 = ingest_records(coll, mentions)
    count_after_run2 = coll.count_documents({})

    logger.info(f"Run 2 Ingested: {stats_run2['inserted_count']} new, {stats_run2['updated_count']} updated, {stats_run2['matched_count']} unchanged.")
    logger.info(f"Collection Document Count after Run 2: {count_after_run2}")

    idempotent_passed = (count_after_run1 == count_after_run2 == 77) and (stats_run2['inserted_count'] == 0)

    # 6. Post-Ingestion Database Audit
    logger.info("\n================ POST-INGESTION AUDIT & SUMMARY ================")
    print(f"1. MongoDB Server Status:           Connected (v{db_version})")
    print(f"2. Database Name:                   {MONGODB_DATABASE}")
    print(f"3. Collection Name:                 {MONGODB_COLLECTION}")
    print(f"4. Source Record Count:             {len(mentions)}")
    print(f"5. First Run Inserts / Upserts:     {stats_run1['inserted_count']} inserted, {stats_run1['updated_count']} updated")
    print(f"6. Collection Count (Run 1):        {count_after_run1}")
    print(f"7. Second Run Inserts / Upserts:    {stats_run2['inserted_count']} inserted, {stats_run2['updated_count']} updated/matched")
    print(f"8. Collection Count (Run 2):        {count_after_run2}")
    print(f"9. Idempotency Result:              {'PASSED 100%' if idempotent_passed else 'FAILED'}")
    print(f"10. Indexes Active ({len(index_names)}):")
    for idx_name in index_names:
        print(f"    - {idx_name}")

    # Unique identity check
    unique_dedup_keys = coll.distinct("dedup_key")
    unique_canonical_urls = coll.distinct("canonical_url")
    print(f"11. Distinct dedup_key count:      {len(unique_dedup_keys)}")
    print(f"12. Distinct canonical_url count:  {len(unique_canonical_urls)}")
    print(f"13. Provenance & Schema Integrity: PASSED")
    print("=================================================================")

    if not idempotent_passed:
        logger.error("CRITICAL: Idempotency test failed! Document count increased on second run.")
        sys.exit(1)

if __name__ == "__main__":
    run_phase5_pipeline()
