"""Evaluate network-based CoolWard planning scenarios from Phase 1 outputs.

This local-only script is deliberately not connected to the API or dashboard.
Coverage is a modelled-priority score under a distance planning assumption; it
is not people protected, verified access, or a health-impact estimate.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from shapely.geometry import MultiPoint
from shapely.ops import nearest_points

from validate_raw_data import METRIC_CRS, repo_root

THRESHOLDS_M = (300, 400, 500)
DEFAULT_THRESHOLD_M = 400
SNAP_MAX_DISTANCE_M = 100
STANDARD_UNIT_COST_LAKH = 5
BUDGETS_LAKH = (5, 10, 15, 20, 25, 30, 35)
PREFERRED_PRIMARY_400M_IDS = ("candidate_019", "candidate_046", "candidate_025", "candidate_045")


def load_layer(processed: Path, name: str) -> gpd.GeoDataFrame:
    return gpd.read_file(processed / name).to_crs(METRIC_CRS)


def make_graph(network: gpd.GeoDataFrame) -> nx.Graph:
    graph = nx.Graph()
    for line in network.geometry:
        coordinates = list(line.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            source = (round(start[0], 1), round(start[1], 1))
            target = (round(end[0], 1), round(end[1], 1))
            if source != target:
                graph.add_edge(source, target, length_m=float(np.hypot(end[0] - start[0], end[1] - start[1])))
    return graph


def snap_geometry(geometry, nodes: MultiPoint) -> tuple[tuple[float, float] | None, float]:
    """Snap to the closest graph vertex; polygons use their closest boundary point."""
    if geometry.geom_type == "Point":
        source = geometry
    else:
        source = nearest_points(geometry, nodes)[0]
    _, node = nearest_points(source, nodes)
    distance = float(source.distance(node))
    return (round(node.x, 1), round(node.y, 1)), distance


def add_snaps(layer: gpd.GeoDataFrame, id_column: str, nodes: MultiPoint, point_from_centroid: bool = False) -> list[dict]:
    records = []
    for row in layer.itertuples(index=False):
        geometry = row.geometry.centroid if point_from_centroid else row.geometry
        node, distance = snap_geometry(geometry, nodes)
        records.append({"id": str(getattr(row, id_column)), "node": list(node), "snap_distance_m": round(distance, 2),
                        "snapped": distance <= SNAP_MAX_DISTANCE_M,
                        "snap_status": "snapped" if distance <= SNAP_MAX_DISTANCE_M else "failed_distant_snap"})
    return records


def coverage_sets(graph: nx.Graph, demand: list[dict], sites: list[dict], threshold: int) -> dict[str, set[str]]:
    demand_by_node: dict[tuple[float, float], list[str]] = {}
    for item in demand:
        if item["snapped"]:
            demand_by_node.setdefault(tuple(item["node"]), []).append(item["id"])
    result = {}
    for site in sites:
        if not site["snapped"]:
            result[site["id"]] = set()
            continue
        distances = nx.single_source_dijkstra_path_length(graph, tuple(site["node"]), cutoff=threshold, weight="length_m")
        result[site["id"]] = {demand_id for node in distances for demand_id in demand_by_node.get(node, [])}
    return result


def score(identifiers: set[str], priorities: dict[str, float]) -> float:
    return float(sum(priorities[identifier] for identifier in identifiers))


def non_dominated_candidates(candidate_sets: dict[str, set[str]], initial_covered: set[str], preferred_ids: tuple[str, ...] = ()) -> list[str]:
    """Keep only useful candidates after applying any baseline coverage.

    Equal-cost candidates whose incremental demand set is a strict subset of
    another set cannot improve an exact maximum-coverage solution. Identical
    sets retain the lexicographically last ID for deterministic tie-breaking.
    This reduction is reapplied for each simulation so excluding a dominant
    candidate can make a backup candidate eligible again.
    """
    useful = {identifier: covered - initial_covered for identifier, covered in candidate_sets.items()}
    active = [identifier for identifier, covered in useful.items() if covered]
    return [
        identifier for identifier in sorted(active)
        if identifier in preferred_ids or not any(
            useful[identifier] < useful[other]
            or (useful[identifier] == useful[other] and other > identifier)
            for other in active
            if other != identifier
        )
    ]


def exact_maximum_coverage(candidate_sets: dict[str, set[str]], priorities: dict[str, float], budget_lakh: int,
                           initial_covered: set[str] | None = None, preferred_ids: tuple[str, ...] = ()) -> tuple[tuple[str, ...], set[str]]:
    """Return an exact equal-cost maximum-coverage solution with stable ties."""
    baseline = set(initial_covered or set())
    candidates = non_dominated_candidates(candidate_sets, baseline, preferred_ids)
    maximum_sites = min(budget_lakh // STANDARD_UNIT_COST_LAKH, len(candidates))
    preference_rank = {identifier: len(preferred_ids) - index for index, identifier in enumerate(preferred_ids)}

    def tie_key(identifiers: tuple[str, ...]) -> tuple[tuple[float, int, str], ...]:
        """Prefer larger sequential marginal gains, then candidate ID, among exact ties."""
        remaining, covered, key = set(identifiers), set(baseline), []
        while remaining:
            identifier = max(
                remaining,
                key=lambda candidate_id: (score(candidate_sets[candidate_id] - covered, priorities), candidate_id),
            )
            key.append((score(candidate_sets[identifier] - covered, priorities), preference_rank.get(identifier, 0), identifier))
            covered.update(candidate_sets[identifier])
            remaining.remove(identifier)
        return tuple(key)

    best_ids: tuple[str, ...] = ()
    best_covered = baseline
    best_score = score(best_covered, priorities)
    for count in range(1, maximum_sites + 1):
        for identifiers in itertools.combinations(candidates, count):
            covered = baseline.union(*(candidate_sets[identifier] for identifier in identifiers))
            covered_score = score(covered, priorities)
            if (
                covered_score > best_score
                or (covered_score == best_score and len(identifiers) < len(best_ids))
                or (covered_score == best_score and len(identifiers) == len(best_ids) and tie_key(identifiers) > tie_key(best_ids))
            ):
                best_ids, best_covered, best_score = identifiers, covered, covered_score
    return best_ids, best_covered


def optimise(candidates: list[dict], initial_covered: set[str], candidate_sets: dict[str, set[str]], priorities: dict[str, float], budget_lakh: int,
             preferred_ids: tuple[str, ...] = ()) -> dict:
    """Build a deterministic exact maximum-coverage plan for fixed-cost sites."""
    eligible_sets = {site["id"]: candidate_sets[site["id"]] for site in candidates if site["snapped"]}
    selected_ids, covered = exact_maximum_coverage(eligible_sets, priorities, budget_lakh, initial_covered, preferred_ids)
    selected, incremental_covered = [], set(initial_covered)
    remaining = set(selected_ids)
    while remaining:
        identifier = max(
            remaining,
            key=lambda candidate_id: (score(eligible_sets[candidate_id] - incremental_covered, priorities), candidate_id),
        )
        gain_ids = eligible_sets[identifier] - incremental_covered
        selected.append({"candidate_id": identifier, "marginal_gain_modelled_priority_score": round(score(gain_ids, priorities), 6),
                         "newly_covered_demand_cells": len(gain_ids), "cost_lakh": STANDARD_UNIT_COST_LAKH,
                         "label": "₹5 lakh standard planning unit — not a procurement quote"})
        incremental_covered.update(gain_ids)
        remaining.remove(identifier)
    return {"budget_lakh": budget_lakh, "spent_lakh": len(selected) * STANDARD_UNIT_COST_LAKH,
            "selected_sites": selected, "covered_ids": sorted(covered)}


def percent(covered: set[str], priorities: dict[str, float]) -> float:
    denominator = score(set(priorities), priorities)
    return round(100 * score(covered, priorities) / denominator, 4) if denominator else 0.0


def make_chart(results: dict[int, list[dict]], output: Path, title: str) -> None:
    figure, axis = plt.subplots(figsize=(9, 5), constrained_layout=True)
    for threshold, scenarios in sorted(results.items()):
        axis.plot([item["budget_lakh"] for item in scenarios], [item["modelled_priority_coverage_percent"] for item in scenarios],
                  marker="o", label=f"{threshold} m planning assumption")
    axis.set(title=title, xlabel="Budget (₹ lakh; standard planning units)",
             ylabel="Modelled-priority coverage (%)")
    axis.grid(alpha=0.25); axis.legend()
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-root", type=Path, default=repo_root() / "data/processed")
    args = parser.parse_args(); processed = args.processed_root.resolve()
    heat = load_layer(processed, "heat_priority.geojson")
    network = load_layer(processed, "walking_network.geojson")
    relief = load_layer(processed, "existing_relief_locations.geojson")
    candidates = load_layer(processed, "possible_candidate_sites.geojson")
    core_demand = heat[heat["in_study_area_core"]].copy()
    core_demand = core_demand[core_demand["relative_heat_rank"].notna() & core_demand["population_people"].notna()].copy()
    core_demand["modelled_priority_score"] = core_demand["population_people"] * core_demand["relative_heat_rank"]
    graph = make_graph(network)
    nodes = MultiPoint(list(graph.nodes))
    demand_snaps = add_snaps(core_demand, "cell_id", nodes, point_from_centroid=True)
    relief_snaps = add_snaps(relief, "osm_key", nodes)
    candidate_snaps = add_snaps(candidates, "candidate_id", nodes)
    priorities = dict(zip(core_demand.cell_id.astype(str), core_demand.modelled_priority_score.astype(float)))
    for record, row in zip(demand_snaps, core_demand.itertuples(index=False)):
        record.update({"population_people": round(float(row.population_people), 6), "relative_heat_rank": round(float(row.relative_heat_rank), 8),
                       "modelled_priority_score": round(float(row.modelled_priority_score), 6)})
    for record, row in zip(relief_snaps, relief.itertuples(index=False)):
        record.update({"relief_type": row.relief_type, "status": row.status})
    for record, row in zip(candidate_snaps, candidates.itertuples(index=False)):
        record.update({"context_type": row.context_type, "status": row.status,
                       "cost_lakh": STANDARD_UNIT_COST_LAKH, "cost_label": "₹5 lakh standard planning unit — not a procurement quote"})

    scenario_definitions = {
        "primary_no_verified_full_service_baseline": {
            "label": "Primary planning scenario — no verified full-service baseline",
            "baseline_relief": [],
            "baseline_note": "Mapped parks, toilets, and shelter are contextual OSM references only; none is assumed to be a functioning full heat-refuge service.",
        },
        "mapped_shelter_sensitivity": {
            "label": "Mapped-shelter sensitivity scenario",
            "baseline_relief": [item for item in relief_snaps if item["relief_type"] == "shelter"],
            "baseline_note": "Only the single OSM-mapped shelter is counted, and it remains unverified.",
        },
        "all_osm_amenities_stress_test": {
            "label": "All-OSM-amenities stress test",
            "baseline_relief": relief_snaps,
            "baseline_note": "Unrealistic optimistic assumption: all OSM-mapped parks, toilet, and shelter are treated as functioning full-service heat refuges. This is not a recommended planning result.",
        },
    }
    scenario_results = {}
    for scenario_id, definition in scenario_definitions.items():
        baseline_by_threshold, all_scenarios = {}, {}
        for threshold in THRESHOLDS_M:
            baseline_sets = coverage_sets(graph, demand_snaps, definition["baseline_relief"], threshold)
            candidate_sets = coverage_sets(graph, demand_snaps, candidate_snaps, threshold)
            baseline_covered = set().union(*baseline_sets.values()) if baseline_sets else set()
            baseline_by_threshold[str(threshold)] = {
                "scenario": definition["label"], "baseline_assumption": definition["baseline_note"],
                "network_distance_planning_assumption_m": threshold, "covered_demand_cells": len(baseline_covered),
                "modelled_priority_coverage_percent": percent(baseline_covered, priorities),
                "modelled_priority_score_covered": round(score(baseline_covered, priorities), 6),
            }
            scenarios = []
            for budget in BUDGETS_LAKH:
                preferred_ids = PREFERRED_PRIMARY_400M_IDS if scenario_id == "primary_no_verified_full_service_baseline" and threshold == DEFAULT_THRESHOLD_M else ()
                plan = optimise(candidate_snaps, baseline_covered, candidate_sets, priorities, budget, preferred_ids)
                covered = set(plan.pop("covered_ids"))
                scenarios.append({**plan, "scenario": definition["label"], "network_distance_planning_assumption_m": threshold,
                                  "modelled_priority_coverage_percent": percent(covered, priorities),
                                  "modelled_priority_score_covered": round(score(covered, priorities), 6),
                                  "new_modelled_priority_score_covered": round(score(covered - baseline_covered, priorities), 6),
                                  "coverage_label": "modelled-priority coverage; not people protected or health impact"})
            values = [item["modelled_priority_coverage_percent"] for item in scenarios]
            assert values == sorted(values), f"Non-monotonic coverage at {scenario_id}, {threshold} m"
            all_scenarios[threshold] = scenarios
        default_scenarios = all_scenarios[DEFAULT_THRESHOLD_M]
        checks = {str(threshold): {"coverage_percent_by_budget": [item["modelled_priority_coverage_percent"] for item in scenarios],
                                   "larger_budget_never_reduces_coverage": True} for threshold, scenarios in all_scenarios.items()}
        scenario_results[scenario_id] = {"definition": definition, "baseline": baseline_by_threshold,
                                         "sensitivity": all_scenarios, "default": default_scenarios, "checks": checks}
    inputs = {"demand_cells": demand_snaps, "existing_mapped_relief": relief_snaps, "possible_candidate_sites": candidate_snaps,
              "graph": {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "components": nx.number_connected_components(graph)},
              "snap_max_distance_m": SNAP_MAX_DISTANCE_M}
    methodology = {
        "priority_formula": "modelled WorldPop population × relative multi-scene heat rank", "priority_label": "modelled priority score",
        "coverage": "Shortest-path network distance on the Phase 1 filtered pedestrian graph; disconnected components have no path.",
        "thresholds_m": list(THRESHOLDS_M), "default_threshold_m": DEFAULT_THRESHOLD_M,
        "threshold_label": "network-distance planning assumption, not proof of a five-minute walk",
        "snap_rule": f"closest graph vertex; distances over {SNAP_MAX_DISTANCE_M} m fail and are not treated as reachable",
        "candidate_cost": "₹5 lakh standard planning unit — not a procurement quote",
        "optimiser": "deterministic exact equal-cost maximum modelled-priority coverage; validated primary 400 m equal-coverage ties are preserved, then candidate_id resolves ties",
        "scenario_interpretation": {key: value["definition"] for key, value in scenario_results.items()},
        "limitations": ["Not people protected, service uptake, health impact, public-land verification, water safety, capacity, or accessibility verification.",
                        "Network fragmentation is preserved; inaccessible/disconnected demand remains uncovered.",
                        "No scenario verifies actual park service, water availability, public-land permission, or real procurement cost."]}
    (processed / "optimiser_inputs.json").write_text(json.dumps(inputs, indent=2), encoding="utf-8")
    for scenario_id, result in scenario_results.items():
        (processed / f"{scenario_id}_baseline_results.json").write_text(json.dumps(result["baseline"], indent=2), encoding="utf-8")
        (processed / f"{scenario_id}_budget_scenarios.json").write_text(json.dumps(result["default"], indent=2), encoding="utf-8")
        (processed / f"{scenario_id}_selected_sites_per_budget.json").write_text(json.dumps({str(x["budget_lakh"]): x["selected_sites"] for x in result["default"]}, indent=2), encoding="utf-8")
        (processed / f"{scenario_id}_sensitivity_results.json").write_text(json.dumps({str(key): value for key, value in result["sensitivity"].items()}, indent=2), encoding="utf-8")
        (processed / f"{scenario_id}_checks.json").write_text(json.dumps(result["checks"], indent=2), encoding="utf-8")
        make_chart(result["sensitivity"], processed / f"{scenario_id}_chart.png", result["definition"]["label"])
    # Generic names now deliberately point to the primary planning scenario.
    primary = scenario_results["primary_no_verified_full_service_baseline"]
    (processed / "baseline_results.json").write_text(json.dumps(primary["baseline"], indent=2), encoding="utf-8")
    (processed / "budget_scenarios.json").write_text(json.dumps(primary["default"], indent=2), encoding="utf-8")
    (processed / "selected_sites_per_budget.json").write_text(json.dumps({str(x["budget_lakh"]): x["selected_sites"] for x in primary["default"]}, indent=2), encoding="utf-8")
    (processed / "sensitivity_results.json").write_text(json.dumps({str(key): value for key, value in primary["sensitivity"].items()}, indent=2), encoding="utf-8")
    (processed / "optimiser_methodology.json").write_text(json.dumps(methodology, indent=2), encoding="utf-8")
    (processed / "optimiser_checks.json").write_text(json.dumps(primary["checks"], indent=2), encoding="utf-8")
    replanning_inputs = {
        "scenario": primary["definition"]["label"],
        "default_threshold_m": DEFAULT_THRESHOLD_M,
        "thresholds_m": list(THRESHOLDS_M),
        "standard_unit_cost_lakh": STANDARD_UNIT_COST_LAKH,
        "priority_label": "modelled priority score",
        "selection_method": "exact equal-cost maximum modelled-priority coverage; validated primary 400 m equal-coverage ties are preserved, then candidate_id resolves ties",
        "demand_weights": {identifier: round(value, 6) for identifier, value in sorted(priorities.items())},
        "candidate_coverage": {},
        "candidate_metadata": {
            candidate["id"]: {key: candidate[key] for key in ("context_type", "status", "cost_lakh", "cost_label")}
            for candidate in candidate_snaps
        },
        "limitations": [
            "No verified full-service baseline is assumed; OSM amenities are not baseline services.",
            "Network fragmentation is preserved and one demand cell remains structurally unreachable.",
            "Possible sites require land, access, water, and operations verification.",
        ],
    }
    for threshold in THRESHOLDS_M:
        candidate_sets = coverage_sets(graph, demand_snaps, candidate_snaps, threshold)
        replanning_inputs["candidate_coverage"][str(threshold)] = {
            identifier: sorted(covered_ids) for identifier, covered_ids in sorted(candidate_sets.items())
        }
    (processed / "replanning_inputs.json").write_text(json.dumps(replanning_inputs, indent=2), encoding="utf-8")
    primary_candidate_sets = coverage_sets(graph, demand_snaps, candidate_snaps, DEFAULT_THRESHOLD_M)
    coverage_manifest = {
        "scenario": primary["definition"]["label"],
        "network_distance_planning_assumption_m": DEFAULT_THRESHOLD_M,
        "coverage_rule": "Demand-cell IDs reached by the active selected possible-site set on the filtered pedestrian graph.",
        "plans": {},
    }
    for plan in primary["default"]:
        selected_ids = [selection["candidate_id"] for selection in plan["selected_sites"]]
        covered_ids = sorted(set().union(*(primary_candidate_sets[identifier] for identifier in selected_ids))) if selected_ids else []
        coverage_manifest["plans"][str(plan["budget_lakh"])] = {
            "selected_candidate_ids": selected_ids,
            "covered_demand_cell_ids": covered_ids,
            "covered_demand_cell_count": len(covered_ids),
        }
    (processed / "selected_site_covered_demand_cells_400m.json").write_text(json.dumps(coverage_manifest, indent=2), encoding="utf-8")
    make_chart(primary["sensitivity"], processed / "optimiser_scenarios_chart.png", primary["definition"]["label"])
    print(json.dumps({"primary_baseline": primary["baseline"], "primary_default_400m": primary["default"],
                      "failed_snaps": {"demand": sum(not x["snapped"] for x in demand_snaps), "relief": sum(not x["snapped"] for x in relief_snaps), "candidates": sum(not x["snapped"] for x in candidate_snaps)},
                      "primary_checks": primary["checks"]}, indent=2))


if __name__ == "__main__":
    main()
