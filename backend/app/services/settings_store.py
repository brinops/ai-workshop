"""Persisted automation settings (Auto Analyze / Auto Remediate / Auto Push)."""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Setting
from app.services.events import record_event

KEY = "automation"


class Automation(BaseModel):
    auto_analyze: bool
    auto_remediate: bool
    auto_push: bool


def defaults() -> Automation:
    s = get_settings()
    return Automation(
        auto_analyze=s.default_auto_analyze,
        auto_remediate=s.default_auto_remediate,
        auto_push=s.default_auto_push,
    )


def get_automation(db: Session) -> Automation:
    row = db.get(Setting, KEY)
    if row is None:
        value = defaults()
        db.add(Setting(key=KEY, value=value.model_dump()))
        db.flush()
        return value
    return Automation(**{**defaults().model_dump(), **row.value})


def update_automation(db: Session, **changes: bool | None) -> Automation:
    current = get_automation(db)
    updated = current.model_copy(update={k: v for k, v in changes.items() if v is not None})
    row = db.get(Setting, KEY)
    assert row is not None
    row.value = updated.model_dump()
    diff = {k: v for k, v in updated.model_dump().items() if current.model_dump()[k] != v}
    if diff:
        record_event(db, None, "settings_changed",
                     "Automation updated: " + ", ".join(f"{k}={'on' if v else 'off'}" for k, v in diff.items()),
                     data=diff)
    return updated
