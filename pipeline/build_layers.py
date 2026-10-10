"""Build CoolWard's local, reproducible, conservative Phase-1 data layers.

All raw inputs remain untouched.  Outputs are confined to data/processed.
The heat field is a relative multi-scene land-surface-temperature ranking, not
a single-date temperature, air temperature, exposure measurement, or outcome.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from validate_raw_data import (
    METRIC_CRS, PEDESTRIAN_HIGHWAYS, PRIVATE_VALUES, RAW_RELATIVE, load_vector,
    repo_root, sha256, validate,
)

NETWORK_DISTANCE_ASSUMPTION_M = 400
CANDIDATE_CONTEXT_DISTANCE_M = 30
CANDIDATE_SPACING_M = 100
LST_SCALE = 0.00341802
LST_OFFSET_K = 149.0


def write_geojson(layer: gpd.GeoDataFrame, path: Path) -> None:
    layer.to_crs("EPSG:4326").to_file(path, driver="GeoJSON")


def road_graph(roads: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, nx.Graph]:
    usable = roads[
        roads["highway"].isin(PEDESTRIAN_HIGHWAYS)
        & ~roads["access"].fillna("").str.lower().isin(PRIVATE_VALUES)
    ].copy().to_crs(METRIC_CRS)
    graph = nx.Graph()
    for geometry in usable.geometry:
        if not isinstance(geometry, LineString):
            continue
        coordinates = list(geometry.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            source = (round(start[0], 1), round(start[1], 1))
            target = (round(end[0], 1), round(end[1], 1))
            if source != target:
                graph.add_edge(source, target, length_m=float(Point(start).distance(Point(end))))
    return usable, graph


def build_heat_grid(raw_root: Path, context: gpd.GeoDataFrame, population: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Sample each valid supplied Landsat scene to native WorldPop cells."""
    values: list[np.ndarray] = []
    target_geometries = population.to_crs(METRIC_CRS).geometry
    for scene in ("scene_01", "scene_02", "scene_03", "scene_05"):
        path = raw_root / "landsat/landsat" / scene / "ST_B10.tif"
        with rasterio.open(path) as raster:
            # A small masked crop verifies and limits processing to supplied context.
            mask(raster, context.to_crs(raster.crs).geometry, crop=True, filled=False)
            scene_values = []
            for geometry in target_geometries:
                clipped, _ = mask(raster, [geometry.__geo_interface__], crop=True, filled=False)
                raw = clipped[0]
                valid = raw.compressed()
                if not len(valid):
                    scene_values.append(np.nan)
                else:
                    # USGS C2 L2 ST transformation; retained in code and provenance.
                    scene_values.append(float(np.mean(valid) * LST_SCALE + LST_OFFSET_K - 273.15))
            values.append(np.asarray(scene_values))
    stack = np.vstack(values)
    output = population.to_crs(METRIC_CRS).copy()
    output["lst_scene_count"] = np.sum(~np.isnan(stack), axis=0)
    output["relative_lst_c"] = np.nanmedian(stack, axis=0)
    # Rank is relative to the supplied context cells only, avoiding a false
    # implication that this is an absolute heat/exposure threshold.
    valid = output["relative_lst_c"].notna()
    output["relative_heat_rank"] = np.nan
    output.loc[valid, "relative_heat_rank"] = output.loc[valid, "relative_lst_c"].rank(pct=True)
    return output


