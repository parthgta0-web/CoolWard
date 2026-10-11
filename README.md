# CoolWard

CoolWard is a heat-refuge planning aid for selecting possible shade, drinking-water, and rest-site locations in the Wazirpur–Bharat Nagar pilot area.

It is a local decision-support tool, not a forecast, service guarantee, procurement plan, or public-land verification system. The primary dashboard scenario uses the validated **400 m network-distance planning assumption** and no verified full-service baseline.

Map/data attribution: © OpenStreetMap contributors ([ODbL](https://www.openstreetmap.org/copyright)); WorldPop population data ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).

## Primary planning scenario

Coverage means the share of the continuous **modelled-priority score** reached by possible sites: 2024 modelled WorldPop population × relative multi-scene land-surface-temperature rank. It is **not people protected, service uptake, health impact, or measured cooling**.

| Budget | Modelled-priority coverage | Possible sites | Actual spend | Unallocated |
|---:|---:|---:|---:|---:|
| ₹5L | 58.1852% | 1 | ₹5L | ₹0L |
| ₹10L | 85.6141% | 2 | ₹10L | ₹0L |
| ₹15L | 94.3440% | 3 | ₹15L | ₹0L |
| ₹20L | 97.9120% | 4 | ₹20L | ₹0L |
| ₹25L | 97.9120% | 4 | ₹20L | ₹5L |
| ₹30L | 97.9120% | 4 | ₹20L | ₹10L |
| ₹35L | 97.9120% | 4 | ₹20L | ₹15L |

Every selected site is a **₹5 lakh standard planning unit — not a procurement quote**. Budget above ₹20L remains unallocated because no supplied candidate adds marginal modelled-priority gain.

## Verification-first replanning

The local dashboard can recompute a plan for a 300 m, 400 m, or 500 m network-distance planning assumption and can simulate a possible site's failed verification. The SAM Local API uses compact exported candidate-to-demand coverage sets and the existing modelled-priority weights to find an exact, deterministic equal-cost maximum-coverage plan from the remaining possible sites.

One local API request returns every budget tier for the selected network-distance assumption. Static map layers are requested only when the dashboard first loads (or when manually refreshed). Exact-solver ties retain the validated primary 400 m ordering where applicable, then use deterministic candidate-ID ordering; ties are never resolved at random.

“Simulate failed verification” is a planning exercise only; it does not label a site as failed in real life. Each selected site shows whether an equally performing backup exists in that simulation, or the modelled-priority coverage consequence if it is excluded. Field verification remains required for land, access, water, safety, capacity, and operations. OSM parks, toilets, and shelter remain unverified context and are never treated as baseline service.

The unmodified default remains the validated primary 400 m scenario above. The network remains fragmented and one demand cell remains structurally unreachable under the supplied pedestrian graph.

## Data and processing

| Input | Supplied coverage and date | Resolution / use |
|---|---|---|
| Landsat 8 Collection 2 Level-2 | 2024-05-18, 2025-04-03, 2025-05-21, 2026-04-22 | Delivered 30 m grid; thermal measurement is natively about 100 m. QA-masked values form a relative multi-scene land-surface-temperature priority rank. |
| WorldPop India population counts | 2024 | Native 3-arc-second cells, roughly 100 m; modelled people per cell, not a census count. |
| OpenStreetMap | Retrieved 2026-10-09 | Roads/paths, buildings, green space, schools/community facilities, parks, toilet, and shelter context. Geometry, tagging, access, and operational status vary. |

Landsat `scene_04` is excluded completely by the pilot-data rule and is never used in derived layers; its full Landsat footprint geometrically touching the context is not treated as evidence that it is an appropriate pilot observation. Distance, area, and network work use EPSG:32643. Outcomes are calculated only for demand-cell centroids inside `study_area_core`; context and wider road geometry are used to reduce edge effects.

```text
supplied raw layers
  → validation and CRS/geometry checks
  → QA-masked relative heat rank + native WorldPop demand cells
  → filtered pedestrian graph + OSM context references
  → possible-site candidates and 300/400/500 m scenario evaluation
  → compact candidate-to-demand coverage inputs for local replanning
  → validated primary 400 m local API data
  → React/Vite dashboard
```

Candidates are generated only from filtered pedestrian-network vertices within 30 m of mapped green space or a school, college, or community facility, then spatially thinned to 100 m. They are labelled **Possible site — requires land, access, water, and operations verification.** The rules are fixed for the reported scenario; they were not tuned to improve coverage.

Demand-cell centroids are snapped to the filtered pedestrian network before evaluation (median snap distance about 17 m; maximum 53.33 m). The snap distance is not added to the 400 m network-distance planning assumption.

## Experimental ML audit

A local scikit-learn `HistGradientBoostingRegressor` feasibility experiment was run on 118 cells using 9 fixed spatial cross-validation blocks. Its held-out MAE was **0.187395**, compared with **0.255021** for the mean baseline (a **26.5%** improvement); held-out R² was **0.379254**.

Features were NDVI, green-area fraction, distance to mapped park, building fraction, and pedestrian-network density; population was excluded. The surrogate is retained as reproducible experimental evidence only and does not replace the transparent satellite-derived heat-priority score. Two of five held-out folds underperformed the mean baseline, and NDVI and the target share Landsat source signal.

This experiment does not estimate air temperature, heat exposure, health risk, people protected, intervention effect, or site suitability. See the [model card](data/processed/ml_feasibility_model_card.md) and [validation chart](data/processed/ml_feasibility_validation.png).

## Limitations

- The 400 m value is a network-distance planning assumption, **not** guaranteed five-minute walking access.
- OSM parks, toilet, and shelter are **OSM-mapped contextual references — unverified**. The primary scenario does not count them as full heat-refuge services.
- There is no verified water availability, public land, access permission, operations plan, capacity, safety assessment, or procurement estimate.
- The pedestrian graph is fragmented; one demand cell is structurally unreachable with the supplied graph and candidate set.
- Landsat indicates relative morning land-surface-temperature priority, not peak-afternoon air temperature, heat exposure, or intervention effect.

Source URLs, licences, dates, resolutions, and source-specific limitations are recorded in [data/sources.csv](data/sources.csv). See [data/README.md](data/README.md) for reproducibility details and [DEMO.md](DEMO.md) for the recorded-demo script.

## Local architecture

```text
React/Vite dashboard
        ↓ local /api proxy
AWS SAM CLI + SAM Local + Docker
        ↓
Lambda-compatible Python API + Lambda Powertools logging
        ↓
validated local processed scenario outputs
```

AWS SAM CLI and SAM Local are used only as local developer tools. No AWS cloud services, credentials, account credits, or deployment are required or used.

## Run locally

Start Docker Desktop first. Then run:

```text
# terminal 1, repository root
sam build
sam local start-api --port 3000 --warm-containers EAGER

# terminal 2
cd frontend
npm run dev
```

On Windows, `npm.cmd run dev` is an equivalent fallback when PowerShell command resolution requires it.

Open the local Vite URL. The frontend calls the SAM Local `/api/optimise` endpoint; it does not call AWS cloud services.
