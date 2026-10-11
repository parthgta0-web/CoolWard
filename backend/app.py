"""Serve locally recomputed CoolWard planning scenarios through SAM Local."""

import itertools
import json
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


def exact_solution(candidate_sets, weights, maximum_sites, preferred_ids=()):
    """Return an exact maximum-coverage set with deterministic, documented ties."""
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


def build_plan(data, budget_lakh, threshold_m=400, excluded_candidate_ids=()):
    """Recompute an exact local plan from exported snapped-network coverage inputs."""
    inputs = data["replanning_inputs"]
    weights = {identifier: float(value) for identifier, value in inputs["demand_weights"].items()}
    excluded_ids = tuple(sorted(set(excluded_candidate_ids)))
    coverage = inputs["candidate_coverage"][str(threshold_m)]
    candidate_sets = {
        identifier: set(demand_ids)
        for identifier, demand_ids in coverage.items()
        if identifier not in excluded_ids
    }
    preferred_ids = PREFERRED_PRIMARY_400M_IDS if threshold_m == 400 else ()
    selected_ids, covered_ids = exact_solution(
        candidate_sets,
        weights,
        budget_lakh // inputs["standard_unit_cost_lakh"],
        preferred_ids,
    )
    candidate_features = {
        feature["properties"]["candidate_id"]: feature
        for feature in data["layers"]["possible_candidate_sites"]["features"]
    }
    selected_sites = ordered_selected_sites(selected_ids, candidate_sets, weights, candidate_features, inputs)
    total_score = score(weights, weights)
    covered_score = score(covered_ids, weights)
    for site in selected_sites:
        backup_sets = {identifier: covered for identifier, covered in candidate_sets.items() if identifier != site["candidate_id"]}
        backup_ids, backup_covered = exact_solution(
            backup_sets,
            weights,
            budget_lakh // inputs["standard_unit_cost_lakh"],
            preferred_ids,
        )
        backup_score = score(backup_covered, weights)
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
        "covered_demand_cell_ids": sorted(covered_ids),
        "modelled_priority_coverage_percent": round(100 * covered_score / total_score, 4) if total_score else 0.0,
        "modelled_priority_score_covered": round(covered_score, 6),
        "baseline_modelled_priority_coverage_percent": 0.0,
        "coverage_label": "Modelled-priority coverage — not people protected or health impact.",
        "excluded_candidate_ids": list(excluded_ids),
        "explanation": "Simulation only — field verification is still required. OSM context is not treated as baseline service.",
        "study_area": data["study_area"],
        "scenario": data["scenario"],
        "network_distance_planning_assumption_m": threshold_m,
        "standard_unit_cost_label": data["standard_unit_cost_label"],
        "disclaimer": data["disclaimer"],
        "limitations": data["limitations"],
        "layers": data["layers"],
    }


def parse_request(event, data):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError as error:
        raise ValueError("Request body must contain valid JSON.") from error
    if not isinstance(body, dict):
        raise ValueError("JSON request body must be an object.")
    try:
        budget_lakh = int(body.get("budget_lakh", 20))
        threshold_m = int(body.get("threshold_m", 400))
    except (TypeError, ValueError) as error:
        raise ValueError("budget_lakh and threshold_m must be whole numbers.") from error
    if budget_lakh not in SUPPORTED_BUDGETS:
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
    return budget_lakh, threshold_m, excluded_ids


@logger.inject_lambda_context
def handler(event, context):
    try:
        data = load_data()
        budget_lakh, threshold_m, excluded_ids = parse_request(event, data)
        result = build_plan(data, budget_lakh, threshold_m, excluded_ids)
        logger.info("Local planning scenario recomputed", extra={"budget_lakh": budget_lakh, "threshold_m": threshold_m, "excluded_count": len(excluded_ids), "site_count": len(result["selected_sites"])})
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
