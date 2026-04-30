"""Validate externally published Flow Workstream operator skills.

The official workstream skill under ``docs/skills`` is shipped to personal
operators, so CI validates it without depending on a developer-local Codex path.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOTS = (
    ROOT / "docs" / "skills",
    ROOT / "skills",
)


def main() -> int:
    errors: list[str] = []
    existing_roots = [root for root in SKILL_ROOTS if root.exists()]
    if not existing_roots:
        print("No external skills found.")
        return 0

    for skills_root in existing_roots:
        for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                errors.append(f"{skill_dir.relative_to(ROOT)} is missing SKILL.md")
                continue
            text = skill_file.read_text(encoding="utf-8")
            errors.extend(_validate_skill(skill_dir, text))

    docs_skill = ROOT / "docs" / "skills" / "flow-workstream" / "SKILL.md"
    packaged_skill = ROOT / "skills" / "flow-workstream" / "SKILL.md"
    if docs_skill.exists() and packaged_skill.exists():
        if docs_skill.read_text(encoding="utf-8") != packaged_skill.read_text(encoding="utf-8"):
            errors.append(
                "docs/skills/flow-workstream/SKILL.md and "
                "skills/flow-workstream/SKILL.md must stay identical"
            )

    if errors:
        print("External skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("External skill validation passed.")
    return 0


def _validate_skill(skill_dir: Path, text: str) -> list[str]:
    errors: list[str] = []
    rel = skill_dir.relative_to(ROOT)
    frontmatter = _frontmatter(text)
    if not frontmatter:
        return [f"{rel}/SKILL.md is missing YAML frontmatter"]

    for field in ("name", "description"):
        if not frontmatter.get(field):
            errors.append(f"{rel}/SKILL.md frontmatter missing {field}")

    required_terms = [
        "WORKSTREAM_API_BASE_URL",
        "x-garden-user-id",
        "x-garden-session-token",
        "GET /v1/tasks",
        "POST /v1/submissions",
        "Operator Minimum Requirements",
        "Do not add an `operator_id` query parameter",
    ]
    for term in required_terms:
        if term not in text:
            errors.append(f"{rel}/SKILL.md missing required term: {term}")

    forbidden_terms = [
        "jarvis-miner",
        "admin cli",
        "APIFY_API_TOKEN",
        "FLOW_WORKSTREAM_API_BASE_URL",
        "JARVIS_OPERATOR_SECRET",
        "JARVIS_OPERATOR_ID",
        "JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON",
    ]
    lower_text = text.casefold()
    for term in forbidden_terms:
        if term.casefold() in lower_text:
            errors.append(f"{rel}/SKILL.md contains internal/operator-confusing term: {term}")

    for reference in re.findall(r"references/[A-Za-z0-9_.-]+\.md", text):
        if not (skill_dir / reference).exists():
            errors.append(f"{rel}/SKILL.md references missing file: {reference}")

    return errors


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    try:
        _, raw, _body = text.split("---\n", 2)
    except ValueError:
        return {}
    values: dict[str, str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


if __name__ == "__main__":
    raise SystemExit(main())
