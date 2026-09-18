"""
Centralized, typed configuration for RootTrace.

Why this exists: hardcoding file paths (and, from Step 2 onward, API keys)
directly in code is both inflexible and a security risk once secrets are
involved. pydantic-settings reads values from a .env file (or real
environment variables in production) and validates them with the same
fail-fast approach as models.py.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    logs_path: Path = Path("mock_data/logs.json")
    deployments_path: Path = Path("mock_data/deployment_history.json")
    output_path: Path = Path("incident_timeline.json")


settings = Settings()