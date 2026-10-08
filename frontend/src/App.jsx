import { useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './App.css'

const heatCells = [
  { id: 'c1', name: 'Industrial east', lat: 28.7007, lng: 77.1607, priority: 95, covered_now: false },
  { id: 'c2', name: 'Workshop lane', lat: 28.7022, lng: 77.1588, priority: 88, covered_now: false },
  { id: 'c3', name: 'Bharat Nagar edge', lat: 28.704, lng: 77.1568, priority: 82, covered_now: false },
  { id: 'c4', name: 'Market approach', lat: 28.706, lng: 77.1596, priority: 72, covered_now: true },
  { id: 'c5', name: 'Transit junction', lat: 28.699, lng: 77.156, priority: 79, covered_now: false },
  { id: 'c6', name: 'Green-belt boundary', lat: 28.708, lng: 77.163, priority: 53, covered_now: true },
  { id: 'c7', name: 'Dense housing south', lat: 28.7017, lng: 77.1539, priority: 91, covered_now: false },
  { id: 'c8', name: 'School-side lane', lat: 28.7055, lng: 77.1536, priority: 68, covered_now: false },
]

const existingPoints = [
  { name: 'Mapped park / relief point', lat: 28.7065, lng: 77.1606 },
  { name: 'Mapped green-belt access', lat: 28.7084, lng: 77.1622 },
]

function App() {
  const [budget, setBudget] = useState(20)
  const [plan, setPlan] = useState(null)
  const [status, setStatus] = useState('Choose a budget, then generate a plan.')
  const selectedIds = useMemo(() => new Set(plan?.selected_sites?.flatMap((site) => site.covers) ?? []), [plan])

  async function generatePlan() {
    setStatus('Optimising coverage…')
    try {
      const response = await fetch('/api/optimise', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ budget_lakh: budget }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || 'The optimiser could not run.')
      setPlan(body)
      setStatus(`Plan generated: ${body.selected_sites.length} cooling points selected.`)
    } catch (error) {
      setStatus(`Local API unavailable — start SAM Local, then try again. (${error.message})`)
    }
  }

  return (
    <main>
      <header className="topbar">
        <div className="brand"><span className="brand-mark">C</span><span>CoolWard</span></div>
        <div className="pilot-label">Delhi pilot · Wazirpur–Bharat Nagar</div>
        <div className="status-dot"><span /> Local planning model</div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">LAST-MILE HEAT REFUGE PLANNER</p>
          <h1>Turn heat maps into <em>accountable ward action.</em></h1>
          <p className="hero-copy">Place shade, water and rest points where a fixed budget can give the most heat-priority residents a five-minute walk to relief.</p>
        </div>
        <aside className="method-card">
          <span className="method-number">01</span>
          <div><b>Transparent by design</b><p>Every recommended site shows its cost, coverage gain and planning basis.</p></div>
        </aside>
      </section>

      <section className="workspace">
        <aside className="controls">
          <p className="eyebrow">PLANNING INPUT</p>
          <h2>Set the ward budget</h2>
          <div className="budget-value">₹{budget} <small>lakh</small></div>
          <input aria-label="Budget in lakh" type="range" min="5" max="35" step="5" value={budget} onChange={(event) => setBudget(Number(event.target.value))} />
          <div className="range-labels"><span>₹5L</span><span>₹35L</span></div>
          <button onClick={generatePlan}>Generate optimal plan <span>→</span></button>
          <p className="api-status">{status}</p>

          <div className="legend">
            <p className="eyebrow">MAP LEGEND</p>
            <div><i className="legend-dot high" /> High heat-priority cell</div>
            <div><i className="legend-dot current" /> Existing mapped relief access</div>
            <div><i className="legend-dot selected" /> Recommended cooling point</div>
          </div>
        </aside>

        <section className="map-panel" aria-label="Heat-priority planning map">
          <div className="map-title"><span>Heat-priority & access map</span><small>Demonstration planning inputs</small></div>
          <MapContainer center={[28.7035, 77.1585]} zoom={15} scrollWheelZoom className="map">
            <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {heatCells.map((cell) => {
              const improved = selectedIds.has(cell.id)
              return <CircleMarker key={cell.id} center={[cell.lat, cell.lng]} radius={Math.max(9, cell.priority / 6)} pathOptions={{ color: improved ? '#0f766e' : '#e85d3f', fillColor: improved ? '#10b981' : '#ef6a4b', fillOpacity: 0.68, weight: 2 }}>
                <Popup><b>{cell.name}</b><br />Heat-priority score: {cell.priority}{improved && <><br />Covered by this plan</>}</Popup>
              </CircleMarker>
            })}
            {existingPoints.map((point) => <CircleMarker key={point.name} center={[point.lat, point.lng]} radius={6} pathOptions={{ color: '#1d4ed8', fillColor: '#60a5fa', fillOpacity: 1, weight: 2 }}><Popup>{point.name}<br />OSM-mapped, unverified</Popup></CircleMarker>)}
            {plan?.selected_sites.map((site) => <CircleMarker key={site.id} center={[site.lat, site.lng]} radius={9} pathOptions={{ color: '#064e3b', fillColor: '#f4bf4f', fillOpacity: 1, weight: 3 }}><Popup><b>{site.name}</b><br />{site.kind}<br />₹{site.cost_lakh} lakh · +{site.new_priority_covered} priority score</Popup></CircleMarker>)}
          </MapContainer>
          <p className="map-note">Heat-priority cells combine demonstration heat and population inputs. Final satellite, population and walking-network layers will replace these documented prototype inputs.</p>
        </section>
      </section>

      <section className="results">
        <div className="result-intro"><p className="eyebrow">PLAN OUTCOME</p><h2>{plan ? 'A transparent coverage gain.' : 'Your plan will appear here.'}</h2></div>
        <div className="metric"><span>Coverage today</span><b>{plan ? `${plan.baseline_coverage_percent}%` : '—'}</b><small>heat-priority score with mapped access</small></div>
        <div className="metric accent"><span>Coverage after plan</span><b>{plan ? `${plan.after_coverage_percent}%` : '—'}</b><small>within the selected budget</small></div>
        <div className="metric"><span>Budget used</span><b>{plan ? `₹${plan.spent_lakh}L` : '—'}</b><small>{plan ? `${plan.selected_sites.length} sites selected` : 'run the optimiser'}</small></div>
      </section>

      {plan && <section className="recommendations"><div><p className="eyebrow">RECOMMENDED LOCATIONS</p><h2>What the ward can do next</h2></div><div className="site-list">{plan.selected_sites.map((site, index) => <article key={site.id}><span>0{index + 1}</span><div><b>{site.name}</b><p>{site.kind} · ₹{site.cost_lakh} lakh · covers +{site.new_priority_covered} heat-priority score</p></div></article>)}</div></section>}

      <footer>{plan?.disclaimer || 'Prototype only: existing relief locations are mapped in OpenStreetMap and unverified.'}</footer>
    </main>
  )
}

export default App
