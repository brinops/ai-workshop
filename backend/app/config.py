"""Runtime configuration. Every value can be overridden by an environment variable or `.env`."""

from __future__ import annotations

import shutil
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env",), extra="ignore")

    # --- service
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    public_url: str = "http://127.0.0.1:8000"
    data_dir: Path = REPO_ROOT / "var"
    database_url: str | None = None
    rcp_api_token: str | None = None  # optional bearer token required by /api/tasks/register
    run_worker: bool = True  # run the worker loop inside the API process
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173"]

    # --- GitHub
    github_token: str | None = None  # falls back to `gh auth token`
    github_api_url: str = "https://api.github.com"
    github_webhook_secret: str | None = None
    git_remote_template: str = "git@github.com:{repo}.git"
    ci_poll_interval_seconds: int = 15
    ci_wait_timeout_seconds: int = 1200
    git_author_name: str = "RCP Remediation Agent"
    git_author_email: str = "rcp-agent@users.noreply.github.com"

    # --- Claude Code
    claude_bin: str = "claude"
    claude_model: str = "sonnet"
    analysis_timeout_seconds: int = 420
    remediation_timeout_seconds: int = 600
    agent_max_budget_usd: float = 2.0
    max_concurrent_agents: int = 2
    analysis_max_runs: int = 2  # agent crashes tolerated per analysis stage
    min_confidence_for_auto_fix: float = 0.6

    # --- repositories, routes (check → skill / agent / validator / allowed paths)
    control_plane_config: str = "control-plane.yaml"  # relative to the repository root

    # --- validation
    validator_python: str = sys.executable
    validator_timeout_seconds: int = 300

    # --- Slack
    slack_webhook_url: str | None = None

    # --- Jira workshop
    workshop_slack_router_url: str | None = None
    workshop_slack_signing_secret: SecretStr | None = None
    workshop_slack_workspace_id: str | None = None
    workshop_slack_channel_id: str | None = None
    workshop_slack_bot_token: SecretStr | None = None
    workshop_slack_app_token: SecretStr | None = None
    jira_workshop_profile_id: str | None = None
    jira_workshop_poll_interval_seconds: float = Field(default=5, ge=0)
    jira_workshop_agent_timeout_seconds: float = Field(default=120, gt=0)
    jira_workshop_dialog_enabled: bool = True

    # --- worker
    worker_tick_seconds: float = 2.0
    lease_seconds: int = 60
    heartbeat_seconds: int = 15

    # --- default automation (persisted copy in DB wins after first start)
    default_auto_analyze: bool = True
    default_auto_remediate: bool = True
    default_auto_push: bool = False

    extra_env_passthrough: list[str] = Field(default_factory=list)

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'rcp.db'}"

    @property
    def claude_path(self) -> str | None:
        return shutil.which(self.claude_bin)


@lru_cache
def get_settings() -> Settings:
    return Settings()
