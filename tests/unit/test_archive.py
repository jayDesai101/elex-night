import gzip
import json
from datetime import UTC, datetime

from elex.db import connect, init_db
from elex.ingest.archive import Archive, canonical_json, raw_path, sha256_hex

FETCHED = datetime(2026, 11, 4, 1, 2, 3, tzinfo=UTC)


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})
    assert canonical_json({"a": 1}) == b'{"a":1}'


def test_raw_path_format(tmp_path) -> None:
    sha = "abcdef0123456789" * 4
    p = raw_path(tmp_path, 87087, FETCHED, sha)
    assert p == tmp_path / "raw/civicapi/race/87087/20261104T010203Z_abcdef012345.json.gz"


def test_persist_dedupes_and_writes_raw(tmp_path, fixtures_dir) -> None:
    payload = json.loads((fixtures_dir / "civicapi/race_86922.json").read_text())
    con = connect(tmp_path)
    init_db(con)
    arch = Archive(con, tmp_path)
    first = arch.persist(86922, payload, FETCHED, test_flag=False)
    second = arch.persist(86922, payload, FETCHED.replace(minute=3), test_flag=False)
    assert first.is_new and not second.is_new
    assert first.sha == sha256_hex(canonical_json(payload))
    raw = raw_path(tmp_path, 86922, FETCHED, first.sha)
    assert json.loads(gzip.decompress(raw.read_bytes())) == payload
    assert con.execute("select count(*) from bronze.race_snapshots").fetchone()[0] == 1
    # a fresh Archive rebuilds the latest hash from the table
    assert not Archive(con, tmp_path).persist(86922, payload, FETCHED, False).is_new


def test_only_our_setting_marks_test_data(tmp_path, fixtures_dir) -> None:
    """civicAPI's own flag is ignored: false on its ?testdata=true responses, and true on
    real Pennsylvania payloads on election night (docs/api_contract.md)."""
    payload = json.loads((fixtures_dir / "civicapi/race_86922_testdata.json").read_text())
    assert payload["test_data"] is False  # civicAPI quirk, see api_contract.md
    con = connect(tmp_path)
    init_db(con)
    arch = Archive(con, tmp_path)
    arch.persist(86922, payload, FETCHED, test_flag=True)
    real = dict(payload, test_data=True, percent_reporting=50.0)  # flagged true, but real
    arch.persist(86922, real, FETCHED.replace(minute=5), test_flag=False)
    rows = con.execute("select test_data from bronze.race_snapshots order by fetched_at").fetchall()
    assert [r[0] for r in rows] == [True, False]


def test_schema_failure_keeps_raw_and_skips_insert(tmp_path, fixtures_dir) -> None:
    payload = json.loads((fixtures_dir / "civicapi/race_86922.json").read_text())
    del payload["last_updated"]
    con = connect(tmp_path)
    init_db(con)
    res = Archive(con, tmp_path).persist(86922, payload, FETCHED, False)
    assert res.error == "schema:last_updated"
    assert raw_path(tmp_path, 86922, FETCHED, res.sha).exists()
    assert con.execute("select count(*) from bronze.race_snapshots").fetchone()[0] == 0
