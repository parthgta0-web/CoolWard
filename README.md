# CoolWard

**AI-powered heat-refuge planner for Delhi wards — prioritising shade, water, and rest points where they protect the most heat-exposed residents.**

CoolWard converts local heat, population and walking-access layers into a transparent answer to one operational question: **where should a ward place its next cooling points for the greatest coverage gain within a fixed budget?**

## Pilot

Wazirpur–Bharat Nagar corridor, Delhi. This repository currently includes a transparent demonstration dataset while the team prepares documented Landsat, OpenStreetMap and population inputs.

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

- Existing relief locations are mapped in OpenStreetMap and unverified.
- Candidate sites are possible locations, not confirmed public land.
- Landsat measures morning land-surface temperature, not peak-afternoon air temperature or health outcomes.
- Intervention estimates are planning estimates, not guarantees.
