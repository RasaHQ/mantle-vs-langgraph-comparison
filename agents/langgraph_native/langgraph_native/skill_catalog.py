"""Skill catalog text from ``agents/mantle_combined`` — same as Mantle's routing list."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

MANTLE_AGENT_DIR_ENV = "MANTLE_AGENT_DIR"
_FRONT_MATTER_DELIMITER = "---"


def mantle_agent_dir() -> Path:
    """Returns the Mantle agent directory skill content is read from."""
    default = Path(__file__).resolve().parents[2] / "mantle_combined"
    return Path(os.environ.get(MANTLE_AGENT_DIR_ENV, default))


@lru_cache(maxsize=1)
def routable_skills() -> tuple[tuple[str, str, str], ...]:
    """Each entry is ``(id, name, description)`` for one non-engine-managed skill."""
    root = mantle_agent_dir() / "skills"
    entries: list[tuple[str, str, str]] = []
    for skill_dir in sorted(root.iterdir()):
        path = skill_dir / "skill.md"
        if not path.exists():
            continue
        spec = _load_skill_front_matter(path, skill_dir.name)
        if spec["engine_managed"]:
            continue
        entries.append((spec["id"], spec["name"], spec["description"]))
    if not entries:
        raise FileNotFoundError(f"No routable skills under {root}")
    return tuple(entries)


def skills_catalog_section() -> str:
    """Returns the same ``## Skills`` block Mantle's orchestrator uses."""
    lines = [
        f"- `{skill_id}` ({name}): {description}"
        for skill_id, name, description in routable_skills()
    ]
    return "## Skills\n" + "\n".join(lines)


def _load_skill_front_matter(path: Path, skill_id: str) -> dict[str, Any]:
    front_matter, _body = _split_front_matter(path.read_text(encoding="utf-8"))
    return {
        "id": skill_id,
        "name": str(front_matter["name"]).strip(),
        "description": str(front_matter.get("description", "")).strip(),
        "engine_managed": bool(
            (front_matter.get("routing") or {}).get("engine_managed")
        ),
    }


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONT_MATTER_DELIMITER:
        raise ValueError("skill.md must start with YAML front matter")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONT_MATTER_DELIMITER:
            front_matter = yaml.safe_load("".join(lines[1:index])) or {}
            return front_matter, "".join(lines[index + 1 :]).strip()
    raise ValueError("skill.md front matter is not closed")
