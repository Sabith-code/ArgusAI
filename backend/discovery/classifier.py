"""
Source classification for discovered URLs.

Classification order (deterministic, no ML):
  1. Explicitly configured official source/account for the brand
  2. Known-domain lookup  (source_domains.DOMAIN_SOURCE_MAP)
  3. URL path heuristic
  4. Default → ``SourceType.OTHER``
"""

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from .models import BrandConfig, SourceType
from .source_domains import DOMAIN_SOURCE_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Path-based heuristics (step 3)
# ---------------------------------------------------------------
# Patterns are checked against the URL path.  Each list entry is
# (compiled regex, SourceType).  Order matters — first match wins.

_PATH_HEURISTICS: List[Tuple[re.Pattern, SourceType]] = [
    (re.compile(r"/blog[s]?(/|$)", re.IGNORECASE), SourceType.BLOG),
    (re.compile(r"/forum[s]?(/|$)", re.IGNORECASE), SourceType.FORUM),
    (re.compile(r"/thread[s]?(/|$)", re.IGNORECASE), SourceType.FORUM),
    (re.compile(r"/community(/|$)", re.IGNORECASE), SourceType.FORUM),
    (re.compile(r"/review[s]?(/|$)", re.IGNORECASE), SourceType.REVIEW),
]


# ---------------------------------------------------------------
# Official-source helpers
# ---------------------------------------------------------------

def _normalise_hostname(hostname: str) -> str:
    """Lowercase and strip ``www.`` prefix."""
    h = hostname.lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def _is_official_domain(hostname: str, official_domains: List[str]) -> bool:
    """
    Label-boundary hostname match.

    ``nike.com`` matches ``nike.com``, ``about.nike.com`` but
    NOT ``nikeshoes.com`` or ``nike.com.evil.com``.
    """
    host = _normalise_hostname(hostname)

    for domain in official_domains:
        d = _normalise_hostname(domain)
        if host == d or host.endswith("." + d):
            return True
    return False


def _normalise_account_pattern(account: str) -> str:
    """
    Normalise an official-account URL pattern to
    ``hostname/path`` form for prefix matching.
    """
    raw = account
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    hostname = _normalise_hostname(parsed.hostname or "")
    path = parsed.path.rstrip("/")
    return hostname + path


def _is_official_account(
    hostname: str,
    path: str,
    normalised_accounts: List[str],
) -> bool:
    """
    URL-prefix match against pre-normalised account patterns.

    Matches at path-segment boundaries:
    ``youtube.com/@Nike`` matches ``youtube.com/@Nike/videos``
    but NOT ``youtube.com/@NikeBasketball``.
    """
    host = _normalise_hostname(hostname)
    url_norm = host + path.rstrip("/")

    for pattern in normalised_accounts:
        if url_norm == pattern:
            return True
        if url_norm.startswith(pattern + "/"):
            return True
    return False


# ---------------------------------------------------------------
# Public API
# ---------------------------------------------------------------

def classify(
    url: str,
    hostname: str,
    brand_config: Optional[BrandConfig] = None,
) -> Tuple[SourceType, bool]:
    """
    Classify a URL and determine whether it is an official brand source.

    Returns:
        (source_type, is_official)
    """
    parsed = urlparse(url)
    host = _normalise_hostname(hostname)
    path = parsed.path or ""

    # Pre-normalise account patterns.
    norm_accounts: List[str] = []
    if brand_config and brand_config.official_accounts:
        norm_accounts = [
            _normalise_account_pattern(a)
            for a in brand_config.official_accounts
        ]

    # --- Step 1a: official domain? ---
    if brand_config and brand_config.official_domains:
        if _is_official_domain(host, brand_config.official_domains):
            return SourceType.OFFICIAL, True

    # --- Step 1b: official account? ---
    if norm_accounts:
        if _is_official_account(host, path, norm_accounts):
            # source_type is the platform, not OFFICIAL
            st = _domain_lookup(host)
            if st is None:
                st = _path_heuristic(path)
            if st is None:
                st = SourceType.OTHER
            return st, True

    # --- Step 2: known-domain lookup ---
    st = _domain_lookup(host)
    if st is not None:
        return st, False

    # --- Step 3: path heuristic ---
    st = _path_heuristic(path)
    if st is not None:
        return st, False

    # --- Step 4: default ---
    return SourceType.OTHER, False


def _domain_lookup(hostname: str) -> Optional[SourceType]:
    """Exact lookup in the known-domain map (after www-strip)."""
    return DOMAIN_SOURCE_MAP.get(hostname)


def _path_heuristic(path: str) -> Optional[SourceType]:
    """Check URL path against structural patterns."""
    for pattern, source_type in _PATH_HEURISTICS:
        if pattern.search(path):
            return source_type
    return None
