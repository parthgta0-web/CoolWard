# CoolWard data workflow

`data/` contains the reproducible local data handoff for the Wazirpur–Bharat Nagar pilot. CoolWard is a planning aid, not a validated heat-service inventory or impact model.

## Folders

- `raw/` contains supplied source downloads. It is ignored by Git and must not be committed.
- `processed/` contains reproducible validation reports, derived map layers, optimiser inputs, scenario results, methodology, and quality-assurance charts.
- `sources.csv` is the copied, verified provenance record from the supplied raw source register.

## Inputs

| Layer | Supplied data used | Processing note |
|---|---|---|
| Boundaries | `study_area_core.geojson`, `study_area_context.geojson`, and wider roads extent | Final reporting is limited to core demand-cell centroids; context and roads avoid edge effects. |
| Heat | Four usable Landsat C2 L2 scenes: 2024-05-18, 2025-04-03, 2025-05-21, 2026-04-22 | QA-masked `ST_B10` forms a relative multi-scene land-surface-temperature rank. `scene_04` is excluded completely. |
| Population | WorldPop India 2024 unconstrained counts | Native 3-arc-second, roughly 100 m, people-per-pixel demand cells are retained; counts are not upsampled to false 30 m precision. |
| Walking/context | OSM roads/paths, buildings, green areas, parks, facilities, toilet, shelter | OSM was retrieved 2026-10-09 and is incomplete/unverified context, not proof of service or public access. |

All distance, area, and network operations use EPSG:32643. Raw data validation records CRS, geometry validity, OSM ID duplication, private/no-access road exclusions, raster coverage, missing values, and graph fragmentation in `processed/data_quality_report.json`.

## Derived layers and scenarios

The pipeline creates:

- native-scale demand cells with relative heat rank and modelled-priority score;
- a filtered pedestrian graph, preserving disconnected components;
- OSM-mapped parks, toilet, and shelter as **unverified contextual references**;
- possible sites generated from pedestrian-network vertices within 30 m of mapped green space or school/college/community-facility context, thinned to 100 m;
- 300 m, 400 m, and 500 m network-distance planning scenarios.

The dashboard/API uses the **primary 400 m scenario**: no OSM feature is treated as a verified full-service baseline. Its coverage is modelled priority (WorldPop population × relative heat rank), not people protected. The `all_osm_amenities_stress_test` outputs retain the parks/toilet/shelter-as-services calculation only as an explicitly unrealistic optimistic sensitivity.

Every possible site requires land, access, water, and operations verification. The ₹5 lakh figure is a standard planning unit, not a procurement quote.

## Reproducibility

The scripts in `pipeline/` are run locally and write derived outputs only to `data/processed/`. The Phase 3 integration export packages the validated primary scenario for the local Lambda-compatible API; it does not rerun the raw-data processing workflow.

Do not add raw data to Git. `.gitignore` explicitly excludes `data/raw/`.
