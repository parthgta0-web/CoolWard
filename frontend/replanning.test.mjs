import assert from 'node:assert/strict'
import test from 'node:test'
import { replanningRequest, simulationControlsLocked } from './src/replanning.js'

test('simulation locks budget and network-distance controls until reset', () => {
  assert.equal(simulationControlsLocked([], false), false)
  assert.equal(simulationControlsLocked([], true), true)
  assert.equal(simulationControlsLocked(['candidate_046'], false), true)
  assert.equal(simulationControlsLocked(['candidate_046'], true), true)
})

test('bulk replanning request carries the active simulation once', () => {
  assert.deepEqual(replanningRequest(400, 20, ['candidate_046'], false), {
    threshold_m: 400,
    active_budget_lakh: 20,
    excluded_candidate_ids: ['candidate_046'],
    include_layers: false,
  })
})
