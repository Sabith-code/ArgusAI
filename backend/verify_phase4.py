import json
import os
import sys

def main():
    p3_file = "phase3_output.json"
    p4_file = "phase4_output.json"

    if not os.path.exists(p4_file):
        print(f"Error: '{p4_file}' not found.")
        sys.exit(1)

    with open(p3_file, "r", encoding="utf-8") as f:
        p3_data = json.load(f)
    with open(p4_file, "r", encoding="utf-8") as f:
        p4_data = json.load(f)

    p3_mentions = p3_data.get("mentions", [])
    p4_mentions = p4_data.get("mentions", [])

    print("================ Phase 4 Verification & Schema Audit ================")
    print(f"Total Input Phase 3 Records:           {len(p3_mentions)}")
    print(f"Total Phase 4 Classified Output Count: {len(p4_mentions)}")

    val_passed = True
    val_errors = []

    # 1. Record Count & 1:1 Matching
    if len(p4_mentions) != 77:
        val_errors.append(f"Expected 77 Phase 4 records, got {len(p4_mentions)}")
        val_passed = False

    p3_urls = [m.get("canonical_url") for m in p3_mentions]
    p4_urls = [m.get("canonical_url") for m in p4_mentions]

    if p3_urls != p4_urls:
        val_errors.append("1:1 Canonical URL sequence mismatch between Phase 3 and Phase 4!")
        val_passed = False

    if len(p4_urls) != len(set(p4_urls)):
        val_errors.append("Duplicate canonical URLs detected in Phase 4 output!")
        val_passed = False

    # 2. Scope & Classification Field Checks
    full_text_count = 0
    fallback_count = 0
    approved_topics = {
        "product_quality_issue",
        "customer_service_complaint",
        "legal_regulatory_dispute",
        "financial_corporate",
        "executive_controversy",
        "routine_marketing_launch",
        "general_discussion"
    }

    for idx, m in enumerate(p4_mentions, start=1):
        scope = m.get("classification_scope")
        if scope == "full_text":
            full_text_count += 1
        elif scope == "snippet_fallback":
            fallback_count += 1
        else:
            val_errors.append(f"Record #{idx} invalid classification_scope: {scope}")
            val_passed = False

        # Provenance Check
        for fld in ["canonical_url", "title", "snippet", "source_type", "domain", "dedup_key"]:
            if not m.get(fld):
                val_errors.append(f"Record #{idx} missing provenance field '{fld}'")
                val_passed = False

        # Four Question Outputs Check
        for q in ["sentiment", "urgency", "reputation_risk", "topic"]:
            if q not in m:
                val_errors.append(f"Record #{idx} missing question output '{q}'")
                val_passed = False

        # Sentiment Check
        s_probs = m.get("sentiment", {}).get("probabilities", {})
        if set(s_probs.keys()) != {"positive", "neutral", "negative"}:
            val_errors.append(f"Record #{idx} invalid sentiment probabilities keys: {set(s_probs.keys())}")
            val_passed = False

        # Urgency Check
        u_probs = m.get("urgency", {}).get("probabilities", {})
        if set(u_probs.keys()) != {"0", "1", "2"}:
            val_errors.append(f"Record #{idx} invalid urgency probabilities keys: {set(u_probs.keys())}")
            val_passed = False

        # Reputation Risk Check (raw P(true) stored, no risk thresholds applied)
        r_prob = m.get("reputation_risk", {}).get("risk_probability")
        if r_prob is None or not (0.0 <= r_prob <= 1.0):
            val_errors.append(f"Record #{idx} invalid reputation_risk risk_probability: {r_prob}")
            val_passed = False

        # Verify no thresholding field was created
        if "high_risk" in m.get("reputation_risk", {}) or "risk_label" in m.get("reputation_risk", {}):
            val_errors.append(f"Record #{idx} unapproved risk threshold field found in reputation_risk!")
            val_passed = False

        # Topic Check
        t_label = m.get("topic", {}).get("selected_label")
        if t_label not in approved_topics:
            val_errors.append(f"Record #{idx} unapproved topic label: '{t_label}'")
            val_passed = False

        t_probs = m.get("topic", {}).get("probabilities", {})
        if set(t_probs.keys()) != approved_topics:
            val_errors.append(f"Record #{idx} invalid topic probabilities keys: {set(t_probs.keys())}")
            val_passed = False

        # Raw Laya Response Check
        if not m.get("raw_laya_response"):
            val_errors.append(f"Record #{idx} missing raw_laya_response field")
            val_passed = False

    print(f"\n- Full-Text Classified Records:       {full_text_count}")
    print(f"- Snippet-Fallback Records:          {fallback_count}")
    print(f"- Schema & Data Integrity Validation: {'PASSED 100%' if val_passed else 'FAILED'}")

    if val_errors:
        print(f"\nValidation Errors ({len(val_errors)}):")
        for err in val_errors:
            print(f"  - {err}")

if __name__ == "__main__":
    main()
