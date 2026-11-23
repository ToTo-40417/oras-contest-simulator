"""Replaceable NPC selection hypotheses. These weights are not ROM findings."""

import math

from . import engine as e
from .catalog import COMBOS, MOVES, NPC_MOVE_SETS

PROFILES = ("uniform", "observed", "competitive")
OPENERS = {
    ("Lisia", "cool"): "dragon-dance",
    ("Lisia", "cute"): "hone-claws",
    ("Wallace", "beauty"): "aqua-ring",
}


def policy(profile, overrides=None):
    if profile not in PROFILES:
        raise ValueError("Unknown NPC profile")
    overrides = {name.casefold(): weights for name, weights in (overrides or {}).items()}
    for name, weights in overrides.items():
        if name not in NPC_MOVE_SETS:
            raise ValueError(f"Unknown NPC move weight: {name}")
        for move, weight in weights.items():
            if move not in NPC_MOVE_SETS[name] or not math.isfinite(weight) or weight < 0:
                raise ValueError(f"Invalid NPC move weight: {move}={weight}")

    def select(entrant, state, turn, position, category, meter, frozen, prior, rng):
        customized = overrides.get(entrant.name.casefold(), {})
        weights = [customized.get(move, 1) for move in entrant.moves]
        if max(weights) > 1e250:
            maximum = max(weights)
            weights = [weight / maximum for weight in weights]
        if profile == "uniform":
            return pick(rng, entrant, weights)
        opener = OPENERS.get((entrant.name, category))
        for i, move_id in enumerate(entrant.moves):
            move = MOVES[move_id]
            effect = move["effect"]
            repeat = state.last == move_id and effect != e.REPEAT
            combo = (state.combo, move_id) in COMBOS
            gain = e.reaction(category, move, position, repeat, frozen)
            appeal = e.appeal_base(effect, position, meter, prior)
            if effect == e.MATCH_PREVIOUS and prior and MOVES[prior[-1].performed]["type"] == move["type"]:
                appeal += 4
            appeal += gain + 3 * combo - repeat
            live = gain > 0 and meter + gain >= 5
            if live:
                appeal += 8 if entrant.mega else 5
            if effect == e.RETIRE and turn < 5:
                appeal -= 5 - turn
            if effect == e.JAM_RECHARGE and turn < 5:
                appeal -= 2
            if effect in e.JAM_EFFECTS:
                targets = prior[-1:] if effect in e.JAM_PREVIOUS_EFFECTS else prior
                appeal += .35 * sum(
                    min(t.points, e.jam_amount(effect, move, t)) for t in targets if not t.shield
                )
            if effect == e.PUMP and state.stars < 3:
                appeal += .5 * (5 - turn)
            weights[i] *= math.exp((.45 if profile == "competitive" else .22) * appeal)
            if profile == "observed":
                if turn == 1 and move_id == opener:
                    weights[i] *= 18
                if entrant.name == "Lisia" and category == "beauty":
                    if move_id == "mist" and position == 0:
                        weights[i] *= 3
                    if move_id == "draco-meteor":
                        weights[i] *= .25
                if entrant.name == "Lisia" and category == "clever" and move_id == "sing":
                    weights[i] *= 2
                if entrant.species == "gorebyss" and position == 0 and move_id in {"whirlpool", "aqua-tail"}:
                    weights[i] *= 2
        return pick(rng, entrant, weights)

    return select


def pick(rng, entrant, weights):
    if not any(weights):
        raise ValueError(f"All move weights are zero for {entrant.name}")
    return rng.choices(entrant.moves, weights)[0]
