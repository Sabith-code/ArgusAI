"""
URL normalisation for deduplication.

Produces:
  canonical_url  — a valid, normalised URL (with scheme)
  dedup_key      — scheme-agnostic identity for dedup comparison

Approved normalisation rules:
  - Remove tracking params: utm_*, ref, fbclid, gclid, mc_cid, mc_eid
  - Remove URL fragments
  - Lowercase hostname
  - Strip www. prefix
  - Prefer https:// in canonical_url
  - Preserve path case
  - Normalise trailing slash for root path only
  - Sort query parameters for stable comparison
  - Do NOT remove arbitrary query parameters
"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Tracking parameter names to strip (checked case-insensitively).
# Any param name starting with "utm_" is also stripped.
_TRACKING_PARAMS = frozenset({
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid",
})


def _is_tracking_param(name: str) -> bool:
    low = name.lower()
    return low.startswith("utm_") or low in _TRACKING_PARAMS


def canonicalize_url(url: str) -> str:
    """
    Return a normalised, valid URL.

    The result always uses ``https://`` as the scheme and is suitable
    for display, linking, and storage.  For dedup comparison use
    :func:`make_dedup_key` on the result.
    """
    parsed = urlparse(url)

    scheme = "https"

    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    port = parsed.port
    netloc = f"{hostname}:{port}" if port and port not in (80, 443) else hostname

    # Root-path normalisation: treat "/" and "" as equivalent.
    # Non-root paths are left untouched (including trailing slashes).
    path = parsed.path
    if path in ("", "/"):
        path = ""

    # Filter tracking params and sort for deterministic output.
    raw_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: sorted(v) for k, v in raw_params.items()
        if not _is_tracking_param(k)
    }
    # Sort by key for stable ordering.
    query = urlencode(sorted(filtered.items()), doseq=True) if filtered else ""

    # If there is a query string but no path, add "/" so the URL is valid.
    if not path and query:
        path = "/"

    # Build — no fragment.
    if not path:
        path = "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def make_dedup_key(canonical_url: str) -> str:
    """
    Scheme-agnostic dedup identity derived from a canonical URL.

    Two canonical URLs differing only in ``http://`` vs ``https://``
    will produce the same key.
    """
    parsed = urlparse(canonical_url)
    key = parsed.netloc + parsed.path
    if parsed.query:
        key += "?" + parsed.query
    return key


def extract_domain(url: str) -> str:
    """Extract and return the lowercased hostname from *url*."""
    hostname = (urlparse(url).hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname
