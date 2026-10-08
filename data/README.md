# CoolWard data handoff

This folder keeps the project reproducible while avoiding large raw-data uploads to the public repository.

## Folder convention

- `raw/` — original downloads. Never commit these files.
- `processed/` — small, reproducible outputs that can be committed when ready.
- `sources.csv` — source and limitation record for every external dataset.

## Required inputs for the Delhi pilot

| Input | Required output | Notes |
|---|---|---|
| Study area | `raw/study_area.geojson` | Wazirpur–Bharat Nagar pilot only, roughly 1.5–2 km². |
| Landsat | `raw/landsat_scenes.csv` | 3–5 low-cloud pre-monsoon Landsat Collection 2 Level-2 scenes. Record `ST_B10`, `SR_B4`, `SR_B5`, `QA_PIXEL`, cloud cover, date and item ID. |
| Population | `raw/population_source_details.txt` | WorldPop or GHSL; record the year and resolution. |
| OpenStreetMap | `raw/osm_features.geojson` | Roads, buildings, green areas, bus stops, marketplaces, schools, community facilities, `drinking_water`, shelters and toilets. |

## Non-negotiable labels

- Existing relief locations: **Mapped in OpenStreetMap, unverified.**
- Candidate sites: **Possible locations, not confirmed public land.**
- Landsat output: **Morning land-surface temperature, not peak-afternoon air temperature or health risk.**

## Minimum source record

Add one row to `sources.csv` for every input with the source URL, access date, licence, temporal coverage, spatial resolution, use in CoolWard, and limitation.
