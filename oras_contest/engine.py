"""Five-turn contest rules. Numeric outcomes depend on the supplied NPC model."""

from dataclasses import dataclass

from .catalog import CATEGORIES, COMBOS, EFFECTS, MOVES, STARTERS
from .cartridge import bounded_bucket_count, percent_bucket_weights, shuffled_slot_weights

# Ribbon Helper effect identifiers, translated to names at the data boundary.
VULNERABLE, PREVIOUS_QUALITY, REPEAT, JAM_ALL_STRONG, JAM_HALF, JAM_EXPECTED, JAM_TYPE, JAM_PREVIOUS_STRONG = range(1, 9)
NEXT_FIRST, NEXT_LAST, VARIABLE, EXCITE_FIRST, EXCITE_LAST, EXCITE_ANY, PUMP, EXCITE_DOWN = range(9, 17)
NERVOUS, SHIELD_ALL, BASIC, COPY_ALL, JAM_ALL, JAM_RECHARGE, JAM_PREVIOUS, LATER, CROWD = range(17, 26)
FIRST, LAST, PUMP_BONUS, RETIRE, RESET_STARS, RESET_COMBO, SHIELD_ONE, FREEZE, MATCH_PREVIOUS, COPY_PREVIOUS, SHUFFLE = range(26, 37)
JAM_PREVIOUS_EFFECTS = {JAM_PREVIOUS, JAM_PREVIOUS_STRONG}
JAM_EFFECTS = JAM_PREVIOUS_EFFECTS | {JAM_ALL_STRONG, JAM_HALF, JAM_EXPECTED, JAM_TYPE, JAM_ALL, JAM_RECHARGE, RESET_STARS, RESET_COMBO}
JAM_POSITION_EFFECTS = JAM_PREVIOUS_EFFECTS | {
    JAM_ALL, JAM_ALL_STRONG, JAM_RECHARGE, JAM_HALF, JAM_EXPECTED, JAM_TYPE, RESET_STARS, RESET_COMBO,
}
VARIABLE_APPEALS = (1, 2, 4, 6, 8)
VARIABLE_WEIGHTS = tuple(
    sum(bounded_bucket_count(10, value) for value in range(low, high))
    for low, high in zip((0, 3, 6, 8, 9), (3, 6, 8, 9, 10))
)


@dataclass
class State:
    total: int = 0
    points: int = 0
    stars: int = 0
    last: str | None = None
    performed: str | None = None
    combo: str | None = None
    shield: int = 0
    vulnerable: bool = False
    retired: bool = False
    rest: bool = False
    nervous: bool = False
    next_order: int = 0


