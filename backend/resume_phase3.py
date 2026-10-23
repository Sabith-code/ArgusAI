import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

from discovery.models import ClassifiedResult, ExtractedMention, ExtractedRun, BrandConfig
from discovery.extractor import Extractor
from discovery.pipeline import suppress_third_party_loggers, _save_checkpoint

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def dict_to_extracted_mention(d: dict) -> ExtractedMention:
    return ExtractedMention(
        text=d.get("text", ""),
        extraction_method=d.get("extraction_method", ""),
        extraction_status=d.get("extraction_status", ""),
        extracted_at=d.get("extracted_at", ""),
        error_message=d.get("error_message"),
        publication_date=d.get("publication_date"),
        author=d.get("author"),
        title=d.get("title", ""),
        snippet=d.get("snippet", ""),
        canonical_url=d.get("canonical_url", ""),
        original_url=d.get("original_url", ""),
        dedup_key=d.get("dedup_key", ""),
        domain=d.get("domain", ""),
        source_type=d.get("source_type", ""),
        is_official=d.get("is_official", False),
        originating_queries=d.get("originating_queries", []),
        searxng_engines=d.get("searxng_engines", []),
        discovered_at=d.get("discovered_at", ""),
        near_duplicate_of=d.get("near_duplicate_of"),
        near_duplicate_score=d.get("near_duplicate_score"),
    )