def population_cells(raw_root: Path) -> gpd.GeoDataFrame:
    path = raw_root / "population/worldpop_2024_100m_study_area.tif"
    rows = []
    with rasterio.open(path) as raster:
        band = raster.read(1, masked=True)
        for row in range(raster.height):
            for column in range(raster.width):
                value = band[row, column]
                if np.ma.is_masked(value):
                    continue
                geometry = rasterio.transform.xy(raster.transform, row, column, offset="ul")
                west, north = geometry
                east, south = rasterio.transform.xy(raster.transform, row + 1, column + 1, offset="ul")
                from shapely.geometry import box
                rows.append({"population_people": float(value), "geometry": box(west, south, east, north)})
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def existing_relief(raw_root: Path) -> gpd.GeoDataFrame:
    relief = load_vector(raw_root / "osm/existing_relief_locations.geojson").to_crs(METRIC_CRS).copy()
    def label(row):
        if row.get("amenity") == "toilets": return "toilet"
        if row.get("amenity") == "shelter": return "shelter"
        if row.get("leisure") == "park": return "park"
        return "other_mapped_relief"
    relief["relief_type"] = relief.apply(label, axis=1)
    relief["status"] = "OSM-mapped, unverified"
    relief["osm_key"] = relief["element"].astype(str) + ":" + relief["id"].astype(str)
    # A park repeated in parks_green_areas is retained once here as a relief
    # location, with its park type preserved.
    return relief.drop_duplicates("osm_key").copy()


