"""Run with python3 -m oras_contest."""

import argparse
from collections import Counter
from itertools import product
import json
from math import prod, sqrt
from pathlib import Path
from random import Random

from . import catalog as c
from .engine import simulate
from .cartridge import (contest_event_roster_mode, contest_result_stage,
                        random_key_collision_probability, solo_roster_filter)
from .cartridge_ai import CartridgeAI, CartridgeLowerAI, SPECIAL_TRAINERS
from .exact import enumerate_outcomes
from .models import PROFILES, policy

MEGA_ELIGIBLE = frozenset("""
venusaur charizard blastoise beedrill pidgeot alakazam slowbro gengar kangaskhan
pinsir gyarados aerodactyl mewtwo ampharos steelix scizor heracross houndoom
tyranitar sceptile blaziken swampert gardevoir sableye mawile aggron medicham
manectric sharpedo camerupt altaria banette absol glalie salamence metagross
latias latios lopunny garchomp lucario abomasnow gallade audino diancie
""".split())


def percentage(counts, denominator):
    return {key: round(float(100 * value / denominator), 6)
            for key, value in sorted(counts.items())} if denominator else {}


def wilson_interval_pct(successes, trials):
    if not trials:
        return None
    z = 1.959963984540054
    p = successes / trials
    adjustment = z * z / trials
    center = (p + adjustment / 2) / (1 + adjustment)
    margin = z * sqrt((p * (1 - p) + adjustment / 4) / trials) / (1 + adjustment)
    return [round(100 * max(0, center - margin), 6),
            round(100 * min(1, center + margin), 6)]


