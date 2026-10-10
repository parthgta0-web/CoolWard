# ML feasibility model card

## Recommendation: KEEP ONLY AS OPTIONAL EXPLANATION

This is an explanatory surrogate trained to estimate the existing relative multi-scene Landsat-derived heat-priority rank. It is not ground-truth air temperature, heat exposure, health risk, people protected, or intervention impact.

- Samples: 118 local demand/context cells across 9 fixed spatial blocks
- Model: scikit-learn HistGradientBoostingRegressor; LightGBM was not available locally
- Baseline MAE / R²: 0.255021 / -0.056754
- Model MAE / R²: 0.187395 / 0.379254
- MAE reduction versus baseline: 26.5%
- Population used as a feature: no

## Features

- `median_qa_masked_ndvi`: held-out permutation MAE increase 0.031267
- `green_area_fraction_100m`: held-out permutation MAE increase 0.001419
- `distance_to_mapped_park_m`: held-out permutation MAE increase -0.001627
- `building_area_fraction_100m`: held-out permutation MAE increase 0.01268
- `pedestrian_network_density_100m`: held-out permutation MAE increase 0.015663

## Validation

Fixed-seed spatial-block cross-validation is used; rows are never randomly split. Each prediction is out-of-fold. The small local sample and shared Landsat signal between NDVI and the target make leakage/optimism a material risk.

## Decision

Spatially held-out metrics meet the pre-set feasibility threshold, but this remains a small-area surrogate sharing Landsat inputs with the target.

Show only as a collapsed 'ML heat-priority explanation (experimental)' panel beside the satellite score, with held-out MAE/R², feature contributions, and the statement that it never replaces the transparent satellite-derived score.
