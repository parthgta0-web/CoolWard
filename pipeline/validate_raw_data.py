"""Read-only validation for CoolWard's supplied pilot inputs.

The script never changes raw data.  Its only output is a JSON report in the
chosen processed directory.  It is deliberately conservative: warnings mean
that a layer may still be useful for planning, not that it has been verified
on the ground.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import rasterio
from pyproj import Transformer
from shapely.geometry import LineString

WGS84 = "EPSG:4326"
METRIC_CRS = "EPSG:32643"
RAW_RELATIVE = Path("data/raw/datawp/datawp")
PRIVATE_VALUES = {"private", "no"}
PEDESTRIAN_HIGHWAYS = {"footway", "path", "pedestrian", "living_street", "residential", "service", "steps"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_vector(path: Path) -> gpd.GeoDataFrame:
    layer = gpd.read_file(path)
    if layer.crs is None:
        # GeoJSON coordinates in this handoff are longitude/latitude.  Record
        # this as an inferred CRS in the report rather than silently assuming
        # metres.
        layer = layer.set_crs(WGS84, allow_override=True)
    return layer


def graph_diagnostics(roads: gpd.GeoDataFrame) -> dict:
    eligible = roads[
        roads["highway"].isin(PEDESTRIAN_HIGHWAYS)
        & ~roads["access"].fillna("").str.lower().isin(PRIVATE_VALUES)
    ].copy()
    metric = eligible.to_crs(METRIC_CRS)
    graph = nx.Graph()
    for geometry in metric.geometry:
        if not isinstance(geometry, LineString) or geometry.is_empty:
            continue
        coordinates = list(geometry.coords)
        for start, end in zip(coordinates, coordinates[1:]):
            # OSM linework normally shares exact nodes.  Round only to 0.1 m
            # to absorb projection floating-point noise without bridging gaps.
            source = (round(start[0], 1), round(start[1], 1))
            target = (round(end[0], 1), round(end[1], 1))
            if source != target:
                graph.add_edge(source, target, length_m=((end[0]-start[0]) ** 2 + (end[1]-start[1]) ** 2) ** 0.5)
    components = sorted((len(component) for component in nx.connected_components(graph)), reverse=True)
    largest_share = (components[0] / graph.number_of_nodes()) if components else 0.0
    return {
        "eligible_segments": int(len(eligible)),
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": len(components),
        "largest_component_nodes": components[0] if components else 0,
        "largest_component_share": round(largest_share, 4),
        "usable": bool(graph.number_of_edges() and largest_share >= 0.5),
    }


def validate(raw_root: Path) -> dict:
    raw_root = raw_root.resolve()
    core_path = raw_root / "study_area_core.geojson"
    context_path = raw_root / "study_area_context.geojson"
    roads_path = raw_root / "osm" / "walkable_roads_paths.geojson"
    warnings: list[str] = []
    errors: list[str] = []
    files = []
    for path in sorted(raw_root.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(raw_root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})

    core = load_vector(core_path)
    context = load_vector(context_path)
    if not core.geometry.within(context.geometry.iloc[0]).all():
        errors.append("Canonical study_area_core is not wholly within canonical study_area_context.")
    vector_results = {}
    osm_ids: Counter[tuple[str, str]] = Counter()
    for path in sorted(raw_root.rglob("*.geojson")):
        layer = load_vector(path)
        invalid = int((~layer.geometry.is_valid).sum())
        missing_geometry = int(layer.geometry.isna().sum() + layer.geometry.is_empty.sum())
        inferred_crs = "crs_missing_in_file_assumed_EPSG:4326" if gpd.read_file(path).crs is None else str(layer.crs)
        vector_results[path.relative_to(raw_root).as_posix()] = {
            "features": int(len(layer)), "crs": inferred_crs,
            "invalid_geometries": invalid, "missing_or_empty_geometries": missing_geometry,
        }
        if invalid or missing_geometry:
            warnings.append(f"{path.name}: invalid or empty geometries require review before use.")
        if "osm" in path.parts and {"element", "id"}.issubset(layer.columns):
            osm_ids.update((str(row.element), str(row.id)) for row in layer[["element", "id"]].dropna().itertuples(index=False))

    duplicates = [{"element": element, "id": identifier, "occurrences": count} for (element, identifier), count in osm_ids.items() if count > 1]
    if duplicates:
        warnings.append(f"{len(duplicates)} OSM element/id pairs occur in more than one OSM layer; de-duplication is required by use case.")

    roads = load_vector(roads_path)
    private = roads[roads["access"].fillna("").str.lower().isin(PRIVATE_VALUES)]
    highway_counts = roads["highway"].fillna("missing").value_counts().to_dict()
    missing_values = {column: int(roads[column].isna().sum()) for column in ["id", "element", "highway", "access"] if column in roads}
    graph = graph_diagnostics(roads)
    if not graph["usable"]:
        warnings.append("Filtered pedestrian graph is not sufficiently connected for network planning.")
    if len(private):
        warnings.append(f"{len(private)} private/no-access road segments are excluded from the pedestrian graph.")

    raster_results = {}
    context_metric = context.to_crs(METRIC_CRS).geometry.iloc[0]
    for path in sorted(raw_root.rglob("*.tif")):
        relative = path.relative_to(raw_root).as_posix()
        with rasterio.open(path) as raster:
            raster_crs = str(raster.crs)
            # Constructing bounds through shapely avoids treating the tuple as a geometry.
            from shapely.geometry import box
            extent = gpd.GeoSeries([box(*raster.bounds)], crs=raster_crs).to_crs(METRIC_CRS).iloc[0]
            overlap = float(extent.intersection(context_metric).area)
            raster_results[relative] = {
                "crs": raster_crs, "width": raster.width, "height": raster.height,
                "resolution": list(raster.res), "nodata": raster.nodata,
                "geometric_context_overlap": overlap > 0,
                "pipeline_eligible": "scene_04" not in relative,
            }
            if "scene_04" in relative:
                # This scene is a user-confirmed non-pilot input.  Its full
                # Landsat footprint can geometrically touch the context, which
                # is not evidence that it is an appropriate pilot observation.
                # Exclusion is therefore policy-based and unconditional.
                warning = "scene_04 is excluded completely by the pilot-data rule; it is never used in derived layers."
                if warning not in warnings:
                    warnings.append(warning)
            elif "landsat" in relative and not overlap:
                errors.append(f"{relative} does not overlap the pilot context.")

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": "data/raw/datawp/datawp", "canonical_boundaries": {"core": "study_area_core.geojson", "context": "study_area_context.geojson"},
        "files": files, "vectors": vector_results, "rasters": raster_results,
        "osm_duplicate_ids": duplicates, "roads": {"private_or_no_access_segments": int(len(private)), "highway_counts": highway_counts, "missing_values": missing_values, "pedestrian_graph": graph},
        "warnings": warnings, "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=repo_root() / RAW_RELATIVE)
    parser.add_argument("--output", type=Path, default=repo_root() / "data/processed/data_quality_report.json")
    args = parser.parse_args()
    report = validate(args.raw_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Warnings: {len(report['warnings'])}; errors: {len(report['errors'])}")


if __name__ == "__main__":
    main()
