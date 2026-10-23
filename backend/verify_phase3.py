"""Verify Phase 3 Extraction output quality and statistics."""
import json
import os
import sys

output_file = "../phase3_output.json"
if not os.path.exists(output_file):
    print(f"Output file {output_file} does not exist yet.")
    sys.exit(1)

data = json.load(open(output_file, "r", encoding="utf-8"))

lines = []
lines.append("=" * 75)
lines.append(f"PHASE 3 EXTRACTION DETAILED REPORT — Brand: {data.get('brand', 'Nike')}")
lines.append("=" * 75)
lines.append(f"Started At:               {data.get('started_at')}")
lines.append(f"Completed At:             {data.get('completed_at')}")
lines.append(f"Total Classified Input:   {data.get('total_classified_input')}")
lines.append(f"Successful Extractions:   {data.get('successful_extractions')}")
lines.append(f"  - Direct HTTP:          {data.get('direct_http_extractions')}")
lines.append(f"  - Playwright Fallback:  {data.get('playwright_extractions')}")
lines.append(f"Failed Extractions:       {data.get('failed_extractions')}")
lines.append("")

mentions = data.get("mentions", [])
successes = [m for m in mentions if m.get("extraction_status") == "success"]
failures = [m for m in mentions if m.get("extraction_status") == "failed"]

lines.append("--- Extraction Method Breakdown ---")
methods = {}
for m in mentions:
    meth = m.get("extraction_method", "unknown")
    methods[meth] = methods.get(meth, 0) + 1
for meth, count in sorted(methods.items()):
    lines.append(f"  {meth:<28} {count}")

lines.append("")
lines.append("--- Fallback Reasons for Failed Extractions ---")
fail_reasons = {}
for m in failures:
    err = m.get("error_message", "Unknown error")
    fail_reasons[err] = fail_reasons.get(err, 0) + 1
if fail_reasons:
    for err, count in sorted(fail_reasons.items()):
        lines.append(f"  [{count}x] {err}")
else:
    lines.append("  None")

lines.append("")
lines.append("--- Timeout Analysis ---")
timeouts = [m for m in mentions if "timeout" in (m.get("error_message") or "").lower()]
lines.append(f"Total Mentions hitting a timeout: {len(timeouts)}")
for t in timeouts:
    lines.append(f"  - {t.get('canonical_url')}: {t.get('error_message')}")

lines.append("")
lines.append("--- Sample Direct HTTP Success ---")
direct_samples = [m for m in mentions if m.get("extraction_method") == "direct_trafilatura"]
if direct_samples:
    s = direct_samples[0]
    lines.append(f"  URL:         {s.get('canonical_url')}")
    lines.append(f"  Author:      {s.get('author')}")
    lines.append(f"  Date:        {s.get('publication_date')}")
    lines.append(f"  Text Length: {len(s.get('text', ''))} chars, {len(s.get('text', '').split())} words")
    snippet = s.get('text', '').replace('\n', ' ')[:200]
    lines.append(f"  Text Snippet: {snippet}...")
else:
    lines.append("  None")

lines.append("")
lines.append("--- Sample Playwright Fallback Success ---")
pw_samples = [m for m in mentions if m.get("extraction_method") == "playwright_trafilatura"]
if pw_samples:
    s = pw_samples[0]
    lines.append(f"  URL:         {s.get('canonical_url')}")
    lines.append(f"  Author:      {s.get('author')}")
    lines.append(f"  Date:        {s.get('publication_date')}")
    lines.append(f"  Text Length: {len(s.get('text', ''))} chars, {len(s.get('text', '').split())} words")
    snippet = s.get('text', '').replace('\n', ' ')[:200]
    lines.append(f"  Text Snippet: {snippet}...")
else:
    lines.append("  None")

lines.append("")
lines.append("--- Schema Field Completeness (77 ExtractedMentions) ---")
fields = [
    "title", "snippet", "canonical_url", "original_url", "dedup_key",
    "domain", "source_type", "is_official", "originating_queries",
    "searxng_engines", "discovered_at", "text", "extraction_method",
    "extraction_status", "extracted_at"
]
for f in fields:
    present = sum(1 for m in mentions if m.get(f) not in (None, ""))
    lines.append(f"  {f:<22} {present}/{len(mentions)}")

report = "\n".join(lines)
with open("../phase3_report.txt", "w", encoding="utf-8") as f:
    f.write(report)
print(report)
