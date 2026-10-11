# CoolWard three-minute demo script

This script demonstrates the local primary planning scenario. It does not claim verified relief access, people protected, water availability, land permission, or procurement cost.

## Before recording

1. Start Docker Desktop and confirm its Linux engine is running.
2. In the repository root, run `sam build` and then `sam local start-api --port 3000 --warm-containers EAGER`.
3. In a second terminal, run `cd frontend` and `npm.cmd run dev`.
4. Open the Vite URL. Keep the SAM Local terminal visible or ready to show briefly.

## 0:00–0:25 — Local proof and purpose

Show the SAM Local terminal, then the dashboard header.

Say: “CoolWard is a local heat-refuge planning aid for the Wazirpur–Bharat Nagar pilot. The React dashboard calls a Python Lambda-compatible API through SAM Local and Docker. Lambda Powertools provides local structured logging. No AWS cloud services, credentials, credits, or deployment are used.”

## 0:25–0:50 — Read the planning frame

Show the map, reporting-core outline, heat-priority demand cells, network, and muted OSM context points.

Say: “The coloured cells are a relative multi-scene land-surface-temperature priority combined with 2024 modelled WorldPop population. The grey parks, toilet, and shelter are OSM-mapped contextual references only; the primary scenario does not assume they are functioning heat-refuge services.”

## 0:50–1:20 — ₹5L state

Set the budget to ₹5L.

Say: “At ₹5 lakh, one possible site is selected. The modelled-priority coverage is 58.2%. This is not people protected or a measured health impact. The point is a possible site that still requires land, access, water, and operations verification.”

Point out the selected marker, selected-site card, and highlighted trade-off row.

## 1:20–1:55 — ₹20L state

Set the budget to ₹20L.

Say: “At ₹20 lakh, four possible sites reach 97.9% of the modelled-priority score under the 400 m network-distance planning assumption. Each is a ₹5 lakh standard planning unit, not a procurement quote. The selected-site cards show the deterministic marginal gains.”

Point out the four selected map markers and the total actual spend.

## 1:55–2:20 — ₹35L plateau

Set the budget to ₹35L.

Say: “The coverage remains 97.9%, with the same four sites and ₹20 lakh actual spend. The remaining ₹15 lakh is deliberately unallocated because no supplied candidate has marginal gain. That plateau is a planning finding, not an invitation to invent extra sites.”

Show the unallocated-budget metric and the highlighted ₹35L trade-off row.

## 2:20–2:40 — Verification-first replanning

Return to ₹20L and leave the 400 m assumption selected. Click “Simulate failed verification” for one selected possible site, then point out the revised markers, coverage outline, and the selected-site backup explanation. Use the reset action afterward.

Say: “This is a simulation only — field verification is still required. The local API recomputes an exact plan from the remaining possible sites using the supplied pedestrian-network coverage inputs. A site is called critical only when excluding it reduces modelled-priority coverage in this simulation; otherwise it is replaceable by the shown backup plan. This does not verify any site in the real world.”

Briefly select 300 m and 500 m to show that the map, coverage, and selected sites are recomputed under the chosen network-distance planning assumption. Return to 400 m before continuing.

## 2:40–3:00 — Limitations and close

Show the limitations panel.

Say: “The 400 m value is a network-distance planning assumption, not a guaranteed five-minute walk. The graph is fragmented and one demand cell is structurally unreachable. OSM context is unverified; there is no verified water, land, access, operations, capacity, or safety assessment. CoolWard helps prioritise field verification and accountable discussion; it does not authorise installation.”

Say: “The experimental ML audit is retained as documented evidence only and does not drive site selection because its features and target share Landsat signal.”

End on the selected-site list and limitations panel.
