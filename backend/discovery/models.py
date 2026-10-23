"""
Data models for the discovery layer.

These are plain dataclasses — no ORM, no database dependency.
Phase 5 (MongoDB) will define persistence schemas separately.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


@dataclass
class DiscoveryResult:
    """A single search result returned by SearXNG discovery."""

    title: str
    url: str
    domain: str
    searxng_engines: List[str]
    snippet: str
    query: str
    discovered_at: str  # ISO-8601 UTC timestamp

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "searxng_engines": self.searxng_engines,
            "snippet": self.snippet,
            "query": self.query,
            "discovered_at": self.discovered_at,
        }


@dataclass
class DiscoveryRun:
    """Aggregated results from a complete one-shot discovery run for one brand."""

    brand: str
    started_at: str   # ISO-8601 UTC
    completed_at: Optional[str]  # ISO-8601 UTC, None while running
    queries_executed: List[str]
    results: List[DiscoveryResult] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "queries_executed": self.queries_executed,
            "total_results": len(self.results),
            "total_errors": len(self.errors),
            "results": [r.to_dict() for r in self.results],
            "errors": self.errors,
        }


# -------------------------------------------------------
# Phase 2: Source classification & deduplication
# -------------------------------------------------------


class SourceType(str, Enum):
    """
    Where/how the content is published.

    Separate from ``is_official`` which indicates whether the specific
    publisher/account belongs to the monitored brand.
    """

    NEWS = "news"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    BLOG = "blog"
    FORUM = "forum"
    REVIEW = "review"
    OFFICIAL = "official"  # Brand-owned web property/domain
    SOCIAL_MEDIA = "social_media"
    ECOMMERCE = "ecommerce"
    OTHER = "other"


@dataclass
class BrandConfig:
    """
    Per-brand configuration including explicitly verified official sources.

    official_domains:
        Domains owned by the brand.  Uses label-boundary hostname
        matching: configuring ``"nike.com"`` matches ``nike.com``,
        ``www.nike.com``, ``about.nike.com`` — but NOT ``nikeshoes.com``
        or ``nike.com.evil.com``.

    official_accounts:
        Specific account/page URL prefixes on third-party platforms.
        URL-prefix matching after normalisation (scheme-stripped,
        www-stripped, hostname lowercased, path case preserved).
        Example: ``"youtube.com/@Nike"`` matches
        ``youtube.com/@Nike/videos`` but NOT ``youtube.com/@NikeBasketball``.
    """

    name: str
    official_domains: List[str] = field(default_factory=list)
    official_accounts: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "BrandConfig":
        return cls(
            name=data["name"],
            official_domains=data.get("official_domains", []),
            official_accounts=data.get("official_accounts", []),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "official_domains": self.official_domains,
            "official_accounts": self.official_accounts,
        }


@dataclass
class ClassifiedResult:
    """
    A single discovery result after source classification,
    URL deduplication, and near-duplicate snippet detection.
    """

    # Content
    title: str
    snippet: str

    # URLs
    canonical_url: str    # Normalised, valid URL (with scheme)
    original_url: str     # First raw URL encountered
    dedup_key: str        # Scheme-agnostic key for dedup comparison

    # Source classification
    domain: str           # Content hostname (lowercased)
    source_type: str      # SourceType value
    is_official: bool     # True only if explicitly configured

    # Provenance
    originating_queries: List[str]   # All queries that found this URL
    searxng_engines: List[str]       # Union of engines across all hits
    discovered_at: str               # Earliest discovery timestamp (ISO-8601)

    # Near-duplicate detection
    near_duplicate_of: Optional[str] = None      # canonical_url of primary
    near_duplicate_score: Optional[float] = None  # Jaccard similarity

    def to_dict(self) -> dict:
        d: dict = {
            "title": self.title,
            "snippet": self.snippet,
            "canonical_url": self.canonical_url,
            "original_url": self.original_url,
            "dedup_key": self.dedup_key,
            "domain": self.domain,
            "source_type": self.source_type,
            "is_official": self.is_official,
            "originating_queries": self.originating_queries,
            "searxng_engines": self.searxng_engines,
            "discovered_at": self.discovered_at,
        }
        if self.near_duplicate_of is not None:
            d["near_duplicate_of"] = self.near_duplicate_of
            d["near_duplicate_score"] = self.near_duplicate_score
        return d


@dataclass
class ProcessedDiscoveryRun:
    """Output of the full Phase 2 classification + dedup pipeline."""

    brand: str
    brand_config: BrandConfig
    started_at: str
    completed_at: str
    queries_executed: List[str]
    results: List[ClassifiedResult]

    # Processing statistics
    total_raw_results: int
    total_classified_results: int
    exact_duplicates_merged: int
    near_duplicates_flagged: int
    source_type_counts: Dict[str, int]
    official_count: int

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "brand_config": self.brand_config.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "queries_executed": self.queries_executed,
            "total_raw_results": self.total_raw_results,
            "total_classified_results": self.total_classified_results,
            "exact_duplicates_merged": self.exact_duplicates_merged,
            "near_duplicates_flagged": self.near_duplicates_flagged,
            "source_type_counts": self.source_type_counts,
            "official_count": self.official_count,
            "results": [r.to_dict() for r in self.results],
        }


# -------------------------------------------------------
# Phase 3: Extraction
# -------------------------------------------------------


@dataclass
class ExtractedMention:
    """
    A single brand mention after web page content extraction.
    Carries the extracted text content, extraction metadata, and full provenance.
    """

    # Extracted Content & Metadata
    text: str                            # Cleaned article text ("" if extraction failed)
    extraction_method: str               # "direct_trafilatura" | "playwright_trafilatura" | "failed"
    extraction_status: str               # "success" | "failed"
    extracted_at: str                    # ISO-8601 UTC timestamp
    error_message: Optional[str] = None  # Populated if extraction failed
    publication_date: Optional[str] = None # Metadata date from trafilatura if found
    author: Optional[str] = None           # Metadata author from trafilatura if found

    # Preserved Phase 1 & 2 Provenance
    title: str = ""
    snippet: str = ""
    canonical_url: str = ""
    original_url: str = ""
    dedup_key: str = ""
    domain: str = ""
    source_type: str = ""
    is_official: bool = False
    originating_queries: List[str] = field(default_factory=list)
    searxng_engines: List[str] = field(default_factory=list)
    discovered_at: str = ""
    near_duplicate_of: Optional[str] = None
    near_duplicate_score: Optional[float] = None

    def to_dict(self) -> dict:
        d: dict = {
            "title": self.title,
            "snippet": self.snippet,
            "canonical_url": self.canonical_url,
            "original_url": self.original_url,
            "dedup_key": self.dedup_key,
            "domain": self.domain,
            "source_type": self.source_type,
            "is_official": self.is_official,
            "originating_queries": self.originating_queries,
            "searxng_engines": self.searxng_engines,
            "discovered_at": self.discovered_at,
            "text": self.text,
            "extraction_method": self.extraction_method,
            "extraction_status": self.extraction_status,
            "extracted_at": self.extracted_at,
        }
        if self.error_message:
            d["error_message"] = self.error_message
        if self.publication_date:
            d["publication_date"] = self.publication_date
        if self.author:
            d["author"] = self.author
        if self.near_duplicate_of is not None:
            d["near_duplicate_of"] = self.near_duplicate_of
            d["near_duplicate_score"] = self.near_duplicate_score
        return d


@dataclass
class ExtractedRun:
    """Output of the full Phase 3 extraction pipeline."""

    brand: str
    brand_config: BrandConfig
    started_at: str
    completed_at: str
    queries_executed: List[str]
    mentions: List[ExtractedMention]

    # Extraction statistics
    total_classified_input: int
    successful_extractions: int
    failed_extractions: int
    direct_http_extractions: int
    playwright_extractions: int

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "brand_config": self.brand_config.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "queries_executed": self.queries_executed,
            "total_classified_input": self.total_classified_input,
            "successful_extractions": self.successful_extractions,
            "failed_extractions": self.failed_extractions,
            "direct_http_extractions": self.direct_http_extractions,
            "playwright_extractions": self.playwright_extractions,
            "mentions": [m.to_dict() for m in self.mentions],
        }