def run(category, rank, args, species, schedule, known_moves, npc_policy, parameters):
    matching_scarf = args.item == "scarf" and args.scarf_category in (None, category)
    intro = c.intro_score(category, args.conditions, matching_scarf)
    mega = args.item == "mega" or (species == "rayquaza" and "dragon-ascent" in known_moves)
    player = c.Entrant("Player", species, known_moves, intro, mega)
    roster_mode = args.cartridge_roster_mode
    if args.contest_event_stage is not None:
        roster_mode = contest_event_roster_mode(category, rank, args.contest_event_stage,
                                              args.event_flag_2720)
    if roster_mode is None:
        eligible = c.pool(category, rank, args.progress)
        fixed = args.opponent
        draw_progress = args.progress
    else:
        eligible, forced = solo_roster_filter(category, rank, roster_mode)
        fixed = args.opponent or forced
        draw_progress = "early"
    if args.npc == "cartridge":
        npc_policy = CartridgeAI(rank)
    if args.npc == "cartridge-lower":
        npc_policy = CartridgeLowerAI(rank)
        included = {p.name.casefold() for p in eligible}
        if len(fixed) == 3:
            included &= {name.casefold() for name in fixed}
        if included & {name.casefold() for name in SPECIAL_TRAINERS}:
            raise ValueError("For ordinary cartridge AI, use early progress, cartridge mode 5, "
                             "or a fully fixed roster of ordinary NPCs")
    roster_rng, appeal_rng = Random(args.seed), Random(args.seed ^ 0xA537)
    ranks, score_counts, appearances, rosters = Counter(), Counter(), Counter(), Counter()
    lisia_ranks, joint_ranks = Counter(), Counter()
    unforced_pass_counts = Counter({turn: 0 for turn, move in enumerate(schedule, 1) if move is None})
    encounters = strict = ties = 0
    sample = None
    roster_weights = parameters.get("roster_weights")
    roster_distribution = tuple(c.roster_distribution(
        eligible, category, draw_progress, fixed, roster_weights
    ))
    roster_probabilities = Counter()
    appearance_probabilities = {entrant.name: 0 for entrant in eligible}
    for roster, probability in roster_distribution:
        roster_probabilities[" / ".join(sorted(p.name for p in roster))] += probability
        for entrant in roster:
            appearance_probabilities[entrant.name] += probability

    def evaluate(random, roster, trace):
        entrants = (player, *roster)
        unforced_passes = set()
        ranking, scores, log = simulate(category, entrants, schedule, npc_policy,
                                        random, trace=trace, unforced_passes=unforced_passes)
        return entrants, ranking, scores, log, unforced_passes

    if args.exact:
        def evaluate_branch(random):
            roster = random.choose(roster_distribution)
            return evaluate(random, roster, args.trace)

        outcomes = enumerate_outcomes(evaluate_branch, args.max_nodes)
    else:
        outcomes = (
            (evaluate(appeal_rng, c.draw_roster(roster_rng, eligible, category, draw_progress,
                                             fixed, roster_weights), args.trace and i == 0), 1)
            for i in range(args.trials)
        )
    for (entrants, ranking, scores, log, unforced_passes), weight in outcomes:
        for turn in unforced_passes:
            unforced_pass_counts[turn] += weight
        player_rank = ranking.index(0) + 1
        ranks[player_rank] += weight
        score_counts[scores[0]] += weight
        ties += weight * (sum(score == scores[0] for score in scores) > 1)
        names = [p.name for p in entrants]
        for name in names[1:]:
            appearances[name] += weight
        rosters[" / ".join(sorted(names[1:]))] += weight
        if "Lisia" in names:
            encounters += weight
            lisia = names.index("Lisia")
            last_rank = ranking.index(lisia) + 1
            lisia_ranks[last_rank] += weight
            joint_ranks[f"{player_rank}/{last_rank}"] += weight
            strict += weight * (scores[0] > max(scores[1:]) and
                       scores[lisia] < min(s for j, s in enumerate(scores) if j != lisia))
        if log and sample is None:
            sample = {"turns": log, "ranking": [names[j] for j in ranking],
                      "scores": dict(zip(names, scores)),
                      "intro_scores": {entrant.name: entrant.intro for entrant in entrants}}
    n = 1 if args.exact else args.trials
    result_stages = Counter()
    if args.contest_event_stage in (17, 19):
        for player_rank, weight in ranks.items():
            stage = contest_result_stage(category, rank, args.contest_event_stage,
                                         args.event_flag_2720, player_rank)
            result_stages[stage] += weight
    return {
        "category": category, "rank": rank, "trials": None if args.exact else n, "player_intro": intro,
        "player_mega_eligible": mega,
        "cartridge_roster_mode": roster_mode,
        **({"roster_key_collision_pct_if_independent":
            float(100 * random_key_collision_probability(len(c.NPCS)))} if roster_mode is not None else {}),
        **({"post_result_event_stage_pct": percentage(result_stages, n)} if result_stages else {}),
        "player_rank_pct": percentage({r: ranks[r] for r in range(1, 5)}, n),
        **({"monte_carlo_95_pct_intervals": {
            "player_rank_pct": {r: wilson_interval_pct(ranks[r], n) for r in range(1, 5)},
            "player_first_lisia_fourth_pct": wilson_interval_pct(joint_ranks["1/4"], n),
            "player_first_lisia_fourth_given_appearance_pct": wilson_interval_pct(
                joint_ranks["1/4"], encounters),
            "strict_player_first_lisia_fourth_pct": wilson_interval_pct(strict, n),
            "strict_player_first_lisia_fourth_given_appearance_pct": wilson_interval_pct(
                strict, encounters),
        }} if not args.exact else {}),
        "unforced_scheduled_pass_pct_by_turn": percentage(unforced_pass_counts, n),
        "player_score_pct": percentage(score_counts, n),
        "player_tied_trials": None if args.exact else ties,
        "player_tied_pct": float(100 * ties / n),
        **({"exact_fractions": {
            "player_rank": {i: str(ranks[i]) for i in range(1, 5)},
            "lisia_appearance": str(encounters),
            "player_first_lisia_fourth": str(joint_ranks["1/4"]),
            "strict_player_first_lisia_fourth": str(strict),
            "strict_given_lisia_appearance": str(strict / encounters) if encounters else None,
        }} if args.exact else {}),
        "npc_appearance_pct": percentage({p.name: appearances[p.name] for p in eligible}, n),
        "roster_pct": percentage(rosters, n),
        "scenario_roster_exact_pct": percentage(roster_probabilities, 1),
        "scenario_npc_appearance_exact_pct": percentage(appearance_probabilities, 1),
        "lisia_encounters": None if args.exact else encounters,
        "lisia_appearance_pct": float(100 * encounters / n),
        "lisia_rank_given_appearance_pct": percentage(lisia_ranks, encounters),
        "player_lisia_joint_ranks_given_appearance_pct": percentage(joint_ranks, encounters),
        "player_first_lisia_fourth_pct": float(100 * joint_ranks["1/4"] / n),
        "player_first_lisia_fourth_given_appearance_pct": (
            float(100 * joint_ranks["1/4"] / encounters) if encounters else None),
        "strict_player_first_lisia_fourth_count": None if args.exact else strict,
        "strict_player_first_lisia_fourth_pct": float(100 * strict / n),
        "strict_player_first_lisia_fourth_given_appearance_pct": (
            float(100 * strict / encounters) if encounters else None),
        **({"trace": sample} if sample is not None else {}),
    }


