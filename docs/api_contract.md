# civicAPI v2 contract (observed 2026-11-03)

Every fact below was read with `jq` from a fixture in `tests/fixtures/civicapi/`; the file is in brackets.
Anything not observed is marked **UNVERIFIED**.

## Endpoints

| Call | Observed | Fixture |
| --- | --- | --- |
| `GET /status` | `{"status":"ok"}` | [status.json] |
| `GET /getElectionDates?country=US` | object with keys `months`, `total_unique_dates`, `year` | [election_dates.json] |
| `GET /race/search` | object `{count, limit, offset, races[]}`; `count` is the size of **this page**, not the total | [search_20261103_p0.json] |
| `GET /race/{id}` | 20 top-level keys (below) | [race_87087.json] |
| `GET /race/{id}?light=true` | same keys minus `region_results` | [race_3827_light.json] |
| `GET /race/{id}?testdata=true` | random votes and `percent_reporting`, a fresh `last_updated`, but **`test_data` stays `false`** | [race_87087_testdata.json] |
| `GET /race/{id}/history` | `{id, count, raw, filtered, timestamps[]}`, newest first. Races whose results have not changed yet return **404 `{"error":"no history found for this race!"}`** (3827, 87087 on 2026-11-03); that means "no snapshots yet", not a missing route. `?raw=true` flips `raw`/`filtered` but returned the same timestamps. | [history_160886.json] |
| `GET /race/{id}/history/{timestamp}` | `{timestamp, data}`; `data` is a full race payload that parses as `CivicRace`. Timestamp format `YYYY-MM-DDTHH:MM:SS.sssZ`. A bad timestamp returns 404 `{"error":"snapshot not found!"}`. | [history_160886_snapshot.json] |

### Search behaviour (important for discovery)

- With only `country` + `start_date` + `end_date` = 2026-11-03, search returns 23,000+ races (23 full pages of 1000 rows, ~1 MB and ~20 s each) and is dominated by local contests. Unfiltered paging is too slow for discovery. [search_20261103_p0.json]
- Search rows use `election_type` as the **scope** (`Local`, `Statewide`, `General`, `Primary`) and `type` as the **office**. [search_20261103_p0.json, search_general_p0.json]
- `election_type=General` returns the federal races (`type` = `US Senate`, `House of Representatives`), but the date filter is not applied strictly: rows from 2020–2026 come back. Filter `election_date[:10] == "2026-11-03"` client-side. Of the 1000 rows on page 0, 649 were tonight: 436 House, 36 US Senate, 5 Delegate, 1 Governor, plus state legislative. [search_general_p0.json]
- Governors are under `election_type=Statewide`, `type` = `Governor` (39 tonight including territories VI, GU, MP). [search_20261103_p0.json]
- Under load the API returns `503 {"code":"DATABASE_TIMEOUT"}` for `query=` searches; `query=Senate` failed repeatedly. Prefer `election_type` filters.
- Search row keys: `candidates, country, district, election_date, election_name, election_type, has_breakdown, has_map, id, municipality, percent_reporting, province, type`. Search rows include `percent_reporting` but **not** `last_updated`. [search_20261103_p0.json]

## Race payload

Top-level keys: `candidates, country, district, election_date, election_name, election_scope, election_type, has_map, is_disputed, last_updated, maps, municipality, percent_reporting, polls_close, polls_open, province, region_results, registered_voters, round, test_data`. [race_87087.json]

**In the race payload the meaning flips:** `election_type` holds the office and `election_scope` the scope.

| Office | `election_type` (race) / `type` (search) | `election_scope` | `election_name` | `district` | Fixture |
| --- | --- | --- | --- | --- | --- |
| Senate | `US Senate` | `General` | `Georgia US Senate`, `Florida US Senate Special`, `Ohio US Senate Special General` | null | race_87087, search_general_p0 |
| Governor | `Governor` | `Statewide` | `Pennsylvania Governor` | null | race_87393 |
| House | `House of Representatives` | `General` | `Arizona US House 6` | `AZ-06` (2-letter + zero-padded number) | race_86922 |
| Primary (old) | `Primary` | `Statewide` | `New Jersey Governor Democratic Primary` | null | race_3827 |

- Search also contains an aggregate row id 87528, `province` = `US`, name `United States Senate`. It is not a state race → office `other`. [search_general_p0.json]
- Delegates (DC, GU, MP, AS, VI; `type` = `Delegate`, district `XX-AL`) → office `other`. [search_general_p0.json]
- Timestamps are ISO UTC strings with milliseconds: `election_date` `2026-11-03T05:00:00.000Z`, `polls_open` `2026-11-03T12:00:00.000Z`, `polls_close` `2026-11-04T00:00:00.000Z`. [race_87087.json]
- `percent_reporting` is a number (0–100), `round` is 1, `registered_voters` null, `is_disputed` false, `municipality` null. [race_87087.json]

### candidates[]

Keys: `name, candidate_id, party, incumbent, major_candidate, winner, advanced, color, votes, percent`. `advanced` exists for 2026 races but not for race 3827. [race_87087.json, race_3827.json]

### region_results{}

Keyed by slug (`appling`). Value keys: `name, type, fips, fill, percent_reporting, candidates[]`. [race_87087.json]

