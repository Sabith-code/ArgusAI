"""
SearXNG HTTP client for the discovery layer.

Handles:
  - Querying the SearXNG JSON API
  - Parsing results into structured DiscoveryResult objects
  - Running a full one-shot discovery across all query templates
  - Inspecting the live SearXNG engine configuration
"""

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import requests

from .models import DiscoveryResult, DiscoveryRun

logger = logging.getLogger(__name__)


class SearXNGError(Exception):
    """Raised when SearXNG returns an unrecoverable error."""


class SearXNGClient:
    """
    Client for SearXNG's JSON search API.

    Args:
        base_url: Root URL of the SearXNG instance (e.g. http://localhost:8080).
        request_timeout: HTTP request timeout in seconds.
        delay_between_queries: Seconds to wait between consecutive queries
            to avoid overwhelming the SearXNG instance.
    """

    def __init__(
        self,
        base_url: str,
        request_timeout: int = 30,
        delay_between_queries: float = 1.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.search_url = f"{self.base_url}/search"
        self.config_url = f"{self.base_url}/config"
        self.request_timeout = request_timeout
        self.delay_between_queries = delay_between_queries

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------
    # Low-level: single search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        categories: str = "general",
        pageno: int = 1,
    ) -> dict:
        """
        Execute a single search query against SearXNG.

        Args:
            query: The search string (exact, including any OR operators).
            categories: SearXNG category filter (default "general").
            pageno: Result page number.

        Returns:
            The full JSON response dict from SearXNG.

        Raises:
            SearXNGError: On HTTP errors or invalid responses.
        """
        params = {
            "q": query,
            "format": "json",
            "pageno": pageno,
        }
        if categories:
            params["categories"] = categories

        logger.info("SearXNG query: %r", query)

        try:
            resp = self.session.get(
                self.search_url,
                params=params,
                timeout=self.request_timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise SearXNGError(
                f"Cannot connect to SearXNG at {self.search_url}. "
                f"Is the container running? Error: {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise SearXNGError(
                f"SearXNG request timed out after {self.request_timeout}s "
                f"for query: {query!r}"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise SearXNGError(
                f"SearXNG returned HTTP {resp.status_code} for query: {query!r}. "
                f"Body: {resp.text[:500]}"
            ) from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise SearXNGError(
                f"SearXNG returned non-JSON response for query: {query!r}. "
                f"Content-Type: {resp.headers.get('Content-Type')}"
            ) from exc

        result_count = len(data.get("results", []))
        unresponsive = data.get("unresponsive_engines", [])
        logger.info(
            "  -> %d results, %d unresponsive engines",
            result_count,
            len(unresponsive),
        )
        if unresponsive:
            logger.warning("  Unresponsive engines: %s", unresponsive)

        return data

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract the hostname from a URL string."""
        try:
            parsed = urlparse(url)
            # netloc includes port; hostname does not
            return parsed.hostname or parsed.netloc or ""
        except Exception:
            return ""

    def parse_results(
        self, raw_results: List[dict], query: str
    ) -> List[DiscoveryResult]:
        """
        Convert raw SearXNG result dicts into DiscoveryResult objects.

        Each result preserves the *exact* query string that produced it
        for downstream provenance tracking.
        """
        parsed: List[DiscoveryResult] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for raw in raw_results:
            url = raw.get("url", "")
            if not url:
                logger.warning("Skipping result with empty URL (query: %r)", query)
                continue

            # SearXNG returns engines as a list of names that surfaced this result.
            engines = raw.get("engines", [])
            if isinstance(engines, str):
                engines = [engines]

            result = DiscoveryResult(
                title=raw.get("title", "").strip(),
                url=url,
                domain=self._extract_domain(url),
                searxng_engines=list(engines),
                snippet=(raw.get("content") or "").strip(),
                query=query,
                discovered_at=now_iso,
            )
            parsed.append(result)

        return parsed

    # ------------------------------------------------------------------
    # One-shot discovery
    # ------------------------------------------------------------------

    def discover(self, brand: str, queries: List[dict]) -> DiscoveryRun:
        """
        Execute a full one-shot discovery scan for a brand.

        Args:
            brand: Brand name being monitored.
            queries: List of dicts with 'category' and 'query' keys,
                     as returned by ``query_generator.generate_queries``.

        Returns:
            A DiscoveryRun containing all parsed results and any errors.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        all_results: List[DiscoveryResult] = []
        all_errors: List[dict] = []
        queries_executed: List[str] = []

        for idx, q in enumerate(queries):
            query_str = q["query"]
            category = q["category"]
            queries_executed.append(query_str)

            try:
                raw_response = self.search(query_str)
                raw_results = raw_response.get("results", [])
                parsed = self.parse_results(raw_results, query_str)
                all_results.extend(parsed)
                logger.info(
                    "[%d/%d] %-16s  %d results",
                    idx + 1,
                    len(queries),
                    category,
                    len(parsed),
                )
            except SearXNGError as exc:
                error_entry = {
                    "query": query_str,
                    "category": category,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                all_errors.append(error_entry)
                logger.error(
                    "[%d/%d] %-16s  ERROR: %s",
                    idx + 1,
                    len(queries),
                    category,
                    exc,
                )
            except Exception as exc:
                # Catch-all so one query failure doesn't kill the whole run.
                error_entry = {
                    "query": query_str,
                    "category": category,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                all_errors.append(error_entry)
                logger.error(
                    "[%d/%d] %-16s  UNEXPECTED ERROR: %s",
                    idx + 1,
                    len(queries),
                    category,
                    exc,
                )

            # Polite delay between queries (skip after the last one).
            if idx < len(queries) - 1:
                time.sleep(self.delay_between_queries)

        completed_at = datetime.now(timezone.utc).isoformat()

        run = DiscoveryRun(
            brand=brand,
            started_at=started_at,
            completed_at=completed_at,
            queries_executed=queries_executed,
            results=all_results,
            errors=all_errors,
        )

        logger.info(
            "Discovery complete for %r: %d total results, %d errors across %d queries",
            brand,
            len(all_results),
            len(all_errors),
            len(queries),
        )
        return run

    # ------------------------------------------------------------------
    # Config inspection
    # ------------------------------------------------------------------

    def get_enabled_engines(self) -> List[dict]:
        """
        Fetch the live SearXNG configuration and return the enabled engines.

        Returns:
            List of engine dicts, each containing at least 'name' and
            'categories' keys.

        Raises:
            SearXNGError: If the config endpoint is unreachable or returns
                non-JSON data.
        """
        logger.info("Fetching SearXNG configuration from %s", self.config_url)
        try:
            resp = self.session.get(self.config_url, timeout=self.request_timeout)
            resp.raise_for_status()
            config = resp.json()
        except requests.exceptions.ConnectionError as exc:
            raise SearXNGError(
                f"Cannot connect to SearXNG config at {self.config_url}: {exc}"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise SearXNGError(
                f"SearXNG config returned HTTP {resp.status_code}: {resp.text[:500]}"
            ) from exc
        except ValueError as exc:
            raise SearXNGError(
                f"SearXNG config returned non-JSON: {exc}"
            ) from exc

        # The /config endpoint returns a dict whose structure may vary across
        # SearXNG versions.  We extract whatever engine information is present.
        engines_raw = config.get("engines", [])

        # engines_raw might be a list of dicts or a dict of dicts depending
        # on the SearXNG version.  Normalise to list of dicts.
        engines: List[dict] = []
        if isinstance(engines_raw, list):
            engines = engines_raw
        elif isinstance(engines_raw, dict):
            for name, info in engines_raw.items():
                entry = {"name": name}
                if isinstance(info, dict):
                    entry.update(info)
                engines.append(entry)

        logger.info("SearXNG reports %d enabled engines", len(engines))
        return engines

    def get_full_config(self) -> dict:
        """
        Fetch and return the complete SearXNG config JSON.
        Useful for debugging and initial inspection.
        """
        try:
            resp = self.session.get(self.config_url, timeout=self.request_timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise SearXNGError(
                f"Failed to fetch SearXNG config: {exc}"
            ) from exc
