# CoolWard Phase 1 pipeline

This local-only pipeline validates the supplied data and writes derived planning layers exclusively to `data/processed/`. It does not edit `data/raw/`, call AWS, deploy anything, or modify the prototype API/dashboard.

## Run

```powershell
py -3.14 -m pip install -r pipeline/requirements.txt
py -3.14 pipeline/validate_raw_data.py
py -3.14 pipeline/build_layers.py
```

`validate_raw_data.py` recursively inventories raw files and reports CRS, raster coverage, invalid/empty geometry, duplicate OSM IDs, private segments, missing road attributes, and pedestrian-graph connectivity.

`build_layers.py` uses the root canonical `study_area_core.geojson` and `study_area_context.geojson`, excludes `scene_04`, and uses EPSG:32643 for all distance, area, and network operations. It keeps population at native WorldPop cells and ranks the median QA-unmasked value from the remaining supplied Landsat scenes as a **relative multi-scene heat-priority indicator**.

Candidate locations are only filtered-pedestrian-network vertices within 30 m of an OSM-mapped park/playground, school/college, or community facility; they are spatially thinned to 100 m. Every candidate remains a **possible location — not confirmed public land**. The 400 m network value is recorded only as a configurable planning assumption, never as proof of five-minute access.

The pipeline does not assess water quality, ownership, permission, accessibility, capacity, actual use, temperature reduction, health effects, or people protected.

## Phase 2 scenarios

```powershell
py -3.14 pipeline/build_optimiser.py
```

This consumes only Phase 1 processed layers. It uses `population_people × relative_heat_rank` as a continuous **modelled priority score**, snaps demand, OSM-mapped relief, and possible sites to the fragmented pedestrian graph, and reports failed snaps. It evaluates 300 m, 400 m, and 500 m network-distance planning assumptions. The default budget scenarios use 400 m and deterministic maximum-marginal-gain selection. Each selected site is a **₹5 lakh standard planning unit — not a procurement quote**.

The evaluator writes three explicitly separate scenario families: the primary no-verified-full-service baseline, an unverified mapped-shelter sensitivity, and an all-OSM-amenities stress test. Parks, toilets, and shelter stay visible as contextual references; only the stress test treats all of them as service points, and it is not a recommended planning result.
