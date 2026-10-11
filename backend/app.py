"""Serve locally recomputed CoolWard planning scenarios through SAM Local."""

import itertools
import json
import time
from functools import lru_cache
from pathlib import Path

from aws_lambda_powertools import Logger

logger = Logger(service="coolward-planning-scenarios")
DATA_PATH = Path(__file__).parent / "data" / "planning_data.json"
SUPPORTED_BUDGETS = {5, 10, 15, 20, 25, 30, 35}
SUPPORTED_THRESHOLDS = {300, 400, 500}
PREFERRED_PRIMARY_400M_IDS = ("candidate_019", "candidate_046", "candidate_025", "candidate_045")


def load_data():
    with DATA_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def score(identifiers, weights):
    return sum(weights[identifier] for identifier in identifiers)


def non_dominated_candidates(candidate_sets, preferred_ids):
    """Remove equal-cost dominated coverage sets without losing excluded-site backups."""
    active = [identifier for identifier, covered in candidate_sets.items() if covered]
    return [
        identifier for identifier in sorted(active)
        if identifier in preferred_ids or not any(
            candidate_sets[identifier] < candidate_sets[other]
            or (candidate_sets[identifier] == candidate_sets[other] and other > identifier)
            for other in active
            if other != identifier
        )
    ]


def exact_solution_bruteforce(candidate_sets, weights, maximum_sites, preferred_ids=()):
    """Reference implementation retained solely as an exact-regression oracle."""
    candidates = non_dominated_candidates(candidate_sets, preferred_ids)
    maximum_sites = min(maximum_sites, len(candidates))
    preference_rank = {identifier: len(preferred_ids) - index for index, identifier in enumerate(preferred_ids)}

    def tie_key(identifiers):
        remaining, covered, key = set(identifiers), set(), []
        while remaining:
            identifier = max(
                remaining,
                key=lambda candidate_id: (score(candidate_sets[candidate_id] - covered, weights), candidate_id),
            )
            key.append((score(candidate_sets[identifier] - covered, weights), preference_rank.get(identifier, 0), identifier))
            covered.update(candidate_sets[identifier])
            remaining.remove(identifier)
        return tuple(key)

    best_ids, best_covered, best_score = (), set(), 0.0
    for count in range(1, maximum_sites + 1):
        for identifiers in itertools.combinations(candidates, count):
            covered = set().union(*(candidate_sets[identifier] for identifier in identifiers))
            covered_score = score(covered, weights)
            if (
                covered_score > best_score
                or (covered_score == best_score and len(identifiers) < len(best_ids))
                or (covered_score == best_score and len(identifiers) == len(best_ids) and tie_key(identifiers) > tie_key(best_ids))
            ):
                best_ids, best_covered, best_score = identifiers, covered, covered_score
    return best_ids, best_covered


def prepare_bitmask_solver(data, threshold_m, excluded_candidate_ids=()):
    """Prepare compact, deterministic coverage masks for one planning state."""
    inputs = data["replanning_inputs"]
    weights_by_id = {identifier: float(value) for identifier, value in inputs["demand_weights"].items()}
    demand_ids = tuple(sorted(weights_by_id))
    demand_index = {identifier: index for index, identifier in enumerate(demand_ids)}
    excluded_ids = tuple(sorted(set(excluded_candidate_ids)))
    coverage = inputs["candidate_coverage"][str(threshold_m)]
    candidate_sets = {
        identifier: set(demand_ids_covered)
        for identifier, demand_ids_covered in coverage.items()
        if identifier not in excluded_ids
    }
    candidate_masks = {
        identifier: sum(1 << demand_index[demand_id] for demand_id in demand_ids_covered)
        for identifier, demand_ids_covered in candidate_sets.items()
    }
    preferred_ids = PREFERRED_PRIMARY_400M_IDS if threshold_m == 400 else ()
    active_ids = [identifier for identifier, mask in candidate_masks.items() if mask]
    candidates = [
        identifier for identifier in sorted(active_ids)
        if identifier in preferred_ids or not any(
            candidate_masks[identifier] | candidate_masks[other] == candidate_masks[other]
            and (candidate_masks[identifier] != candidate_masks[other] or other > identifier)
            for other in active_ids
            if other != identifier
        )
    ]
    weights = tuple(weights_by_id[identifier] for identifier in demand_ids)

    @lru_cache(maxsize=None)
    def score_mask(mask):
        total = 0.0
        while mask:
            least_significant_bit = mask & -mask
            index = least_significant_bit.bit_length() - 1
            total += weights[index]
            mask ^= least_significant_bit
        return total

    return {
        "inputs": inputs,
        "weights_by_id": weights_by_id,
        "demand_ids": demand_ids,
        "candidate_sets": candidate_sets,
        "candidate_masks": candidate_masks,
        "candidates": tuple(candidates),
        "excluded_ids": excluded_ids,
        "preferred_ids": preferred_ids,
        "score_mask": score_mask,
        "total_score": sum(weights),
    }


