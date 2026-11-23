"""Independent behavioral implementation of contest NPC scoring rules.

Policies prepare the NPC choices together, before the first appeal is resolved.
"""
from . import engine as e
from .catalog import CATEGORIES, COMBOS, MOVES

LOWER_RANKS = ("normal", "super", "hyper")
SPECIAL_TRAINERS = frozenset(("Chaz", "Wallace", "Lisia"))
ORDINARY_APPEALS = {e.BASIC, e.REPEAT, e.RETIRE, e.VULNERABLE}
ORDER_MOVES = {e.NEXT_FIRST, e.NEXT_LAST, e.SHUFFLE}
EXCITE_MOVES = {e.EXCITE_FIRST, e.EXCITE_LAST, e.EXCITE_DOWN}
PROTECTION = {e.SHIELD_ONE, e.SHIELD_ALL}


def move_score(rank, category, move_id, turn, position, meter, last, combo_ready):
    """Rank-specific AI preference before its per-slot random increment."""
    if rank not in LOWER_RANKS:
        raise ValueError(f"No decoded ordinary NPC scoring policy for {rank}")
    move = MOVES[move_id]
    effect = move["effect"]
    distance = (CATEGORIES.index(move["type"]) - CATEGORIES.index(category)) % 5
    penalty = 1 if rank == "normal" else 2
    score = -2 * (move_id == last) - (distance in (1, 4))
    if rank == "hyper":
        score += distance == 0 and effect in ORDINARY_APPEALS
    else:
        score += distance in (2, 3)
    if position == 4 and (effect in {e.SHIELD_ONE, e.NERVOUS} or
                          rank != "hyper" and effect == e.SHIELD_ALL):
        score -= penalty
    if combo_ready and (last, move_id) in COMBOS:
        score += 2
    if turn == 5 and effect in ORDER_MOVES:
        score -= penalty
    if turn != 5 and effect == e.RETIRE:
        score -= penalty
    if meter >= 2 and effect in ORDINARY_APPEALS | ORDER_MOVES | EXCITE_MOVES:
        score -= 1
    if position == 1 and effect == e.RESET_STARS:
        score -= penalty
    if rank != "normal" and position == 1 and (effect == e.PUMP or effect in PROTECTION):
        score += 1
    if rank == "hyper":
        if position == 1 and effect in {e.JAM_EXPECTED, e.MATCH_PREVIOUS,
                                      e.RESET_COMBO, e.PREVIOUS_QUALITY}:
            score -= 2
        if effect in PROTECTION and position == 4:
            score -= 1
        if position == 1 and effect in e.JAM_PREVIOUS_EFFECTS | {
            e.JAM_ALL, e.JAM_ALL_STRONG, e.JAM_HALF, e.JAM_TYPE, e.JAM_RECHARGE, e.JAM_EXPECTED,
        }:
            score -= 1
        if position == 2 and effect in e.JAM_PREVIOUS_EFFECTS:
            score += 1
        if position == 4 and effect in {
            e.JAM_ALL, e.JAM_ALL_STRONG, e.JAM_HALF, e.JAM_TYPE, e.JAM_RECHARGE, e.JAM_EXPECTED,
        }:
            score += 1
        if position == 1 and effect == e.NERVOUS:
            score += 1
    return score


def select_slot(scores, rng):
    best = 0
    for slot in range(1, len(scores)):
        if scores[slot] > scores[best]:
            best = slot
        elif scores[slot] == scores[best]:
            replace = rng.percent(50) if hasattr(rng, "percent") else rng.randrange(100) < 50
            if replace:
                best = slot
    return best


class CartridgeLowerAI:
    def __init__(self, rank):
        if rank not in LOWER_RANKS:
            raise ValueError("Cartridge AI currently supports ordinary Normal, Super and Hyper NPCs")
        self.rank = rank

    def plan(self, players, states, order, category, turn, meter, rng):
        positions = {index: pos for pos, index in enumerate(order, 1)}
        decisions = {}
        for index, npc in enumerate(players[1:], 1):
            if npc.name in SPECIAL_TRAINERS:
                raise ValueError("Cartridge lower-rank AI cannot score a special contestant")
            state = states[index]
            scores = [move_score(self.rank, category, move, turn, positions[index],
                                 meter, state.last, bool(state.combo)) + rng.choice((0, 1))
                      for move in npc.moves]
            decisions[index] = npc.moves[select_slot(scores, rng)]
        return decisions


