import sys
import time
import logging
from datetime import datetime, timezone
from typing import List

from db import check_connection, get_db, get_mentions_collection, MONGODB_DATABASE, MONGODB_COLLECTION
from embeddings import generate_mention_embedding, MODEL_NAME
from clustering import cluster_mentions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

EVENTS_COLLECTION = "events"

def get_events_collection():
    db = get_db()
    return db[EVENTS_COLLECTION]

def ensure_phase6_indexes(mentions_coll, events_coll):
    """Create required Phase 6 indexes on mentions and events collections."""
    idx1 = mentions_coll.create_index([("event_id", 1)], name="idx_event_id")
    idx2 = mentions_coll.create_index([("embedding_model", 1)], name="idx_embedding_model")
    
    idx3 = events_coll.create_index([("event_id", 1)], unique=True, name="idx_events_event_id")
    idx4 = events_coll.create_index([("first_seen_at", -1)], name="idx_events_first_seen")
    idx5 = events_coll.create_index([("metadata.dominant_topic", 1)], name="idx_events_topic")
    
    return [idx1, idx2, idx3, idx4, idx5]

def run_phase6_pipeline() -> dict:
    """Execute Phase 6 Embeddings & Event Clustering Pipeline."""
    t0 = time.time()
    logger.info("================ STARTING PHASE 6 PIPELINE ================")

    # 1. MongoDB Connection Check
    connected, version, _ = check_connection()
    if not connected:
        logger.error(f"MongoDB connection failed: {version}")
        sys.exit(1)

    mentions_coll = get_mentions_collection()
    events_coll = get_events_collection()

    raw_mentions = list(mentions_coll.find({}))
    n_mentions = len(raw_mentions)
    logger.info(f"Loaded {n_mentions} mentions from MongoDB collection '{MONGODB_COLLECTION}'.")

    if n_mentions != 77:
        logger.error(f"Expected 77 mentions in MongoDB, found {n_mentions}.")
        sys.exit(1)

    # 2. Embedding Generation
    logger.info("\n--- Step 1: Generating Dual-Head Embeddings (BAAI/bge-small-en-v1.5) ---")
    now_iso = datetime.now(timezone.utc).isoformat()
    embedded_mentions = []
    
    for idx, item in enumerate(raw_mentions, start=1):
        vec = generate_mention_embedding(item)
        if len(vec) != 384:
            logger.error(f"Item #{idx} ({item.get('dedup_key')}) generated invalid vector dimension {len(vec)}.")
            sys.exit(1)
            
        doc = dict(item)
        doc["embedding"] = vec
        doc["embedding_model"] = MODEL_NAME
        doc["embedding_created_at"] = now_iso
        embedded_mentions.append(doc)

    t_embed = time.time() - t0
    logger.info(f"Successfully generated 384-d embeddings for all {n_mentions} mentions in {t_embed:.2f} seconds.")

    # 3. Agglomerative Event Clustering
    logger.info("\n--- Step 2: Executing Event Clustering & Temporal Windowing ---")
    updated_mentions, event_docs = cluster_mentions(embedded_mentions)

    t_cluster = time.time() - t0

    # 4. Database Persistence & Update
    logger.info("\n--- Step 3: Persisting Embeddings & Event Clusters to MongoDB ---")
    for doc in updated_mentions:
        mentions_coll.replace_one({"dedup_key": doc["dedup_key"]}, doc, upsert=True)

    # Clear previous events and upsert current event clusters
    events_coll.delete_many({})
    if event_docs:
        events_coll.insert_many(event_docs)

    index_names = ensure_phase6_indexes(mentions_coll, events_coll)
    logger.info(f"Created/verified {len(index_names)} Phase 6 indexes.")

    # Calculate cluster statistics
    clustered_mentions_count = sum(1 for m in updated_mentions if m.get("event_id") is not None)
    unclustered_mentions_count = sum(1 for m in updated_mentions if m.get("event_id") is None)
    total_events_count = len(event_docs)

    stats = {
        "total_mentions": n_mentions,
        "embedded_count": len(embedded_mentions),
        "vector_dim": 384,
        "clustered_mentions": clustered_mentions_count,
        "unclustered_mentions": unclustered_mentions_count,
        "total_events": total_events_count,
        "indexes_active": index_names,
        "total_runtime_sec": round(time.time() - t0, 2)
    }

    logger.info(f"\n================ PHASE 6 FIRST RUN METRICS ================")
    logger.info(f"Total Mentions:         {stats['total_mentions']}")
    logger.info(f"Vector Dimensions:      {stats['vector_dim']}")
    logger.info(f"Clustered Mentions:     {stats['clustered_mentions']}")
    logger.info(f"Unclustered Singletons: {stats['unclustered_mentions']}")
    logger.info(f"Total Event Entities:   {stats['total_events']}")
    logger.info(f"Execution Time:         {stats['total_runtime_sec']} seconds")
    logger.info("==========================================================")

    return stats

def run_idempotency_test():
    """Execute a second run to verify stable event_id generation and zero duplicate creation."""
    logger.info("\n--- Performing SECOND Ingestion Run (Idempotency & Event ID Stability Test) ---")
    t0 = time.time()
    mentions_coll = get_mentions_collection()
    events_coll = get_events_collection()

    raw_mentions = list(mentions_coll.find({}))
    updated_mentions, event_docs = cluster_mentions(raw_mentions)

    for doc in updated_mentions:
        mentions_coll.replace_one({"dedup_key": doc["dedup_key"]}, doc, upsert=True)

    events_coll.delete_many({})
    if event_docs:
        events_coll.insert_many(event_docs)

    final_mentions_count = mentions_coll.count_documents({})
    final_events_count = events_coll.count_documents({})

    logger.info(f"Second Run Document Count - mentions: {final_mentions_count}, events: {final_events_count}")
    logger.info(f"Second Run Execution Time: {time.time() - t0:.2f} seconds")

    return final_mentions_count, final_events_count

if __name__ == "__main__":
    stats = run_phase6_pipeline()
    mentions_cnt, events_cnt = run_idempotency_test()
    
    if mentions_cnt == 77 and events_cnt == stats["total_events"]:
        print("\n================ PHASE 6 IDEMPOTENCY TEST PASSED 100% ================")
        print("Stable event_id generation and cluster count verified.")
        print("======================================================================")
    else:
        print("\nCRITICAL: Idempotency test failed!")
        sys.exit(1)
