"""Configuration system for trans-epub.

Glossary loading for character pronouns and terminology.
"""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass, field
from pathlib import Path

# ── Search paths ──────────────────────────────────────────────────────────────

_CONFIG_DIR = Path(".trans-epub")
_USER_CONFIG_DIR = Path.home() / ".config" / "trans-epub"


def _find_file(filename: str) -> Path | None:
    """Find file in project-local then user-global config dirs."""
    for base in [_CONFIG_DIR, _USER_CONFIG_DIR]:
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None


# ── TOML loading ──────────────────────────────────────────────────────────────


def _load_toml(path: Path) -> dict[str, Any]:
    """Load TOML file, return empty dict on failure."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef, import-untyped]
        except ImportError:
            return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Glossary ──────────────────────────────────────────────────────────────────


@dataclass
class CharacterEntry:
    """Pronoun mapping for a character."""

    self_ref: str | None = None  # xưng (self-reference)
    address: str | None = None  # hô (how others address them)
    narrator: str | None = None  # narrator reference
    note: str | None = None  # context (age, role, relationship)

    def is_empty(self) -> bool:
        return not any([self.self_ref, self.address, self.narrator, self.note])


@dataclass
class Glossary:
    """Translation glossary with character pronouns and term mappings."""

    characters: dict[str, CharacterEntry] = field(default_factory=dict)
    terms: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.characters and not self.terms


def load_glossary(path: Path | None = None) -> Glossary | None:
    """Load glossary from path or auto-detect.

    Returns None if not found or empty.
    """
    glossary_file = path or _find_file("glossary.toml")
    if not glossary_file:
        return None

    data = _load_toml(glossary_file)
    if not data:
        return None

    characters: dict[str, CharacterEntry] = {}
    for name, entry in data.get("characters", {}).items():
        if isinstance(entry, str):
            # Simple form: John = "anh"
            characters[name] = CharacterEntry(address=entry)
        elif isinstance(entry, dict):
            char = CharacterEntry(
                self_ref=entry.get("self"),
                address=entry.get("form"),
                narrator=entry.get("narrator"),
                note=entry.get("note"),
            )
            if not char.is_empty():
                characters[name] = char

    terms: dict[str, str] = data.get("terms", {})

    glossary = Glossary(characters=characters, terms=terms)
    return None if glossary.is_empty() else glossary


def build_glossary_prompt(glossary: Glossary) -> str:
    """Build prompt section from glossary for LLM injection."""
    if glossary.is_empty():
        return ""

    parts = ["\nGlossary (follow strictly for consistency):"]

    if glossary.characters:
        parts.append("Characters (pronouns):")
        for name, entry in glossary.characters.items():
            details = []
            if entry.self_ref:
                details.append(f'self="{entry.self_ref}"')
            if entry.address:
                details.append(f'address="{entry.address}"')
            if entry.narrator:
                details.append(f'narrator="{entry.narrator}"')
            detail_str = ", ".join(details)
            if entry.note:
                detail_str += f" — {entry.note}"
            parts.append(f"• {name}: {detail_str}")

    if glossary.terms:
        parts.append("Terms:")
        for eng, vi in glossary.terms.items():
            parts.append(f'• "{eng}" → "{vi}"')

    return "\n".join(parts) + "\n"


def validate_glossary(glossary: Glossary) -> list[str]:
    """Validate glossary entries and return list of warnings.

    Checks: empty character entries, empty term keys/values,
    suspiciously short or long values, duplicate mappings.
    """
    warnings: list[str] = []

    for name, entry in glossary.characters.items():
        if entry.is_empty():
            warnings.append(f"Character '{name}' has no pronoun fields — skipped")
        elif not entry.address and not entry.self_ref:
            warnings.append(
                f"Character '{name}' has no address or self-ref — may be ignored"
            )
        if not name.strip():
            warnings.append("Character entry with empty name — skipped")

    for eng, vi in glossary.terms.items():
        if not eng.strip():
            warnings.append("Term with empty English key — skipped")
        elif not vi.strip():
            warnings.append(f"Term '{eng}' has empty Vietnamese value — skipped")
        elif len(eng.strip()) < 2:
            warnings.append(
                f"Term '{eng}' is very short (1 char) — might cause false matches"
            )

    return warnings


def scan_glossary_matches(
    glossary: Glossary, chapter_texts: list[str]
) -> dict[str, int]:
    """Scan chapter texts for glossary term occurrences.

    Returns dict mapping each English term to its match count across all chapters.
    Case-insensitive matching.
    """
    matches: dict[str, int] = {}
    combined = " ".join(chapter_texts).lower()

    for eng in glossary.terms:
        count = combined.count(eng.lower())
        matches[eng] = count

    for name in glossary.characters:
        count = combined.count(name.lower())
        matches[f"[character] {name}"] = count

    return matches
