"""
Agent Hub - HTTP Client

A robust HTTP client with:
- User-Agent rotation to avoid fingerprinting
- Optional Bright Data Web Unlocker proxy routing
- Configurable timeouts and retries
- RSS feed parsing support via feedparser
"""

import random
import time
import logging
from typing import Optional

import requests
import feedparser

from src.config import config

logger = logging.getLogger(__name__)

# Realistic browser User-Agent strings for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# Default request settings
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


class HttpClient:
    """
    HTTP client with user-agent rotation and optional Bright Data proxy support.

    Usage:
        client = HttpClient()
        response = client.get("https://example.com")
        feed = client.fetch_rss("https://reddit.com/r/ClaudeDev/.rss")
    """

    def __init__(
        self,
        use_proxy: Optional[bool] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Args:
            use_proxy: Force proxy on/off. If None, auto-detects from config.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts on failure.
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

        # Proxy configuration
        if use_proxy is None:
            self._proxy_enabled = config.proxy_enabled
        else:
            self._proxy_enabled = use_proxy

        if self._proxy_enabled and config.brightdata_api_key:
            # Bright Data Web Unlocker proxy configuration
            # Format: http://username:password@host:port
            proxy_url = f"http://brd-customer-hl_918951ea-zone-unblocker:{config.brightdata_api_key}@brd.superproxy.io:33335"
            self.session.proxies = {
                "http": proxy_url,
                "https": proxy_url,
            }
            # Bright Data requires certificate verification to be disabled for HTTPS proxying
            self.session.verify = False
            logger.info("HTTP Client initialized with Bright Data Web Unlocker proxy.")
        else:
            logger.info("HTTP Client initialized in direct (no-proxy) mode.")

    def _get_random_user_agent(self) -> str:
        """Return a random user-agent string."""
        return random.choice(USER_AGENTS)

    def _build_headers(self, extra_headers: Optional[dict] = None) -> dict:
        """Build request headers with a rotated User-Agent."""
        headers = {
            "User-Agent": self._get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def get(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> requests.Response:
        """
        Perform an HTTP GET request with retries and user-agent rotation.

        Args:
            url: The target URL.
            headers: Optional extra headers to merge.
            params: Optional query parameters.

        Returns:
            requests.Response object.

        Raises:
            requests.exceptions.RequestException after all retries are exhausted.
        """
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                merged_headers = self._build_headers(headers)
                response = self.session.get(
                    url,
                    headers=merged_headers,
                    params=params,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                logger.debug(f"GET {url} — {response.status_code} (attempt {attempt})")
                return response

            except requests.exceptions.HTTPError as e:
                last_exception = e
                status = e.response.status_code if e.response is not None else "unknown"
                logger.warning(f"HTTP {status} for {url} (attempt {attempt}/{self.max_retries})")

                # Don't retry on client errors (except 429 rate-limiting)
                if e.response is not None and 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise

                # Backoff before retry
                wait = RETRY_BACKOFF_BASE ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                logger.warning(f"Connection error for {url} (attempt {attempt}/{self.max_retries}): {e}")
                wait = RETRY_BACKOFF_BASE ** attempt
                time.sleep(wait)

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"Timeout for {url} (attempt {attempt}/{self.max_retries})")
                wait = RETRY_BACKOFF_BASE ** attempt
                time.sleep(wait)

        # All retries exhausted
        raise requests.exceptions.RequestException(
            f"Failed to fetch {url} after {self.max_retries} attempts"
        ) from last_exception

    def get_json(
        self,
        url: str,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Perform a GET request and return parsed JSON."""
        response = self.get(url, headers=headers, params=params)
        return response.json()

    def fetch_rss(self, url: str) -> feedparser.FeedParserDict:
        """
        Fetch and parse an RSS/Atom feed.

        Args:
            url: The RSS feed URL.

        Returns:
            A feedparser.FeedParserDict with parsed feed data.
        """
        response = self.get(url)
        feed = feedparser.parse(response.text)

        if feed.bozo and feed.bozo_exception:
            logger.warning(f"RSS parse warning for {url}: {feed.bozo_exception}")

        logger.info(f"Fetched RSS {url} — {len(feed.entries)} entries")
        return feed

    @property
    def proxy_enabled(self) -> bool:
        """Whether proxy routing is currently active."""
        return self._proxy_enabled