def candidate_sites(network: gpd.GeoDataFrame, parks: gpd.GeoDataFrame, facilities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    context = gpd.GeoDataFrame(
        [{"context_type": "green_space", "geometry": geometry} for geometry in parks.to_crs(METRIC_CRS).geometry]
        + [{"context_type": "community_facility", "geometry": geometry} for geometry in facilities.to_crs(METRIC_CRS).geometry], crs=METRIC_CRS
    )
    context_union = unary_union(context.geometry.tolist())
    candidates = []
    for geometry in network.geometry:
        for coordinate in geometry.coords:
            point = Point(coordinate)
            if point.distance(context_union) <= CANDIDATE_CONTEXT_DISTANCE_M:
                nearby = context[context.geometry.distance(point) <= CANDIDATE_CONTEXT_DISTANCE_M]
                context_types = ",".join(sorted(nearby.context_type.unique()))
                candidates.append((point, context_types))
    # Greedy spatial thinning makes the generated set inspectable rather than a
    # candidate at every road vertex.  It does not establish land permission.
    selected = []
    for point, context_types in sorted(candidates, key=lambda item: (item[0].x, item[0].y, item[1])):
        if all(point.distance(existing[0]) >= CANDIDATE_SPACING_M for existing in selected):
            selected.append((point, context_types))
    return gpd.GeoDataFrame([
        {"candidate_id": f"candidate_{index:03d}", "context_type": context_types,
         "rule": f"filtered pedestrian-network vertex within {CANDIDATE_CONTEXT_DISTANCE_M} m of mapped green space or community facility; thinned to {CANDIDATE_SPACING_M} m",
         "status": "possible location — not confirmed public land", "geometry": point}
        for index, (point, context_types) in enumerate(selected, start=1)
    ], crs=METRIC_CRS)


def make_map(core, context, heat, roads, relief, candidates, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(10, 8), constrained_layout=True)
    context.boundary.plot(ax=axis, color="#61758a", linewidth=1, label="Context")
    roads.plot(ax=axis, color="#c3cbd4", linewidth=0.35, label="Filtered pedestrian network")
    heat.plot(ax=axis, column="relative_heat_rank", cmap="YlOrRd", alpha=0.62, legend=True,
              legend_kwds={"label": "Relative multi-scene heat rank"})
    core.boundary.plot(ax=axis, color="#172d44", linewidth=1.5, label="Reporting core")
    relief.plot(ax=axis, color="#176b87", markersize=18, label="OSM-mapped relief, unverified")
    candidates.plot(ax=axis, color="#a13f15", marker="^", markersize=24, label="Possible location")
    axis.set_title("CoolWard Phase 1 derived planning layers")
    axis.set_axis_off(); axis.legend(loc="lower left", fontsize=8)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=repo_root() / RAW_RELATIVE)
    parser.add_argument("--processed-root", type=Path, default=repo_root() / "data/processed")
    args = parser.parse_args()
    raw_root, processed = args.raw_root.resolve(), args.processed_root.resolve()
    processed.mkdir(parents=True, exist_ok=True)
    report = validate(raw_root)
    (processed / "data_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report["errors"]:
        raise RuntimeError("Raw validation errors: " + "; ".join(report["errors"]))

    core = load_vector(raw_root / "study_area_core.geojson").to_crs(METRIC_CRS)
    context = load_vector(raw_root / "study_area_context.geojson").to_crs(METRIC_CRS)
    roads, graph = road_graph(load_vector(raw_root / "osm/walkable_roads_paths.geojson"))
    population = population_cells(raw_root)
    heat = build_heat_grid(raw_root, context, population)
    heat["cell_id"] = [f"demand_{index:03d}" for index in range(1, len(heat) + 1)]
    heat["in_study_area_core"] = heat.geometry.centroid.within(core.geometry.iloc[0])
    heat["population_in_core_people"] = np.where(heat["in_study_area_core"], heat["population_people"], 0.0)
    population_rank = heat.loc[heat["in_study_area_core"], "population_people"].rank(pct=True)
    heat["population_rank_core"] = np.nan
    heat.loc[population_rank.index, "population_rank_core"] = population_rank
    heat["relative_priority_score"] = heat["relative_heat_rank"] * heat["population_rank_core"]
    relief = existing_relief(raw_root)
    parks = load_vector(raw_root / "osm/parks_green_areas.geojson")
    facilities = load_vector(raw_root / "osm/schools_community_facilities.geojson")
    candidates = candidate_sites(roads, parks, facilities)

    write_geojson(roads, processed / "walking_network.geojson")
    write_geojson(heat, processed / "heat_priority.geojson")
    write_geojson(relief, processed / "existing_relief_locations.geojson")
    write_geojson(candidates, processed / "possible_candidate_sites.geojson")
    make_map(core, context, heat, roads, relief, candidates, processed / "derived_layers_map.png")

    core_cells = heat[heat["in_study_area_core"]]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "crs_for_distance_area_network": METRIC_CRS,
        "reporting_rule": "Only demand cells with centroid in study_area_core are included in summary outcomes.",
        "network_distance_planning_assumption_m": NETWORK_DISTANCE_ASSUMPTION_M,
        "network_distance_note": "Planning assumption only; not proof of a five-minute walk.",
        "heat_method": "Median of supplied, QA-unmasked Landsat C2 L2 ST_B10 values from scenes 01, 02, 03 and 05, transformed to Celsius then ranked relatively across supplied WorldPop-scale context cells.",
        "heat_limitations": "Relative multi-scene land-surface-temperature priority only; not single-date temperature, peak-afternoon air temperature, measured exposure, or intervention effect.",
        "excluded_landsat_scene": "scene_04: excluded completely by the pilot-data rule",
        "core_summary": {"demand_cells": int(len(core_cells)), "population_people": round(float(core_cells.population_people.sum()), 2),
                         "cells_with_heat": int(core_cells.relative_heat_rank.notna().sum()),
                         "relative_heat_rank_min": round(float(core_cells.relative_heat_rank.min()), 4),
                         "relative_heat_rank_median": round(float(core_cells.relative_heat_rank.median()), 4),
                         "relative_heat_rank_max": round(float(core_cells.relative_heat_rank.max()), 4)},
        "existing_relief_by_type": relief.relief_type.value_counts().to_dict(),
        "possible_candidate_sites": int(len(candidates)),
        "pedestrian_graph": {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "components": nx.number_connected_components(graph)},
    }
    (processed / "provenance.json").write_text(json.dumps({
        "summary": summary,
        "raw_files": [{"path": path.relative_to(raw_root).as_posix(), "sha256": sha256(path)} for path in sorted(raw_root.rglob("*")) if path.is_file()],
        "source_record_copied_from": "data/raw/datawp/datawp/sources.csv",
        "processing_constants": {"metric_crs": METRIC_CRS, "lst_scale": LST_SCALE, "lst_offset_kelvin": LST_OFFSET_K,
                                  "candidate_context_distance_m": CANDIDATE_CONTEXT_DISTANCE_M, "candidate_spacing_m": CANDIDATE_SPACING_M},
    }, indent=2), encoding="utf-8")
    # Copy only the supplied provenance record after successful validation.
    (repo_root() / "data/sources.csv").write_text((raw_root / "sources.csv").read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