def master_move_score(category, move_id, turn, position, meter, last, combo_ready,
                      *, special=False, stars=0, earlier_stars=0, earlier_combos=0,
                      lowest_appeal_total=False):
    """Score a candidate using the advanced rule family, before random adjustment."""
    move = MOVES[move_id]
    effect = move["effect"]
    distance = (CATEGORIES.index(move["type"]) - CATEGORIES.index(category)) % 5
    score = -2 * (move_id == last) - (distance in (1, 4))
    if combo_ready and (last, move_id) in COMBOS:
        score += 2
    if effect in ORDINARY_APPEALS:
        score += (2 if meter == 4 else 0) + (distance == 0)
    if effect in PROTECTION:
        score += 2 if position == 1 else -6 if position == 4 else 0
    if effect in e.JAM_PREVIOUS_EFFECTS:
        score += 2 if position == 2 else -1 if position == 1 else 0
    if effect in {e.JAM_ALL, e.JAM_ALL_STRONG, e.JAM_HALF, e.JAM_TYPE, e.JAM_RECHARGE,
                  e.JAM_EXPECTED}:
        score += 2 if position == 4 else -1 if position == 1 else 0

    if effect == e.LATER:
        score += {1: -1, 3: 1, 4: 3}.get(position, 0)
    elif effect == e.FIRST:
        score += 3 if position == 1 else 0
    elif effect == e.LAST:
        score += 3 if position == 4 else 0
    elif effect == e.EXCITE_FIRST:
        score += 2 * (position == 1) + (2 if special else 1) * (meter >= 3)
    elif effect == e.EXCITE_LAST:
        score += 2 * (position == 4) + (2 if special and meter <= 2 else
                                        1 if not special and meter <= 1 else 0)
    elif effect == e.JAM_HALF:
        score += lowest_appeal_total + 2 * (position == 4)
    elif effect == e.NERVOUS:
        score += {1: 2, 2: 1, 4: -6}.get(position, 0)
    elif effect == e.EXCITE_DOWN:
        score += 3 * (distance in (1, 4)) - 3 + (turn != 1)
    elif effect == e.FREEZE:
        score += (meter >= 3) + (position == 1)
    elif effect == e.CROWD:
        score += 2 * (meter >= 3)
    elif effect == e.EXCITE_ANY:
        score += 3 * (meter >= 3) + (distance == 0)
    elif effect in (e.JAM_EXPECTED, e.RESET_COMBO):
        score += 2 * (earlier_combos >= 2)
    elif effect == e.COPY_ALL:
        score += position == 3
    elif effect == e.JAM_RECHARGE:
        score += 5 * (turn == 5)
    elif effect == e.NEXT_FIRST:
        score += (2 if special else 1) * (position != 1) - 6 * (turn == 5)
    elif effect == e.NEXT_LAST:
        score += (2 if special else 1) * (position != 4) - 6 * (turn == 5)
    elif effect == e.SHUFFLE:
        score += 2 - 6 * (turn == 5)
    elif effect in (e.MATCH_PREVIOUS, e.JAM_TYPE):
        score += (distance == 0) - 2 * (position == 1)
    elif effect == e.VULNERABLE:
        score -= position != 4
    elif effect == e.PUMP:
        score += 2 * (turn == 1) + (position == 2) - (turn == 5)
    elif effect == e.PUMP_BONUS:
        score += 4 * (stars >= 2)
    elif effect == e.RESET_STARS:
        score += 3 * (earlier_stars >= 3) - 6 * (position == 1)
    elif effect == e.COPY_PREVIOUS:
        score += 1 + (position == 2)
    elif effect == e.PREVIOUS_QUALITY:
        score += 1 + (position != 1)
    elif effect == e.VARIABLE:
        score += 1
    elif effect == e.RETIRE:
        score += 6 if turn == 5 else -6
    return score


class CartridgeAI:
    """All rank books, choosing the special book where the roster flags require it."""

    cartridge_appeal = True

    def __init__(self, rank):
        self.rank = rank

    def plan(self, players, states, order, category, turn, meter, rng):
        positions = {index: pos for pos, index in enumerate(order)}
        decisions = {}
        for index, npc in enumerate(players[1:], 1):
            position = positions[index]
            state = states[index]
            special = npc.name in SPECIAL_TRAINERS
            if self.rank == "master" or special:
                earlier = [states[slot] for slot in order[:position]]
                scores = [
                    master_move_score(
                        category, move, turn, position + 1, meter, state.last,
                        bool(state.combo), special=special, stars=state.stars,
                        earlier_stars=sum(other.stars for other in earlier),
                        earlier_combos=sum(bool(other.combo) for other in earlier),
                        lowest_appeal_total=state.total == min(other.total for other in states),
                    ) for move in npc.moves
                ]
            else:
                scores = [
                    move_score(self.rank, category, move, turn, position + 1,
                               meter, state.last, bool(state.combo)) for move in npc.moves
                ]
            if not special:
                scores = [score + rng.choice((0, 1)) for score in scores]
            decisions[index] = npc.moves[select_slot(scores, rng)]
        return decisions
