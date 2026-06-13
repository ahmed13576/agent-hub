"""
Agent Hub - HTTP Client

A robust HTTP client with:
- User-Agent rotation to avoid fingerprinting
- Domain-aware User-Agent (bot UA for Reddit, browser UA elsewhere)
- Per-domain rate limiting (respects Reddit's x-ratelimit-* headers)
- Optional Bright Data Web Unlocker proxy routing
- Configurable timeouts and retries
- RSS feed parsing support via feedparser
"""

import random
import time
import logging
from typing import Optional
from urllib.parse import urlparse

import requests
import feedparser

from src.config import config

logger = logging.getLogger(__name__)

# Realistic browser User-Agent strings for rotation (used for blogs and general sites)
BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

# Bot-style UA for sites that prefer honest bot identification (e.g., Reddit).
# Reddit blocks browser-mimicking UAs with 403 but allows descriptive bot UAs.
BOT_USER_AGENT = "AgentHub/1.0 (automated research bot; https://github.com/agent-hub)"

# Domains that require bot-style User-Agent instead of browser UA
BOT_UA_DOMAINS = {"reddit.com", "www.reddit.com", "old.reddit.com"}

# Minimum seconds between requests to the same rate-limited domain.
# Reddit's unauthenticated limit is ~100 requests per 10 minutes = 1 req/6s.
# We use 2s as a comfortable default that stays well within limits.
DOMAIN_RATE_LIMITS = {
    "reddit.com": 2.0,
    "www.reddit.com": 2.0,
}

# Keep USER_AGENTS as backward-compatible alias
USER_AGENTS = BROWSER_USER_AGENTS

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

        # Per-domain request timestamps for rate limiting
        self._domain_last_request: dict[str, float] = {}

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
        """Return a random browser user-agent string."""
        return random.choice(BROWSER_USER_AGENTS)

    @staticmethod
    def _get_domain(url: str) -> str:
        """Extract the domain from a URL."""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    @staticmethod
    def _needs_bot_ua(url: str) -> bool:
        """Check if a URL's domain requires a bot-style User-Agent."""
        try:
            domain = urlparse(url).netloc.lower()
            return any(domain == d or domain.endswith("." + d) for d in BOT_UA_DOMAINS)
        except Exception:
            return False

    def _domain_throttle(self, url: str):
        """
        Enforce per-domain rate limiting.

        Sleeps if needed to maintain minimum interval between requests
        to the same rate-limited domain (e.g., Reddit).
        """
        domain = self._get_domain(url)

        # Check if this domain has a rate limit configured
        min_interval = None
        for rate_domain, interval in DOMAIN_RATE_LIMITS.items():
            if domain == rate_domain or domain.endswith("." + rate_domain):
                min_interval = interval
                break

        if min_interval is None:
            return

        # Use the base domain for tracking (e.g., www.reddit.com -> reddit.com)
        track_key = next(
            (d for d in DOMAIN_RATE_LIMITS if domain == d or domain.endswith("." + d)),
            domain,
        )

        last_time = self._domain_last_request.get(track_key, 0.0)
        elapsed = time.time() - last_time
        if elapsed < min_interval:
            wait = min_interval - elapsed
            logger.debug(f"Domain throttle: sleeping {wait:.1f}s for {track_key}")
            time.sleep(wait)

        self._domain_last_request[track_key] = time.time()

    def _build_headers(self, extra_headers: Optional[dict] = None, url: Optional[str] = None) -> dict:
        """
        Build request headers with appropriate User-Agent.

        Uses bot-style UA for domains that block browser UAs (e.g., Reddit).
        Uses browser-style rotating UAs for all other sites.
        """
        if url and self._needs_bot_ua(url):
            user_agent = BOT_USER_AGENT
        else:
            user_agent = self._get_random_user_agent()

        headers = {
            "User-Agent": user_agent,
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
                # Enforce per-domain rate limiting before each attempt
                self._domain_throttle(url)

                merged_headers = self._build_headers(headers, url=url)
                response = self.session.get(
                    url,
                    headers=merged_headers,
                    params=params,
                    timeout=self.timeout,
                )

                # Log Reddit rate limit headers if present
                rl_remaining = response.headers.get("x-ratelimit-remaining")
                rl_reset = response.headers.get("x-ratelimit-reset")
                if rl_remaining is not None:
                    logger.debug(
                        f"Rate limit for {self._get_domain(url)}: "
                        f"remaining={rl_remaining}, reset_in={rl_reset}s"
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

                # For 429, check Retry-After and Reddit's x-ratelimit-reset headers
                if e.response is not None and e.response.status_code == 429:
                    wait = self._compute_429_wait(e.response, attempt)
                else:
                    wait = RETRY_BACKOFF_BASE ** attempt  # 2-4-8s for server errors

                logger.info(f"Retrying in {wait:.0f}s...")
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

    @staticmethod
    def _compute_429_wait(response: requests.Response, attempt: int) -> float:
        """
        Compute wait time for a 429 Too Many Requests response.

        Checks (in order):
        1. Standard Retry-After header
        2. Reddit's x-ratelimit-reset header (seconds until bucket refill)
        3. Fallback: 10 * attempt seconds

        Returns:
            Seconds to wait before retrying (capped at 120s).
        """
        # Check standard Retry-After
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 120.0)
            except ValueError:
                pass

        # Check Reddit's x-ratelimit-reset (seconds until rate limit window resets)
        rl_reset = response.headers.get("x-ratelimit-reset")
        if rl_reset:
            try:
                return min(float(rl_reset) + 1.0, 120.0)  # +1s buffer
            except ValueError:
                pass

        # Fallback: escalating backoff (10-20-30s)
        return min(10.0 * attempt, 120.0)

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

        Uses an XML-appropriate Accept header for RSS endpoints.

        Args:
            url: The RSS feed URL.

        Returns:
            A feedparser.FeedParserDict with parsed feed data.
        """
        rss_headers = {
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        }
        response = self.get(url, headers=rss_headers)
        feed = feedparser.parse(response.text)

        if feed.bozo and hasattr(feed, 'bozo_exception') and feed.bozo_exception:
            logger.warning(f"RSS parse warning for {url}: {feed.bozo_exception}")

        logger.info(f"Fetched RSS {url} — {len(feed.entries)} entries")
        return feed

    @property
    def proxy_enabled(self) -> bool:
        """Whether proxy routing is currently active."""
        return self._proxy_enabled
