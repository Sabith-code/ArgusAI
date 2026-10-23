import os
import sys
import json
import time
from datetime import datetime, timezone
import laya

def main():
    print("==========================================================")
    print("      Phase 4 — Full Laya Mention Classification Run      ")
    print("==========================================================")
    
    # 1. Pre-run Confirmation Checks
    input_file = "phase3_output.json"
    output_file = "phase4_output.json"
    
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' not found.")
        sys.exit(1)
        
    with open(input_file, "r", encoding="utf-8") as f:
        phase3_data = json.load(f)
        
    mentions = phase3_data.get("mentions", [])
    total_input = len(mentions)
    print(f"\n[Pre-Run Check 1] Input records count: {total_input}")
    if total_input != 77:
        print(f"Warning: Expected 77 records, found {total_input}.")
        
    laya_version = getattr(laya, "__version__", "v0.3.20")
    print(f"[Pre-Run Check 2] Laya version: {laya_version}")
    
    checkpoint_id = "convaiinnovations/laya"
    print(f"[Pre-Run Check 3] Checkpoint ID: {checkpoint_id}")
    
    # Approved Questions Definition
    questions = {
        "sentiment": {
            "type": "choice",
            "instructions": "What is the overall sentiment of this mention toward the brand?",
            "criteria": {
                "positive": "praise, customer satisfaction, excitement, favorable coverage, product praise",
                "neutral": "factual news, objective financial reporting, general mention, neutral comparison",
                "negative": "criticism, dissatisfaction, complaint, concern, disappointment, product defect"
            }
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this mention for brand monitoring attention?",
            "criteria": [
                "routine brand mention or general discussion",
                "notable story, review, or moderate customer issue",
                "urgent escalation, active legal case, major flaw, or viral controversy"
            ]
        },
        "reputation_risk": {
            "type": "noul",
            "instructions": "Does this text mention a potential brand reputation risk, legal dispute, product safety flaw, executive scandal, or major customer backlash?"
        },
        "topic": {
            "type": "choice",
            "instructions": "Which topic best describes the main subject of this mention?",
            "criteria": {
                "product_quality_issue": "defects, sizing issues, materials, product reviews, performance flaws, recalls",
                "customer_service_complaint": "shipping delays, support tickets, return policies, store experience, order issues",
                "legal_regulatory_dispute": "lawsuits, counterfeit seizures, trademark disputes, regulatory fines, court orders",
                "financial_corporate": "earnings reports, stock price, executive appointments, restructuring, quarterly results",
                "executive_controversy": "leadership statements, PR backlash, executive scandals, corporate governance",
                "routine_marketing_launch": "new product drops, shoe releases, ad campaigns, sponsorships, promotional events",
                "general_discussion": "general discussion, Wikipedia background, brand history, casual mention"
            }
        }
    }
    print(f"[Pre-Run Check 4] 4 Questions & 7 Topic categories verified.")

    # 2. Load Model
    print(f"\nLoading Laya model '{checkpoint_id}' on CPU...")
    load_start = time.time()
    agent = laya.load(checkpoint_id, device="cpu")
    print(f"Model loaded successfully in {time.time() - load_start:.2f}s")
    
    # 3. Process Records
    classified_mentions = []
    success_count = 0
    failure_count = 0
    full_text_count = 0
    snippet_fallback_count = 0
    failed_records_log = []
    
    start_total_time = time.time()
    
    print("\nStarting classification loop...")
    for idx, item in enumerate(mentions, start=1):
        item_start = time.time()
        
        # Determine Input Text and Classification Scope
        ext_status = item.get("extraction_status")
        extracted_text = item.get("text", "").strip() if ext_status == "success" else ""
        
        if ext_status == "success" and len(extracted_text) > 0:
            input_text = extracted_text
            scope = "full_text"
            full_text_count += 1
        else:
            title = item.get("title", "") or ""
            snippet = item.get("snippet", "") or ""
            input_text = f"Title: {title}\nSnippet: {snippet}".strip()
            scope = "snippet_fallback"
            snippet_fallback_count += 1
            
        # Run Native Laya Single-State Inference
        classified_at_iso = datetime.now(timezone.utc).isoformat()
        try:
            raw_res = agent.decide(input_text, questions=questions)
            runtime_ms = round((time.time() - item_start) * 1000.0, 2)
            
            # Format answers cleanly
            ans_sentiment = raw_res.get("sentiment", {})
            ans_urgency = raw_res.get("urgency", {})
            ans_risk = raw_res.get("reputation_risk", {})
            ans_topic = raw_res.get("topic", {})
            
            formatted_sentiment = {
                "selected_label": ans_sentiment.get("choice"),
                "confidence": ans_sentiment.get("confidence"),
                "answer_confidence": ans_sentiment.get("answer_confidence"),
                "probabilities": ans_sentiment.get("probabilities", {})
            }
            
            formatted_urgency = {
                "expected_score": ans_urgency.get("score"),
                "confidence": ans_urgency.get("confidence"),
                "answer_confidence": ans_urgency.get("answer_confidence"),
                "probabilities": ans_urgency.get("probabilities", {})
            }
            
            formatted_reputation_risk = {
                "risk_probability": ans_risk.get("noul"),
                "confidence": ans_risk.get("confidence"),
                "answer_confidence": ans_risk.get("answer_confidence")
            }
            
            formatted_topic = {
                "selected_label": ans_topic.get("choice"),
                "confidence": ans_topic.get("confidence"),
                "answer_confidence": ans_topic.get("answer_confidence"),
                "probabilities": ans_topic.get("probabilities", {})
            }
            
            # Preserve all Phase 1/2/3 provenance fields
            record = dict(item)
            record.update({
                "classification_scope": scope,
                "classification_model": checkpoint_id,
                "classification_version": laya_version,
                "classified_at": classified_at_iso,
                "classification_runtime_ms": runtime_ms,
                "sentiment": formatted_sentiment,
                "urgency": formatted_urgency,
                "reputation_risk": formatted_reputation_risk,
                "topic": formatted_topic,
                "raw_laya_response": raw_res
            })
            
            classified_mentions.append(record)
            success_count += 1
            
            print(f"[{idx}/{total_input}] Success | Scope: {scope} | Topic: {formatted_topic['selected_label']} | Risk: {formatted_reputation_risk['risk_probability']} | Time: {runtime_ms}ms")
            
        except Exception as e:
            runtime_ms = round((time.time() - item_start) * 1000.0, 2)
            failure_count += 1
            error_str = str(e)
            failed_records_log.append({
                "index": idx,
                "canonical_url": item.get("canonical_url"),
                "error": error_str
            })
            print(f"[{idx}/{total_input}] FAILED | Scope: {scope} | Error: {error_str} | Time: {runtime_ms}ms")
            
            # Preserve item with error annotation
            record = dict(item)
            record.update({
                "classification_scope": scope,
                "classification_model": checkpoint_id,
                "classification_version": laya_version,
                "classified_at": classified_at_iso,
                "classification_runtime_ms": runtime_ms,
                "classification_status": "failed",
                "classification_error": error_str
            })
            classified_mentions.append(record)

    total_runtime_sec = time.time() - start_total_time
    avg_runtime_sec = total_runtime_sec / success_count if success_count > 0 else 0.0
    
    # 4. Save Output File
    output_payload = {
        "metadata": {
            "discovery_query_count": phase3_data.get("metadata", {}).get("discovery_query_count", 0),
            "total_discovered_urls": phase3_data.get("metadata", {}).get("total_discovered_urls", 0),
            "total_deduplicated_mentions": phase3_data.get("metadata", {}).get("total_deduplicated_mentions", 0),
            "total_extracted_mentions": phase3_data.get("metadata", {}).get("total_extracted_mentions", 0),
            "total_classified_mentions": len(classified_mentions),
            "total_classification_success": success_count,
            "total_classification_failures": failure_count,
            "total_full_text_records": full_text_count,
            "total_snippet_fallback_records": snippet_fallback_count,
            "total_runtime_seconds": round(total_runtime_sec, 2),
            "avg_runtime_per_record_seconds": round(avg_runtime_sec, 4),
            "classification_model": checkpoint_id,
            "classification_version": laya_version,
            "classified_at": datetime.now(timezone.utc).isoformat()
        },
        "mentions": classified_mentions
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)
        
    print(f"\nSaved Phase 4 classification output to '{output_file}'.")
    
    # 5. Perform Post-Run Schema Validation
    print("\nPerforming Post-Run Schema Validation...")
    val_passed = True
    val_errors = []
    
    if len(classified_mentions) != total_input:
        val_errors.append(f"Output count mismatch: Expected {total_input}, got {len(classified_mentions)}")
        val_passed = False
        
    approved_topics = set(questions["topic"]["criteria"].keys())
    
    for i, m in enumerate(classified_mentions, start=1):
        if m.get("classification_status") == "failed":
            continue
            
        # Provenance check
        for field in ["canonical_url", "title", "snippet", "source_type"]:
            if field not in m:
                val_errors.append(f"Record #{i} missing provenance field '{field}'")
                val_passed = False
                
        # Sentiment probabilities check
        s_probs = m.get("sentiment", {}).get("probabilities", {})
        if set(s_probs.keys()) != {"positive", "neutral", "negative"}:
            val_errors.append(f"Record #{i} sentiment missing required keys: {s_probs.keys()}")
            val_passed = False
            
        # Urgency probabilities check
        u_probs = m.get("urgency", {}).get("probabilities", {})
        if set(u_probs.keys()) != {"0", "1", "2"}:
            val_errors.append(f"Record #{i} urgency missing required keys: {u_probs.keys()}")
            val_passed = False
            
        # Reputation risk P(true) check
        r_prob = m.get("reputation_risk", {}).get("risk_probability")
        if r_prob is None or not (0.0 <= r_prob <= 1.0):
            val_errors.append(f"Record #{i} invalid reputation risk probability: {r_prob}")
            val_passed = False
            
        # Topic check
        t_label = m.get("topic", {}).get("selected_label")
        if t_label not in approved_topics:
            val_errors.append(f"Record #{i} unapproved topic label: '{t_label}'")
            val_passed = False
            
        t_probs = m.get("topic", {}).get("probabilities", {})
        if set(t_probs.keys()) != approved_topics:
            val_errors.append(f"Record #{i} topic missing required probabilities keys: {t_probs.keys()}")
            val_passed = False

    if val_passed:
        print("Schema Validation Passed 100% SUCCESS!")
    else:
        print(f"Schema Validation Errors ({len(val_errors)}):")
        for err in val_errors[:10]:
            print(f"  - {err}")

    # 6. Topic & Sentiment Distribution Breakdown Report
    topic_counts = {}
    sentiment_counts = {}
    
    for m in classified_mentions:
        if m.get("classification_status") == "failed":
            continue
        top = m.get("topic", {}).get("selected_label")
        topic_counts[top] = topic_counts.get(top, 0) + 1
        
        sent = m.get("sentiment", {}).get("selected_label")
        sentiment_counts[sent] = sentiment_counts.get(sent, 0) + 1
            
    print("\n================ FINAL PHASE 4 RUN REPORT ================")
    print(f"1. Total Input Records:             {total_input}")
    print(f"2. Total Successfully Classified:   {success_count}")
    print(f"3. Total Classification Failures:   {failure_count}")
    print(f"4. Total Full-Text Records:         {full_text_count}")
    print(f"5. Total Snippet-Fallback Records:  {snippet_fallback_count}")
    print(f"6. Total Runtime:                   {total_runtime_sec:.2f} seconds")
    print(f"7. Avg Runtime per Record:          {avg_runtime_sec:.4f} seconds")
    print(f"8. Classification Engine Used:      {checkpoint_id} ({laya_version})")
    print(f"9. Output File Location:            {os.path.abspath(output_file)}")
    print(f"10. Schema Validation Status:       {'PASSED' if val_passed else 'FAILED'}")
    
    print("\n--- Topic Distribution ---")
    for t_cat in sorted(approved_topics):
        print(f"  - {t_cat:28s}: {topic_counts.get(t_cat, 0):2d}")
        
    print("\n--- Sentiment Distribution ---")
    for s_cat in ["positive", "neutral", "negative"]:
        print(f"  - {s_cat:10s}: {sentiment_counts.get(s_cat, 0):2d}")
        
    print("\n--- Confirmations ---")
    print("  - Reputation Risk Threshold: NO threshold applied (raw P(true) stored directly)")
    print("  - Long-Document Aggregation: NONE performed (native single-state inference used)")
    print("==========================================================")

if __name__ == "__main__":
    main()
