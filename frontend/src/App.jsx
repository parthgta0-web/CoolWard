import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const budgets = [5, 10, 15, 20, 25, 30, 35]
const heatColour = (rank) => rank > 0.75 ? '#c94834' : rank > 0.5 ? '#e27b3d' : rank > 0.25 ? '#e9b958' : '#f7dfa4'

function featureCentre(feature) {
  const geometry = feature.geometry
  if (geometry.type === 'Point') return [geometry.coordinates[1], geometry.coordinates[0]]
  const ring = geometry.coordinates[0]
  const [lng, lat] = ring.reduce((total, coordinate) => [total[0] + coordinate[0], total[1] + coordinate[1]], [0, 0])
  return [lat / ring.length, lng / ring.length]
}

function App() {
  const [budget, setBudget] = useState(20)
  const [plans, setPlans] = useState([])
  const [layers, setLayers] = useState(null)
  const [status, setStatus] = useState('Loading the local 400 m planning scenario…')

  async function loadPlans() {
    setStatus('Loading validated local scenarios…')
    try {
      const responses = await Promise.all(budgets.map(async (budgetLakh) => {
        const response = await fetch('/api/optimise', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ budget_lakh: budgetLakh }) })
        const body = await response.json()
        if (!response.ok) throw new Error(body.error || 'The optimiser could not run.')
        return body
      }))
      setPlans(responses); setLayers(responses[0].layers)
      setStatus('Validated primary scenario loaded from SAM Local.')
    } catch (error) { setStatus(`Local API unavailable — start SAM Local, then retry. (${error.message})`) }
  }

  useEffect(() => { loadPlans() }, [])
  const plan = useMemo(() => plans.find((item) => item.budget_lakh === budget), [plans, budget])
  const selectedIds = useMemo(() => new Set(plan?.selected_sites?.map((site) => site.candidate_id) ?? []), [plan])
  const heatCells = layers?.heat_priority_demand_cells?.features ?? []
  const candidates = layers?.possible_candidate_sites?.features ?? []
  const references = layers?.osm_contextual_references?.features ?? []

  return <main>
    <header className="topbar"><div className="brand"><span className="brand-mark">C</span><span>CoolWard</span></div><div className="pilot-label">Wazirpur–Bharat Nagar pilot · local planning scenario</div><div className="status-dot"><span /> SAM Local API</div></header>
    <section className="hero"><div><p className="eyebrow">LOCAL HEAT-RESPITE PLANNING AID</p><h1>Prioritise possible sites with <em>transparent assumptions.</em></h1><p>Primary scenario: no verified full-service baseline. Results use a 400 m network-distance planning assumption, not a guaranteed five-minute walk.</p></div><button className="reload" onClick={loadPlans}>Refresh local scenario</button></section>
    <section className="workspace">
      <aside className="controls"><p className="eyebrow">PRIMARY SCENARIO</p><h2>Budget selection</h2><div className="budget-value">₹{budget}<small> lakh</small></div><input aria-label="Budget in lakh" type="range" min="5" max="35" step="5" value={budget} onChange={(event) => setBudget(Number(event.target.value))} /><div className="range-labels"><span>₹5L</span><span>₹35L</span></div><p className="api-status">{status}</p><div className="legend"><p className="eyebrow">MAP LAYERS</p><div><i className="legend-dot heat" /> Relative heat-priority demand cell</div><div><i className="legend-dot reference" /> OSM-mapped contextual reference — unverified</div><div><i className="legend-dot candidate" /> Possible site</div><div><i className="legend-dot selected" /> Selected possible site</div></div></aside>
      <section className="map-panel" aria-label="Primary planning scenario map"><div className="map-title"><span>Modelled-priority & possible-site map</span><small>400 m network-distance planning assumption</small></div><MapContainer center={[28.6805, 77.1705]} zoom={15} scrollWheelZoom className="map">{layers && <><GeoJSON data={layers.context} style={{ color: '#8393a1', weight: 1, fillOpacity: 0.02 }} /><GeoJSON data={layers.filtered_pedestrian_network} style={{ color: '#8e9aa4', weight: 1, opacity: 0.55 }} /><GeoJSON data={layers.heat_priority_demand_cells} style={(feature) => ({ color: '#fffaf0', weight: 0.5, fillColor: heatColour(feature.properties.relative_heat_rank), fillOpacity: 0.72 })} /><GeoJSON data={layers.reporting_core} style={{ color: '#142b42', weight: 3, fillOpacity: 0 }} />{references.map((feature) => <CircleMarker key={`reference-${feature.properties.osm_key}`} center={featureCentre(feature)} radius={4} pathOptions={{ color: '#63778a', fillColor: '#b9c5ce', fillOpacity: 0.85, weight: 1 }}><Popup><b>OSM-mapped contextual reference — unverified</b><br />{feature.properties.relief_type}</Popup></CircleMarker>)}{candidates.map((feature) => { const selected = selectedIds.has(feature.properties.candidate_id); return <CircleMarker key={feature.properties.candidate_id} center={featureCentre(feature)} radius={selected ? 8 : 3} pathOptions={{ color: selected ? '#5c3610' : '#88959d', fillColor: selected ? '#f2b94b' : '#edf1f2', fillOpacity: selected ? 1 : 0.55, weight: selected ? 2 : 1 }}><Popup><b>{selected ? 'Selected possible site' : 'Possible site'}</b><br />{feature.properties.candidate_id}<br />Requires land, access, water, and operations verification.</Popup></CircleMarker>})}</>}</MapContainer><p className="map-note">Only reporting-core demand-cell centroids are scored. OSM parks, toilet, and shelter remain unverified contextual references and are not counted as baseline service.</p></section>
    </section>
    <section className="results"><div className="result-intro"><p className="eyebrow">SELECTED PLAN</p><h2>{plan ? `₹${budget}L scenario` : 'Waiting for SAM Local'}</h2></div><div className="metric accent"><span>Modelled-priority coverage</span><b>{plan ? `${plan.modelled_priority_coverage_percent}%` : '—'}</b><small>Not people protected or health impact</small></div><div className="metric"><span>Actual spend</span><b>{plan ? `₹${plan.spent_lakh}L` : '—'}</b><small>{plan ? `${plan.selected_sites.length} standard planning unit${plan.selected_sites.length === 1 ? '' : 's'}` : 'Loading'}</small></div><div className="metric"><span>Unallocated</span><b>{plan ? `₹${plan.unallocated_lakh}L` : '—'}</b><small>{plan?.unallocated_lakh ? 'No further candidate has marginal gain' : 'No remaining budget'}</small></div></section>
    <section className="assumptions" aria-label="Planning limitations and assumptions"><p className="eyebrow">LIMITATIONS & ASSUMPTIONS</p><div className="assumption-grid"><span>Relative multi-scene land-surface-temperature priority</span><span>2024 modelled WorldPop population</span><span>Unverified OSM context</span><span>Fragmented pedestrian network</span><span>One structurally unreachable demand cell</span><span>No verified full-service baseline assumed</span></div></section>
    {plan && <section className="recommendations"><div><p className="eyebrow">SELECTED POSSIBLE SITES</p><h2>Verification is required before any action.</h2><p>Each is a ₹5 lakh standard planning unit — not a procurement quote.</p></div><div className="site-list">{plan.selected_sites.map((site, index) => <article key={site.candidate_id}><span>0{index + 1}</span><div><b>{site.candidate_id}</b><p>Marginal modelled-priority gain: {site.marginal_gain_modelled_priority_score.toFixed(2)} · {site.newly_covered_demand_cells} newly covered demand cells</p><small>Possible site — requires land, access, water, and operations verification.</small></div></article>)}</div></section>}
    {plans.length > 0 && <section className="budget-comparison"><div><p className="eyebrow">BUDGET TRADE-OFF</p><h2>Marginal gains plateau after ₹20L.</h2><p>Extra budget remains unallocated where no possible candidate adds modelled-priority gain.</p></div><div className="tier-list">{plans.map((tier) => <div className={tier.budget_lakh === budget ? 'tier active-tier' : 'tier'} key={tier.budget_lakh}><b>₹{tier.budget_lakh}L</b><div className="tier-track"><span style={{ width: `${tier.modelled_priority_coverage_percent}%` }} /></div><strong>{tier.modelled_priority_coverage_percent}%</strong><small>{tier.unallocated_lakh ? `₹${tier.unallocated_lakh}L unallocated` : `₹${tier.spent_lakh}L spent`}</small></div>)}</div></section>}
    <footer>{plan?.disclaimer || 'Local scenario data is loading.'} {plan?.standard_unit_cost_label}</footer>
  </main>
}

export default App
