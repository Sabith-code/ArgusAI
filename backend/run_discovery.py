#!/usr/bin/env python3
"""
Brand discovery CLI — one-shot SearXNG scan with Phase 2 processing.

Usage examples:

  # Full pipeline (discover + classify/dedup):
  python run_discovery.py "Nike" --output results.json

  # Reprocess a saved Phase 1 output through Phase 2:
  python run_discovery.py "Nike" --from-file ../test_output.json -o processed.json

  # With brand config (official domains/accounts):
  python run_discovery.py "Nike" --brand-config nike_config.json -o results.json

  # Raw Phase 1 output only (skip Phase 2):
  python run_discovery.py "Nike" --raw -o raw.json

  # Inspect SearXNG engines:
  python run_discovery.py --inspect-engines

  # Custom near-dedup threshold:
  python run_discovery.py "Nike" --from-file raw.json --near-dedup-threshold 0.9
"""

import argparse
import json
import logging
import os
import sys

from dotenv import find_dotenv, load_dotenv

from discovery.models import BrandConfig, ClassifiedResult, DiscoveryResult, DiscoveryRun, ProcessedDiscoveryRun
from discovery.pipeline import process_discovery_run, process_extraction_run
from discovery.query_generator import generate_queries
from discovery.searxng_client import SearXNGClient, SearXNGError


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_searxng_url() -> str:
    url = os.getenv("SEARXNG_BASE_URL")
    if not url:
        print(
            "ERROR: SEARXNG_BASE_URL is not set.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Set SEARXNG_BASE_URL (default: http://localhost:8080)\n"
            "  3. Make sure SearXNG is running (docker compose up)\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return url


def load_brand_config(path: str) -> BrandConfig:
    """Load BrandConfig from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return BrandConfig.from_dict(data)


def load_discovery_run(path: str) -> DiscoveryRun:
    """Reconstruct a DiscoveryRun from a saved JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = [
        DiscoveryResult(
            title=r["title"],
            url=r["url"],
            domain=r["domain"],
            searxng_engines=r["searxng_engines"],
            snippet=r["snippet"],
            query=r["query"],
            discovered_at=r["discovered_at"],
        )
        for r in data.get("results", [])
    ]
    return DiscoveryRun(
        brand=data["brand"],
        started_at=data.get("started_at", ""),
        completed_at=data.get("completed_at"),
        queries_executed=data.get("queries_executed", []),
        results=results,
        errors=data.get("errors", []),
    )


def load_processed_run(path: str) -> ProcessedDiscoveryRun:
    """Reconstruct a ProcessedDiscoveryRun from a saved JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = [
        ClassifiedResult(
            title=r["title"],
            snippet=r["snippet"],
            canonical_url=r["canonical_url"],
            original_url=r["original_url"],
            dedup_key=r["dedup_key"],
            domain=r["domain"],
            source_type=r["source_type"],
            is_official=r["is_official"],
            originating_queries=r["originating_queries"],
            searxng_engines=r["searxng_engines"],
            discovered_at=r["discovered_at"],
            near_duplicate_of=r.get("near_duplicate_of"),
            near_duplicate_score=r.get("near_duplicate_score"),
        )
        for r in data.get("results", [])
    ]
    return ProcessedDiscoveryRun(
        brand=data["brand"],
        brand_config=BrandConfig.from_dict(data.get("brand_config", {"name": data["brand"]})),
        started_at=data.get("started_at", ""),
        completed_at=data.get("completed_at", ""),
        queries_executed=data.get("queries_executed", []),
        results=results,
        total_raw_results=data.get("total_raw_results", len(results)),
        total_classified_results=data.get("total_classified_results", len(results)),
        exact_duplicates_merged=data.get("exact_duplicates_merged", 0),
        near_duplicates_flagged=data.get("near_duplicates_flagged", 0),
        source_type_counts=data.get("source_type_counts", {}),
        official_count=data.get("official_count", 0),
    )


def cmd_inspect_engines(client: SearXNGClient) -> None:
    logger = logging.getLogger("discovery")
    logger.info("Fetching SearXNG engine configuration...")
    try:
        engines = client.get_enabled_engines()
    except SearXNGError as exc:
        logger.error("Could not fetch SearXNG config: %s", exc)
        sys.exit(1)

    if not engines:
        print("No engines found in SearXNG configuration.")
        return

    by_category: dict[str, list[str]] = {}
    for eng in engines:
        name = eng.get("name", "unknown")
        categories = eng.get("categories", ["uncategorised"])
        if isinstance(categories, str):
            categories = [categories]
        for cat in categories:
            by_category.setdefault(cat, []).append(name)

    print(f"\n{'='*60}")
    print(f"SearXNG Enabled Engines: {len(engines)} total")
    print(f"{'='*60}\n")
    for cat in sorted(by_category):
        names = sorted(by_category[cat])
        print(f"  [{cat}] ({len(names)} engines)")
        for name in names:
            print(f"    - {name}")
        print()


def cmd_discover(
    brand: str,
    output_path: str | None,
    raw_only: bool,
    phase2_only: bool,
    from_file: str | None,
    from_processed_file: str | None,
    brand_config_path: str | None,
    near_dedup_threshold: float,
    extract: bool,
) -> None:
    logger = logging.getLogger("discovery")

    # If loading directly from a processed Phase 2 file:
    if from_processed_file:
        logger.info("Loading saved Phase 2 processed run from: %s", from_processed_file)
        processed = load_processed_run(from_processed_file)
    else:
        # --- Phase 1: get raw results ---
        if from_file:
            logger.info("Loading saved discovery run from: %s", from_file)
            run = load_discovery_run(from_file)
            logger.info("Loaded %d results for brand %r", len(run.results), run.brand)
        else:
            searxng_url = get_searxng_url()
            client = SearXNGClient(base_url=searxng_url)

            queries = generate_queries(brand)
            logger.info("Generated %d queries for brand: %r", len(queries), brand)
            for q in queries:
                logger.info("  [%-16s] %s", q["category"], q["query"])

            run = client.discover(brand, queries)

        # --- Raw output? ---
        if raw_only:
            output_data = run.to_dict()
            _write_output(output_data, output_path, logger)
            logger.info("Raw output: %d results, %d errors",
                         len(run.results), len(run.errors))
            return

        # --- Phase 2: classify + dedup ---
        brand_config = None
        if brand_config_path:
            brand_config = load_brand_config(brand_config_path)
            logger.info("Loaded brand config: %s (%d official domains, %d accounts)",
                         brand_config.name,
                         len(brand_config.official_domains),
                         len(brand_config.official_accounts))

        processed = process_discovery_run(
            run,
            brand_config=brand_config,
            near_dedup_threshold=near_dedup_threshold,
        )

    if phase2_only or not extract:
        output_data = processed.to_dict()
        _write_output(output_data, output_path, logger)

        logger.info("=== Phase 2 Summary ===")
        logger.info("  Raw results:        %d", processed.total_raw_results)
        logger.info("  After dedup:        %d", processed.total_classified_results)
        logger.info("  Exact dupes merged: %d", processed.exact_duplicates_merged)
        logger.info("  Near-dupes flagged: %d", processed.near_duplicates_flagged)
        logger.info("  Official:           %d", processed.official_count)
        logger.info("  Source types:")
        for st, count in sorted(processed.source_type_counts.items()):
            logger.info("    %-16s %d", st, count)
        return

    # --- Phase 3: Extraction ---
    logger.info("=== Starting Phase 3 Extraction Pipeline ===")
    extracted_run = process_extraction_run(
        processed,
        checkpoint_path=output_path,
    )

    output_data = extracted_run.to_dict()
    _write_output(output_data, output_path, logger)


    logger.info("=== Phase 3 Extraction Summary ===")
    logger.info("  Total input:              %d", extracted_run.total_classified_input)
    logger.info("  Successful extractions:   %d", extracted_run.successful_extractions)
    logger.info("    Direct HTTP:            %d", extracted_run.direct_http_extractions)
    logger.info("    Playwright fallback:    %d", extracted_run.playwright_extractions)
    logger.info("  Failed extractions:       %d", extracted_run.failed_extractions)


def _write_output(data: dict, path: str | None, logger: logging.Logger) -> None:
    output_json = json.dumps(data, indent=2, ensure_ascii=False)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
            fh.write("\n")
        logger.info("Results written to: %s", path)
    else:
        print(output_json)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Brand Reputation Monitoring — discovery, classification, and extraction pipeline",
    )
    parser.add_argument("brand", nargs="?", default=None,
                        help="Brand name (e.g. 'Nike')")
    parser.add_argument("-o", "--output", default=None,
                        help="Write JSON results to this file")
    parser.add_argument("--raw", action="store_true",
                        help="Output raw Phase 1 results only (skip Phase 2 & 3)")
    parser.add_argument("--phase2-only", action="store_true",
                        help="Output Phase 2 classified results only (skip Phase 3 extraction)")
    parser.add_argument("--from-file", default=None,
                        help="Load a saved Phase 1 JSON instead of querying SearXNG")
    parser.add_argument("--from-processed-file", default=None,
                        help="Load a saved Phase 2 JSON directly for Phase 3 extraction")
    parser.add_argument("--brand-config", default=None,
                        help="Path to brand config JSON (official domains/accounts)")
    parser.add_argument("--near-dedup-threshold", type=float, default=0.85,
                        help="Jaccard threshold for snippet near-dedup (default: 0.85)")
    parser.add_argument("--extract", action="store_true", default=True,
                        help="Run Phase 3 content extraction pipeline (default: True)")
    parser.add_argument("--inspect-engines", action="store_true",
                        help="Print enabled SearXNG engines and exit")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()
    setup_logging(args.verbose)
    load_dotenv(find_dotenv(usecwd=True))

    if args.inspect_engines:
        client = SearXNGClient(base_url=get_searxng_url())
        cmd_inspect_engines(client)
        return

    if not args.brand and not args.from_processed_file:
        parser.error("brand name is required (unless using --from-processed-file or --inspect-engines)")

    cmd_discover(
        brand=args.brand or "",
        output_path=args.output,
        raw_only=args.raw,
        phase2_only=args.phase2_only,
        from_file=args.from_file,
        from_processed_file=args.from_processed_file,
        brand_config_path=args.brand_config,
        near_dedup_threshold=args.near_dedup_threshold,
        extract=not args.phase2_only and not args.raw,
    )


if __name__ == "__main__":
    main()



if __name__ == "__main__":
    main()
