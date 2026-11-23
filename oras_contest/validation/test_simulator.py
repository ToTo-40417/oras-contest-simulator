from itertools import product
from fractions import Fraction
from random import Random
import unittest

from oras_contest import catalog as c
from oras_contest.cartridge_ai import CartridgeAI, CartridgeLowerAI, master_move_score, move_score
from oras_contest import engine as e
from oras_contest.models import policy
from oras_contest.__main__ import road_to_lisia
from oras_contest.exact import BranchLimit, enumerate_outcomes
from oras_contest.cartridge import (TinyMT32, bounded_bucket_count, contest_event_roster_mode,
                                    contest_result_stage,
                                    move_slot_distribution, percent_bucket_weights,
                                    shuffled_slot_weights, solo_roster_filter)

SCHEDULE = ("roar", "giga-impact", None, "roar", "giga-impact")


def scripted(entrant, *_):
    return entrant.moves[0]


class ContestTest(unittest.TestCase):
    def test_catalog_integrity(self):
        self.assertEqual((len(c.MOVES), len(c.SPECIES), len(c.NPCS), len(c.EFFECTS)),
                         (621, 721, 69, 36))
        self.assertEqual(set(c.EFFECTS), {m["effect"] for m in c.MOVES.values()})
        for row in c.NPCS:
            self.assertIn(row["species"], c.SPECIES)
            self.assertEqual(len(row["moves"]), 4)
            self.assertTrue(set(row["moves"]) <= c.MOVES.keys())
        self.assertEqual(c.species_id("トドゼルガ"), "walrein")
        self.assertTrue({"roar", "giga-impact"} <= c.learned_moves("walrein"))
        self.assertNotIn(("roar", "giga-impact"), c.COMBOS)
        self.assertIn(("block", "explosion"), c.COMBOS)
        self.assertIn(("thunder-wave", "hex"), c.COMBOS)
        self.assertIn(("thunder-wave", "smelling-salts"), c.COMBOS)
        self.assertEqual(len(c.COMBOS), 189)
        self.assertEqual(c.EFFECTS[e.JAM_ALL]["jam"], 2)

    def test_intro_score_uses_adjacent_conditions_and_rounds_after_summing(self):
        conditions = (13, 3, 4, 7, 1)
        expected = (15, 11, 9, 9, 11)
        for category, score in zip(c.CATEGORIES, expected):
            self.assertEqual(c.intro_score(category, conditions), score)
            self.assertEqual(c.intro_score(category, conditions, scarf=True), score + 20)
            self.assertEqual(c.intro_score(category, (255,) * 5, scarf=True), 530)

    def test_walrein_orders_and_recharge_without_interference(self):
        players = (c.Entrant("Player", "walrein", ("roar", "giga-impact"), 510),
                   *(c.Entrant(str(i), "glalie", ("ice-fang", "shadow-claw"), 100 + i) for i in range(3)))
        _, _, rounds = e.simulate("tough", players, SCHEDULE,
                                   lambda entrant, state, *_: entrant.moves[state.last == entrant.moves[0]],
                                   Random(10), True)
        for index in (1, 4):
            actions = rounds[index]["actions"]
            self.assertEqual(actions[-1]["name"], "Player")
            self.assertEqual(actions[-1]["move"], "giga-impact")
            self.assertEqual(actions[-1]["jam"], {"0": 4, "1": 4, "2": 4})
            self.assertFalse(actions[-1]["combo"])
        player_t3 = next(a for a in rounds[2]["actions"] if a["name"] == "Player")
        self.assertEqual(player_t3["skipped"], "recharge")

    def test_fixed_turns_across_interruptions_and_all_divisions(self):
        interrupted = False
        for category, rank, seed in product(c.CATEGORIES, c.RANKS, range(12)):
            rng = Random(seed)
            eligible = c.pool(category, rank, "rematch")
            opponents = c.draw_roster(rng, eligible, category, "rematch")
            player = c.Entrant("Player", "walrein", ("roar", "giga-impact"), 510)
            unforced_passes = set()
            ranking, scores, log = e.simulate(category, (player, *opponents),
                                               SCHEDULE, policy("observed"), rng, True,
                                               unforced_passes=unforced_passes)
            self.assertEqual(set(ranking), set(range(4)))
            self.assertEqual([scores[i] for i in ranking], sorted(scores, reverse=True))
            self.assertEqual(len(log), 5)
            for index, turn in enumerate(log):
                action = next(a for a in turn["actions"] if a["name"] == "Player")
                self.assertEqual(action["scheduled"], SCHEDULE[index])
                if "move" in action:
                    self.assertEqual(action["move"], SCHEDULE[index])
                if index == 2:
                    recharging = any(a.get("move") == "giga-impact" and a["name"] == "Player"
                                     for a in log[1]["actions"])
                    nervous = any("Player" in a.get("nervous", ()) for a in turn["actions"])
                    expected = "recharge" if recharging else "nervous" if nervous else "scheduled_pass"
                    self.assertEqual(action["skipped"], expected)
                    self.assertEqual(unforced_passes, {3} if expected == "scheduled_pass" else set())
                interrupted |= action.get("skipped") == "nervous"
                self.assertTrue(all(0 <= hearts <= 16 for hearts in turn["hearts"].values()))
        self.assertTrue(interrupted)

    def test_appearance_presets_and_fixed_roster(self):
        for category in c.CATEGORIES:
            early = c.pool(category, "master", "early")
            self.assertNotIn("Lisia", [p.name for p in early])
            eligible = c.pool(category, "master", "challenger")
            roster = c.draw_roster(Random(12), eligible, category, "challenger")
            self.assertIn("Lisia", [p.name for p in roster])
            self.assertEqual("Wallace" in [p.name for p in roster], category == "beauty")
        eligible = c.pool("beauty", "master", "rematch")
        chosen = ("Lisia", "Wallace", "Layla")
        roster = c.draw_roster(Random(12), eligible, "beauty", "rematch", chosen)
        self.assertEqual(tuple(p.name for p in roster), chosen)

    def test_shield_charges_and_half_jam(self):
        mist = e.State(points=8, shield=-1, performed="mist")
        safeguard = e.State(points=8, shield=1, performed="safeguard")
        targets = [(0, mist), (1, safeguard)]
        for _ in range(2):
            e.apply_jam(e.JAM_ALL_STRONG, c.MOVES["blizzard"], targets)
        self.assertEqual((mist.points, safeguard.points), (8, 5))
        vulnerable = e.State(points=7, vulnerable=True, performed="draco-meteor")
        e.apply_jam(e.JAM_HALF, c.MOVES["hail"], [(0, vulnerable)])
        self.assertEqual(vulnerable.points, 0)

    def test_cartridge_reset_consumes_protection_only_with_a_matching_status(self):
        for effect, status, value in (
            (e.RESET_STARS, "stars", 1),
            (e.RESET_COMBO, "combo", "thunder-wave"),
        ):
            target = e.State(shield=1)
            e.apply_jam(effect, None, [(0, target)], cartridge=True)
            self.assertEqual(target.shield, 1)
            setattr(target, status, value)
            e.apply_jam(effect, None, [(0, target)], cartridge=True)
            self.assertEqual(target.shield, 0)
            self.assertEqual(getattr(target, status), value)
            e.apply_jam(effect, None, [(0, target)], cartridge=True)
            self.assertFalse(getattr(target, status))

    def test_cartridge_jam_effects_reach_an_earlier_recharging_slot(self):
        class Plan:
            cartridge_appeal = True

            def __init__(self, third_turn_move):
                self.third_turn_move = third_turn_move

            def plan(self, players, states, order, category, turn, meter, rng):
                return {1: self.third_turn_move if turn == 3 else "mist", 2: "mist", 3: "mist"}

        entrants = (c.Entrant("Player", "walrein", (), 510),
                    *(c.Entrant(str(i), "glalie", (), 100 + i) for i in (1, 2, 3)))
        schedule = ("focus-energy", "giga-impact", None, "strength")
        for move, expected in (("haze", 5), ("mist", 6)):
            _, _, log = e.simulate("tough", entrants, schedule, Plan(move), Random(1), trace=True)
            self.assertEqual(log[2]["actions"][0]["skipped"], "recharge")
            followup = next(a for a in log[3]["actions"] if a["name"] == "Player")
            self.assertEqual(followup["appeal"], expected)
        for move, loss in (("ice-beam", 4), ("blizzard", 3), ("hail", 1),
                           ("bonemerang", 4), ("double-hit", 1)):
            _, _, log = e.simulate("tough", entrants, schedule, Plan(move), Random(1), trace=True)
            self.assertEqual(log[2]["actions"][0]["skipped"], "recharge")
            self.assertEqual(log[2]["hearts"]["Player"], -loss)
            self.assertEqual(log[2]["cumulative_hearts"]["Player"],
                             log[1]["cumulative_hearts"]["Player"] - loss)

    def test_cartridge_nervous_target_keeps_combo_expectation_until_turn_end(self):
        class Plan:
            cartridge_appeal = True

            def __init__(self, jam_move):
                self.jam_move = jam_move

            def plan(self, players, states, order, category, turn, meter, rng):
                if turn == 2:
                    return {1: "attract", 2: self.jam_move, 3: "mist"}
                return {1: "thunderbolt", 2: "mist", 3: "mist"}

        class FirstTargetNervous(Random):
            draws = 0

            def choices(self, population, weights):
                if population == (True, False):
                    self.draws += 1
                    return [self.draws == 1]
                return super().choices(population, weights)

        entrants = (c.Entrant("Player", "walrein", (), 510),
                    *(c.Entrant(str(i), "glalie", (), 100 + i) for i in (1, 2, 3)))
        for move, loss in (("punishment", 5), ("double-hit", 0)):
            _, _, log = e.simulate("cool", entrants, ("thunder-wave", "hex", "hex"),
                                   Plan(move), FirstTargetNervous(1), trace=True)
            turn_two = {a["name"]: a for a in log[1]["actions"]}
            self.assertEqual(turn_two["Player"]["skipped"], "nervous")
            self.assertEqual(turn_two["2"]["jam"].get("Player", 0), loss)
            turn_three = next(a for a in log[2]["actions"] if a["name"] == "Player")
            self.assertFalse(turn_three["combo"])

    def test_cartridge_appeal_copies_and_half_jam(self):
        for points, copied_sum, copied_previous in ((-3, 1, 1), (3, 3, 4), (16, 9, 16)):
            prior = [e.State(points=points)]
            self.assertEqual(e.appeal_base(e.COPY_ALL, 1, 0, prior, cartridge=True), copied_sum)
            self.assertEqual(e.appeal_base(e.COPY_PREVIOUS, 1, 0, prior, cartridge=True),
                             copied_previous)
        high_scores = [e.State(points=16)] * 3
        self.assertEqual(e.appeal_base(e.COPY_ALL, 3, 0, high_scores, cartridge=True), 16)
        for points, vulnerable, remaining in ((-1, True, -3), (0, True, -2), (1, True, 0),
                                                (7, True, 0), (7, False, 4), (0, False, -1)):
            target = e.State(points=points, vulnerable=vulnerable, performed="mist")
            e.apply_jam(e.JAM_HALF, c.MOVES["hail"], [(0, target)], cartridge=True)
            self.assertEqual(target.points, remaining)

    def test_cartridge_previous_quality_uses_base_and_stars(self):
        for stars in range(4):
            for previous, expected in ((2 + stars, 6), (3 + stars, 3), (4 + stars, 0)):
                self.assertEqual(e.appeal_base(e.PREVIOUS_QUALITY, 1, 0,
                                               [e.State(points=previous)],
                                               cartridge=True, stars=stars), expected)

    def test_cartridge_repetition_keeps_last_successful_move_through_recharge(self):
        entrants = (
            c.Entrant("Player", "walrein", ("giga-impact",), 510),
            *(c.Entrant(name, "glalie", ("mist",) * 4, intro)
              for name, intro in (("A", 100), ("B", 120), ("C", 140))),
        )
        schedule = ("giga-impact", None, "giga-impact")
        _, _, log = e.simulate("tough", entrants, schedule, CartridgeAI("master"),
                               Random(123), trace=True)
        actions = [next(a for a in row["actions"] if a["name"] == "Player") for row in log]
        self.assertFalse(actions[0]["repeated"])
        self.assertEqual(actions[1]["skipped"], "recharge")
        self.assertTrue(actions[2]["repeated"])

    def test_priority_and_excitement(self):
        states = [e.State(next_order=x) for x in (-1, 2, -3, 4)]
        self.assertEqual(e.next_order(states, Random(7)), [2, 0, 1, 3])
        self.assertEqual(e.reaction("beauty", c.MOVES["giga-impact"], 3, False, False), -1)
        self.assertEqual(e.reaction("beauty", c.MOVES["giga-impact"], 3, True, False), 0)
        self.assertEqual(e.reaction("beauty", c.MOVES["pay-day"], 0, False, True), 1)
        self.assertEqual(e.appeal_base(e.COPY_ALL, 2, 0, [e.State(points=3),
                                                          e.State(points=6)]), 6)

    def test_cartridge_position_and_crowd_scores(self):
        self.assertEqual(
            [e.appeal_base(e.CROWD, 0, meter, (), cartridge=True) for meter in range(5)],
            [1, 2, 3, 5, 6],
        )
        self.assertEqual(
            [e.appeal_base(e.LATER, position, 0, (), cartridge=True) for position in range(4)],
            [1, 2, 4, 6],
        )
        self.assertEqual(e.reaction("tough", c.MOVES["giga-impact"], 1, False, True), 0)
        self.assertEqual(e.reaction("beauty", c.MOVES["giga-impact"], 1, False, True), -1)
        self.assertEqual(e.reaction("tough", c.MOVES["pay-day"], 1, False, True), 1)

    def test_road_to_lisia_uses_all_five_master_win_rates(self):
        divisions = [{"category": category, "player_rank_pct": {1: 50.0}}
                     for category in c.CATEGORIES]
        result = road_to_lisia(divisions, 2)
        self.assertAlmostEqual(result["all_five_first_attempt_pct"], 100 * .5**5)
        self.assertAlmostEqual(result["all_five_within_attempt_budget_pct"], 100 * .75**5)

    def test_weighted_roster_enumeration(self):
        pool = c.pool("beauty", "master", "rematch")
        entries = list(c.roster_distribution(
            pool, "beauty", "rematch", ("Lisia", "Wallace"),
            {"Layla": 2, "Chaz": 0},
        ))
        self.assertEqual(sum(weight for _, weight in entries), 1)
        self.assertEqual({row[-1].name: weight for row, weight in entries}["Layla"],
                         Fraction(2, 5))
        self.assertNotIn("Chaz", {row[-1].name for row, _ in entries})

    def test_exact_branch_mass_and_limit(self):
        def evaluate(rng):
            return rng.percent(20), rng.choices(("a", "b"), (1, 3))[0]

        outcomes = dict(enumerate_outcomes(evaluate, 20))
        self.assertEqual(sum(outcomes.values()), 1)
        self.assertEqual(outcomes[(True, "b")], Fraction(3, 20))
        with self.assertRaises(BranchLimit):
            list(enumerate_outcomes(evaluate, 1))

    def test_exact_end_to_end_walrein(self):
        entrants = (c.Entrant("Player", "walrein", ("roar", "giga-impact"), 510),
                    c.Entrant("A", "glalie", ("ice-beam",), 200),
                    c.Entrant("B", "gorebyss", ("aqua-tail",), 150),
                    c.Entrant("C", "altaria", ("draco-meteor",), 100))
        outcomes = list(enumerate_outcomes(
            lambda rng: e.simulate("tough", entrants, SCHEDULE, scripted, rng), 10000
        ))
        self.assertEqual(sum(weight for _, weight in outcomes), 1)

    def test_cartridge_rng_reference_and_reduction(self):
        rng = TinyMT32(1)
        self.assertEqual([rng.uint32() for _ in range(5)],
                         [2545341989, 981918433, 3715302833, 2387538352, 3591001365])
        for bound in (3, 100, 65535):
            self.assertEqual(sum(bounded_bucket_count(bound, i) for i in range(bound)), 2**32)
        self.assertEqual(sum(bounded_bucket_count(100, i) for i in range(50)), 2**31)
        self.assertEqual(TinyMT32(1).bounded(100), 59)
        self.assertEqual(TinyMT32(1).bounded(65535), 2545341989 % 65535)

    def test_cartridge_sequential_ai_ties(self):
        self.assertEqual(move_slot_distribution((0, 0, 0, 0)),
                         {0: Fraction(1, 8), 1: Fraction(1, 8),
                          2: Fraction(1, 4), 3: Fraction(1, 2)})
        self.assertEqual(move_slot_distribution((1, 2, 0, 2)), {1: .5, 3: .5})

    def test_cartridge_solo_roster_filters_all_divisions(self):
        for category, rank, mode in product(c.CATEGORIES, c.RANKS, (0, 3, 4, 5)):
            pool, forced = solo_roster_filter(category, rank, mode)
            self.assertFalse(forced)
            self.assertGreaterEqual(len(pool), 3)
            names = {p.name for p in pool}
            if mode in (0, 5):
                self.assertFalse(names & {"Lisia", "Wallace"})
            if mode == 5:
                self.assertNotIn("Chaz", names)
            if mode in (3, 4) and rank == "master":
                self.assertIn("Lisia", names)
        self.assertEqual(solo_roster_filter("cool", "master", 1)[1], ("Lisia",))
        first_pool, first_fixed = solo_roster_filter("beauty", "master", 1)
        self.assertEqual(first_fixed, ("Lisia",))
        self.assertFalse({"Wallace", "Chaz"} & {p.name for p in first_pool})
        paired_pool, paired_fixed = solo_roster_filter("beauty", "master", 2)
        self.assertEqual(paired_fixed, ("Lisia", "Wallace"))
        rosters = tuple(c.roster_distribution(paired_pool, "beauty", "early", paired_fixed))
        self.assertEqual(sum(weight for _, weight in rosters), 1)
        self.assertTrue(all(tuple(p.name for p in roster[:2]) == paired_fixed
                            for roster, _ in rosters))
        self.assertEqual(sum(weight for roster, weight in rosters if roster[2].name == "Chaz"),
                         Fraction(1, len(paired_pool) - len(paired_fixed)))

    def test_contest_event_stage_to_roster_mode(self):
        for category, rank in product(c.CATEGORIES, c.RANKS):
            self.assertEqual(contest_event_roster_mode(category, rank, 8),
                             0 if rank == "master" else 5)
            self.assertEqual(contest_event_roster_mode(category, rank, 9), 0)
            self.assertEqual(contest_event_roster_mode(category, rank, 17),
                             1 if rank == "master" else 0)
            self.assertEqual(contest_event_roster_mode(category, rank, 19),
                             3 if rank == "master" else 0)
            self.assertEqual(contest_event_roster_mode(category, rank, 19, flag_2720=True),
                             (2 if category == "beauty" else 3) if rank == "master" else 0)
            self.assertEqual(contest_event_roster_mode(category, rank, 21),
                             4 if rank == "master" else 0)

    def test_lisia_match_result_stage_transitions(self):
        for place in range(1, 5):
            self.assertEqual(contest_result_stage("cool", "master", 17, False, place),
                             18 if place == 1 else 17)
            self.assertEqual(contest_result_stage("beauty", "master", 19, True, place), 20)
            self.assertEqual(contest_result_stage("beauty", "master", 19, False, place), 19)
            self.assertEqual(contest_result_stage("cool", "master", 19, True, place), 19)
        self.assertEqual(contest_result_stage("beauty", "hyper", 17, True, 1), 17)

    def test_cartridge_ai_penalties_and_preselection(self):
        self.assertEqual(move_score("normal", "beauty", "block", 1, 4, 0, None, False), -2)
        self.assertEqual(move_score("hyper", "beauty", "round", 1, 1, 2, None, False), -2)
        self.assertEqual(move_score("hyper", "beauty", "recycle", 1, 1, 2, None, False), 0)
        self.assertEqual(move_score("super", "beauty", "explosion", 5, 4, 0, "block", True), 2)
        for rank, category in product(("normal", "super", "hyper"), c.CATEGORIES):
            rng = Random(9)
            roster = c.draw_roster(rng, c.pool(category, rank, "early"), category, "early")
            player = c.Entrant("Player", "walrein", ("roar", "giga-impact"), 510)
            _, _, rounds = e.simulate(category, (player, *roster), SCHEDULE,
                                      CartridgeLowerAI(rank), rng, True)
            for round_log in rounds:
                for action in round_log["actions"]:
                    if action["name"] != "Player":
                        npc = next(p for p in roster if p.name == action["name"])
                        self.assertIn(action["planned_move"], npc.moves)
                        if "move" in action:
                            self.assertEqual(action["planned_move"], action["move"])

    def test_cartridge_master_and_special_decisions(self):
        self.assertEqual(master_move_score("beauty", "draco-meteor", 2, 1, 4, None, False), 2)
        self.assertEqual(master_move_score("beauty", "giga-impact", 5, 4, 0, None, False), 7)
        normal = master_move_score("cool", "electric-terrain", 2, 1, 3, None, False)
        special = master_move_score("cool", "electric-terrain", 2, 1, 3, None, False,
                                    special=True)
        self.assertEqual(special, normal + 1)
        for category, rank in product(c.CATEGORIES, c.RANKS):
            rng = Random(47)
            roster = c.draw_roster(rng, c.pool(category, rank, "rematch"), category, "rematch")
            player = c.Entrant("Player", "walrein", ("roar", "giga-impact"), 510)
            ranking, _, trace = e.simulate(category, (player, *roster), SCHEDULE,
                                          CartridgeAI(rank), rng, True)
            self.assertEqual(set(ranking), set(range(4)))
            self.assertEqual(len(trace), 5)
        rng = Random(2)
        beauty_pool = {npc.name: npc for npc in c.pool("beauty", "master", "rematch")}
        roster = tuple(beauty_pool[name] for name in ("Lisia", "Wallace", "Chaz"))
        _, _, trace = e.simulate("beauty", (player, *roster), SCHEDULE, CartridgeAI("master"), rng, True)
        self.assertEqual(len(trace), 5)

    def test_signed_turn_reduces_prior_appeal_total(self):
        class ScriptedCartridge:
            cartridge_appeal = True

            def plan(self, players, states, order, category, turn, meter, rng):
                return dict.fromkeys((1, 2, 3), "blizzard" if turn == 2 else "shadow-ball")

        player = c.Entrant("Player", "smeargle", ("draco-meteor", "ice-beam"), 510)
        rivals = tuple(c.Entrant(str(i), "glalie", ("blizzard", "shadow-ball"), 150 + i)
                       for i in range(3))
        _, scores, rounds = e.simulate(
            "beauty", (player, *rivals), ("draco-meteor", "ice-beam", None, None, None),
            ScriptedCartridge(), Random(12), True,
        )
        self.assertEqual(rounds[0]["hearts"]["Player"], 7)
        self.assertEqual(rounds[1]["hearts"]["Player"], -7)
        self.assertEqual(scores[0], 510)

    def test_cartridge_forced_slots_are_assigned_by_swaps(self):
        class NoTieSwap:
            def percent(self, threshold):
                return False

        states = [e.State(), e.State(), e.State(), e.State(next_order=-4)]
        self.assertEqual(e.cartridge_next_order([0, 1, 2, 3], states, NoTieSwap(), False),
                         [3, 1, 2, 0])
        states[2].next_order = 3
        self.assertEqual(e.cartridge_next_order([0, 1, 2, 3], states, NoTieSwap(), False),
                         [3, 1, 0, 2])

    def test_cartridge_variable_appeal_probabilities(self):
        outcomes = dict(enumerate_outcomes(
            lambda rng: e.appeal_base(e.VARIABLE, 0, 0, (), rng, cartridge=True), 10))
        counts = {1: 1288490189, 2: 1288490189, 4: 858993459, 6: 429496730, 8: 429496729}
        self.assertEqual(outcomes, {hearts: Fraction(count, 1 << 32)
                                    for hearts, count in counts.items()})
        self.assertEqual(percent_bucket_weights(20), (858993460, 3435973836))

    def test_cartridge_shuffle_preserves_later_forced_slots_and_key_ties(self):
        states = [e.State(next_order=order) for order in (0, 0, -3, 4)]
        outcomes = dict(enumerate_outcomes(
            lambda rng: tuple(e.cartridge_next_order([0, 1, 2, 3], states, rng, True)), 10
        ))
        self.assertEqual(outcomes, {
            (2, 0, 1, 3): Fraction((1 << 32) - 1, 1 << 33),
            (2, 1, 0, 3): Fraction((1 << 32) + 1, 1 << 33),
        })
        self.assertEqual(sum(shuffled_slot_weights(4)[1]), 1 << 128)

    def test_cartridge_solo_final_ties(self):
        self.assertEqual(e.cartridge_ranking([500, 500, 400, 400], None), [0, 1, 3, 2])
        self.assertEqual(e.cartridge_ranking([400, 500, 300, 400], None), [1, 3, 0, 2])
        for scores, top, tail in (
            ([500, 500, 500, 500], {(0, 1, 2, 3), (0, 1, 3, 2),
                                    (0, 2, 1, 3), (0, 2, 3, 1),
                                    (0, 3, 1, 2), (0, 3, 2, 1)}, ()),
            ([400, 500, 500, 300], {(1, 2), (2, 1)}, (0, 3)),
        ):
            outcomes = dict(enumerate_outcomes(
                lambda rng: tuple(e.cartridge_ranking(scores, rng)), 50
            ))
            self.assertEqual(set(outcomes), {order + tail for order in top})
            self.assertEqual(sum(outcomes.values()), 1)
            if len(top) == 2:
                self.assertEqual(set(outcomes.values()), {Fraction(1, 2)})
            else:
                second_place_for_npc_two = sum(
                    weight for order, weight in outcomes.items() if order[1] == 2
                )
                self.assertEqual(second_place_for_npc_two, Fraction(1431655766, 1 << 32))

    def test_all_effects_execute(self):
        representatives = {move["effect"]: key for key, move in c.MOVES.items()}
        for category, move in product(c.CATEGORIES, representatives.values()):
            players = (c.Entrant("Player", "smeargle", (move,), 510),
                       *(c.Entrant(str(i), "glalie", ("mist",), 200 + i) for i in range(3)))
            for intro in (0, 510):
                first = c.Entrant("Player", "smeargle", (move,), intro)
                ranking, _, log = e.simulate(category, (first, *players[1:]),
                                              (move,) * 5, scripted, Random(0), True)
                self.assertEqual(len(ranking), 4)
                self.assertEqual(len(log), 5)


if __name__ == "__main__":
    unittest.main()
