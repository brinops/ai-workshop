"""`control-plane.yaml`: which repositories are watched and which skill / agent / validator handle which check.

Domain knowledge lives in the standard `.claude/` layout (skills, agents, scripts inside skills); this file
only wires it together. Routing is deterministic — by the name of the failed CI check — so a PR cannot
steer the pipeline to a different agent or a wider set of editable paths.
"""

from __future__ import annotations

import fnmatch
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.config import REPO_ROOT, get_settings

REPO_RE = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
NAME_RE = r"^[a-z0-9][a-z0-9-]*$"


class ConfigError(ValueError):
    pass


class Route(BaseModel):
    check: str = Field(min_length=1, description="CI check-run name that selects this route")
    analysis_skill: str = Field(pattern=NAME_RE)
    remediation_agent: str = Field(pattern=NAME_RE)
    validator: str = Field(description="script run by CI, the backend and the agent (relative to the control plane root)")
    allowed_paths: list[str] = Field(min_length=1, description="globs the fix may touch")
    max_changed_lines: int = Field(default=40, gt=0)
    max_attempts: int = Field(default=2, gt=0, le=5)

    def in_scope(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pat) for pat in self.allowed_paths)

    @property
    def scan_roots(self) -> list[str]:
        """Directories handed to the validator: the literal prefix of every allowed glob."""
        roots = []
        for pat in self.allowed_paths:
            prefix = re.split(r"[*?\[]", pat, maxsplit=1)[0].rstrip("/")
            roots.append(prefix or ".")
        return sorted(set(roots))

    @property
    def validator_path(self) -> Path:
        return (REPO_ROOT / self.validator).resolve()


class Repository(BaseModel):
    repo: str = Field(pattern=REPO_RE)
    protected_branches: list[str] = ["main", "master", "release/*", "production"]
    routes: list[Route] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_checks(self) -> Repository:
        checks = [r.check for r in self.routes]
        if len(checks) != len(set(checks)):
            raise ValueError(f"{self.repo}: duplicate route check names {checks}")
        return self

    @property
    def required_checks(self) -> list[str]:
        return [r.check for r in self.routes]

    def route(self, check: str | None) -> Route | None:
        return next((r for r in self.routes if r.check == check), None)

    def is_protected(self, branch: str) -> bool:
        return any(fnmatch.fnmatch(branch, pat) for pat in self.protected_branches)


AgentName = Annotated[str, Field(pattern=NAME_RE)]
JiraImplementation = Literal["booking", "static-page"]


class JiraRoute(BaseModel):
    description: str = Field(min_length=1)
    execution_agent: AgentName
    qa_agent: AgentName
    implementation: JiraImplementation = "booking"


class ControlPlaneConfig(BaseModel):
    repositories: list[Repository] = Field(min_length=1)
    jira_routes: dict[AgentName, JiraRoute] = Field(default_factory=dict)

    def repository(self, repo: str) -> Repository | None:
        return next((r for r in self.repositories if r.repo.lower() == repo.lower()), None)

    def problems(self, root: Path = REPO_ROOT) -> list[str]:
        """References that do not resolve to files in the standard `.claude/` layout."""
        out = []
        for repo in self.repositories:
            for r in repo.routes:
                where = f"{repo.repo} → {r.check}"
                if not (root / ".claude" / "skills" / r.analysis_skill / "SKILL.md").exists():
                    out.append(f"{where}: skill .claude/skills/{r.analysis_skill}/SKILL.md not found")
                if not (root / ".claude" / "agents" / f"{r.remediation_agent}.md").exists():
                    out.append(f"{where}: agent .claude/agents/{r.remediation_agent}.md not found")
                if not (root / r.validator).is_file():
                    out.append(f"{where}: validator {r.validator} not found")
        for route_id, route in self.jira_routes.items():
            for name in (route.execution_agent, route.qa_agent):
                if not (root / ".claude" / "agents" / f"{name}.md").is_file():
                    out.append(f"Jira → {route_id}: agent .claude/agents/{name}.md not found")
        return out


def config_path() -> Path:
    p = Path(get_settings().control_plane_config)
    return p if p.is_absolute() else REPO_ROOT / p


def load(path: Path | None = None) -> ControlPlaneConfig:
    path = path or config_path()
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"{path} not found — copy control-plane.yaml from the repository root") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    try:
        cfg = ControlPlaneConfig.model_validate(raw)
    except ValueError as exc:
        raise ConfigError(f"{path} is invalid: {exc}") from exc
    if problems := cfg.problems():
        raise ConfigError(f"{path}: " + "; ".join(problems))
    return cfg


@lru_cache
def get_config() -> ControlPlaneConfig:
    return load()
