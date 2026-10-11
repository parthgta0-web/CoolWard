"""Package verified Phase 1/2.1 outputs for the local Lambda-compatible API.

This is an integration export only: it does not rerun the raw-data pipeline or
change any raw input.  The two canonical boundary files are copied unchanged
as map reference geometry alongside Phase 1/2.1 processed layers.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
RAW = ROOT / "data/raw/datawp/datawp"
OUTPUT = ROOT / "backend/data/planning_data.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def feature_index(collection, property_name):
    return {str(feature["properties"][property_name]): feature for feature in collection["features"]}


def main() -> None:
    heat = load_json(PROCESSED / "heat_priority.geojson")
    network = load_json(PROCESSED / "walking_network.geojson")
    references = load_json(PROCESSED / "existing_relief_locations.geojson")
    candidates = load_json(PROCESSED / "possible_candidate_sites.geojson")
    core = load_json(RAW / "study_area_core.geojson")
    context = load_json(RAW / "study_area_context.geojson")
    scenarios = load_json(PROCESSED / "primary_no_verified_full_service_baseline_budget_scenarios.json")
    coverage_manifest = load_json(PROCESSED / "selected_site_covered_demand_cells_400m.json")
    replanning_inputs = load_json(PROCESSED / "replanning_inputs.json")
    methodology = load_json(PROCESSED / "optimiser_methodology.json")
    candidate_by_id = feature_index(candidates, "candidate_id")
    plans = {}
    for scenario in scenarios:
        budget = int(scenario["budget_lakh"])
        selected = []
        for selection in scenario["selected_sites"]:
            feature = candidate_by_id[selection["candidate_id"]]
            selected.append({
                **selection,
                "name": f"Possible site {selection['candidate_id']}",
                "geometry": feature["geometry"],
                "context_type": feature["properties"]["context_type"],
                "status": "Possible site — requires land, access, water, and operations verification.",
            })
        plans[str(budget)] = {
            "budget_lakh": budget,
            "spent_lakh": scenario["spent_lakh"],
            "unallocated_lakh": budget - scenario["spent_lakh"],
            "selected_sites": selected,
            "modelled_priority_coverage_percent": scenario["modelled_priority_coverage_percent"],
            "modelled_priority_score_covered": scenario["modelled_priority_score_covered"],
            "covered_demand_cell_ids": coverage_manifest["plans"][str(budget)]["covered_demand_cell_ids"],
            "baseline_modelled_priority_coverage_percent": 0.0,
            "coverage_label": "Modelled-priority coverage — not people protected or health impact.",
        }
    core_heat = {
        "type": "FeatureCollection",
        "features": [feature for feature in heat["features"] if feature["properties"].get("in_study_area_core")],
    }
    payload = {
        "study_area": "Wazirpur–Bharat Nagar pilot area, Delhi",
        "scenario": "Primary planning scenario — no verified full-service baseline",
        "network_distance_planning_assumption_m": 400,
        "standard_unit_cost_label": "₹5 lakh standard planning unit — not a procurement quote.",
        "disclaimer": "Modelled-priority coverage only. No verified full-service baseline is assumed.",
        "limitations": [
            "Relative multi-scene land-surface-temperature priority; not peak-afternoon air temperature or measured exposure.",
            "2024 modelled WorldPop population; not a local census or people-protected estimate.",
            "OSM-mapped parks, toilet, and shelter are contextual references only and unverified.",
            "The pedestrian network is fragmented; one demand cell is structurally unreachable.",
            "Possible sites require land, access, water, and operations verification.",
        ],
        "layers": {
            "reporting_core": core,
            "context": context,
            "heat_priority_demand_cells": core_heat,
            "filtered_pedestrian_network": network,
            "possible_candidate_sites": candidates,
            "osm_contextual_references": references,
        },
        "plans": plans,
        "replanning_inputs": replanning_inputs,
        "methodology": methodology,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
