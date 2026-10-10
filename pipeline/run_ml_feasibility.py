"""Local-only feasibility experiment for a heat-priority surrogate model.

The target is the existing relative multi-scene Landsat-derived heat-priority
rank. This script does not estimate air temperature, health risk, people
protected, or intervention effects, and does not alter product inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.mask import mask
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from shapely.geometry import box


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/datawp/datawp"
PROCESSED = ROOT / "data/processed"
METRIC_CRS = "EPSG:32643"
SEED = 20261010
SCENES = ("scene_01", "scene_02", "scene_03", "scene_05")


def read_layer(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_file(path).to_crs(METRIC_CRS)


def masked_ndvi(red, nir, qa, geometry) -> float:
    red_data, _ = mask(red, [geometry.__geo_interface__], crop=True, filled=False)
    nir_data, _ = mask(nir, [geometry.__geo_interface__], crop=True, filled=False)
    qa_data, _ = mask(qa, [geometry.__geo_interface__], crop=True, filled=False)
    raw_red, raw_nir, raw_qa = red_data[0], nir_data[0], qa_data[0]
    valid = (~np.ma.getmaskarray(raw_red) & ~np.ma.getmaskarray(raw_nir) & ~np.ma.getmaskarray(raw_qa)
             & (raw_red > 0) & (raw_nir > 0) & ((raw_qa.astype(np.uint16) & 0b111111) == 0))
    if not np.any(valid):
        return np.nan
    # Collection 2 Level-2 surface-reflectance conversion documented for the
    # supplied product. Both bands share the scale/offset.
    red_reflectance = raw_red[valid] * 0.0000275 - 0.2
    nir_reflectance = raw_nir[valid] * 0.0000275 - 0.2
    denominator = nir_reflectance + red_reflectance
    values = (nir_reflectance - red_reflectance) / denominator
    values = values[np.isfinite(values) & (np.abs(denominator) > 1e-8)]
    return float(np.mean(values)) if len(values) else np.nan


def ndvi_feature(cells: gpd.GeoDataFrame) -> np.ndarray:
    samples = []
    for scene in SCENES:
        base = RAW / "landsat/landsat" / scene
        with rasterio.open(base / "SR_B4.tif") as red, rasterio.open(base / "SR_B5.tif") as nir, rasterio.open(base / "QA_PIXEL.tif") as qa:
            samples.append(np.array([masked_ndvi(red, nir, qa, geometry) for geometry in cells.geometry]))
    return np.nanmedian(np.vstack(samples), axis=0)


def area_fraction(geometries: gpd.GeoSeries, context: gpd.GeoDataFrame, radius_m: float) -> np.ndarray:
    values = []
    index = context.sindex
    for geometry in geometries:
        neighbourhood = geometry.buffer(radius_m)
        candidates = context.iloc[list(index.intersection(neighbourhood.bounds))]
        values.append(sum(item.intersection(neighbourhood).area for item in candidates.geometry) / neighbourhood.area)
    return np.array(values)


def line_density(geometries: gpd.GeoSeries, network: gpd.GeoDataFrame, radius_m: float) -> np.ndarray:
    values = []
    index = network.sindex
    for geometry in geometries:
        neighbourhood = geometry.buffer(radius_m)
        candidates = network.iloc[list(index.intersection(neighbourhood.bounds))]
        values.append(sum(item.intersection(neighbourhood).length for item in candidates.geometry) / neighbourhood.area)
    return np.array(values)


def spatial_groups(cells: gpd.GeoDataFrame) -> np.ndarray:
    centroids = cells.geometry.centroid
    x, y = np.array(centroids.x), np.array(centroids.y)
    x_block = np.minimum(2, ((x - x.min()) / (x.max() - x.min()) * 3).astype(int))
    y_block = np.minimum(2, ((y - y.min()) / (y.max() - y.min()) * 3).astype(int))
    return x_block + 3 * y_block


def evaluate(features: np.ndarray, target: np.ndarray, groups: np.ndarray, names: list[str]) -> dict:
    splitter = GroupKFold(n_splits=min(5, len(np.unique(groups))))
    baseline_predictions = np.zeros_like(target)
    model_predictions = np.zeros_like(target)
    importances = np.zeros(len(names))
    fold_rows = []
    rng = np.random.default_rng(SEED)
    for fold, (train, test) in enumerate(splitter.split(features, target, groups), start=1):
        imputer = SimpleImputer(strategy="median")
        train_x, test_x = imputer.fit_transform(features[train]), imputer.transform(features[test])
        baseline_value = float(np.mean(target[train]))
        baseline_predictions[test] = baseline_value
        model = HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, max_leaf_nodes=8, l2_regularization=1.0, random_state=SEED)
        model.fit(train_x, target[train])
        prediction = model.predict(test_x)
        model_predictions[test] = prediction
        base_mae = mean_absolute_error(target[test], prediction)
        for column in range(len(names)):
            permuted = test_x.copy()
            permuted[:, column] = rng.permutation(permuted[:, column])
            importances[column] += mean_absolute_error(target[test], model.predict(permuted)) - base_mae
        fold_rows.append({"fold": fold, "train_samples": int(len(train)), "held_out_samples": int(len(test)),
                          "held_out_blocks": sorted(map(int, np.unique(groups[test]))),
                          "baseline_mae": round(float(mean_absolute_error(target[test], baseline_predictions[test])), 6),
                          "model_mae": round(float(base_mae), 6)})
    metrics = lambda observed, predicted: {"mae": round(float(mean_absolute_error(observed, predicted)), 6), "r2": round(float(r2_score(observed, predicted)), 6)}
    return {"baseline": metrics(target, baseline_predictions), "hist_gradient_boosting": metrics(target, model_predictions),
            "oof_baseline_predictions": baseline_predictions, "oof_model_predictions": model_predictions,
            "feature_importance_held_out_permutation_mae_increase": {name: round(float(value / len(fold_rows)), 6) for name, value in zip(names, importances)},
            "folds": fold_rows}


def main() -> None:
    heat = read_layer(PROCESSED / "heat_priority.geojson")
    cells = heat[heat["relative_heat_rank"].notna()].copy()
    parks = read_layer(PROCESSED / "existing_relief_locations.geojson")
    parks = parks[parks["relief_type"] == "park"]
    buildings = read_layer(RAW / "osm/buildings.geojson")
    network = read_layer(PROCESSED / "walking_network.geojson")
    target = cells["relative_heat_rank"].to_numpy(float)
    cell_centres = cells.geometry.centroid
    feature_names = ["median_qa_masked_ndvi", "green_area_fraction_100m", "distance_to_mapped_park_m", "building_area_fraction_100m", "pedestrian_network_density_100m"]
    features = np.column_stack([
        ndvi_feature(cells),
        area_fraction(cell_centres, parks, 100),
        np.array([point.distance(parks.geometry.union_all()) for point in cell_centres]),
        area_fraction(cell_centres, buildings, 100),
        line_density(cell_centres, network, 100),
    ])
    groups = spatial_groups(cells)
    result = evaluate(features, target, groups, feature_names)
    mae_reduction = 1 - result["hist_gradient_boosting"]["mae"] / result["baseline"]["mae"]
    credible = result["hist_gradient_boosting"]["r2"] >= 0.3 and mae_reduction >= 0.15 and len(np.unique(groups)) >= 5
    recommendation = "KEEP ONLY AS OPTIONAL EXPLANATION" if credible else "DO NOT KEEP"
    feature_rows = [{"cell_id": str(identifier), "target_relative_heat_rank": round(float(y), 8), "spatial_block": int(group),
                     **{name: None if not np.isfinite(value) else round(float(value), 8) for name, value in zip(feature_names, row)}}
                    for identifier, y, group, row in zip(cells.cell_id, target, groups, features)]
    output = {
        "experiment": "Local supervised surrogate feasibility experiment", "seed": SEED,
        "target": "existing relative multi-scene Landsat-derived heat-priority rank", "samples": int(len(cells)),
        "spatial_blocks": int(len(np.unique(groups))), "feature_names": feature_names,
        "population_feature_used": False, "model": "scikit-learn HistGradientBoostingRegressor (LightGBM unavailable locally)",
        "metrics": {"baseline_mean_predictor": result["baseline"], "hist_gradient_boosting": result["hist_gradient_boosting"],
                    "mae_reduction_vs_baseline": round(float(mae_reduction), 6)},
        "folds": result["folds"], "feature_importance": result["feature_importance_held_out_permutation_mae_increase"],
        "recommendation": recommendation,
        "recommendation_reason": "Spatially held-out metrics meet the pre-set feasibility threshold, but this remains a small-area surrogate sharing Landsat inputs with the target." if credible else "Spatially held-out performance does not meet the pre-set feasibility threshold; do not integrate ML.",
        "data_leakage_risks": ["NDVI and the target are derived from the same supplied Landsat scenes, so agreement may reflect shared remote-sensing signal rather than independent predictive validity.", "Nearby cells have spatial autocorrelation even with block cross-validation.", "Mapped green context and buildings are OSM-derived and may be incomplete or temporally mismatched."],
        "limitations": ["This predicts a satellite-derived relative priority rank only, not ground-truth air temperature, heat exposure, health risk, people protected, or intervention impact.", "No population feature is used.", "The sample is limited to supplied local cells and cannot establish transferability beyond this pilot."],
        "optional_display_if_kept": "Show only as a collapsed 'ML heat-priority explanation (experimental)' panel beside the satellite score, with held-out MAE/R², feature contributions, and the statement that it never replaces the transparent satellite-derived score." if credible else None,
    }
    (PROCESSED / "ml_feasibility_metrics.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    (PROCESSED / "ml_feasibility_features.json").write_text(json.dumps(feature_rows, indent=2), encoding="utf-8")
    card = f"""# ML feasibility model card\n\n## Recommendation: {recommendation}\n\nThis is an explanatory surrogate trained to estimate the existing relative multi-scene Landsat-derived heat-priority rank. It is not ground-truth air temperature, heat exposure, health risk, people protected, or intervention impact.\n\n- Samples: {len(cells)} local demand/context cells across {len(np.unique(groups))} fixed spatial blocks\n- Model: scikit-learn HistGradientBoostingRegressor; LightGBM was not available locally\n- Baseline MAE / R²: {result['baseline']['mae']} / {result['baseline']['r2']}\n- Model MAE / R²: {result['hist_gradient_boosting']['mae']} / {result['hist_gradient_boosting']['r2']}\n- MAE reduction versus baseline: {mae_reduction:.1%}\n- Population used as a feature: no\n\n## Features\n\n{chr(10).join(f'- `{name}`: held-out permutation MAE increase {value}' for name, value in result['feature_importance_held_out_permutation_mae_increase'].items())}\n\n## Validation\n\nFixed-seed spatial-block cross-validation is used; rows are never randomly split. Each prediction is out-of-fold. The small local sample and shared Landsat signal between NDVI and the target make leakage/optimism a material risk.\n\n## Decision\n\n{output['recommendation_reason']}\n\n{output['optional_display_if_kept'] or 'Do not display this model in the product.'}\n"""
    (PROCESSED / "ml_feasibility_model_card.md").write_text(card, encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for axis, prediction, title in zip(axes, [result["oof_baseline_predictions"], result["oof_model_predictions"]], ["Mean baseline", "Spatial OOF HistGradientBoosting"]):
        axis.scatter(target, prediction, c=groups, cmap="tab10", edgecolor="white", linewidth=.4)
        axis.plot([0, 1], [0, 1], "--", color="#46535c")
        axis.set(xlabel="Observed relative heat-priority rank", ylabel="Out-of-fold prediction", title=title, xlim=(0, 1), ylim=(0, 1))
    fig.suptitle(f"Local surrogate feasibility: {recommendation}")
    fig.savefig(PROCESSED / "ml_feasibility_validation.png", dpi=180)
    plt.close(fig)
    print(json.dumps({"recommendation": recommendation, "metrics": output["metrics"], "samples": len(cells), "blocks": len(np.unique(groups))}, indent=2))


if __name__ == "__main__":
    main()