- **County regions carry `fips`, a 5-character string** (`"13001"`). Race 3827 (older) has no `fips`. [race_87087.json, race_3827.json]
- Region `type` values seen: `County`, `Township` (ME), `Town` (NH), `Borough`, `House District`, `Overseas`, `State` (AK). Non-county regions have no `fips`. ME and NH ship counties **and** towns in the same race, so filter on `type = 'County'` to avoid double counting. [race_87188.json, race_87284.json, race_86916.json]
- Region candidates have no `candidate_id`; keys are `name, party, votes, percent, color, winner, advanced, incumbent, major_candidate`. [race_87087.json]
- The earliest history snapshots (2026-10-22/23, weeks before the election, every candidate at 0 votes) list **race** candidates without `candidate_id` too (87011, 87012, 87390). `stg_civic__candidate_results` drops those rows.

### Party labels

The most common labels across search page 0 and General page 0 are `Republican`, `Nonpartisan`, `Democratic`, `Independent`, `Libertarian`, `Nonaffiliated`, `Green`, `Write-In`, `Constitution`, `U.S. Taxpayers`, `Unaffiliated`, plus a long tail of minor parties. [search_general_p0.json, search_20261103_p0.json]

## Classification rules (`elex.civic.classify`)

- `classify_office(election_type, province)`: `US Senate` → senate; `Governor` → governor; `House of Representatives` → house; province `US` → other; anything else → other.
- `party_code(party)`: `Democratic` → D, `Republican` → R, `Independent` / `Nonaffiliated` / `Unaffiliated` → I, everything else → O.
- Test data: civicAPI's `test_data` flag is unreliable in both directions: `false` on its own `?testdata=true` responses, and **`true` on all 18 real Pennsylvania races** (governor + every House district) from 22:33 UTC on election night, with genuine counts that match its search totals. The archiver therefore sets `test_data` from **our own `ELEX_TESTDATA` setting only** and ignores the payload flag.

## Fixtures

status, election_dates, search_20261103_p0 (page 0 of 23), search_general_p0, race_3827 (+ light), race_87087 GA-Sen (+ testdata), race_87393 PA-Gov (+ testdata), race_86922 AZ-06 (+ testdata), race_87188 ME-Sen, race_86916 AK-Sen, race_87284 NH-Gov, history_160886 (+ snapshot) Guam Governor.

## Reference sources (Chunk 3, loaded 2026-11-03 by `elex load-ref`)

| Table | Source | Notes |
| --- | --- | --- |
| `ref.county_baseline` | Public GitHub mirror `tonmcg/US_County_Level_Election_Results_08-24`, commit `8cccc82f`, files `{2020,2024}_US_County_Level_Presidential_Results.csv` | **Not MEDSL.** MEDSL County Presidential Returns (`doi:10.7910/DVN/VOQCHQ`, file id 13573089) returns `400 "required Guestbook response for guestbookID 458"` (name, email, institution, position). The user chose the mirror. 3,152 counties (2020), 3,160 (2024); `dem`/`rep` = Biden/Harris and Trump; `total` = all candidates. No Alaska boroughs (AK is excluded from the model anyway). |
| `ref.state_turnout_prior` | k0 = 2022 total ballots counted (University of Florida Election Lab, `https://election.lab.ufl.edu/data-downloads/turnoutdata/Turnout_2022G_v1.2.csv`, sourced from EAVS and state results) / the state's 2024 presidential votes in `ref.county_baseline` | Replaces the plan's MEDSL 2022 House totals (`doi:10.7910/DVN/IG0UN2`, guestbook-gated). All 51 states covered; k0 0.573–0.905, median 0.729. Ballots slightly exceed any one race's votes (undervotes), so k0 runs ~1–3% high; the model's shrinkage corrects it from fully reported counties. |
| `ref.county_features` | ACS 5-year **2024** (`api.census.gov/data/2024/acs/acs5`); all 8 variables confirmed via `/variables/<VAR>.json` (200) | 3,222 counties; negative sentinels → NULL. 1 county has no median income. |
| `land_sqmi` | Census Gazetteer 2025 counties: `https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_counties_national.zip` (pipe-delimited, `ALAND_SQMI`) | Also the source of names for the crosswalk. Connecticut appears as 2022 planning regions (091x0). |

### Region → FIPS findings from the live archive

- County regions in 2026 races carry `fips` for nearly all counties. Six have `fips` = null with odd casing (`Mcleod`, `Lac Qui Parle`, `Lake Of The Woods` MN; `Le Flore` OK; `Oglala Lakota` SD; `Lewis And Clark` MT); the name crosswalk resolves all of them. Use `coalesce(api fips, crosswalk fips)`.
- Connecticut regions use the old 8-county FIPS (09001–09015), which match neither the Gazetteer nor the 2024 baseline. CT stays allow-listed (unsupported in the model).
- `Doña Ana` (NM) loses its ñ in normalization; it is fixed by a row in `dbt/seeds/region_overrides.csv`.
- Kalawao, HI (15005) has no presidential votes in the mirror.
- Remaining unmatched (all CT): `reports/unmatched_regions.csv`.
