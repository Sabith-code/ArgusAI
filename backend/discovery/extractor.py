"""
Content extractor for discovery mentions.

Cheapest-first extraction chain:
  1. Direct HTTP request → trafilatura.extract()
  2. If direct HTTP fails or text is below thresholds (MIN_TEXT_CHARS / MIN_TEXT_WORDS)
     → Fallback to headless Playwright page fetch → trafilatura.extract()
  3. If Playwright fails or extracted text is still insufficient
     → Log error explicitly, set extraction_status="failed", text="" (never fake content).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests
import trafilatura
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .models import ClassifiedResult, ExtractedMention

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class Extractor:
    """
    Cheapest-first web page content extractor.

    Args:
        min_chars: Minimum character length for usable extracted text.
        min_words: Minimum word count for usable extracted text.
        http_timeout: Timeout in seconds for direct HTTP requests.
        playwright_timeout: Timeout in seconds for Playwright page loads.
    """

    def __init__(
        self,
        min_chars: Optional[int] = None,
        min_words: Optional[int] = None,
        http_timeout: Optional[int] = None,
        playwright_timeout: Optional[int] = None,
    ):
        self.min_chars = (
            min_chars
            if min_chars is not None
            else int(os.getenv("MIN_TEXT_CHARS", "100"))
        )
        self.min_words = (
            min_words
            if min_words is not None
            else int(os.getenv("MIN_TEXT_WORDS", "20"))
        )
        self.http_timeout = (
            http_timeout
            if http_timeout is not None
            else int(os.getenv("HTTP_EXTRACTION_TIMEOUT", "15"))
        )
        self.playwright_timeout = (
            playwright_timeout
            if playwright_timeout is not None
            else int(os.getenv("PLAYWRIGHT_EXTRACTION_TIMEOUT", "15"))
        )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def is_text_sufficient(self, text: Optional[str]) -> bool:
        """Check if extracted text meets character and word thresholds."""
        if not text:
            return False
        text_clean = text.strip()
        if len(text_clean) < self.min_chars:
            return False
        words = text_clean.split()
        if len(words) < self.min_words:
            return False
        return True

    def _extract_metadata(self, html: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract publication_date and author using trafilatura metadata parser."""
        try:
            meta = trafilatura.extract_metadata(html)
            if meta:
                pub_date = meta.date if hasattr(meta, "date") else None
                author = meta.author if hasattr(meta, "author") else None
                return pub_date, author
        except Exception as exc:
            logger.debug("Metadata extraction error: %s", exc)
        return None, None

    def _direct_http_extract(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Attempt 1 & 2: Direct HTTP fetch followed by Trafilatura clean.
        Returns: (text, pub_date, author, error_message)
        """
        try:
            resp = self.session.get(url, timeout=self.http_timeout, allow_redirects=True)
            if resp.status_code >= 400:
                return None, None, None, f"HTTP status {resp.status_code}"

            html = resp.text
            text = trafilatura.extract(html, include_links=False, include_images=False)
            pub_date, author = self._extract_metadata(html)

            if self.is_text_sufficient(text):
                return text, pub_date, author, None

            reason = "extracted text below threshold" if text else "trafilatura returned empty/None"
            return None, pub_date, author, f"Direct HTTP trafilatura: {reason}"

        except requests.exceptions.Timeout:
            return None, None, None, f"Direct HTTP timeout after {self.http_timeout}s"
        except requests.exceptions.RequestException as exc:
            return None, None, None, f"Direct HTTP error: {exc}"
        except Exception as exc:
            return None, None, None, f"Unexpected direct HTTP error: {exc}"

    def _playwright_extract(self, browser, url: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Attempt 3: Reused Playwright browser fetch followed by Trafilatura clean.
        Creates a fresh BrowserContext and Page per URL, properly closing them.
        Returns: (text, pub_date, author, error_message)
        """
        context = None
        page = None
        try:
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            # Navigate to URL with configurable timeout
            page.goto(url, timeout=self.playwright_timeout * 1000, wait_until="domcontentloaded")

            # Brief pause for JS rendering
            page.wait_for_timeout(1000)

            html = page.content()
            text = trafilatura.extract(html, include_links=False, include_images=False)
            pub_date, author = self._extract_metadata(html)

            if self.is_text_sufficient(text):
                return text, pub_date, author, None

            reason = "extracted text below threshold" if text else "trafilatura returned empty/None"
            return None, pub_date, author, f"Playwright trafilatura: {reason}"

        except PlaywrightTimeoutError:
            return None, None, None, f"Playwright timeout after {self.playwright_timeout}s"
        except Exception as exc:
            return None, None, None, f"Playwright error: {exc}"
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if context:
                try:
                    context.close()
                except Exception:
                    pass

    def extract_mention(
        self,
        item: ClassifiedResult,
        browser=None,
        item_index: int = 1,
        total_items: int = 1,
    ) -> ExtractedMention:
        """
        Extract content for a single ClassifiedResult using the cheapest-first chain.
        Logs clean progress in the format:
          [1/77] Processing <URL>
          [1/77] SUCCESS via direct_trafilatura
          [1/77] Direct extraction insufficient → Playwright fallback
          [1/77] SUCCESS via playwright_trafilatura
          [1/77] FAILED — <actual reason>
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        target_url = item.canonical_url or item.original_url
        prefix = f"[{item_index}/{total_items}]"

        logger.info("%s Processing %s", prefix, target_url)

        # Attempt 1 & 2: Direct HTTP
        text, pub_date, author, http_err = self._direct_http_extract(target_url)

        if text and self.is_text_sufficient(text):
            logger.info("%s SUCCESS via direct_trafilatura (%d chars)", prefix, len(text))
            return ExtractedMention(
                text=text.strip(),
                extraction_method="direct_trafilatura",
                extraction_status="success",
                extracted_at=now_iso,
                error_message=None,
                publication_date=pub_date,
                author=author,
                title=item.title,
                snippet=item.snippet,
                canonical_url=item.canonical_url,
                original_url=item.original_url,
                dedup_key=item.dedup_key,
                domain=item.domain,
                source_type=item.source_type,
                is_official=item.is_official,
                originating_queries=list(item.originating_queries),
                searxng_engines=list(item.searxng_engines),
                discovered_at=item.discovered_at,
                near_duplicate_of=item.near_duplicate_of,
                near_duplicate_score=item.near_duplicate_score,
            )

        logger.info("%s Direct extraction insufficient (%s) → Playwright fallback", prefix, http_err)

        # Attempt 3: Playwright fallback using reused browser
        pw_text = None
        pw_date = None
        pw_author = None
        pw_err = None

        if browser is not None:
            pw_text, pw_date, pw_author, pw_err = self._playwright_extract(browser, target_url)
        else:
            # Fallback if no browser instance passed in
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                temp_browser = pw.chromium.launch(headless=True)
                try:
                    pw_text, pw_date, pw_author, pw_err = self._playwright_extract(temp_browser, target_url)
                finally:
                    temp_browser.close()

        if pw_text and self.is_text_sufficient(pw_text):
            logger.info("%s SUCCESS via playwright_trafilatura (%d chars)", prefix, len(pw_text))
            return ExtractedMention(
                text=pw_text.strip(),
                extraction_method="playwright_trafilatura",
                extraction_status="success",
                extracted_at=now_iso,
                error_message=None,
                publication_date=pw_date or pub_date,
                author=pw_author or author,
                title=item.title,
                snippet=item.snippet,
                canonical_url=item.canonical_url,
                original_url=item.original_url,
                dedup_key=item.dedup_key,
                domain=item.domain,
                source_type=item.source_type,
                is_official=item.is_official,
                originating_queries=list(item.originating_queries),
                searxng_engines=list(item.searxng_engines),
                discovered_at=item.discovered_at,
                near_duplicate_of=item.near_duplicate_of,
                near_duplicate_score=item.near_duplicate_score,
            )

        # Extraction failed on both attempts — log explicitly & do not fake content
        combined_err = f"Direct HTTP: [{http_err}] | Playwright: [{pw_err}]"
        logger.warning("%s FAILED — %s", prefix, combined_err)

        return ExtractedMention(
            text="",
            extraction_method="failed",
            extraction_status="failed",
            extracted_at=now_iso,
            error_message=combined_err,
            publication_date=pub_date or pw_date,
            author=author or pw_author,
            title=item.title,
            snippet=item.snippet,
            canonical_url=item.canonical_url,
            original_url=item.original_url,
            dedup_key=item.dedup_key,
            domain=item.domain,
            source_type=item.source_type,
            is_official=item.is_official,
            originating_queries=list(item.originating_queries),
            searxng_engines=list(item.searxng_engines),
            discovered_at=item.discovered_at,
            near_duplicate_of=item.near_duplicate_of,
            near_duplicate_score=item.near_duplicate_score,
        )
