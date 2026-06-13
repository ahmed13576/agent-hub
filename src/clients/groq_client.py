"""
Agent Hub - Groq LLM Client

Provides a rate-limited client for the Groq API, targeting Llama 3.3 70B Versatile
for AI enrichment tasks (summarization, tagging, categorization).

Features:
- Exponential backoff for 429 rate-limit responses
- Automatic fallback to lighter model on persistent failures
- Structured JSON output parsing
- Request throttling to stay under 30 RPM free-tier limit
"""

import json
import time
import logging
from typing import Optional

from groq import Groq, APIStatusError, RateLimitError

from src.config import config

logger = logging.getLogger(__name__)

# Minimum delay between requests (seconds) to stay under RPM limits
MIN_REQUEST_INTERVAL = 60.0 / max(config.groq_max_rpm, 1)

# Retry settings
MAX_RETRIES = 5
INITIAL_BACKOFF = 2.0  # seconds
MAX_BACKOFF = 120.0  # seconds


class GroqClient:
    """
    Rate-limited Groq API client for AI enrichment.

    Usage:
        client = GroqClient()
        result = client.analyze(
            "Summarize this GitHub repo description and tag it.",
            system_prompt="You are an AI strategy analyst..."
        )
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Args:
            api_key: Groq API key. Defaults to config.groq_api_key.
            model: Model name. Defaults to config.groq_model.
        """
        self._api_key = api_key or config.groq_api_key
        if not self._api_key:
            raise ValueError(
                "GROQ_API_KEY is required. Set it in .env or pass it directly."
            )

        self.model = model or config.groq_model
        self.fallback_model = config.groq_fallback_model
        self._client = Groq(api_key=self._api_key)
        self._last_request_time: float = 0.0
        self._request_count: int = 0

        logger.info(f"GroqClient initialized — model={self.model}")

    def _throttle(self):
        """Enforce minimum delay between requests to respect RPM limits."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            sleep_time = MIN_REQUEST_INTERVAL - elapsed
            logger.debug(f"Throttling: sleeping {sleep_time:.2f}s to respect RPM limit")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def chat(
        self,
        user_message: str,
        system_prompt: str = "You are a helpful AI assistant.",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        use_fallback: bool = False,
    ) -> str:
        """
        Send a chat completion request to Groq with retry and backoff.

        Args:
            user_message: The user's message/prompt.
            system_prompt: System-level instructions.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens: Maximum tokens in response.
            use_fallback: If True, uses the lighter fallback model.

        Returns:
            The assistant's response text.

        Raises:
            Exception after all retries are exhausted.
        """
        model = self.fallback_model if use_fallback else self.model
        backoff = INITIAL_BACKOFF
        last_exception = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._throttle()

                response = self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                self._request_count += 1
                content = response.choices[0].message.content
                logger.debug(
                    f"Groq response (attempt {attempt}, model={model}): "
                    f"{len(content)} chars, "
                    f"usage={response.usage.total_tokens} tokens"
                )
                return content

            except RateLimitError as e:
                last_exception = e
                logger.warning(
                    f"Rate limited (429) on attempt {attempt}/{MAX_RETRIES}. "
                    f"Backing off {backoff:.1f}s..."
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

            except APIStatusError as e:
                last_exception = e
                if e.status_code == 503:
                    # Service overloaded — retry with backoff
                    logger.warning(
                        f"Groq service overloaded (503) on attempt {attempt}/{MAX_RETRIES}. "
                        f"Backing off {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                else:
                    # Non-retryable API error
                    logger.error(f"Groq API error {e.status_code}: {e.message}")
                    raise

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error on attempt {attempt}: {e}")
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

        raise RuntimeError(
            f"Groq API call failed after {MAX_RETRIES} retries"
        ) from last_exception

    def analyze_json(
        self,
        user_message: str,
        system_prompt: str = "You are an AI assistant. Respond only with valid JSON.",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict:
        """
        Send a chat request expecting a JSON response, and parse it.

        Falls back to the lighter model if JSON parsing fails on the primary model.

        Args:
            user_message: The user prompt requesting JSON output.
            system_prompt: System prompt instructing JSON output.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.

        Returns:
            Parsed dictionary from the JSON response.
        """
        raw = self.chat(
            user_message=user_message,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Try to parse JSON from the response
        try:
            return self._extract_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"Failed to parse JSON from primary model ({self.model}). "
                f"Retrying with fallback model ({self.fallback_model})..."
            )
            # Retry with fallback model
            raw = self.chat(
                user_message=user_message,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                use_fallback=True,
            )
            return self._extract_json(raw)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """
        Extract JSON from a response that may contain markdown code fences.

        Handles responses like:
            ```json
            {"key": "value"}
            ```
        """
        cleaned = text.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        result = json.loads(cleaned)
        if not isinstance(result, dict):
            raise ValueError(f"Expected JSON object, got {type(result).__name__}")
        return result

    @property
    def request_count(self) -> int:
        """Number of successful API requests made in this session."""
        return self._request_count
