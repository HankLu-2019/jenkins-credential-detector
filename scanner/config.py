"""Configuration loader using Pydantic Settings + YAML."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class JenkinsInstance(BaseModel):
    name: str
    jobs_path: Path
    description: str = ""


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    timeout_seconds: int = 120
    max_chunk_lines: int = 50


class ScanConfig(BaseModel):
    initial_backfill_days: int = 7
    concurrency: int = 4
    max_log_size_bytes: int = 50 * 1024 * 1024  # 50 MB


class NotificationsConfig(BaseModel):
    channels: list[str] = Field(default_factory=list)
    fallback_recipient: str = ""
    min_severity: str = "HIGH"


class TruffleHogConfig(BaseModel):
    binary: str = "trufflehog"
    extra_args: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_nested_delimiter="__")

    database_url: str = "postgresql://sentinel:sentinel@localhost:5432/sentinel"
    jenkins_instances: list[JenkinsInstance] = Field(default_factory=list)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    trufflehog: TruffleHogConfig = Field(default_factory=TruffleHogConfig)


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from YAML file, then overlay environment variables."""
    raw: dict[str, Any] = {}

    path = config_path or os.environ.get("SENTINEL_CONFIG", "config.yml")
    path = Path(path)
    if path.exists():
        with path.open() as f:
            raw = yaml.safe_load(f) or {}

    return Settings(**raw)