def main():
    p2_path = "phase2_output.json"
    p3_path = "phase3_output.json"

    if not os.path.exists(p2_path):
        print(f"Error: {p2_path} not found.")
        sys.exit(1)

    # 1. Load Phase 2 data
    with open(p2_path, "r", encoding="utf-8") as f:
        p2_data = json.load(f)

    p2_results = p2_data.get("results", [])
    total_p2 = len(p2_results)

    print(f"Loaded {total_p2} Phase 2 records from {p2_path}.")

    # 2. Load existing Phase 3 records if present
    existing_mentions = []
    existing_urls = set()
    started_at = p2_data.get("started_at") or datetime.now(timezone.utc).isoformat()
    brand_name = p2_data.get("brand", "Nike")
    brand_cfg_dict = p2_data.get("brand_config", {})
    brand_config = BrandConfig(
        name=brand_cfg_dict.get("name", brand_name),
        official_domains=brand_cfg_dict.get("official_domains", []),
        official_accounts=brand_cfg_dict.get("official_accounts", [])
    )
    queries_executed = p2_data.get("queries_executed", [])

    if os.path.exists(p3_path):
        with open(p3_path, "r", encoding="utf-8") as f:
            p3_data = json.load(f)
        raw_mentions = p3_data.get("mentions", [])
        if p3_data.get("started_at"):
            started_at = p3_data.get("started_at")
        for m in raw_mentions:
            existing_urls.add(m.get("canonical_url"))
            existing_mentions.append(dict_to_extracted_mention(m))

    starting_count = len(existing_mentions)
    print(f"Starting Phase 3 mentions in {p3_path}: {starting_count}")

    # 3. Identify missing Phase 2 records
    missing_items = []
    for item_dict in p2_results:
        can_url = item_dict.get("canonical_url")
        if can_url not in existing_urls:
            missing_items.append(item_dict)

    missing_count = len(missing_items)
    print(f"Missing Phase 2 records identified: {missing_count}")

    newly_processed = 0
    newly_successful = 0
    newly_failed = 0

    if missing_count == 0:
        print("No missing records to process. All 77 records already present in Phase 3.")
    else:
        # Initialize Extractor & suppress verbose logs
        suppress_third_party_loggers()
        extractor = Extractor()

        # Count current stats
        direct_count = sum(1 for m in existing_mentions if m.extraction_method == "direct_trafilatura")
        playwright_count = sum(1 for m in existing_mentions if m.extraction_method == "playwright_trafilatura")
        failed_count = sum(1 for m in existing_mentions if m.extraction_status == "failed")

        start_time = time.time()

        print(f"\nResuming extraction for {missing_count} missing records using Playwright browser reuse...")
        
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for idx, item_dict in enumerate(missing_items, start=starting_count + 1):
                    # Construct ClassifiedResult dataclass
                    classified_obj = ClassifiedResult(
                        title=item_dict.get("title", ""),
                        snippet=item_dict.get("snippet", ""),
                        canonical_url=item_dict.get("canonical_url", ""),
                        original_url=item_dict.get("original_url", ""),
                        dedup_key=item_dict.get("dedup_key", ""),
                        domain=item_dict.get("domain", ""),
                        source_type=item_dict.get("source_type", ""),
                        is_official=item_dict.get("is_official", False),
                        originating_queries=item_dict.get("originating_queries", []),
                        searxng_engines=item_dict.get("searxng_engines", []),
                        discovered_at=item_dict.get("discovered_at", ""),
                        near_duplicate_of=item_dict.get("near_duplicate_of"),
                        near_duplicate_score=item_dict.get("near_duplicate_score")
                    )

                    mention_obj = extractor.extract_mention(
                        classified_obj,
                        browser=browser,
                        item_index=idx,
                        total_items=total_p2
                    )

                    existing_mentions.append(mention_obj)
                    newly_processed += 1

                    if mention_obj.extraction_status == "success":
                        newly_successful += 1
                        if mention_obj.extraction_method == "direct_trafilatura":
                            direct_count += 1
                        elif mention_obj.extraction_method == "playwright_trafilatura":
                            playwright_count += 1
                    else:
                        newly_failed += 1
                        failed_count += 1

                    # Atomic checkpoint update after each item
                    _save_checkpoint(
                        checkpoint_path=p3_path,
                        brand=brand_name,
                        brand_config=brand_config,
                        started_at=started_at,
                        queries_executed=queries_executed,
                        mentions=existing_mentions,
                        total_input=total_p2,
                        direct_count=direct_count,
                        playwright_count=playwright_count,
                        failed_count=failed_count
                    )
            finally:
                browser.close()

        total_runtime = time.time() - start_time
        print(f"\nCompleted extraction of missing {newly_processed} records in {total_runtime:.2f}s.")

    # 4. Final Validation & Summary Report
    print("\n================ Performing Final Phase 3 Integrity Validation ================")
    with open(p3_path, "r", encoding="utf-8") as f:
        final_p3 = json.load(f)

    final_mentions = final_p3.get("mentions", [])
    val_passed = True
    val_errors = []

    if len(final_mentions) != 77:
        val_errors.append(f"Expected 77 records in phase3_output.json, got {len(final_mentions)}")
        val_passed = False

    p2_canonical_urls = [r.get("canonical_url") for r in p2_results]
    p3_canonical_urls = [m.get("canonical_url") for m in final_mentions]

    if set(p2_canonical_urls) != set(p3_canonical_urls):
        val_errors.append("1:1 Canonical URL mismatch between Phase 2 and Phase 3!")
        val_passed = False

    if len(p3_canonical_urls) != len(set(p3_canonical_urls)):
        val_errors.append("Duplicate canonical URLs found in Phase 3 output!")
        val_passed = False

    total_success = sum(1 for m in final_mentions if m.get("extraction_status") == "success")
    total_failed = sum(1 for m in final_mentions if m.get("extraction_status") == "failed")
    direct_total = sum(1 for m in final_mentions if m.get("extraction_method") == "direct_trafilatura")
    pw_total = sum(1 for m in final_mentions if m.get("extraction_method") == "playwright_trafilatura")

    failures_list = []
    for m in final_mentions:
        if m.get("extraction_status") == "failed":
            failures_list.append({
                "url": m.get("canonical_url"),
                "error": m.get("error_message")
            })

        # Field completeness checks
        for fld in ["title", "snippet", "canonical_url", "extraction_status"]:
            if not m.get(fld):
                val_errors.append(f"Record {m.get('canonical_url')} missing field {fld}")
                val_passed = False

        if m.get("extraction_status") == "success" and not m.get("text"):
            val_errors.append(f"Record {m.get('canonical_url')} has extraction_status='success' but empty text")
            val_passed = False

        if m.get("extraction_status") == "failed" and m.get("text") != "":
            val_errors.append(f"Record {m.get('canonical_url')} has extraction_status='failed' but non-empty text")
            val_passed = False

    print(f"\n1. Starting Phase 3 records:         {starting_count}")
    print(f"2. Missing records identified:       {missing_count}")
    print(f"3. Newly processed count:            {newly_processed}")
    print(f"4. Newly successful extractions:     {newly_successful}")
    print(f"5. Newly failed extractions:         {newly_failed}")
    print(f"6. Final phase3_output.json count:   {len(final_mentions)}")
    print(f"7. Total Phase 3 success rate:       {total_success}/77 ({total_success/77*100:.1f}%)")
    print(f"   - Direct HTTP Extractions:       {direct_total}")
    print(f"   - Playwright Fallback:           {pw_total}")
    print(f"   - Total Failed Extractions:      {total_failed}")
    print(f"8. Output File Path:                 {os.path.abspath(p3_path)}")
    print(f"9. Validation Result:                {'PASSED 100%' if val_passed else 'FAILED'}")

    if val_errors:
        print(f"\nValidation Errors ({len(val_errors)}):")
        for err in val_errors:
            print(f"  - {err}")

    if failures_list:
        print(f"\n--- Detailed Failure Log ({len(failures_list)} records) ---")
        for idx, f_item in enumerate(failures_list, start=1):
            print(f"  [{idx}] {f_item['url']}\n      Error: {f_item['error']}")

if __name__ == "__main__":
    main()
