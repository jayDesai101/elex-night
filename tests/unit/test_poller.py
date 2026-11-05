import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import respx

from elex.civic.client import CivicClient
from elex.ingest.poller import due_races

NOW = datetime(2026, 11, 4, 2, 0, tzinfo=UTC)
BASE = "https://civicapi.test/api/v2"


def test_due_races_by_tier() -> None:
    tiers = {1: "A", 2: "B", 3: "C", 4: "C"}
    last = {
        1: NOW - timedelta(seconds=60),
        2: NOW - timedelta(seconds=120),
        3: NOW - timedelta(seconds=601),
    }
    assert due_races(tiers, last, NOW) == [4, 3, 1]  # never-polled, then most overdue


def test_stale_tier_b_jumps_ahead_of_fresh_tier_a() -> None:
    # KY-Sen (tier B) unpolled for an hour must not wait behind tier A polled a minute ago.
    tiers = {1: "A", 2: "A", 87174: "B"}
    last = {
        1: NOW - timedelta(seconds=60),
        2: NOW - timedelta(seconds=70),
        87174: NOW - timedelta(seconds=3600),
    }
    assert due_races(tiers, last, NOW) == [87174, 2, 1]


def test_longest_waiting_first_within_uncapped_tier() -> None:
    # A budget cut after the first few races must not always skip the high ids.
    tiers = {87068: "A", 87174: "A", 87472: "A"}
    last = {
        87068: NOW - timedelta(seconds=60),
        87174: NOW - timedelta(seconds=3600),
        87472: NOW - timedelta(seconds=7200),
    }
    assert due_races(tiers, last, NOW) == [87472, 87174, 87068]


def test_race_polled_late_in_cycle_is_due_next_cycle() -> None:
    # polled 10 s into the previous cycle -> only 50 s elapsed at this cycle's start
    last = {1: NOW - timedelta(seconds=50)}
    assert due_races({1: "A"}, last, NOW) == [1]
    # but not polled again within 45 s (60 s interval minus 15 s slack)
    assert due_races({1: "A"}, {1: NOW - timedelta(seconds=44)}, NOW) == []


def test_slack_is_capped_for_slow_tiers() -> None:
    assert due_races({1: "C"}, {1: NOW - timedelta(seconds=585)}, NOW) == [1]
    assert due_races({1: "C"}, {1: NOW - timedelta(seconds=584)}, NOW) == []


def test_tier_c_capped_longest_waiting_first() -> None:
    tiers = {i: "C" for i in range(1, 101)} | {500: "A"}
    last = {i: NOW - timedelta(seconds=600 + i) for i in range(1, 91)}  # 91..100 never polled
    due = due_races(tiers, last, NOW)
    assert due[0] == 500  # tier A is never capped and comes first
    c = due[1:]
    assert len(c) == 60
    assert set(range(91, 101)) <= set(c)  # never-polled races go first
    assert set(c) - set(range(91, 101)) == set(range(41, 91))  # then the oldest polls


def test_cap_can_be_disabled() -> None:
    tiers = {i: "C" for i in range(100)}
    assert len(due_races(tiers, {}, NOW, max_per_cycle={})) == 100


def test_due_races_tier_a_first() -> None:
    assert due_races({9: "C", 5: "B", 7: "A"}, {}, NOW) == [7, 5, 9]


async def _nosleep(_: float) -> None:
    return None


def _client(clock=lambda: 0.0) -> CivicClient:
    return CivicClient(BASE, jitter_s=0, sleep=_nosleep, clock=clock)


@respx.mock
def test_retry_429_then_200() -> None:
    route = respx.get(f"{BASE}/status").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"status": "ok"})]
    )
    f = asyncio.run(_client().get("/status"))
    assert f.error is None and f.data == {"status": "ok"}
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_two_attempts_by_default() -> None:
    route = respx.get(f"{BASE}/status").mock(return_value=httpx.Response(503))
    f = asyncio.run(_client().get("/status"))
    assert f.error == "http:503" and route.call_count == 2
    asyncio.run(_client().get("/status", attempts=1))
    assert route.call_count == 3  # one more call, no retry
    asyncio.run(_client().get("/status", attempts=3))
    assert route.call_count == 6


@respx.mock
def test_five_429s_open_breaker() -> None:
    t = [0.0]
    route = respx.get(f"{BASE}/status").mock(return_value=httpx.Response(429))
    c = _client(clock=lambda: t[0])

    async def go():
        a = await c.get("/status", attempts=3)  # 3 attempts
        b = await c.get("/status", attempts=3)  # 2 more -> 5 consecutive -> breaker opens
        blocked = await c.get("/status")
        t[0] = 121.0
        reopened = c.breaker_open
        return a, b, blocked, reopened

    a, b, blocked, reopened = asyncio.run(go())
    assert a.error == "http:429"
    assert route.call_count == 5
    assert blocked.error == "circuit_open"
    assert reopened is False


@respx.mock
def test_testdata_param_only_on_race_calls() -> None:
    race = respx.get(f"{BASE}/race/1", params={"testdata": "true"}).mock(
        return_value=httpx.Response(200, json={})
    )
    status = respx.get(f"{BASE}/status").mock(return_value=httpx.Response(200, json={}))
    c = CivicClient(BASE, testdata=True, jitter_s=0, sleep=_nosleep)

    async def go():
        await c.get("/race/1")
        await c.get("/status")

    asyncio.run(go())
    assert race.called and status.called
    assert "testdata" not in str(status.calls[0].request.url)


@respx.mock
def test_read_timeouts_race_short_search_long() -> None:
    from elex.civic.client import READ_TIMEOUT_S, SEARCH_TIMEOUT_S

    race = respx.get(f"{BASE}/race/1").mock(return_value=httpx.Response(200, json={}))
    search = respx.get(f"{BASE}/race/search").mock(return_value=httpx.Response(200, json={}))
    c = _client()

    async def go():
        await c.get("/race/1")
        await c.get("/race/search", {"country": "US"}, timeout=SEARCH_TIMEOUT_S)

    asyncio.run(go())
    assert race.calls[0].request.extensions["timeout"]["read"] == READ_TIMEOUT_S == 40.0
    assert READ_TIMEOUT_S < SEARCH_TIMEOUT_S
    assert search.calls[0].request.extensions["timeout"]["read"] == SEARCH_TIMEOUT_S


@respx.mock
def test_deadline_passed_sends_nothing() -> None:
    route = respx.get(f"{BASE}/race/1").mock(return_value=httpx.Response(200, json={}))
    c = _client(clock=lambda: 100.0)
    f = asyncio.run(c.get("/race/1", deadline=99.0))
    assert f.error == "deadline" and not route.called
    ok = asyncio.run(c.get("/race/1", deadline=101.0))
    assert ok.error is None and route.call_count == 1
