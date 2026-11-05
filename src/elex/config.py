"""Runtime settings, read from env vars (prefix ELEX_) and .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ELEX_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    testdata: bool = False
    include_test_data: bool = False
    interval_s: int = 60
    # Risk fallback: widen these via env (ELEX_TIER_A_S etc.) if civicAPI slows down
    tier_a_s: int = 60
    tier_b_s: int = 180
    tier_c_s: int = 600
    tier_c_max_per_cycle: int = 60
    web_dist: Path = Path("web/dist")  # built dashboard served at / by the API
    concurrency: int = 8  # parallel civicAPI requests (it answered in ~22 s on the night)
    search_refresh_s: int = 90  # race totals for every race from search (search_refresh.py)
    cycle_budget_s: float = 45.0  # stop starting new polls after this; in-flight ones finish
    civic_base_url: str = "https://civicapi.org/api/v2"
    census_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("CENSUS_API_KEY", "census_api_key")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
