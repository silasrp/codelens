"""
OpenAI rate limit manager.

Combines three layers of protection:

  1. Token budgeting   — tracks estimated tokens-per-minute (TPM) against
                         the account limit and inserts pre-emptive sleeps
                         before a request would breach the budget window.

  2. Concurrency limit — asyncio.Semaphore caps simultaneous in-flight
                         requests so we never pile up 50 goroutines worth
                         of tokens at once.

  3. Retry + backoff   — if a 429 slips through anyway (estimation error,
                         burst from another process), exponential backoff
                         with jitter retries up to MAX_RETRIES times.
                         On a RateLimitError the response header
                         `retry-after` is respected when present.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

import openai
from openai import RateLimitError, APIStatusError

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class RateLimitConfig:
    # Hard limit on simultaneous in-flight requests
    max_concurrent: int   = 3

    # Conservative TPM ceiling — set below your actual limit so estimation
    # errors don't cause 429s. Free tier: 30_000. Tier 1: 90_000.
    tpm_limit: int        = 25_000

    # How much of the TPM budget a single request may consume before we
    # pre-emptively slow down (0.0–1.0)
    tpm_request_ceiling: float = 0.8

    # Retry settings
    max_retries: int      = 6
    base_delay:  float    = 1.0   # seconds for first retry
    max_delay:   float    = 60.0  # cap on backoff

    # Tokens-per-character estimate for code (conservative)
    chars_per_token: float = 3.5


# ── Token window tracker ──────────────────────────────────────────────────────

@dataclass
class _TokenWindow:
    """
    Sliding 60-second window of token usage.
    Thread-safe via asyncio lock — only used from the async path.
    """
    tpm_limit: int
    _lock:   asyncio.Lock = field(default_factory=asyncio.Lock)
    _events: list[tuple[float, int]] = field(default_factory=list)  # (timestamp, tokens)

    def _prune(self) -> None:
        cutoff = time.monotonic() - 60.0
        self._events = [(t, n) for t, n in self._events if t > cutoff]

    def current_usage(self) -> int:
        self._prune()
        return sum(n for _, n in self._events)

    async def acquire(self, estimated_tokens: int) -> None:
        """Block until adding `estimated_tokens` won't exceed tpm_limit."""
        async with self._lock:
            while True:
                self._prune()
                used = sum(n for _, n in self._events)
                if used + estimated_tokens <= self.tpm_limit:
                    self._events.append((time.monotonic(), estimated_tokens))
                    return
                # Calculate how long until oldest event falls out of window
                oldest = self._events[0][0] if self._events else time.monotonic()
                wait = max(0.1, (oldest + 60.0) - time.monotonic())
                logger.debug("TPM budget full (%d/%d) — waiting %.1fs", used, self.tpm_limit, wait)
                await asyncio.sleep(wait)


# ── Main rate limiter ─────────────────────────────────────────────────────────

class RateLimiter:
    """
    Drop-in wrapper around AsyncOpenAI that enforces all three layers.

    Usage:
        limiter = RateLimiter(async_client, config)
        result  = await limiter.chat(system=..., user=..., max_tokens=400)
    """

    def __init__(
        self,
        client: openai.AsyncOpenAI,
        model:  str,
        config: RateLimitConfig | None = None,
    ) -> None:
        self._client  = client
        self._model   = model
        self._config  = config or RateLimitConfig()
        self._sem     = asyncio.Semaphore(self._config.max_concurrent)
        self._window  = _TokenWindow(tpm_limit=self._config.tpm_limit)

    def _estimate_tokens(self, system: str, user: str, max_tokens: int) -> int:
        """
        Rough upper-bound token estimate for a request.
        Input tokens (prompt) + reserved output tokens.
        """
        prompt_chars  = len(system) + len(user)
        prompt_tokens = int(prompt_chars / self._config.chars_per_token)
        return prompt_tokens + max_tokens

    async def chat(
        self,
        system:     str,
        user:       str,
        max_tokens: int,
    ) -> str:
        """
        Make one chat completion with full rate-limit protection.
        Returns the response text.
        """
        estimated = self._estimate_tokens(system, user, max_tokens)

        # Layer 1: token budget pre-check
        await self._window.acquire(estimated)

        # Layer 2: concurrency cap
        async with self._sem:
            return await self._call_with_retry(system, user, max_tokens)

    async def _call_with_retry(
        self,
        system:     str,
        user:       str,
        max_tokens: int,
    ) -> str:
        """Layer 3: exponential backoff with jitter on 429."""
        config = self._config
        delay  = config.base_delay

        for attempt in range(config.max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                )
                return response.choices[0].message.content.strip()

            except RateLimitError as exc:
                if attempt == config.max_retries:
                    logger.error("Rate limit: giving up after %d retries", config.max_retries)
                    raise

                # Respect retry-after header when present
                retry_after = _parse_retry_after(exc)
                wait = retry_after if retry_after else min(
                    delay * (2 ** attempt) + random.uniform(0, 1),
                    config.max_delay,
                )
                logger.warning(
                    "429 rate limit (attempt %d/%d) — waiting %.1fs: %s",
                    attempt + 1, config.max_retries, wait, _short_msg(exc),
                )
                await asyncio.sleep(wait)

            except APIStatusError as exc:
                # 500/503 from OpenAI — retry with backoff, but fewer times
                if exc.status_code in (500, 502, 503, 529) and attempt < 3:
                    wait = min(delay * (2 ** attempt), config.max_delay)
                    logger.warning("OpenAI %d (attempt %d) — retrying in %.1fs", exc.status_code, attempt + 1, wait)
                    await asyncio.sleep(wait)
                else:
                    raise

        raise RuntimeError("Unreachable")  # mypy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_retry_after(exc: RateLimitError) -> float | None:
    """Extract retry-after seconds from the exception headers if present."""
    try:
        headers = exc.response.headers  # type: ignore[union-attr]
        val = headers.get("retry-after") or headers.get("x-ratelimit-reset-tokens")
        if val:
            return float(val)
    except Exception:
        pass
    return None


def _short_msg(exc: Exception) -> str:
    msg = str(exc)
    return msg[:120] + "…" if len(msg) > 120 else msg