def appeal_base(effect, position, meter, prior, rng=None, *, cartridge=False, stars=0):
    base = EFFECTS[effect]["appeal"]
    previous = prior[-1] if prior else None
    if effect == PREVIOUS_QUALITY and previous:
        if cartridge:
            expected = base + stars
            return base * 2 if previous.points < expected else 0 if previous.points > expected else base
        return 6 if previous.points <= 2 else 0 if previous.points >= 4 else 3
    if effect == VARIABLE:
        if cartridge:
            return rng.choices(VARIABLE_APPEALS, VARIABLE_WEIGHTS)[0] if rng else 3.1
        return rng.choice(VARIABLE_APPEALS) if rng else 4.2
    if effect == COPY_ALL and prior:
        total = sum(target.points for target in prior)
        if cartridge:
            return min(16, base + (max(0, total) + 1) // 2)
        return base + (total + 1) // 2
    if effect == COPY_PREVIOUS and previous:
        if cartridge:
            return min(16, base + max(0, previous.points))
        return 1 + previous.points
    if effect == LATER:
        return (1, 2, 4, 6)[position]
    if effect == CROWD:
        return (1, 2, 3, 5, 6)[meter]
    if effect == FIRST and position == 0 or effect == LAST and position == 3:
        return 6
    return base


def reaction(category, move, position, repeated, frozen):
    effect = move["effect"]
    distance = (CATEGORIES.index(move["type"]) - CATEGORIES.index(category)) % 5
    if repeated:
        return 0
    if distance in (2, 3) and effect != EXCITE_ANY:
        return -2 if effect == EXCITE_DOWN else -1
    if frozen and effect != EXCITE_ANY:
        return 0
    if effect == EXCITE_ANY:
        return 1
    if distance == 0:
        return 2 if (effect == EXCITE_FIRST and position == 0 or
                     effect == EXCITE_LAST and position == 3) else 1
    return 0


def jam_amount(effect, move, target, *, cartridge=False):
    if effect == JAM_HALF:
        return max(1, target.points // 2)
    if effect == JAM_EXPECTED:
        return 5 if target.combo else 1
    if effect == JAM_TYPE:
        previous = target.last if cartridge else target.performed
        return 4 if previous is not None and MOVES[previous]["type"] == move["type"] else 1
    return EFFECTS[effect]["jam"]


def apply_jam(effect, move, targets, *, cartridge=False):
    changes = []
    for index, target in targets:
        if cartridge and (effect == JAM_TYPE and target.nervous or
                          effect == RESET_STARS and not target.stars or
                          effect == RESET_COMBO and target.combo is None):
            continue
        if target.shield:
            if target.shield > 0:
                target.shield -= 1
            continue
        if effect == JAM_HALF and target.vulnerable:
            loss = 2 if cartridge and target.points < 1 else max(0, target.points)
        else:
            loss = jam_amount(effect, move, target, cartridge=cartridge) * (2 if target.vulnerable else 1)
        if effect == RESET_STARS:
            target.stars = 0
        if effect == RESET_COMBO:
            target.combo = None
        loss = min(target.points + (16 if cartridge else 0), loss)
        target.points -= loss
        if loss:
            changes.append((index, loss))
    return changes


def randomized_order(rng, count, key):
    if hasattr(rng, "ordered"):
        return rng.ordered(range(count), key)
    order = list(range(count))
    rng.shuffle(order)
    return sorted(order, key=key)


def next_order(states, rng, shuffle=False, initial=None):
    if initial is not None:
        return randomized_order(rng, len(states), lambda i: -initial[i].intro)

    def priority(i):
        flag = states[i].next_order
        if flag:
            return (-1 if flag < 0 else 1, flag)
        return (0, 0 if shuffle else -states[i].points)

    return randomized_order(rng, len(states), priority)


def coin(rng):
    return rng.percent(50) if hasattr(rng, "percent") else rng.randrange(100) < 50


def pairwise_order(order, score, rng):
    ordered = list(order)
    for left in range(len(ordered) - 1):
        for right in range(left + 1, len(ordered)):
            lead, trail = score(ordered[left]), score(ordered[right])
            if trail > lead or trail == lead and coin(rng):
                ordered[left], ordered[right] = ordered[right], ordered[left]
    return ordered


def cartridge_next_order(order, states, rng, shuffle):
    """Assign forced slots by swapping, then compare the remaining slots."""
    ordered = list(order)
    free = list(range(len(order)))
    requested = sorted(
        (index for index in order if states[index].next_order),
        key=lambda index: -abs(states[index].next_order),
    )
    for actor in requested:
        target = free.pop(0 if states[actor].next_order < 0 else -1)
        source = ordered.index(actor)
        ordered[target], ordered[source] = ordered[source], ordered[target]
    remaining = [ordered[index] for index in free]
    if shuffle and len(remaining) > 1:
        permutations, weights = shuffled_slot_weights(len(remaining))
        indices = rng.choices(permutations, weights)[0]
        remaining = [remaining[index] for index in indices]
    elif not shuffle:
        remaining = pairwise_order(remaining, lambda index: states[index].points, rng)
    for index, actor in zip(free, remaining):
        ordered[index] = actor
    return ordered


def cartridge_ranking(scores, rng):
    """Resolve the single-player result screen's ranking."""
    order = list(range(len(scores)))
    for left in range(len(order) - 1):
        for right in range(left + 1, len(order)):
            if scores[order[left]] > scores[order[right]]:
                order[left], order[right] = order[right], order[left]
    order.reverse()
    tied = sum(score == scores[order[0]] for score in scores)
    if tied > 1 and scores[0] == scores[order[0]]:
        player = order.index(0)
        order[0], order[player] = order[player], order[0]
        tied -= 1
        first = 1
    else:
        first = 0
    if tied > 1:
        free = list(range(first, first + tied))
        weights = {slot: bounded_bucket_count(tied, slot - first) for slot in free}
        for actor in order[first:first + tied]:
            # Repeated draws of occupied slots leave the same relative weights.
            slot = rng.choices(free, [weights[i] for i in free])[0] if len(free) > 1 else free[0]
            order[slot] = actor
            free.remove(slot)
    return order


def simulate(category, players, schedule, npc_move, rng, trace=False, *, unforced_passes=None):
    states = [State() for _ in players]
    cartridge = getattr(npc_move, "cartridge_appeal", False)
    order = (pairwise_order(range(len(players)), lambda i: players[i].intro, rng)
             if cartridge else next_order(states, rng, initial=players))
    meter = 0
    log = []
    for turn, scheduled in enumerate(schedule, 1):
        nervous_chance = (20, 30, 60, 0)
        acted = []
        actions = []
        frozen = shuffle = False
        for state in states:
            state.points = state.shield = state.next_order = 0
            state.vulnerable = state.nervous = False
            state.performed = None
        planned = (npc_move.plan(players, states, order, category, turn, meter, rng)
                   if hasattr(npc_move, "plan") else None)
        for pos, idx in enumerate(order):
            entrant = players[idx]
            state = states[idx]
            action = {"name": entrant.name, "scheduled": scheduled if idx == 0 else None}
            if trace and planned is not None and idx != 0:
                action["planned_move"] = planned[idx]
            if state.retired or state.rest or state.nervous or (idx == 0 and scheduled is None):
                reason = ("retired" if state.retired else "recharge" if state.rest else
                          "nervous" if state.nervous else "scheduled_pass")
                if reason == "scheduled_pass" and unforced_passes is not None:
                    unforced_passes.add(turn)
                state.rest = False
                if not cartridge or reason == "scheduled_pass":
                    state.last = state.combo = None
                if trace:
                    actions.append(dict(action, skipped=reason))
                continue
            prior = [states[i] for i in acted]
            if idx == 0:
                chosen = scheduled
            elif planned is not None:
                chosen = planned[idx]
            else:
                chosen = npc_move(entrant, state, turn, pos, category, meter, frozen, prior, rng)
            move = MOVES[chosen]
            effect = move["effect"]
            repeated = state.last == chosen and effect != REPEAT
            combo = (state.combo, chosen) in COMBOS
            base = appeal_base(effect, pos, meter, prior, rng, cartridge=cartridge, stars=state.stars)
            if effect == MATCH_PREVIOUS and prior and MOVES[prior[-1].performed]["type"] == move["type"]:
                base += 4
            gain = reaction(category, move, pos, repeated, frozen)
            score = base + (3 if effect == PUMP_BONUS else 1) * state.stars
            score += 3 * combo
            if cartridge:
                # Base appeal and then combo are applied before the crowd reacts.
                score = min(16, score)
            score += gain - repeated
            live = gain > 0 and meter + gain >= 5
            meter = 0 if live else max(0, meter + gain)
            if live:
                score += 8 if entrant.mega else 5
            state.points = min(16, max(-16 if cartridge else 0, score))
            state.performed = state.last = chosen
            state.combo = chosen if not (combo or repeated) and chosen in STARTERS else None
            if effect == PUMP:
                state.stars = min(3, state.stars + 1)
            if effect in (SHIELD_ALL, SHIELD_ONE):
                state.shield = -1 if effect == SHIELD_ALL else 1
            if effect == NEXT_FIRST:
                state.next_order = -(pos + 1)
            if effect == NEXT_LAST:
                state.next_order = pos + 1
            frozen |= effect == FREEZE
            if effect == SHUFFLE:
                shuffle = True
                for target in states:
                    target.next_order = 0
            state.vulnerable = effect == VULNERABLE
            state.rest = effect == JAM_RECHARGE
            state.retired = effect == RETIRE
            changes = []
            if effect in JAM_EFFECTS:
                targets = order[:pos] if cartridge and effect in JAM_POSITION_EFFECTS else acted
                if effect in JAM_PREVIOUS_EFFECTS:
                    targets = targets[-1:]
                if cartridge:
                    targets = [i for i in targets if not states[i].retired or i in acted]
                changes = apply_jam(effect, move, [(i, states[i]) for i in targets],
                                    cartridge=cartridge)
            victims = []
            if effect == NERVOUS:
                for i in order[pos+1:]:
                    target = states[i]
                    if target.rest or target.retired or target.nervous:
                        continue
                    threshold = max(0, nervous_chance[pos] - 10 * target.stars)
                    if cartridge:
                        nervous = bool(threshold) and rng.choices(
                            (True, False), percent_bucket_weights(threshold))[0]
                    else:
                        nervous = (rng.percent(threshold) if hasattr(rng, "percent")
                                   else rng.randrange(100) < threshold)
                    if nervous:
                        target.nervous = True
                        victims.append(players[i].name)
            acted.append(idx)
            if trace:
                actions.append(dict(action, move=chosen, appeal=state.points, combo=combo,
                                    repeated=repeated,
                                    meter=meter, live=live, nervous=victims,
                                    jam={players[i].name: loss for i, loss in changes}))
        for state in states:
            if cartridge and state.performed is None:
                state.combo = None
            state.total = max(0, state.total + state.points)
        if trace:
            log.append({"turn": turn, "actions": actions,
                        "hearts": {p.name: s.points for p, s in zip(players, states)},
                        "cumulative_hearts": {p.name: s.total for p, s in zip(players, states)}})
        if turn < len(schedule) or not hasattr(rng, "ordered"):
            if cartridge:
                order = cartridge_next_order(order, states, rng, shuffle)
            else:
                order = next_order(states, rng, shuffle)
    scores = [p.intro + 20 * s.total for p, s in zip(players, states)]
    ranking = (cartridge_ranking(scores, rng) if cartridge else
               randomized_order(rng, len(players), lambda i: -scores[i]))
    return ranking, scores, log
