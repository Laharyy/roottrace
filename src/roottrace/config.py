from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    logs_path: Path = Path("mock_data/logs.json")
    deployments_path: Path = Path("mock_data/deployment_history.json")
    output_path: Path = Path("incident_timeline.json")

    postmortems_dir: Path = Path("mock_data/postmortems")
    voyage_api_key: Optional[str] = None

    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None

    github_token: Optional[str] = None
    github_repo: Optional[str] = None


settings = Settings()