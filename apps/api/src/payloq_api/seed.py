"""Seed default user + good / weak / cash_critical scenarios."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from payloq_api.auth import hash_password
from payloq_api.config import get_settings
from payloq_api.db import get_engine, init_db
from payloq_api.models import Scenario, User

PRESETS = (
    ("good", "Hyvä tilanne", "Good situation"),
    ("weak", "Heikko tulos", "Weak result"),
    ("cash_critical", "Kriittinen kassa", "Cash critical"),
)


def seed(session: Session | None = None) -> None:
    settings = get_settings()
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    own_session = session is None
    if own_session:
        session = Session(get_engine())
    assert session is not None

    try:
        user = session.exec(select(User).where(User.username == settings.auth_username)).first()
        if user is None:
            session.add(
                User(
                    username=settings.auth_username,
                    password_hash=hash_password(settings.auth_password),
                    display_name="PayLoq",
                )
            )

        for slug, title_fi, title_en in PRESETS:
            path = settings.repo_root / "scenarios" / slug / "input.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            desc = data.get("scenario_description", {})
            existing = session.exec(select(Scenario).where(Scenario.slug == slug)).first()
            now = datetime.now(timezone.utc)
            if existing is None:
                session.add(
                    Scenario(
                        slug=slug,
                        title_fi=title_fi,
                        title_en=title_en,
                        description_fi=desc.get("fi", title_fi),
                        description_en=desc.get("en", title_en),
                        is_preset=True,
                        input_json=data,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                existing.title_fi = title_fi
                existing.title_en = title_en
                existing.description_fi = desc.get("fi", title_fi)
                existing.description_en = desc.get("en", title_en)
                existing.is_preset = True
                existing.input_json = data
                existing.updated_at = now
                session.add(existing)

        session.commit()
    finally:
        if own_session:
            session.close()


def main() -> None:
    seed()
    print("Seeded user + preset scenarios (good, weak, cash_critical).")


if __name__ == "__main__":
    main()