def road_to_lisia(divisions, attempts):
    """Combine independent per-division estimates for a fixed entrant."""
    probabilities = {
        row["category"]: row["player_rank_pct"][1] / 100
        for row in divisions
    }
    return {
        "attempts_per_category": attempts,
        "assumption": "independent attempts with unchanged pre-Lisia opponent pool",
        "master_win_pct": {key: 100 * p for key, p in probabilities.items()},
        "all_five_first_attempt_pct": 100 * prod(probabilities.values()),
        "all_five_within_attempt_budget_pct": 100 * prod(
            1 - (1 - p) ** attempts for p in probabilities.values()
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    sim = subs.add_parser("simulate")
    sim.add_argument("--species", required=True)
    sim.add_argument("--conditions", nargs=5, required=True, type=int,
                     metavar=("COOL", "BEAUTY", "CUTE", "CLEVER", "TOUGH"))
    sim.add_argument("--turns", required=True, nargs=5, metavar="MOVE")
    sim.add_argument("--known-move", action="append", default=[], metavar="MOVE",
                     help="include a move the Pokémon knows but never uses in the five turns")
    sim.add_argument("--category", choices=(*c.CATEGORIES, "all"), required=True)
    sim.add_argument("--rank", choices=(*c.RANKS, "all"), required=True)
    sim.add_argument("--item", choices=("none", "scarf", "mega"), default="none")
    sim.add_argument("--scarf-category", choices=c.CATEGORIES,
                     help="hold the same category's scarf across all divisions")
    sim.add_argument("--progress", choices=("early", "postgame", "challenger", "rematch"),
                     default="early")
    sim.add_argument("--npc", choices=(*PROFILES, "cartridge", "cartridge-lower"), required=True)
    roster = sim.add_mutually_exclusive_group()
    roster.add_argument("--cartridge-roster-mode", type=int, choices=range(6),
                        help="use a verified single-player roster filter by numeric mode")
    roster.add_argument("--contest-event-stage", type=int, metavar="STAGE",
                        help="resolve the roster mode using the single-player contest event stage")
    sim.add_argument("--hall-of-fame", "--event-flag-2720", dest="event_flag_2720",
                     action="store_true",
                     help="use the post-Hall of Fame roster rules for the supplied event stage")
    sim.add_argument("--opponent", action="append", default=[])
    sim.add_argument("--parameters", type=Path)
    sim.add_argument("--exact", action="store_true")
    sim.add_argument("--max-nodes", type=int, default=100000)
    sim.add_argument("--trials", type=int, default=10000)
    sim.add_argument("--seed", type=int, default=1)
    sim.add_argument("--trace", action="store_true")
    sim.add_argument("--road-to-lisia", type=int, metavar="ATTEMPTS_PER_CATEGORY",
                     help="summarize winning all five Masters before Lisia unlocks")
    sim.add_argument("--output", type=Path)
    listing = subs.add_parser("list")
    listing.add_argument("kind", choices=("moves", "species", "npcs"))
    listing.add_argument("--category", choices=c.CATEGORIES)
    listing.add_argument("--rank", choices=c.RANKS)
    listing.add_argument("--species")
    args = parser.parse_args()
    try:
        if args.command == "list":
            if args.kind == "species":
                output = {k: {f: v[f] for f in ("id", "name", "ja")}
                          for k, v in c.SPECIES.items()}
                output["forms"] = sorted(c.FORMS)
            elif args.kind == "moves":
                eligible = c.learned_moves(c.species_id(args.species)) if args.species else c.MOVES
                output = {k: dict(v, rules=c.EFFECTS[v["effect"]]) for k, v in c.MOVES.items()
                          if k in eligible and (not args.category or v["type"] == args.category)}
            else:
                output = [row for row in c.NPCS if
                          (not args.rank or c.RANKS[row["rank"] - 1] == args.rank) and
                          (not args.category or args.category in row["scores"])]
        else:
            if args.trials < 1 or args.max_nodes < 1:
                raise ValueError("Trial count and exact branch limit must be positive")
            species = c.species_id(args.species)
            schedule = tuple(None if m == "-" else c.move_id(m) for m in args.turns)
            used = tuple(move for move in schedule if move is not None)
            known_moves = tuple(dict.fromkeys((*used, *(c.move_id(m) for m in args.known_move))))
            known = set(known_moves)
            if not used or len(known) > 4:
                raise ValueError("Specify at least one scheduled move and at most four known moves")
            illegal = known - c.learned_moves(species) | (known & {"struggle"})
            if illegal:
                raise ValueError(f"Moves unavailable to {species}: {', '.join(sorted(illegal))}")
            if args.item == "mega" and species not in MEGA_ELIGIBLE:
                raise ValueError(f"No usable Mega Stone for {species}")
            if args.scarf_category is not None and args.item != "scarf":
                raise ValueError("--scarf-category requires --item scarf")
            categories = c.CATEGORIES if args.category == "all" else (args.category,)
            ranks = c.RANKS if args.rank == "all" else (args.rank,)
            if args.contest_event_stage is not None and args.contest_event_stage < 0:
                raise ValueError("Contest event stage must be nonnegative")
            if args.event_flag_2720 and args.contest_event_stage is None:
                raise ValueError("--hall-of-fame requires --contest-event-stage")
            if args.road_to_lisia is not None:
                if args.road_to_lisia < 1:
                    raise ValueError("Attempts per category must be positive")
                if (args.category != "all" or args.rank != "master" or
                        args.progress not in {"early", "postgame"} or args.opponent):
                    raise ValueError("Road to Lisia requires all categories, Master rank, "
                                     "early or postgame progress, and an open roster")
            parameters = json.loads(args.parameters.read_text(encoding="utf-8")) if args.parameters else {}
            if (args.cartridge_roster_mode is None and args.contest_event_stage is None
                    and args.npc == "cartridge" and args.progress == "challenger"
                    and not args.opponent and not parameters.get("roster_weights")):
                args.contest_event_stage = 17
            if args.cartridge_roster_mode is not None or args.contest_event_stage is not None:
                if args.opponent or parameters.get("roster_weights"):
                    raise ValueError("Cartridge roster mode cannot use custom roster overrides")
                if args.road_to_lisia is not None:
                    modes = {args.cartridge_roster_mode} if args.contest_event_stage is None else {
                        contest_event_roster_mode(category, "master", args.contest_event_stage,
                                                  args.event_flag_2720)
                        for category in categories
                    }
                    if not modes <= {0, 5}:
                        raise ValueError("Road to Lisia needs cartridge modes that exclude Lisia")
            if args.npc in {"cartridge", "cartridge-lower"}:
                if parameters.get("move_weights"):
                    raise ValueError("Cartridge scoring cannot use hypothetical move weights")
                npc_policy = None
            else:
                npc_policy = policy(args.npc, parameters.get("move_weights"))
            output = {
                "probability_basis": "scenario model, not measured game probabilities",
                "probability_method": "exact_enumeration" if args.exact else "monte_carlo",
                "fidelity": {
                    "rom_cross_checked": ["intro condition weights and matching scarf bonus",
                                          "contestant eligibility flags", "ordered NPC move slots",
                                          "base appeal and jam", "combination pairs"],
                    "npc_selection": ("ROM score rules with modeled turn inputs and random branches"
                                      if args.npc == "cartridge" else
                                      "ordinary lower-rank score rules and preselection; "
                                      "modeled random branches" if args.npc == "cartridge-lower"
                                      else "hypothetical NPC policy"),
                    "appeal_resolution": ("ROM-checked signed turn scores, weighted random-score "
                                          "moves, copying and half-jam arithmetic, and forced turn-order slots"
                                          if args.npc == "cartridge" else "legacy appeal model"),
                    "final_ranking": ("ROM-checked solo result sort and player priority "
                                      "on first-place ties"
                                      if args.npc == "cartridge" else "uniform score ties"),
                    "roster_selection": (
                        "ROM-checked mapping from supplied event stage and flag"
                        if args.contest_event_stage is not None else
                        "explicit ROM-checked roster mode"
                        if args.cartridge_roster_mode is not None else "hypothetical progress preset"
                    ),
                    "scenario_assumptions": ["supplied event state and idealized roster draws",
                                             "random branch probabilities and independence",
                                             "unverified turn-resolution edge cases"],
                },
                "npc_profile": args.npc,
                "roster_model": (
                    "ROM roster filters and forced slots; uniform order of distinct random keys"
                    if args.cartridge_roster_mode is not None or args.contest_event_stage is not None
                    else "weighted sampling without replacement; unspecified weights are 1"
                ),
                "progress": (args.progress if args.cartridge_roster_mode is None and
                             args.contest_event_stage is None else None),
                "cartridge_roster_mode": args.cartridge_roster_mode,
                "contest_event_stage": args.contest_event_stage,
                "event_flag_2720": args.event_flag_2720 if args.contest_event_stage is not None else None,
                "parameters": parameters,
                "species": species, "schedule": schedule, "known_moves": known_moves,
                "conditions": args.conditions,
                "item": args.item, "scarf_category": args.scarf_category, "seed": args.seed,
                "divisions": [run(category, rank, args, species, schedule, known_moves, npc_policy, parameters)
                              for category, rank in product(categories, ranks)],
            }
            if args.road_to_lisia is not None:
                output["road_to_lisia"] = road_to_lisia(output["divisions"], args.road_to_lisia)
        serialized = json.dumps(output, ensure_ascii=False, indent=2)
        if args.command == "simulate" and args.output:
            args.output.write_text(serialized + "\n", encoding="utf-8")
        else:
            print(serialized)
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