def bitmask_tie_key(identifiers, candidate_masks, score_mask, preferred_ids):
    """Mirror the legacy deterministic marginal-gain tie rule using masks."""
    preference_rank = {identifier: len(preferred_ids) - index for index, identifier in enumerate(preferred_ids)}
    remaining, covered, key = set(identifiers), 0, []
    while remaining:
        identifier = max(
            remaining,
            key=lambda candidate_id: (score_mask(candidate_masks[candidate_id] & ~covered), candidate_id),
        )
        gain_mask = candidate_masks[identifier] & ~covered
        key.append((score_mask(gain_mask), preference_rank.get(identifier, 0), identifier))
        covered |= candidate_masks[identifier]
        remaining.remove(identifier)
    return tuple(key)


def exact_bitmask_solutions(solver, maximum_sites):
    """Solve all capacities up to maximum_sites in one exact combination pass."""
    candidates = solver["candidates"]
    candidate_masks = solver["candidate_masks"]
    score_mask = solver["score_mask"]
    maximum_sites = min(maximum_sites, len(candidates))
    best = {capacity: ((), 0, 0.0) for capacity in range(1, maximum_sites + 1)}
    for count in range(1, maximum_sites + 1):
        for identifiers in itertools.combinations(candidates, count):
            covered_mask = 0
            for identifier in identifiers:
                covered_mask |= candidate_masks[identifier]
            covered_score = score_mask(covered_mask)
            tie_key = None
            for capacity in range(count, maximum_sites + 1):
                best_ids, best_mask, best_score = best[capacity]
                if covered_score < best_score:
                    continue
                if covered_score == best_score and len(identifiers) > len(best_ids):
                    continue
                if covered_score == best_score and len(identifiers) == len(best_ids):
                    if tie_key is None:
                        tie_key = bitmask_tie_key(identifiers, candidate_masks, score_mask, solver["preferred_ids"])
                    if tie_key <= bitmask_tie_key(best_ids, candidate_masks, score_mask, solver["preferred_ids"]):
                        continue
                best[capacity] = (identifiers, covered_mask, covered_score)
    return best


def mask_to_ids(mask, demand_ids):
    return [identifier for index, identifier in enumerate(demand_ids) if mask & (1 << index)]


def ordered_selected_sites(selected_ids, candidate_sets, weights, candidate_features, inputs):
    """Report exact-plan sites in deterministic marginal-gain order."""
    remaining, covered, selected = set(selected_ids), set(), []
    while remaining:
        identifier = max(
            remaining,
            key=lambda candidate_id: (score(candidate_sets[candidate_id] - covered, weights), candidate_id),
        )
        gain_ids = candidate_sets[identifier] - covered
        feature = candidate_features[identifier]
        metadata = inputs["candidate_metadata"][identifier]
        selected.append({
            "candidate_id": identifier,
            "name": f"Possible site {identifier}",
            "geometry": feature["geometry"],
            "context_type": metadata["context_type"],
            "status": "Possible site — requires land, access, water, and operations verification.",
            "marginal_gain_modelled_priority_score": round(score(gain_ids, weights), 6),
            "newly_covered_demand_cells": len(gain_ids),
            "cost_lakh": inputs["standard_unit_cost_lakh"],
            "label": "₹5 lakh standard planning unit — not a procurement quote",
        })
        covered.update(gain_ids)
        remaining.remove(identifier)
    return selected


