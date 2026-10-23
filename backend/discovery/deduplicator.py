"""
Deduplication for classified discovery results.

Two stages:
  1. Exact URL deduplication — merge results sharing a dedup_key.
  2. Near-duplicate snippet detection — flag (not delete) results
     whose snippets have normalised Jaccard similarity >= threshold.
"""

import logging
import re
from typing import Dict, List, Optional

from .models import ClassifiedResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Text tokenisation for Jaccard
# ---------------------------------------------------------------

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenise(text: str) -> set:
    """Lowercase word-character tokens from *text*."""
    return set(_WORD_RE.findall(text.lower())) if text else set()


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    Word-level Jaccard similarity between two texts.

    Returns 1.0 if both are empty, 0.0 if exactly one is empty.
    """
    a = _tokenise(text_a)
    b = _tokenise(text_b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------
# Exact URL deduplication (merge)
# ---------------------------------------------------------------

def deduplicate_urls(
    results: List[ClassifiedResult],
) -> List[ClassifiedResult]:
    """
    Merge results that share the same ``dedup_key``.

    Merge rules:
      - ``originating_queries``: union of all queries
      - ``searxng_engines``: union of all engines
      - ``discovered_at``: earliest timestamp
      - ``original_url``: from the first occurrence
      - ``title`` / ``snippet``: from the first occurrence
    """
    seen: Dict[str, ClassifiedResult] = {}
    order: List[str] = []  # preserve insertion order

    for r in results:
        key = r.dedup_key
        if key in seen:
            existing = seen[key]
            # Merge queries
            for q in r.originating_queries:
                if q not in existing.originating_queries:
                    existing.originating_queries.append(q)
            # Merge engines
            for e in r.searxng_engines:
                if e not in existing.searxng_engines:
                    existing.searxng_engines.append(e)
            # Keep earliest timestamp
            if r.discovered_at < existing.discovered_at:
                existing.discovered_at = r.discovered_at
        else:
            seen[key] = r
            order.append(key)

    merged = [seen[k] for k in order]
    dup_count = len(results) - len(merged)
    if dup_count:
        logger.info("Exact URL dedup: merged %d duplicates (%d → %d)",
                     dup_count, len(results), len(merged))
    return merged


# ---------------------------------------------------------------
# Near-duplicate snippet detection
# ---------------------------------------------------------------

def detect_near_duplicates(
    results: List[ClassifiedResult],
    threshold: float = 0.85,
) -> int:
    """
    Flag near-duplicate snippets in-place.

    For each result, compare against all earlier results.  If the
    highest similarity is ≥ *threshold*, set ``near_duplicate_of``
    to the canonical_url of the most-similar earlier result and
    ``near_duplicate_score`` to the similarity value.

    Neither result is deleted.

    Returns the number of results flagged as near-duplicates.
    """
    flagged = 0
    # Pre-tokenise for efficiency.
    token_cache: List[set] = []

    for i, current in enumerate(results):
        current_tokens = _tokenise(current.snippet)
        token_cache.append(current_tokens)

        if not current_tokens:
            continue

        best_score = 0.0
        best_url: Optional[str] = None

        for j in range(i):
            prev_tokens = token_cache[j]
            if not prev_tokens:
                continue

            # Inline Jaccard for speed (avoid function-call overhead).
            intersection = len(current_tokens & prev_tokens)
            union = len(current_tokens | prev_tokens)
            score = intersection / union if union else 0.0

            if score >= threshold and score > best_score:
                best_score = score
                best_url = results[j].canonical_url

        if best_url is not None:
            current.near_duplicate_of = best_url
            current.near_duplicate_score = round(best_score, 4)
            flagged += 1

    if flagged:
        logger.info("Near-duplicate detection: flagged %d results "
                     "(threshold=%.2f)", flagged, threshold)
    return flagged
