from datetime import UTC, datetime, timedelta

from elex.pipeline.static_export import file_name, step_key, steps_between, write_index


def test_file_names_match_the_web_client() -> None:
    # mirrors replayPath() in web/src/lib/replay.ts
    assert file_name("/api/health") == "health.json"
    assert file_name("/api/map?office=senate") == "map__office-senate.json"
    assert (
        file_name("/api/races?office=house&tracked=true") == "races__office-house_tracked-true.json"
    )
    assert (
        file_name("/api/races?tracked=true&office=house") == "races__office-house_tracked-true.json"
    )
    assert file_name("/api/races/87087/votes") == "races_87087_votes.json"


def test_steps_and_index(tmp_path) -> None:
    t0 = datetime(2026, 11, 3, 22, 0, tzinfo=UTC)
    steps = steps_between(t0, t0 + timedelta(minutes=25), timedelta(minutes=10))
    assert [s.minute for s in steps] == [0, 10, 20]
    assert step_key(steps[1]) == "20261103T221000Z"
    write_index(tmp_path, steps)
    import json

    idx = json.loads((tmp_path / "index.json").read_text())
    assert idx["keys"] == ["20261103T220000Z", "20261103T221000Z", "20261103T222000Z"]
    assert idx["steps"][0] == "2026-11-03T22:00:00Z"


def test_append_live_step_floor_and_index(tmp_path, monkeypatch) -> None:
    """A step is appended only when 10 minutes have passed since the last one, and the
    index grows by exactly that step."""
    from elex.pipeline import static_export as se

    written: list[str] = []
    monkeypatch.setattr(se, "export_step", lambda d, out, ids: written.append(out.name) or 1)
    t0 = datetime(2026, 11, 4, 1, 0, tzinfo=UTC)
    assert se.append_live_step(tmp_path, t0, [1]) == "20261104T010000Z"
    assert se.append_live_step(tmp_path, t0 + timedelta(minutes=9), [1]) is None
    assert se.append_live_step(tmp_path, t0 + timedelta(minutes=10), [1]) == "20261104T011000Z"
    idx = se.read_index(se.replay_root(tmp_path))
    assert idx["keys"] == written == ["20261104T010000Z", "20261104T011000Z"]
    assert idx["steps"] == ["2026-11-04T01:00:00Z", "2026-11-04T01:10:00Z"]
