# CoolWard

**A heat-refuge planning aid for Delhi wards — prioritising shade, water, and rest points in high heat-priority areas.**

CoolWard is a decision-support prototype that converts local heat, population and walking-access layers into a transparent answer to one operational question: **where should a ward place its next cooling points for the greatest coverage gain within a fixed budget?**

## Pilot

Wazirpur–Bharat Nagar corridor, Delhi. This repository currently includes transparent demonstration inputs while the team prepares documented Landsat, OpenStreetMap and population inputs.

## What the terms mean

- **Heat-priority cell** — a small map area ranked using the documented heat, population and urban-context inputs.
- **Covered** — a cell that can reach a mapped or proposed heat-respite point using the configured walking-access assumption. It does not mean the point has unlimited capacity or that people will use it.
- **Heat-respite point** — a proposed combination of shade, drinking-water access and seating. Water quality, permission and suitability are not assessed.

## Built with AWS open-source tools

- AWS SAM CLI and SAM Local run the Python optimiser as a Lambda-compatible local API in Docker.
- AWS Lambda Powertools provides structured request logging.
- No AWS cloud resources, account credits, or paid service are used.

## Run locally

```powershell
# terminal 1
sam build
sam local start-api --warm-containers EAGER

# terminal 2
cd frontend
npm install
npm run dev
```

Open the local Vite URL and choose a budget. The dashboard calls `/api/optimise`, which selects sites using a greedy maximum-coverage algorithm.

## Honest limitations

- This is a planning aid, not an official, medical, heat-forecasting or emergency-response tool.
- Existing relief locations are mapped in OpenStreetMap and unverified.
- Candidate sites are possible locations, not confirmed public land.
- Landsat measures morning land-surface temperature, not peak-afternoon air temperature or health outcomes.
- Intervention estimates are planning estimates, not guarantees.
- The current repository dashboard uses demonstration inputs until the documented pilot layers are integrated.

## Data provenance and attribution

Every external input and its licence, date, resolution and limitation is recorded in [`data/sources.csv`](data/sources.csv). The final map will credit OpenStreetMap contributors and cite the Landsat and population-data sources used.

## Local architecture

```text
React + Leaflet dashboard
        ↓ local /api proxy
AWS SAM Local + Docker
        ↓
Lambda-compatible Python optimiser + documented planning inputs
```
