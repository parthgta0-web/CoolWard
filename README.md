# CoolWard

CoolWard is a heat-refuge planning aid for selecting possible shade, drinking-water, and rest-site locations in the Wazirpur–Bharat Nagar pilot area.

It is a local decision-support tool, not a forecast, service guarantee, procurement plan, or public-land verification system. The primary dashboard scenario uses the validated **400 m network-distance planning assumption** and no verified full-service baseline.

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

## Data and processing

| Input | Supplied coverage and date | Resolution / use |
|---|---|---|
| Landsat 8 Collection 2 Level-2 | 2024-05-18, 2025-04-03, 2025-05-21, 2026-04-22 | Delivered 30 m grid; thermal measurement is natively about 100 m. QA-masked values form a relative multi-scene land-surface-temperature priority rank. |
| WorldPop India population counts | 2024 | Native 3-arc-second cells, roughly 100 m; modelled people per cell, not a census count. |
| OpenStreetMap | Retrieved 2026-10-09 | Roads/paths, buildings, green space, schools/community facilities, parks, toilet, and shelter context. Geometry, tagging, access, and operational status vary. |

Landsat `scene_04` is excluded completely from processing and the planning model. Distance, area, and network work use EPSG:32643. Outcomes are calculated only for demand-cell centroids inside `study_area_core`; context and wider road geometry are used to reduce edge effects.

```text
supplied raw layers
  → validation and CRS/geometry checks
  → QA-masked relative heat rank + native WorldPop demand cells
  → filtered pedestrian graph + OSM context references
  → possible-site candidates and 300/400/500 m scenario evaluation
  → validated primary 400 m local API data
  → React/Vite dashboard
```

Candidates are generated only from filtered pedestrian-network vertices within 30 m of mapped green space or a school, college, or community facility, then spatially thinned to 100 m. They are labelled **Possible site — requires land, access, water, and operations verification.** The rules are fixed for the reported scenario; they were not tuned to improve coverage.

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

```powershell
# terminal 1, repository root
sam build
sam local start-api --port 3000 --warm-containers EAGER

# terminal 2
cd frontend
npm.cmd run dev
```

Open the local Vite URL. The frontend calls the SAM Local `/api/optimise` endpoint; it does not call AWS cloud services.
