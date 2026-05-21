"""
Predefined relationship type registry for MythosEngine.

Provides the canonical list of relationship types, a fast lookup map,
and a helper for retrieving the reverse-direction display label.
"""

from typing import Optional

RELATIONSHIP_TYPES: list[dict] = [
    # ── Social ────────────────────────────────────────────────────────────────
    {"type": "ally", "category": "Social", "inverse": None, "default_direction": "bidirectional"},
    {"type": "enemy", "category": "Social", "inverse": None, "default_direction": "bidirectional"},
    {"type": "rival", "category": "Social", "inverse": None, "default_direction": "bidirectional"},
    {"type": "friend", "category": "Social", "inverse": None, "default_direction": "bidirectional"},
    {"type": "acquaintance", "category": "Social", "inverse": None, "default_direction": "bidirectional"},
    {"type": "admires", "category": "Social", "inverse": "is admired by", "default_direction": "unidirectional"},
    {"type": "despises", "category": "Social", "inverse": "is despised by", "default_direction": "unidirectional"},
    {"type": "fears", "category": "Social", "inverse": "is feared by", "default_direction": "unidirectional"},
    {"type": "trusts", "category": "Social", "inverse": "is trusted by", "default_direction": "unidirectional"},
    {"type": "distrusts", "category": "Social", "inverse": "is distrusted by", "default_direction": "unidirectional"},
    {"type": "respects", "category": "Social", "inverse": "is respected by", "default_direction": "unidirectional"},
    {"type": "envies", "category": "Social", "inverse": "is envied by", "default_direction": "unidirectional"},
    # ── Family & Romance ──────────────────────────────────────────────────────
    {"type": "parent of", "category": "Family & Romance", "inverse": "child of", "default_direction": "unidirectional"},
    {"type": "child of", "category": "Family & Romance", "inverse": "parent of", "default_direction": "unidirectional"},
    {"type": "sibling of", "category": "Family & Romance", "inverse": None, "default_direction": "bidirectional"},
    {"type": "spouse of", "category": "Family & Romance", "inverse": None, "default_direction": "bidirectional"},
    {"type": "former spouse of", "category": "Family & Romance", "inverse": None, "default_direction": "bidirectional"},
    {"type": "lover", "category": "Family & Romance", "inverse": None, "default_direction": "bidirectional"},
    {"type": "former lover", "category": "Family & Romance", "inverse": None, "default_direction": "bidirectional"},
    {"type": "guardian of", "category": "Family & Romance", "inverse": "ward of", "default_direction": "unidirectional"},
    {"type": "ward of", "category": "Family & Romance", "inverse": "guardian of", "default_direction": "unidirectional"},
    # ── Conflict ──────────────────────────────────────────────────────────────
    {"type": "killed", "category": "Conflict", "inverse": "was killed by", "default_direction": "unidirectional"},
    {"type": "defeated", "category": "Conflict", "inverse": "was defeated by", "default_direction": "unidirectional"},
    {"type": "betrayed", "category": "Conflict", "inverse": "was betrayed by", "default_direction": "unidirectional"},
    {"type": "imprisoned", "category": "Conflict", "inverse": "was imprisoned by", "default_direction": "unidirectional"},
    {"type": "captured", "category": "Conflict", "inverse": "was captured by", "default_direction": "unidirectional"},
    {"type": "rescued", "category": "Conflict", "inverse": "was rescued by", "default_direction": "unidirectional"},
    {"type": "hunted", "category": "Conflict", "inverse": "is hunted by", "default_direction": "unidirectional"},
    {"type": "sacrificed for", "category": "Conflict", "inverse": "received sacrifice from", "default_direction": "unidirectional"},
    {"type": "at war with", "category": "Conflict", "inverse": None, "default_direction": "bidirectional"},
    # ── Power & Hierarchy ─────────────────────────────────────────────────────
    {"type": "commands", "category": "Power & Hierarchy", "inverse": "reports to", "default_direction": "unidirectional"},
    {"type": "reports to", "category": "Power & Hierarchy", "inverse": "commands", "default_direction": "unidirectional"},
    {"type": "serves", "category": "Power & Hierarchy", "inverse": "is served by", "default_direction": "unidirectional"},
    {"type": "employs", "category": "Power & Hierarchy", "inverse": "is employed by", "default_direction": "unidirectional"},
    {"type": "rules over", "category": "Power & Hierarchy", "inverse": "is ruled by", "default_direction": "unidirectional"},
    {"type": "overthrew", "category": "Power & Hierarchy", "inverse": "was overthrown by", "default_direction": "unidirectional"},
    {"type": "succeeded", "category": "Power & Hierarchy", "inverse": "was succeeded by", "default_direction": "unidirectional"},
    {"type": "founded", "category": "Power & Hierarchy", "inverse": "was founded by", "default_direction": "unidirectional"},
    {"type": "member of", "category": "Power & Hierarchy", "inverse": "has member", "default_direction": "unidirectional"},
    {"type": "exiled from", "category": "Power & Hierarchy", "inverse": "exiled", "default_direction": "unidirectional"},
    # ── Knowledge & Secrets ───────────────────────────────────────────────────
    {"type": "knows about", "category": "Knowledge & Secrets", "inverse": "is known about by", "default_direction": "unidirectional"},
    {"type": "witnessed", "category": "Knowledge & Secrets", "inverse": "was witnessed by", "default_direction": "unidirectional"},
    {"type": "is deceiving", "category": "Knowledge & Secrets", "inverse": "is being deceived by", "default_direction": "unidirectional"},
    {"type": "was deceived by", "category": "Knowledge & Secrets", "inverse": "deceived", "default_direction": "unidirectional"},
    {"type": "is blackmailing", "category": "Knowledge & Secrets", "inverse": "is being blackmailed by", "default_direction": "unidirectional"},
    {"type": "shares a secret with", "category": "Knowledge & Secrets", "inverse": None, "default_direction": "bidirectional"},
    {"type": "unaware of", "category": "Knowledge & Secrets", "inverse": "is unknown to", "default_direction": "unidirectional"},
    # ── Creation & Origin ─────────────────────────────────────────────────────
    {"type": "created", "category": "Creation & Origin", "inverse": "was created by", "default_direction": "unidirectional"},
    {"type": "destroyed", "category": "Creation & Origin", "inverse": "was destroyed by", "default_direction": "unidirectional"},
    {"type": "discovered", "category": "Creation & Origin", "inverse": "was discovered by", "default_direction": "unidirectional"},
    {"type": "forged", "category": "Creation & Origin", "inverse": "was forged by", "default_direction": "unidirectional"},
    {"type": "summoned", "category": "Creation & Origin", "inverse": "was summoned by", "default_direction": "unidirectional"},
    {"type": "cursed", "category": "Creation & Origin", "inverse": "was cursed by", "default_direction": "unidirectional"},
    {"type": "blessed", "category": "Creation & Origin", "inverse": "was blessed by", "default_direction": "unidirectional"},
    {"type": "enchanted", "category": "Creation & Origin", "inverse": "was enchanted by", "default_direction": "unidirectional"},
    {"type": "corrupted", "category": "Creation & Origin", "inverse": "was corrupted by", "default_direction": "unidirectional"},
    # ── Location ──────────────────────────────────────────────────────────────
    {"type": "located at", "category": "Location", "inverse": "is location of", "default_direction": "unidirectional"},
    {"type": "originated from", "category": "Location", "inverse": "is origin of", "default_direction": "unidirectional"},
    {"type": "guards", "category": "Location", "inverse": "is guarded by", "default_direction": "unidirectional"},
    {"type": "haunts", "category": "Location", "inverse": "is haunted by", "default_direction": "unidirectional"},
    {"type": "was born in", "category": "Location", "inverse": "is birthplace of", "default_direction": "unidirectional"},
    {"type": "died in", "category": "Location", "inverse": "is death location of", "default_direction": "unidirectional"},
    {"type": "exiled to", "category": "Location", "inverse": "received exile", "default_direction": "unidirectional"},
    {"type": "adjacent to", "category": "Location", "inverse": None, "default_direction": "bidirectional"},
    {"type": "part of", "category": "Location", "inverse": "contains", "default_direction": "unidirectional"},
    {"type": "leads to", "category": "Location", "inverse": "is reached from", "default_direction": "unidirectional"},
    {"type": "borders", "category": "Location", "inverse": None, "default_direction": "bidirectional"},
    {"type": "visible from", "category": "Location", "inverse": "can see", "default_direction": "unidirectional"},
    {"type": "connected to", "category": "Location", "inverse": None, "default_direction": "bidirectional"},
    {"type": "sacred to", "category": "Location", "inverse": "considers sacred", "default_direction": "unidirectional"},
    {"type": "controlled by", "category": "Location", "inverse": "controls", "default_direction": "unidirectional"},
    {"type": "was built by", "category": "Location", "inverse": "built", "default_direction": "unidirectional"},
    {"type": "was built for", "category": "Location", "inverse": "was built for", "default_direction": "unidirectional"},
    {"type": "ruins of", "category": "Location", "inverse": "became ruins", "default_direction": "unidirectional"},
    # ── Item ──────────────────────────────────────────────────────────────────
    {"type": "contains", "category": "Item", "inverse": "is part of", "default_direction": "unidirectional"},
    {"type": "is part of", "category": "Item", "inverse": "contains", "default_direction": "unidirectional"},
    {"type": "was found in", "category": "Item", "inverse": "contained", "default_direction": "unidirectional"},
    {"type": "crafted by", "category": "Item", "inverse": "crafted", "default_direction": "unidirectional"},
    {"type": "crafted for", "category": "Item", "inverse": "was crafted for", "default_direction": "unidirectional"},
    {"type": "requires", "category": "Item", "inverse": "is required by", "default_direction": "unidirectional"},
    {"type": "upgrades", "category": "Item", "inverse": "is upgraded by", "default_direction": "unidirectional"},
    {"type": "previously owned by", "category": "Item", "inverse": "previously owned", "default_direction": "unidirectional"},
    {"type": "bound to", "category": "Item", "inverse": None, "default_direction": "bidirectional"},
    {"type": "sought by", "category": "Item", "inverse": "is seeking", "default_direction": "unidirectional"},
    {"type": "keys", "category": "Item", "inverse": "is keyed by", "default_direction": "unidirectional"},
    {"type": "unlocks", "category": "Item", "inverse": "is unlocked by", "default_direction": "unidirectional"},
    # ── Belief & Ideology ─────────────────────────────────────────────────────
    {"type": "worships", "category": "Belief & Ideology", "inverse": "is worshipped by", "default_direction": "unidirectional"},
    {"type": "rejects", "category": "Belief & Ideology", "inverse": "is rejected by", "default_direction": "unidirectional"},
    {"type": "belongs to cult of", "category": "Belief & Ideology", "inverse": "has cult member", "default_direction": "unidirectional"},
    {"type": "heretic of", "category": "Belief & Ideology", "inverse": "has heretic", "default_direction": "unidirectional"},
    # ── Economic ──────────────────────────────────────────────────────────────
    {"type": "owes debt to", "category": "Economic", "inverse": "is owed debt by", "default_direction": "unidirectional"},
    {"type": "trades with", "category": "Economic", "inverse": None, "default_direction": "bidirectional"},
    {"type": "competes with", "category": "Economic", "inverse": None, "default_direction": "bidirectional"},
    {"type": "stole from", "category": "Economic", "inverse": "was stolen from by", "default_direction": "unidirectional"},
    {"type": "gifted to", "category": "Economic", "inverse": "was gifted by", "default_direction": "unidirectional"},
    # ── Faction & Organization ────────────────────────────────────────────────
    {"type": "controls", "category": "Faction & Organization", "inverse": "controlled by", "default_direction": "unidirectional"},
    {"type": "absorbed", "category": "Faction & Organization", "inverse": "was absorbed by", "default_direction": "unidirectional"},
    {"type": "split from", "category": "Faction & Organization", "inverse": "split into", "default_direction": "unidirectional"},
    {"type": "vassal of", "category": "Faction & Organization", "inverse": "has vassal", "default_direction": "unidirectional"},
    {"type": "tributary of", "category": "Faction & Organization", "inverse": "receives tribute from", "default_direction": "unidirectional"},
    {"type": "sponsors", "category": "Faction & Organization", "inverse": "is sponsored by", "default_direction": "unidirectional"},
    {"type": "opposes", "category": "Faction & Organization", "inverse": "is opposed by", "default_direction": "unidirectional"},
    {"type": "allied with", "category": "Faction & Organization", "inverse": None, "default_direction": "bidirectional"},
    {"type": "at war with", "category": "Faction & Organization", "inverse": None, "default_direction": "bidirectional"},
    # ── Event & Lore ──────────────────────────────────────────────────────────
    {"type": "caused", "category": "Event & Lore", "inverse": "was caused by", "default_direction": "unidirectional"},
    {"type": "preceded", "category": "Event & Lore", "inverse": "followed", "default_direction": "unidirectional"},
    {"type": "commemorates", "category": "Event & Lore", "inverse": "is commemorated by", "default_direction": "unidirectional"},
    {"type": "was covered up by", "category": "Event & Lore", "inverse": "covered up", "default_direction": "unidirectional"},
    {"type": "prophesied", "category": "Event & Lore", "inverse": "is prophesied by", "default_direction": "unidirectional"},
    # ── Narrative & Meta ──────────────────────────────────────────────────────
    {"type": "foreshadows", "category": "Narrative & Meta", "inverse": "is foreshadowed by", "default_direction": "unidirectional"},
    {"type": "parallels", "category": "Narrative & Meta", "inverse": None, "default_direction": "bidirectional"},
    {"type": "contrasts with", "category": "Narrative & Meta", "inverse": None, "default_direction": "bidirectional"},
    {"type": "inspired by", "category": "Narrative & Meta", "inverse": "inspired", "default_direction": "unidirectional"},
    {"type": "references", "category": "Narrative & Meta", "inverse": "is referenced by", "default_direction": "unidirectional"},
    {"type": "is evidence of", "category": "Narrative & Meta", "inverse": "has evidence", "default_direction": "unidirectional"},
    {"type": "symbolizes", "category": "Narrative & Meta", "inverse": "is symbolized by", "default_direction": "unidirectional"},
    {"type": "is a relic of", "category": "Narrative & Meta", "inverse": "has a relic", "default_direction": "unidirectional"},
    {"type": "marks the site of", "category": "Narrative & Meta", "inverse": "site marked by", "default_direction": "unidirectional"},
]

# Fast lookup by type string — first occurrence wins for duplicates (e.g. "at war with")
RELATIONSHIP_TYPE_MAP: dict[str, dict] = {}
for _entry in RELATIONSHIP_TYPES:
    if _entry["type"] not in RELATIONSHIP_TYPE_MAP:
        RELATIONSHIP_TYPE_MAP[_entry["type"]] = _entry


def get_inverse_label(type_str: str) -> str:
    """Return the display label for the reverse direction of a relationship type.

    For symmetric types (inverse=None) the label equals the type itself.
    For custom types not in the registry, the type string is returned unchanged.
    """
    entry = RELATIONSHIP_TYPE_MAP.get(type_str)
    if not entry:
        return type_str
    inv: Optional[str] = entry.get("inverse")
    return inv if inv is not None else type_str
