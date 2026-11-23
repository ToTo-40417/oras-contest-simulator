"""Rules identified in the cartridge and reproduced independently."""

from functools import lru_cache
from fractions import Fraction
from itertools import product
from math import comb, prod

from .catalog import pool

UINT32 = (1 << 32) - 1


class TinyMT32:
    """RFC 8682 stream primitive, with the cartridge's bounded reduction."""

    MAT1 = 0x8F7011EE
    MAT2 = 0xFC78FF1F
    TMAT = 0x3793FDFF

    def __init__(self, seed):
        self.state = [seed & UINT32, self.MAT1, self.MAT2, self.TMAT]
        for i in range(1, 8):
            previous = self.state[(i - 1) % 4]
            self.state[i % 4] ^= (i + 1812433253 * (previous ^ (previous >> 30))) & UINT32
        for _ in range(8):
            self.advance()

    def advance(self):
        first, second, third, last = self.state
        mixed = (first & 0x7FFFFFFF) ^ second ^ third
        mixed ^= (mixed << 1) & UINT32
        last ^= (last >> 1) ^ mixed
        mixed ^= (last << 10) & UINT32
        if last & 1:
            third ^= self.MAT1
            mixed ^= self.MAT2
        self.state = [second, third, mixed, last]

    def uint32(self):
        self.advance()
        first, _, third, last = self.state
        mixed = (first + (third >> 8)) & UINT32
        return last ^ mixed ^ (self.TMAT if mixed & 1 else 0)

    def bounded(self, bound):
        if not 0 <= bound <= UINT32:
            raise ValueError("TinyMT bound is outside uint32")
        value = self.uint32()
        if bound < 0xFFFF:
            return (value * bound) >> 32
        return value % bound


def bounded_bucket_count(bound, result):
    """Number of 32-bit inputs producing result, independent of seed distribution."""
    if not 1 <= bound <= UINT32 or not 0 <= result < bound:
        raise ValueError("Result must be in the bounded range")
    if bound < 0xFFFF:
        def boundary(k):
            return ((k << 32) + bound - 1) // bound
        return boundary(result + 1) - boundary(result)
    quotient, remainder = divmod(1 << 32, bound)
    return quotient + (result < remainder)


@lru_cache(maxsize=100)
def percent_bucket_weights(threshold):
    """Count the inputs on each side of a bounded 0–99 comparison."""
    passed = sum(bounded_bucket_count(100, value) for value in range(threshold))
    return passed, (1 << 32) - passed


def random_key_collision_probability(count):
    """Probability that independent uniform uint32 keys include a tie."""
    space = UINT32 + 1
    distinct = Fraction(prod(range(space - count + 1, space + 1)), space ** count)
    return 1 - distinct


@lru_cache(maxsize=4)
def shuffled_slot_weights(count):
    """Count independent uint32 key assignments yielding each slot order."""
    weights = {}
    for distinct in range(1, count + 1):
        assignments = comb(UINT32 + 1, distinct)
        keys_used = set(range(distinct))
        for keys in product(range(distinct), repeat=count):
            if set(keys) != keys_used:
                continue
            slots = list(range(count))
            for left in range(count - 1):
                for right in range(left + 1, count):
                    if keys[slots[left]] > keys[slots[right]]:
                        slots[left], slots[right] = slots[right], slots[left]
            order = tuple(slots)
            weights[order] = weights.get(order, 0) + assignments
    return tuple(weights), tuple(weights.values())


def contest_event_roster_mode(category, rank, stage, flag_2720=False):
    """Resolve the roster mode selected by the single-player event."""
    if rank == "master":
        if stage == 17:
            return 1
        if stage == 19:
            return 2 if category == "beauty" and flag_2720 else 3
        if stage == 21:
            return 4
        return 0
    return 5 if stage < 9 else 0


def contest_result_stage(category, rank, stage, flag_2720, player_rank):
    """Resolve the result handler's transitions for the two Lisia milestones."""
    if rank == "master":
        if stage == 17 and player_rank == 1:
            return 18
        if stage == 19 and category == "beauty" and flag_2720:
            return 20
    return stage


def solo_roster_filter(category, rank, mode):
    """Filter and forced slots in the single-player roster function.

    The story state that supplies the numeric mode is a separate input.
    """
    if mode not in range(6):
        raise ValueError("Cartridge roster mode must be 0 through 5")
    regular = pool(category, rank, "early")
    special = {p.name: p for p in pool(category, rank, "rematch") if p not in regular}
    if mode in (1, 2):
        if rank != "master" or (mode == 2 and category != "beauty"):
            raise ValueError("Forced cartridge roster mode is incompatible with the division")
        if mode == 1:
            return regular + [special["Lisia"]], ("Lisia",)
        return regular + [special[name] for name in ("Lisia", "Wallace", "Chaz")], ("Lisia", "Wallace")

    allowed = {
        0: ("Chaz",),
        3: ("Lisia", "Chaz"),
        4: ("Lisia", "Wallace", "Chaz"),
        5: (),
    }[mode]
    return regular + [special[name] for name in allowed if name in special], ()


def move_slot_distribution(scores):
    """Resolve scores in slot order with the cartridge's sequential tie rule."""
    from fractions import Fraction

    if len(scores) != 4:
        raise ValueError("The contest AI evaluates four move slots")
    tie_replaces = Fraction(sum(bounded_bucket_count(100, r) for r in range(50)), 1 << 32)
    best = scores[0]
    distribution = {0: Fraction(1)}
    for slot, score in enumerate(scores[1:], 1):
        if score > best:
            best = score
            distribution = {slot: Fraction(1)}
        elif score == best:
            distribution = {i: weight * (1 - tie_replaces)
                            for i, weight in distribution.items()}
            distribution[slot] = tie_replaces
    return distribution