def build_plan_from_solution(data, budget_lakh, threshold_m, solver, solution, include_verification_insights=True):
    """Format an exact bitmask solution without changing published planning semantics."""
    inputs = solver["inputs"]
    selected_ids, covered_mask, covered_score = solution
    candidate_features = {
        feature["properties"]["candidate_id"]: feature
        for feature in data["layers"]["possible_candidate_sites"]["features"]
    }
    selected_sites = ordered_selected_sites(selected_ids, solver["candidate_sets"], solver["weights_by_id"], candidate_features, inputs)
    total_score = solver["total_score"]
    if include_verification_insights:
        for site in selected_sites:
            backup_solver = prepare_bitmask_solver(data, threshold_m, (*solver["excluded_ids"], site["candidate_id"]))
            backup_solution = exact_bitmask_solutions(backup_solver, budget_lakh // inputs["standard_unit_cost_lakh"])[min(budget_lakh // inputs["standard_unit_cost_lakh"], len(backup_solver["candidates"]))]
            backup_ids, _, backup_score = backup_solution
            loss_score = covered_score - backup_score
            loss_percent = round(100 * loss_score / total_score, 4) if total_score else 0.0
            site["verification_insight"] = {
                "classification": "critical" if loss_score > 0 else "replaceable",
                "coverage_consequence_modelled_priority_score": round(loss_score, 6),
                "coverage_consequence_percent": loss_percent,
                "best_available_backup_plan": {
                    "selected_candidate_ids": list(backup_ids),
                    "modelled_priority_coverage_percent": round(100 * backup_score / total_score, 4) if total_score else 0.0,
                },
            }
    spent_lakh = len(selected_sites) * inputs["standard_unit_cost_lakh"]
    return {
        "budget_lakh": budget_lakh,
        "threshold_m": threshold_m,
        "spent_lakh": spent_lakh,
        "unallocated_lakh": budget_lakh - spent_lakh,
        "selected_sites": selected_sites,
        "covered_demand_cell_ids": sorted(mask_to_ids(covered_mask, solver["demand_ids"])),
        "modelled_priority_coverage_percent": round(100 * covered_score / total_score, 4) if total_score else 0.0,
        "modelled_priority_score_covered": round(covered_score, 6),
        "baseline_modelled_priority_coverage_percent": 0.0,
        "coverage_label": "Modelled-priority coverage — not people protected or health impact.",
        "excluded_candidate_ids": list(solver["excluded_ids"]),
        "explanation": "Simulation only — field verification is still required. OSM context is not treated as baseline service.",
        "study_area": data["study_area"],
        "scenario": data["scenario"],
        "network_distance_planning_assumption_m": threshold_m,
        "standard_unit_cost_label": data["standard_unit_cost_label"],
        "disclaimer": data["disclaimer"],
        "limitations": data["limitations"],
    }


def build_plan(data, budget_lakh, threshold_m=400, excluded_candidate_ids=()):
    """Return one exact local plan, including insights for its active budget."""
    solver = prepare_bitmask_solver(data, threshold_m, excluded_candidate_ids)
    capacity = min(budget_lakh // solver["inputs"]["standard_unit_cost_lakh"], len(solver["candidates"]))
    solution = exact_bitmask_solutions(solver, capacity)[capacity]
    return build_plan_from_solution(data, budget_lakh, threshold_m, solver, solution)


def build_all_plans(data, threshold_m=400, excluded_candidate_ids=(), active_budget_lakh=20):
    """Return all tiers from shared exact work; insights exist only for active budget."""
    solver = prepare_bitmask_solver(data, threshold_m, excluded_candidate_ids)
    unit_cost = solver["inputs"]["standard_unit_cost_lakh"]
    maximum_sites = min(max(SUPPORTED_BUDGETS) // unit_cost, len(solver["candidates"]))
    solutions = exact_bitmask_solutions(solver, maximum_sites)
    plans = []
    for budget_lakh in sorted(SUPPORTED_BUDGETS):
        capacity = min(budget_lakh // unit_cost, maximum_sites)
        plans.append(build_plan_from_solution(
            data, budget_lakh, threshold_m, solver, solutions[capacity],
            include_verification_insights=budget_lakh == active_budget_lakh,
        ))
    return plans


def parse_request(event, data):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as error:
        raise ValueError("Request body must contain valid JSON.") from error
    if not isinstance(body, dict):
        raise ValueError("JSON request body must be an object.")
    try:
        budget_lakh = body.get("budget_lakh")
        budget_lakh = int(budget_lakh) if budget_lakh is not None else None
        threshold_m = int(body.get("threshold_m", 400))
    except (TypeError, ValueError) as error:
        raise ValueError("budget_lakh and threshold_m must be whole numbers.") from error
    if budget_lakh is not None and budget_lakh not in SUPPORTED_BUDGETS:
        raise ValueError("Budget must be one of ₹5L, ₹10L, ₹15L, ₹20L, ₹25L, ₹30L, or ₹35L.")
    if threshold_m not in SUPPORTED_THRESHOLDS:
        raise ValueError("threshold_m must be one of 300, 400, or 500.")
    excluded_ids = body.get("excluded_candidate_ids", [])
    if not isinstance(excluded_ids, list) or any(not isinstance(identifier, str) or not identifier for identifier in excluded_ids):
        raise ValueError("excluded_candidate_ids must be an array of candidate IDs.")
    known_ids = set(data["replanning_inputs"]["candidate_coverage"][str(threshold_m)])
    unknown_ids = sorted(set(excluded_ids) - known_ids)
    if unknown_ids:
        raise ValueError(f"Unknown candidate ID(s): {', '.join(unknown_ids)}.")
    include_layers = body.get("include_layers", False)
    if not isinstance(include_layers, bool):
        raise ValueError("include_layers must be true or false.")
    active_budget_lakh = body.get("active_budget_lakh", 20)
    try:
        active_budget_lakh = int(active_budget_lakh)
    except (TypeError, ValueError) as error:
        raise ValueError("active_budget_lakh must be a whole number.") from error
    if active_budget_lakh not in SUPPORTED_BUDGETS:
        raise ValueError("active_budget_lakh must be one of ₹5L, ₹10L, ₹15L, ₹20L, ₹25L, ₹30L, or ₹35L.")
    return budget_lakh, threshold_m, excluded_ids, include_layers, active_budget_lakh


@logger.inject_lambda_context
def handler(event, context):
    try:
        started = time.perf_counter()
        data = load_data()
        budget_lakh, threshold_m, excluded_ids, include_layers, active_budget_lakh = parse_request(event, data)
        if budget_lakh is None:
            result = {
                "plans": build_all_plans(data, threshold_m, excluded_ids, active_budget_lakh),
                "threshold_m": threshold_m,
                "active_budget_lakh": active_budget_lakh,
                "excluded_candidate_ids": sorted(set(excluded_ids)),
                "explanation": "Simulation only — field verification is still required. OSM context is not treated as baseline service.",
            }
            if include_layers:
                result["layers"] = data["layers"]
        else:
            # Preserve the single-plan response for existing local integrations.
            result = build_plan(data, budget_lakh, threshold_m, excluded_ids)
            if include_layers:
                result["layers"] = data["layers"]
        result["recomputed_local_ms"] = round((time.perf_counter() - started) * 1000, 1)
        logger.info("Local planning scenario recomputed", extra={"budget_lakh": budget_lakh, "threshold_m": threshold_m, "excluded_count": len(excluded_ids), "tier_count": len(result.get("plans", [])) or 1, "include_layers": include_layers})
        return response(200, result)
    except ValueError as error:
        logger.warning("Invalid planning-scenario request", extra={"error": str(error)})
        return response(400, {"error": str(error)})


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
