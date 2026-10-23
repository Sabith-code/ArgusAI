"""
Phase 2 & Phase 3 processing pipelines.

Phase 2:
  DiscoveryRun → URL normalisation → Exact URL dedup → Source classification → Snippet near-dedup → ProcessedDiscoveryRun

Phase 3:
  ProcessedDiscoveryRun → Cheapest-first content extraction (Direct HTTP → Trafilatura → Playwright → Trafilatura) → Checkpointing → ExtractedRun
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from .classifier import classify
from .deduplicator import deduplicate_urls, detect_near_duplicates
from .models import (
    BrandConfig,
    ClassifiedResult,
    DiscoveryResult,
    DiscoveryRun,
    ExtractedMention,
    ExtractedRun,
    ProcessedDiscoveryRun,
)
from .url_normalizer import canonicalize_url, extract_domain, make_dedup_key

logger = logging.getLogger(__name__)


def suppress_third_party_loggers() -> None:
    """Silence verbose third-party loggers so console progress remains clean."""
    noisy_loggers = [
        "trafilatura",
        "trafilatura.core",
        "trafilatura.metadata",
        "trafilatura.xml",
        "trafilatura.utils",
        "urllib3",
        "urllib3.connectionpool",
        "requests",
        "playwright",
        "asyncio",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)


def _to_classified(raw: DiscoveryResult) -> ClassifiedResult:
    """
    Convert a Phase 1 DiscoveryResult into an unclassified
    ClassifiedResult with normalised URL fields.
    """
    canonical = canonicalize_url(raw.url)
    return ClassifiedResult(
        title=raw.title,
        snippet=raw.snippet,
        canonical_url=canonical,
        original_url=raw.url,
        dedup_key=make_dedup_key(canonical),
        domain=extract_domain(raw.url),
        source_type="",         # filled by classify step
        is_official=False,      # filled by classify step
        originating_queries=[raw.query],
        searxng_engines=list(raw.searxng_engines),
        discovered_at=raw.discovered_at,
    )


def process_discovery_run(
    run: DiscoveryRun,
    brand_config: Optional[BrandConfig] = None,
    near_dedup_threshold: float = 0.85,
) -> ProcessedDiscoveryRun:
    """
    Run the full Phase 2 pipeline on a Phase 1 DiscoveryRun.

    Args:
        run: Phase 1 discovery output.
        brand_config: Optional per-brand official-source configuration.
                      If None, a default config (no official sources) is used.
        near_dedup_threshold: Jaccard similarity threshold for snippet
                              near-duplicate detection (default 0.85).

    Returns:
        A fully processed and classified ``ProcessedDiscoveryRun``.
    """
    if brand_config is None:
        brand_config = BrandConfig(name=run.brand)

    total_raw = len(run.results)
    logger.info("Phase 2 pipeline: processing %d raw results for %r",
                total_raw, run.brand)

    # --- Step 1: URL normalisation + initial conversion ---
    classified = [_to_classified(r) for r in run.results]
    logger.info("  URL normalisation: done")

    # --- Step 2: Exact URL deduplication ---
    classified = deduplicate_urls(classified)
    exact_dupes = total_raw - len(classified)
    logger.info("  Exact dedup: %d → %d (%d merged)",
                total_raw, len(classified), exact_dupes)

    # --- Step 3: Source classification ---
    for result in classified:
        source_type, is_official = classify(
            url=result.canonical_url,
            hostname=result.domain,
            brand_config=brand_config,
        )
        result.source_type = source_type.value
        result.is_official = is_official
    logger.info("  Source classification: done")

    # --- Step 4: Snippet near-duplicate detection ---
    near_dupes = detect_near_duplicates(classified, threshold=near_dedup_threshold)
    logger.info("  Near-dedup: %d flagged (threshold=%.2f)",
                near_dupes, near_dedup_threshold)

    # --- Compute statistics ---
    type_counts = dict(Counter(r.source_type for r in classified))
    official_count = sum(1 for r in classified if r.is_official)

    processed = ProcessedDiscoveryRun(
        brand=run.brand,
        brand_config=brand_config,
        started_at=run.started_at or "",
        completed_at=run.completed_at or "",
        queries_executed=run.queries_executed,
        results=classified,
        total_raw_results=total_raw,
        total_classified_results=len(classified),
        exact_duplicates_merged=exact_dupes,
        near_duplicates_flagged=near_dupes,
        source_type_counts=type_counts,
        official_count=official_count,
    )

    logger.info(
        "Phase 2 complete: %d results, %d exact dupes merged, "
        "%d near-dupes flagged, %d official",
        len(classified), exact_dupes, near_dupes, official_count,
    )
    return processed


# -------------------------------------------------------
# Phase 3: Extraction Pipeline
# -------------------------------------------------------

def _save_checkpoint(
    checkpoint_path: str,
    brand: str,
    brand_config: BrandConfig,
    started_at: str,
    queries_executed: list,
    mentions: list,
    total_input: int,
    direct_count: int,
    playwright_count: int,
    failed_count: int,
) -> None:
    """Save valid, complete ExtractedRun JSON checkpoint atomically."""
    run_obj = ExtractedRun(
        brand=brand,
        brand_config=brand_config,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc).isoformat(),
        queries_executed=queries_executed,
        mentions=mentions,
        total_classified_input=total_input,
        successful_extractions=direct_count + playwright_count,
        failed_extractions=failed_count,
        direct_http_extractions=direct_count,
        playwright_extractions=playwright_count,
    )
    tmp_file = f"{checkpoint_path}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(run_obj.to_dict(), f, indent=2, ensure_ascii=False)
    os.replace(tmp_file, checkpoint_path)


def process_extraction_run(
    processed_run: ProcessedDiscoveryRun,
    min_chars: Optional[int] = None,
    min_words: Optional[int] = None,
    http_timeout: Optional[int] = None,
    playwright_timeout: Optional[int] = None,
    checkpoint_path: Optional[str] = None,
) -> ExtractedRun:
    """
    Run the Phase 3 extraction chain on all ClassifiedResult items in a ProcessedDiscoveryRun.

    Features:
      - Suppresses noisy third-party loggers
      - Reuses a SINGLE Chromium browser instance across all URLs
      - Periodically checkpoints valid JSON after every URL to checkpoint_path
    """
    from playwright.sync_api import sync_playwright
    from .extractor import Extractor

    suppress_third_party_loggers()

    start_iso = datetime.now(timezone.utc).isoformat()
    extractor = Extractor(
        min_chars=min_chars,
        min_words=min_words,
        http_timeout=http_timeout,
        playwright_timeout=playwright_timeout,
    )

    items = processed_run.results
    total = len(items)
    logger.info("Phase 3 pipeline: starting extraction for %d mentions (%s)...", total, processed_run.brand)

    mentions = []
    direct_count = 0
    playwright_count = 0
    failed_count = 0

    if not checkpoint_path:
        checkpoint_path = f"checkpoint_{processed_run.brand.lower()}_phase3.json"

    with sync_playwright() as pw:
        # Launch SINGLE browser instance for the entire run
        browser = pw.chromium.launch(headless=True)
        try:
            for idx, item in enumerate(items, 1):
                mention = extractor.extract_mention(
                    item,
                    browser=browser,
                    item_index=idx,
                    total_items=total,
                )
                mentions.append(mention)

                if mention.extraction_status == "success":
                    if mention.extraction_method == "direct_trafilatura":
                        direct_count += 1
                    elif mention.extraction_method == "playwright_trafilatura":
                        playwright_count += 1
                else:
                    failed_count += 1

                # Incremental valid JSON checkpointing after every item
                _save_checkpoint(
                    checkpoint_path,
                    processed_run.brand,
                    processed_run.brand_config,
                    start_iso,
                    processed_run.queries_executed,
                    mentions,
                    total,
                    direct_count,
                    playwright_count,
                    failed_count,
                )

        finally:
            browser.close()

    end_iso = datetime.now(timezone.utc).isoformat()

    final_run = ExtractedRun(
        brand=processed_run.brand,
        brand_config=processed_run.brand_config,
        started_at=processed_run.started_at or start_iso,
        completed_at=end_iso,
        queries_executed=processed_run.queries_executed,
        mentions=mentions,
        total_classified_input=total,
        successful_extractions=direct_count + playwright_count,
        failed_extractions=failed_count,
        direct_http_extractions=direct_count,
        playwright_extractions=playwright_count,
    )

    logger.info("=== Phase 3 Summary ===")
    logger.info("  Total input:            %d", total)
    logger.info("  Successful extractions: %d", direct_count + playwright_count)
    logger.info("    Direct HTTP:          %d", direct_count)
    logger.info("    Playwright fallback:  %d", playwright_count)
    logger.info("  Failed extractions:     %d", failed_count)

    return final_run
