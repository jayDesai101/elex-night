"""Async civicAPI client: concurrency cap, jitter, retries and a 429 circuit breaker."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
)

log = logging.getLogger(__name__)

USER_AGENT = "elex-night/0.1 (+https://github.com/jayDesai101/elex-night)"
RACE_PATH_PREFIX = "/race/"
DEADLINE = "deadline"
# Election night: civicAPI answered race requests in ~22 s (p50), so 8 s timed out nearly
# every request. 40 s lets slow responses land; stalls still free the slot eventually.
READ_TIMEOUT_S = 40.0
# Search took 17-23 s before the first byte, and over 60 s at the peak.
SEARCH_TIMEOUT_S = 90.0


@dataclass
class Fetch:
    status: int | None
    latency_ms: int
    nbytes: int
    data: Any
    error: str | None


class RetryableStatus(Exception):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, RetryableStatus | httpx.TimeoutException | httpx.TransportError)


def _wait(state: RetryCallState) -> float:
    """2, 4, 8 s plus jitter; honor Retry-After when present."""
    base = 2.0**state.attempt_number + random.uniform(0, 0.5)
    exc = state.outcome.exception() if state.outcome else None
    if isinstance(exc, RetryableStatus):
        ra = exc.response.headers.get("Retry-After")
        if ra and ra.isdigit():
            return max(base, float(ra))
    return base


class CivicClient:
    def __init__(
        self,
        base_url: str,
        *,
        testdata: bool = False,
        concurrency: int = 4,
        jitter_s: float = 0.5,
        breaker_threshold: int = 5,
        breaker_pause_s: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.testdata = testdata
        self._sem = asyncio.Semaphore(concurrency)
        self._jitter_s = jitter_s
        self._sleep = sleep
        self._clock = clock
        self._breaker_threshold = breaker_threshold
        self._breaker_pause_s = breaker_pause_s
        self._consecutive_429 = 0
        self._open_until = 0.0
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(READ_TIMEOUT_S, connect=5.0),
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def clock(self) -> float:
        return self._clock()

    @property
    def breaker_open(self) -> bool:
        return self._clock() < self._open_until

    def _note_status(self, status: int) -> None:
        if status == 429:
            self._consecutive_429 += 1
            if self._consecutive_429 >= self._breaker_threshold:
                self._open_until = self._clock() + self._breaker_pause_s
                self._consecutive_429 = 0
                log.warning("circuit breaker open for %.0f s", self._breaker_pause_s)
        else:
            self._consecutive_429 = 0

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        deadline: float | None = None,
        attempts: int = 2,
    ) -> Fetch:
        """deadline (on this client's clock): if the slot only frees up after it, return
        error "deadline" without sending. In-flight requests are never cancelled."""
        params = dict(params or {})
        if self.testdata and path.startswith(RACE_PATH_PREFIX):
            params["testdata"] = "true"
        if self.breaker_open:
            return Fetch(None, 0, 0, None, "circuit_open")
        async with self._sem:
            if deadline is not None and self._clock() >= deadline:
                return Fetch(None, 0, 0, None, DEADLINE)
            if self._jitter_s:
                await self._sleep(random.uniform(0, self._jitter_s))
            t0 = time.perf_counter()
            try:
                resp = await self._send(path, params, timeout, attempts)
            except RetryableStatus as exc:
                r = exc.response
                ms = int((time.perf_counter() - t0) * 1000)
                return Fetch(r.status_code, ms, len(r.content), None, f"http:{r.status_code}")
            except httpx.HTTPError as exc:
                ms = int((time.perf_counter() - t0) * 1000)
                return Fetch(None, ms, 0, None, f"transport:{type(exc).__name__}")
            ms = int((time.perf_counter() - t0) * 1000)
            if resp.status_code >= 400:
                return Fetch(
                    resp.status_code, ms, len(resp.content), None, f"http:{resp.status_code}"
                )
            try:
                data = resp.json()
            except ValueError:
                return Fetch(resp.status_code, ms, len(resp.content), None, "json:decode")
            return Fetch(resp.status_code, ms, len(resp.content), data, None)

    async def _send(
        self,
        path: str,
        params: dict[str, Any],
        timeout: float | None = None,
        attempts: int = 2,
    ) -> httpx.Response:
        retrying = AsyncRetrying(
            # 2 attempts by default (was 3): every cycle retries anyway, and on election
            # night each retry of a 40 s timeout kept the whole cycle waiting
            stop=stop_after_attempt(attempts),
            wait=_wait,
            retry=retry_if_exception(_retryable),
            sleep=self._sleep,
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                if self.breaker_open:
                    raise httpx.TransportError("circuit_open")
                kwargs = {"timeout": httpx.Timeout(timeout, connect=5.0)} if timeout else {}
                resp = await self._client.get(path, params=params, **kwargs)
                self._note_status(resp.status_code)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise RetryableStatus(resp)
                return resp
        raise AssertionError("unreachable")
