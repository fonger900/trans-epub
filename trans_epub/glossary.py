"""Glossary loading and prompt generation for consistent translations.

Provides character pronoun mappings and term glossaries to ensure
consistent Vietnamese translations across chapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Standard search paths for auto-detection
_GLOSSARY_PATHS: list[Path] = [
    Path(".trans-epub") / "glossary.toml",
    Path.home() / ".config" / "trans-epub" / "glossary.toml",
]


@dataclass
class CharacterEntry:
    """Pronoun mapping for a character."""

    self_ref: str | None = None  # xưng (self-reference)
    address: str | None = None  # hô (how others address them)
    narrator: str | None = None  # narrator reference
    note: str | None = None  # context (age, role, relationship)


@dataclass
class Glossary:
    """Translation glossary with character pronouns and term mappings."""

    characters: dict[str, CharacterEntry] = field(default_factory=dict)
    terms: dict[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Check if glossary has any entries."""
        return not self.characters and not self.terms


def load_glossary(path: Path) -> Glossary:
    """Load glossary from TOML file.

    Supports two formats for characters:
    - Simple: John = "anh" (just address pronoun)
    - Detailed: [characters.John] with self/form/narrator/note fields
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    data = tomllib.loads(path.read_text(encoding="utf-8"))

    characters: dict[str, CharacterEntry] = {}
    for name, entry in data.get("characters", {}).items():
        if isinstance(entry, str):
            # Simple form: John = "anh"
            characters[name] = CharacterEntry(address=entry)
        elif isinstance(entry, dict):
            characters[name] = CharacterEntry(
                self_ref=entry.get("self"),
                address=entry.get("form"),
                narrator=entry.get("narrator"),
                note=entry.get("note"),
            )

    terms: dict[str, str] = data.get("terms", {})

    return Glossary(characters=characters, terms=terms)


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


def find_glossary() -> Path | None:
    """Auto-detect glossary file in standard locations."""
    for candidate in _GLOSSARY_PATHS:
        if candidate.exists():
            return candidate
    return None
