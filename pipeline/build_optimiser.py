"""Evaluate network-based CoolWard planning scenarios from Phase 1 outputs.

This local-only script is deliberately not connected to the API or dashboard.
Coverage is a modelled-priority score under a distance planning assumption; it
is not people protected, verified access, or a health-impact estimate.
"""

from __future__ import annotations

import argparse
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


def optimise(candidates: list[dict], initial_covered: set[str], candidate_sets: dict[str, set[str]], priorities: dict[str, float], budget_lakh: int) -> dict:
    covered, selected, spent = set(initial_covered), [], 0
    remaining = {site["id"]: site for site in candidates if site["snapped"]}
    while spent + STANDARD_UNIT_COST_LAKH <= budget_lakh and remaining:
        ranked = []
        for identifier, site in remaining.items():
            gain_ids = candidate_sets[identifier] - covered
            ranked.append((score(gain_ids, priorities), identifier, gain_ids, site))
        gain, identifier, gain_ids, site = max(ranked, key=lambda item: (item[0], item[1]))
        if gain <= 0:
            break
        covered.update(gain_ids)
        selected.append({"candidate_id": identifier, "marginal_gain_modelled_priority_score": round(gain, 6),
                         "newly_covered_demand_cells": len(gain_ids), "cost_lakh": STANDARD_UNIT_COST_LAKH,
                         "label": "₹5 lakh standard planning unit — not a procurement quote"})
        spent += STANDARD_UNIT_COST_LAKH
        del remaining[identifier]
    return {"budget_lakh": budget_lakh, "spent_lakh": spent, "selected_sites": selected, "covered_ids": sorted(covered)}


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
                plan = optimise(candidate_snaps, baseline_covered, candidate_sets, priorities, budget)
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
        "optimiser": "deterministic greedy maximum marginal modelled-priority gain; ties resolve by candidate_id",
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
    make_chart(primary["sensitivity"], processed / "optimiser_scenarios_chart.png", primary["definition"]["label"])
    print(json.dumps({"primary_baseline": primary["baseline"], "primary_default_400m": primary["default"],
                      "failed_snaps": {"demand": sum(not x["snapped"] for x in demand_snaps), "relief": sum(not x["snapped"] for x in relief_snaps), "candidates": sum(not x["snapped"] for x in candidate_snaps)},
                      "primary_checks": primary["checks"]}, indent=2))


if __name__ == "__main__":
    main()
