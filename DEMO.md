# CoolWard three-minute demo script

This demo starts with the planning problem: how can field teams prioritise possible heat-respite locations when no full-service relief site has been verified? CoolWard is a local planning aid; it does not claim verified access, people protected, water availability, land permission, or procurement cost.

## Before recording

1. Start Docker Desktop.
2. At the repository root, run `sam build`, then `sam local start-api --port 3000 --warm-containers EAGER`.
3. In a second terminal, run `cd frontend` and `npm run dev`. On Windows, use `npm.cmd run dev` if needed.
4. Open the Vite URL at the default 400 m, ₹20L scenario.

## 0:00–0:35 — The planning problem

Show the map, the core outline, demand cells, pedestrian network, and muted OSM context.

Say: “CoolWard helps the Wazirpur–Bharat Nagar pilot prioritise possible shade, drinking-water, and rest-site locations before field verification. Its primary scenario starts with a 0.0% baseline because no full-service relief site is verified. OSM parks, toilets, and shelter are context only, not assumed services.”

## 0:35–1:15 — The 400 m plan

Show ₹5L, then set ₹20L.

Say: “At ₹5 lakh, one possible site reaches 58.2% of the modelled-priority score. At ₹20 lakh, four possible sites reach 97.9% under a 400 m network-distance planning assumption. This is modelled-priority coverage, not people protected or measured cooling. Every possible site still needs land, access, water, safety, and operations verification.”

Point out the 400 m assumption, selected possible-site markers, covered-demand outlines, and local recomputation status.

## 1:15–2:05 — Site 02 critical-failure replan

At ₹20L and 400 m, select Site 02’s “Simulate failed verification” control.

Say: “This is a simulation only — not a real-world failure label. Site 02 is critical in this model. The local Lambda-compatible API, through SAM Local, recomputes the exact deterministic plan from the remaining candidates. Coverage changes from 97.9% to 94.3%, and the map distinguishes the excluded possible site and any replacement.”

Show the amber simulation banner, active excluded candidate ID, map summary, replacement marker, and the locked budget and 300/400/500 m controls. Say: “The controls lock until reset so this before-and-after comparison remains interpretable.”

Use “Reset simulation and restore original plan.” Confirm the original four sites and 97.9% return.

## 2:05–2:30 — Budget ceiling

Set ₹35L.

Say: “The same four sites remain selected, actual spend is ₹20 lakh, and ₹15 lakh is unallocated by design because no supplied candidate adds marginal modelled-priority coverage. This is an evidence-based spending ceiling, not a reason to invent locations.”

## 2:30–3:00 — Limits and local proof

Show the verification-context and limitations panels.

Say: “The 400 m value is a network-distance planning assumption, not a guaranteed five-minute walk. The supplied walking graph is fragmented and one demand cell is structurally unreachable. There is no verified public land, water, access, capacity, safety, or operations plan.”

Say: “The React/Vite dashboard calls a Lambda-compatible Python API through SAM Local and Docker, with Lambda Powertools logging. No AWS cloud services, credentials, credits, or deployment are used. The experimental ML audit is retained as documented evidence only and does not drive site selection because its features and target share Landsat signal.”
