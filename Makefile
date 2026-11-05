.PHONY: check dq live-smoke backtest archive up

check:  ## the gate for every chunk
	uv run ruff check . && uv run ruff format --check .
	uv run pytest -q -x --tb=short -m "not slow and not live"
	@if [ -d web/node_modules ]; then cd web && npm run -s typecheck && npm run -s test -- --run; fi
dq:  ## dbt build + DQ tests on a warehouse built from recorded fixtures
	uv run elex fixture-warehouse data-test/warehouse/dbt_test.duckdb
	uv run dbt build --project-dir dbt --profiles-dir dbt --target test
live-smoke:
	uv run pytest -q -m live
backtest:
	uv run elex backtest && uv run pytest -q -m slow tests/model
archive:  ## tonight, in tmux or Docker
	uv run elex run --interval 60
up:  ## production: archiver + API (serves the dashboard at :8000)
	docker compose up -d --build
