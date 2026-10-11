# Verification-failure interaction QA

1. From the repository root, run `sam build`, stop any previous SAM Local process, then run `sam local start-api --port 3000 --warm-containers EAGER`.
2. In a second terminal, run `cd frontend` and `npm.cmd run dev`. Hard-refresh the browser after opening the Vite URL.
3. Keep the 400 m assumption and ₹20L selected. Confirm the initial plan is 97.9% with Sites 01–04 and no amber simulation banner.
4. Click Site 01's **Simulate failed verification** button. It should immediately read **Recomputing…**, disable during the request, then show an amber banner naming the active candidate ID and calling Site 01 **replaceable**. The map summary should remain `97.9% → 97.9%`, with a red crossed excluded marker and a blue replacement marker.
5. Reset the simulation. Confirm the banner disappears, the original four gold selected markers return, and coverage is 97.9%.
6. Click Site 02's **Simulate failed verification** button. Confirm the local API status message names the excluded candidate, the map summary reads `97.9% → 94.3% after simulated Site 02 failure`, and the updated plan shows replacement selected markers.
7. Click **Reset simulation and restore original plan**. Confirm 97.9% and the original four selected sites return.

These are modelled replanning checks only. They do not verify land, water, access, operations, or actual heat-relief service.
