"""Enumerate the random branches of a configured scenario without sampling."""

from fractions import Fraction
from itertools import groupby, permutations
from math import factorial


class Branch(Exception):
    def __init__(self, outcomes):
        self.outcomes = outcomes


class BranchLimit(ValueError):
    pass


class EnumeratingRandom:
    def __init__(self, prefix):
        self.prefix = iter(prefix)

    def choose(self, outcomes):
        if len(outcomes) == 1:
            return outcomes[0][0]
        index = next(self.prefix, None)
        if index is None:
            raise Branch(outcomes)
        return outcomes[index][0]

    def choices(self, population, weights):
        entries = [(value, Fraction(str(weight))) for value, weight in zip(population, weights)
                   if weight > 0]
        total = sum(weight for _, weight in entries)
        return [self.choose(tuple((value, weight / total) for value, weight in entries))]

    def choice(self, population):
        probability = Fraction(1, len(population))
        return self.choose(tuple((value, probability) for value in population))

    def percent(self, threshold):
        if threshold <= 0:
            return False
        if threshold >= 100:
            return True
        return self.choose(((True, Fraction(threshold, 100)),
                            (False, Fraction(100 - threshold, 100))))

    def ordered(self, population, key):
        """Randomize only within equal-priority groups."""
        result = []
        for _, group in groupby(sorted(population, key=key), key):
            members = tuple(group)
            weight = Fraction(1, factorial(len(members)))
            result.extend(self.choose(tuple((p, weight) for p in permutations(members))))
        return result


def enumerate_outcomes(evaluate, max_nodes):
    """Replay an event path for each reachable branch and yield weighted outcomes."""
    stack = [((), Fraction(1))]
    visited = 0
    while stack:
        prefix, probability = stack.pop()
        visited += 1
        if visited > max_nodes:
            raise BranchLimit(f"Exact branch limit ({max_nodes}) reached; no exact result produced")
        try:
            result = evaluate(EnumeratingRandom(prefix))
        except Branch as branch:
            stack.extend((prefix + (index,), probability * weight)
                         for index, (_, weight) in enumerate(branch.outcomes))
        else:
            yield result, probability
