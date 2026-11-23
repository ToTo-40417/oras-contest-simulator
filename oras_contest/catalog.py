"""Versioned local contest data and name resolution."""

from dataclasses import dataclass
from json import loads
from pathlib import Path
import math
from fractions import Fraction
from itertools import permutations

CATEGORIES = ("cool", "beauty", "cute", "clever", "tough")
RANKS = ("normal", "super", "hyper", "master")
DATA_DIR = Path(__file__).with_name("data")


def load(name):
    return loads((DATA_DIR / (name + ".json")).read_text(encoding="utf-8"))


MOVES = load("moves")
EFFECTS = {int(key): value for key, value in load("effects").items()}
SPECIES = load("species")
FORMS = load("forms")
NPCS = load("npcs")
NPC_MOVE_SETS = {}
for row in NPCS:
    NPC_MOVE_SETS.setdefault(row["trainer"].casefold(), set()).update(row["moves"])
MOVE_JA = {row["ja"]: key for key, row in MOVES.items()}
SPECIES_JA = {row["ja"]: key for key, row in SPECIES.items()}
COMBOS = frozenset(
    (before, after)
    for key, row in MOVES.items()
    for before, after in (
        [(previous, key) for previous in row.get("combos", {}).get("after", ())]
        + [(key, following) for following in row.get("combos", {}).get("before", ())]
    )
    if before in MOVES and after in MOVES
)
STARTERS = frozenset(before for before, _ in COMBOS)


def move_id(value):
    value = MOVE_JA.get(value, value.lower())
    if value not in MOVES:
        raise ValueError(f"Unknown move: {value}")
    return value


def species_id(value):
    value = SPECIES_JA.get(value, value.lower())
    if value not in SPECIES and value not in FORMS:
        raise ValueError(f"Unknown Pokémon: {value}")
    return value


def learned_moves(species):
    if species == "smeargle":
        return set(MOVES) - {"struggle", "chatter"}
    methods = SPECIES[species]["moves"] if species in SPECIES else FORMS[species]
    return set().union(*(record["moves"] for record in methods.values()))


def intro_score(category, conditions, scarf=False):
    i = CATEGORIES.index(category)
    if len(conditions) != 5 or any(type(c) is not int or not 0 <= c <= 255 for c in conditions):
        raise ValueError("Conditions must be five integers between 0 and 255")
    return conditions[i] + (conditions[i-1] + conditions[(i+1)%5]) // 2 + 20 * scarf


@dataclass(frozen=True)
class Entrant:
    name: str
    species: str
    moves: tuple
    intro: int
    mega: bool = False


def pool(category, rank, progress):
    if progress not in {"early", "postgame", "challenger", "rematch"}:
        raise ValueError("Unknown story progress")
    eligible = []
    for row in NPCS:
        name = row["trainer"]
        if row["rank"] != RANKS.index(rank) + 1 or category not in row["scores"]:
            continue
        if name in {"Lisia", "Wallace"} and progress not in {"challenger", "rematch"}:
            continue
        if name == "Chaz" and progress == "early":
            continue
        eligible.append(Entrant(name, row["species"], tuple(row["moves"]),
                                row["scores"][category], name == "Lisia"))
    return eligible


def roster_inputs(eligible, category, progress, fixed=(), weights=None):
    by_name = {p.name.casefold(): p for p in eligible}
    names = [name.casefold() for name in fixed]
    if len(set(names)) != len(names) or len(names) > 3:
        raise ValueError("Specify up to three different fixed opponents")
    if any(name not in by_name for name in names):
        raise ValueError("Fixed opponent is outside the selected division/progress")
    weights = {k.casefold(): v for k, v in (weights or {}).items()}
    unknown = weights.keys() - NPC_MOVE_SETS.keys()
    if unknown:
        raise ValueError(f"Unknown NPC roster weight: {', '.join(sorted(unknown))}")
    if any(not math.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError("Roster weights must be finite and non-negative")
    if not names and progress == "challenger" and "lisia" in by_name:
        names = ["lisia"]
        if category == "beauty" and "wallace" in by_name:
            names.append("wallace")
    available = [name for name in by_name if name not in names and weights.get(name, 1) > 0]
    if len(available) < 3 - len(names):
        raise ValueError("Fewer than three eligible opponents with positive weights")
    return by_name, names, available, weights


def draw_roster(rng, eligible, category, progress, fixed=(), weights=None):
    by_name, names, available, weights = roster_inputs(eligible, category, progress, fixed, weights)
    while len(names) < 3:
        draw_weights = [weights.get(key, 1) for key in available]
        if not math.isfinite(sum(draw_weights)):
            maximum = max(draw_weights)
            draw_weights = [weight / maximum for weight in draw_weights]
        name = rng.choices(available, draw_weights)[0]
        available.remove(name)
        names.append(name)
    return tuple(by_name[name] for name in names)


def roster_distribution(eligible, category, progress, fixed=(), weights=None):
    """Enumerate all ordered draws under the selected scenario."""
    by_name, names, available, weights = roster_inputs(eligible, category, progress, fixed, weights)
    fractions = {key: Fraction(str(weights.get(key, 1))) for key in available}
    total = sum(fractions.values())
    for draw in permutations(available, 3 - len(names)):
        remaining = total
        probability = Fraction(1)
        for key in draw:
            weight = fractions[key]
            probability *= weight / remaining
            remaining -= weight
        yield tuple(by_name[key] for key in (*names, *draw)), probability
