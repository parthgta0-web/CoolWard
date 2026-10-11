export function simulationControlsLocked(excludedCandidateIds, isRecomputing) {
  return isRecomputing || excludedCandidateIds.length > 0
}

export function replanningRequest(thresholdM, activeBudgetLakh, excludedCandidateIds, includeLayers) {
  return {
    threshold_m: thresholdM,
    active_budget_lakh: activeBudgetLakh,
    excluded_candidate_ids: [...excludedCandidateIds].sort(),
    include_layers: includeLayers,
  }
}
